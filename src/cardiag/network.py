"""Wi-Fi control for the box in the car, through NetworkManager's `nmcli`.

The box has one Wi-Fi radio, so it is either its own hotspot or a member of
another network, never both. The hotspot is the resting state: it starts at
every boot, and it comes back whenever joining another network fails or that
network goes away.

Two other networks can be saved. The home network is joined only when asked: a
deliberate, temporary step for working on the box at home. The travelling
network is a phone's or tablet's hotspot, which gives the box a way out to the
internet on the road; the box joins that one by itself whenever it sees it, and
keeps looking for it while it is away.
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
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
        uplink: str = "cardiag-uplink",
        interface: str = "wlan0",
        run: Run = _nmcli,
        join_timeout: int = 45,
        settle: float = 1.5,
        watch_interval: float = 20.0,
        retry_after: float = 300.0,
    ) -> None:
        self.hotspot = hotspot  # NetworkManager connection that is the box's own network
        self.profile = profile  # NetworkManager connection for the saved home network
        self.uplink = uplink  # NetworkManager connection for the saved travelling hotspot
        self.interface = interface
        self._run = run
        self._join_timeout = join_timeout
        self._settle = settle  # lets the reply reach the browser before its network goes away
        self._watch_interval = watch_interval
        self._retry_after = retry_after  # seconds to leave the travelling hotspot alone after it refused us

        self._lock = threading.Lock()
        self._switching: str | None = None  # what the radio is changing to, while it is
        self._problem: str | None = None  # why the last attempt to join failed
        self._hold = False  # the person asked for the box's own hotspot: do not wander off by itself
        self._refused_at: float | None = None  # when the travelling hotspot last turned us away
        self._looks = 0
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
        elif active == self.uplink:
            mode = "uplink"
        else:
            mode = "offline"
        return {
            "managed": True,
            "mode": mode,
            "address": address,
            "hotspot": self._ssid(self.hotspot),
            "saved": self._ssid(self.profile),
            "uplink": self._ssid(self.uplink),
            "uplink_auto": not self._hold,
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

    def _named(self, which: object) -> str:
        if which == "home":
            return self.profile
        if which == "uplink":
            return self.uplink
        raise ValueError("which must be 'home' or 'uplink'")

    def save(self, ssid: object, password: object, which: object = "home") -> None:
        """Remember a network. Home is joined only when asked; the travelling hotspot whenever it is seen."""
        profile = self._named(which)
        if not isinstance(ssid, str) or not 1 <= len(ssid.encode()) <= 32:
            raise ValueError("the network name must be 1 to 32 characters")
        password = password or ""
        if not isinstance(password, str) or (password and not 8 <= len(password) <= 63):
            raise ValueError("a Wi-Fi password is 8 to 63 characters; leave it empty for an open network")
        if self._active()[0] == profile:
            raise ValueError("switch back to the hotspot before changing the saved network")

        args = ["connection", "add", "type", "wifi", "ifname", self.interface, "con-name", profile,
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
            self._run(["connection", "delete", profile], 15)
        except NetworkError:
            pass  # nothing was saved before
        self._run(args, 15)
        with self._lock:
            self._problem = None
            if profile == self.uplink:
                self._refused_at, self._hold = None, False

    def join(self, which: object = "home") -> None:
        """Leave the hotspot for a saved network. Falls back to the hotspot if that fails."""
        profile = self._named(which)
        ssid = self._ssid(profile)
        if ssid is None:
            raise ValueError("save a network first")
        self._begin(ssid)
        if profile == self.uplink:
            with self._lock:
                self._hold, self._refused_at = False, None  # asking for it means: keep looking for it
        self._spawn(lambda: self._join(ssid, profile))

    def use_hotspot(self) -> None:
        """Go back to the box's own hotspot, and stay there until asked otherwise."""
        leaving_uplink = self._active()[0] == self.uplink
        self._begin(self._ssid(self.hotspot) or self.hotspot)
        with self._lock:
            # Leaving the travelling hotspot by hand means "stay put"; leaving home does not.
            self._hold = leaving_uplink
        self._spawn(self._to_hotspot)

    def forget(self, which: object = "home") -> None:
        profile = self._named(which)
        was_joined = self._active()[0] == profile
        try:
            self._run(["connection", "delete", profile], 15)
        except NetworkError:
            pass  # nothing was saved
        with self._lock:
            self._problem = None
        if was_joined:
            self._begin(self._ssid(self.hotspot) or self.hotspot)
            self._spawn(self._to_hotspot)

    def _begin(self, target: str) -> None:
        with self._lock:
            if self._switching:
                raise ValueError(f"already switching to {self._switching}; give it a minute")
            self._switching = target
            self._problem = None

    def _join(self, ssid: str, profile: str) -> None:
        try:
            if self._stop.wait(self._settle):
                return
            try:
                self._run(["--wait", str(self._join_timeout), "connection", "up", profile],
                          self._join_timeout + 15)
            except NetworkError as exc:
                with self._lock:
                    self._problem = f"Could not join {ssid}: {_plain_reason(str(exc))}. The hotspot is back on."
                    if profile == self.uplink:
                        self._refused_at = time.monotonic()
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
                active = self._active()[0]
                if active is None:
                    self._hotspot_up()
                elif active == self.hotspot:
                    self._look_for_uplink()
            except NetworkError:
                pass

    def _look_for_uplink(self) -> None:
        """On the box's own hotspot: move to the travelling hotspot if it has come into range."""
        with self._lock:
            waiting = self._refused_at is not None and time.monotonic() - self._refused_at < self._retry_after
            if self._hold or waiting:
                return
        ssid = self._ssid(self.uplink)
        if ssid is None:
            return
        self._looks += 1
        try:
            # A fresh look around interrupts the hotspot for a moment, so only every third time.
            visible = self._visible(rescan=self._looks % 3 == 1)
        except NetworkError:
            visible = self._visible(rescan=False)
        if not any(network["ssid"] == ssid for network in visible):
            return
        try:
            self._begin(ssid)
        except ValueError:
            return  # the person started a switch of their own in the meantime
        self._join(ssid, self.uplink)
