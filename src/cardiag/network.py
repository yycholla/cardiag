"""Wi-Fi control for the box in the car, through NetworkManager's `nmcli`.

The box has one Wi-Fi radio, so it is either its own hotspot or a member of
another network, never both. The hotspot is the resting state: it starts at
every boot, and it comes back whenever joining another network fails or that
network goes away. Joining a saved network is a deliberate, temporary step for
working on the box at home, where it can reach the internet.
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
from typing import Callable

Run = Callable[[list[str], float], str]


class NetworkError(Exception):
    """NetworkManager refused or failed a request."""


def _nmcli(args: list[str], timeout: float) -> str:
    try:
        done = subprocess.run(
            ["nmcli", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "LC_ALL": "C"},
        )
    except FileNotFoundError:
        raise NetworkError("NetworkManager (nmcli) is not installed on this machine") from None
    except subprocess.TimeoutExpired:
        raise NetworkError("NetworkManager took too long to answer") from None
    if done.returncode != 0:
        raise NetworkError((done.stderr or done.stdout).strip() or "NetworkManager reported a failure")
    return done.stdout


def _split_terse(line: str, fields: int) -> list[str]:
    """Split one line of `nmcli -t` output, where a colon inside a value is written as \\:."""
    parts, value, escaped = [], "", False
    for char in line:
        if escaped:
            value, escaped = value + char, False
        elif char == "\\":
            escaped = True
        elif char == ":" and len(parts) < fields - 1:
            parts.append(value)
            value = ""
        else:
            value += char
    return parts + [value]


def _plain_reason(error: str) -> str:
    """NetworkManager's wording, put the way the person at the phone needs it."""
    lowered = error.lower()
    if "secrets were required" in lowered or "802-11-wireless-security" in lowered:
        return "the password was not accepted"
    if "no network with ssid" in lowered or "not found" in lowered:
        return "that network is not in range"
    if "too long" in lowered or "timeout" in lowered or "timed out" in lowered:
        return "the network did not answer in time"
    return error.removeprefix("Error: ").rstrip(".")


class Wifi:
    def __init__(
        self,
        *,
        hotspot: str = "cardiag",
        profile: str = "cardiag-wifi",
        interface: str = "wlan0",
        run: Run = _nmcli,
        join_timeout: int = 45,
        settle: float = 1.5,
        watch_interval: float = 20.0,
    ) -> None:
        self.hotspot = hotspot  # NetworkManager connection that is the box's own network
        self.profile = profile  # NetworkManager connection for the one saved network
        self.interface = interface
        self._run = run
        self._join_timeout = join_timeout
        self._settle = settle  # lets the reply reach the browser before its network goes away
        self._watch_interval = watch_interval

        self._lock = threading.Lock()
        self._switching: str | None = None  # what the radio is changing to, while it is
        self._problem: str | None = None  # why the last attempt to join failed
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ---- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Watch the radio, and put the hotspot back if it is ever left with no network."""
        self._spawn(self._watch)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=5)

    def _spawn(self, target: Callable[[], None]) -> None:
        thread = threading.Thread(target=target, name="cardiag-wifi", daemon=True)
        self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        thread.start()

    # ---- reading -----------------------------------------------------------

    def status(self) -> dict:
        active, address = self._active()
        with self._lock:
            switching, problem = self._switching, self._problem
        if active == self.hotspot:
            mode = "hotspot"
        elif active == self.profile:
            mode = "wifi"
        else:
            mode = "offline"
        return {
            "managed": True,
            "mode": mode,
            "address": address,
            "hotspot": self._ssid(self.hotspot),
            "saved": self._ssid(self.profile),
            "switching": switching,
            "problem": problem,
            "hostname": socket.gethostname(),
        }

    def scan(self) -> list[dict]:
        """Networks in range, strongest first. The radio may see fewer while it is a hotspot."""
        own = self._ssid(self.hotspot)
        try:
            visible = self._visible(rescan=True)
        except NetworkError:
            visible = self._visible(rescan=False)  # some radios refuse to look around while a hotspot
        return [network for network in visible if network["ssid"] != own]

    def _visible(self, rescan: bool) -> list[dict]:
        out = self._run(
            ["-t", "-f", "SIGNAL,SECURITY,SSID", "device", "wifi", "list", "ifname", self.interface,
             "--rescan", "yes" if rescan else "no"],
            30,
        )
        best: dict[str, dict] = {}
        for line in out.splitlines():
            signal, security, ssid = (_split_terse(line, 3) + ["", ""])[:3]
            if not ssid:
                continue  # a hidden network
            found = {
                "ssid": ssid,
                "signal": int(signal) if signal.isdigit() else 0,
                "security": "" if security in ("", "--") else security,
            }
            if ssid not in best or found["signal"] > best[ssid]["signal"]:
                best[ssid] = found
        return sorted(best.values(), key=lambda network: -network["signal"])

    def _active(self) -> tuple[str | None, str | None]:
        """The connection the radio is using, and its address."""
        out = self._run(["-t", "-f", "GENERAL.CONNECTION,IP4.ADDRESS", "device", "show", self.interface], 10)
        connection = address = None
        for line in out.splitlines():
            name, value = (_split_terse(line, 2) + [""])[:2]
            if name == "GENERAL.CONNECTION" and value not in ("", "--"):
                connection = value
            elif name.startswith("IP4.ADDRESS") and address is None and value:
                address = value.split("/")[0]
        return connection, address

    def _ssid(self, connection: str) -> str | None:
        try:
            out = self._run(["-g", "802-11-wireless.ssid", "connection", "show", connection], 10)
        except NetworkError:
            return None  # there is no such connection
        return out.strip() or None

    # ---- changing ----------------------------------------------------------

    def save(self, ssid: object, password: object) -> None:
        """Remember one network to join. It is never joined by itself, only when asked."""
        if not isinstance(ssid, str) or not 1 <= len(ssid.encode()) <= 32:
            raise ValueError("the network name must be 1 to 32 characters")
        password = password or ""
        if not isinstance(password, str) or (password and not 8 <= len(password) <= 63):
            raise ValueError("a Wi-Fi password is 8 to 63 characters; leave it empty for an open network")
        if self._active()[0] == self.profile:
            raise ValueError("switch back to the hotspot before changing the saved network")

        args = ["connection", "add", "type", "wifi", "ifname", self.interface, "con-name", self.profile,
                "ssid", ssid, "connection.autoconnect", "no"]
        if password:
            try:
                seen = {network["ssid"]: network["security"] for network in self._visible(rescan=False)}
            except NetworkError:
                seen = {}
            security = seen.get(ssid, "")
            wpa3_only = "WPA3" in security and "WPA2" not in security and "WPA1" not in security
            # nmcli takes the password as an argument, so it is briefly visible to other
            # processes on the box. NetworkManager then stores it readable by root only.
            args += ["wifi-sec.key-mgmt", "sae" if wpa3_only else "wpa-psk", "wifi-sec.psk", password]
        try:
            self._run(["connection", "delete", self.profile], 15)
        except NetworkError:
            pass  # nothing was saved before
        self._run(args, 15)
        with self._lock:
            self._problem = None

    def join(self) -> None:
        """Leave the hotspot for the saved network. Falls back to the hotspot if that fails."""
        ssid = self._ssid(self.profile)
        if ssid is None:
            raise ValueError("save a network first")
        self._begin(ssid)
        self._spawn(lambda: self._join(ssid))

    def use_hotspot(self) -> None:
        self._begin(self._ssid(self.hotspot) or self.hotspot)
        self._spawn(self._to_hotspot)

    def forget(self) -> None:
        was_joined = self._active()[0] == self.profile
        try:
            self._run(["connection", "delete", self.profile], 15)
        except NetworkError:
            pass  # nothing was saved
        with self._lock:
            self._problem = None
        if was_joined:
            self.use_hotspot()

    def _begin(self, target: str) -> None:
        with self._lock:
            if self._switching:
                raise ValueError(f"already switching to {self._switching}; give it a minute")
            self._switching = target
            self._problem = None

    def _join(self, ssid: str) -> None:
        try:
            if self._stop.wait(self._settle):
                return
            try:
                self._run(["--wait", str(self._join_timeout), "connection", "up", self.profile],
                          self._join_timeout + 15)
            except NetworkError as exc:
                with self._lock:
                    self._problem = f"Could not join {ssid}: {_plain_reason(str(exc))}. The hotspot is back on."
                self._hotspot_up()
        finally:
            with self._lock:
                self._switching = None

    def _to_hotspot(self) -> None:
        try:
            if not self._stop.wait(self._settle):
                self._hotspot_up()
        finally:
            with self._lock:
                self._switching = None

    def _hotspot_up(self) -> None:
        try:
            self._run(["--wait", "30", "connection", "up", self.hotspot], 45)
        except NetworkError:
            pass  # the watcher tries again

    def _watch(self) -> None:
        while not self._stop.wait(self._watch_interval):
            with self._lock:
                if self._switching:
                    continue
            try:
                if self._active()[0] is None:
                    self._hotspot_up()
            except NetworkError:
                pass
