"""Driver for ELM327-compatible adapters, including the STN chips in OBDLink devices."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from .transport import Transport


class AdapterError(Exception):
    """The adapter reported a problem or sent something unexpected."""


class AdapterTimeout(AdapterError):
    """The adapter did not finish its reply in time."""


class NoData(AdapterError):
    """The vehicle did not answer a request, usually because it does not support it."""


class NoVehicle(AdapterError):
    """The adapter could not find a vehicle network to talk to."""


PROTOCOL_NAMES = {
    "1": "SAE J1850 PWM",
    "2": "SAE J1850 VPW",
    "3": "ISO 9141-2",
    "4": "ISO 14230-4 KWP (slow init)",
    "5": "ISO 14230-4 KWP (fast init)",
    "6": "ISO 15765-4 CAN (11-bit, 500 kbit/s)",
    "7": "ISO 15765-4 CAN (29-bit, 500 kbit/s)",
    "8": "ISO 15765-4 CAN (11-bit, 250 kbit/s)",
    "9": "ISO 15765-4 CAN (29-bit, 250 kbit/s)",
    "A": "SAE J1939 CAN",
    "B": "User-defined CAN 1",
    "C": "User-defined CAN 2",
}


@dataclass(frozen=True)
class BusProtocol:
    """The vehicle network the adapter settled on."""

    number: str  # ELM327 protocol number, "1" to "C"
    name: str

    @property
    def family(self) -> str:
        return "can" if self.number in "6789ABC" else "legacy"

    @property
    def id_bits(self) -> int:
        return 29 if self.number in "79A" else 11


@dataclass(frozen=True)
class AdapterInfo:
    elm_version: str
    device: str | None  # OBDLink model string; None on plain ELM327 adapters
    firmware: str | None
    voltage: float | None

    @property
    def label(self) -> str:
        return " / ".join(p for p in (self.device, self.firmware, self.elm_version) if p)


_HEX_LINE = re.compile(r"[0-9A-Fa-f ]+")


class Elm327:
    def __init__(self, transport: Transport, *, timeout: float = 5.0) -> None:
        self.transport = transport
        self.timeout = timeout

    def command(self, text: str, *, timeout: float | None = None) -> list[str]:
        """Send one command and return its reply lines, without echo or prompt."""
        limit = self.timeout if timeout is None else timeout
        self.transport.flush_input()
        self.transport.write(text.encode("ascii") + b"\r")
        deadline = time.monotonic() + limit
        buffer = bytearray()
        while b">" not in buffer:
            buffer += self.transport.read()
            if time.monotonic() > deadline and b">" not in buffer:
                raise AdapterTimeout(f"no complete reply to {text!r} within {limit:g} s")
        # The ELM327 documentation says stray NUL bytes may appear and must be ignored.
        reply = bytes(buffer).replace(b"\x00", b"").split(b">", 1)[0]
        lines = [part.strip() for part in re.split(r"[\r\n]+", reply.decode("ascii", "replace"))]
        lines = [line for line in lines if line]
        if lines and _squash(lines[0]) == _squash(text):
            lines = lines[1:]  # the adapter echoed the command back
        return lines

    def initialise(self) -> AdapterInfo:
        """Reset the adapter and put it into the reply format the parsers expect."""
        banner = self.command("ATZ", timeout=8)
        version = next((line for line in banner if line.upper().startswith("ELM")), None)
        if version is None:
            raise AdapterError(f"unexpected reply to adapter reset: {banner!r}")
        # Echo off, linefeeds off, spaces off, headers on (needed to tell modules
        # apart and to reassemble long replies), automatic protocol search.
        for setting in ("ATE0", "ATL0", "ATS0", "ATH1", "ATSP0"):
            if "OK" not in self.command(setting):
                raise AdapterError(f"the adapter refused setting {setting}")
        return AdapterInfo(
            elm_version=version,
            device=self._optional("STDI"),
            firmware=self._optional("STI"),
            voltage=self.voltage(),
        )

    def _optional(self, text: str) -> str | None:
        lines = self.command(text)
        if not lines or lines[0] == "?":
            return None
        return lines[0]

    def voltage(self) -> float | None:
        """Battery voltage measured at the diagnostic port."""
        match = re.match(r"\d+(\.\d+)?", (self._optional("ATRV") or ""))
        return float(match.group()) if match else None

    def protocol(self) -> BusProtocol:
        """The protocol in use. Only meaningful after a successful request."""
        number = (self._optional("ATDPN") or "").upper()
        if len(number) > 1 and number.startswith("A"):
            number = number[1:]  # leading "A" means "found automatically"
        if number in PROTOCOL_NAMES:
            return BusProtocol(number, PROTOCOL_NAMES[number])
        raise AdapterError(f"the adapter reported an unknown protocol {number!r}")

    def set_header(self, header: str) -> None:
        """Address the requests that follow to one module, or to all of them (7DF on 11-bit CAN)."""
        if "OK" not in self.command(f"ATSH{header}"):
            raise AdapterError(f"the adapter refused to address module {header}")

    def request(self, payload_hex: str, *, timeout: float | None = None) -> list[str]:
        """Send a diagnostic request and return the raw data lines from the vehicle."""
        data: list[str] = []
        for line in self.command(payload_hex, timeout=timeout):
            if _HEX_LINE.fullmatch(line):
                data.append(line)
                continue
            upper = line.upper()
            if upper.startswith("SEARCHING") or (upper.startswith("BUS INIT") and upper.endswith("OK")):
                continue  # progress messages
            if "NO DATA" in upper:
                raise NoData(payload_hex)
            if "UNABLE TO CONNECT" in upper:
                raise NoVehicle(
                    "the adapter found no vehicle network; plug it into the car and turn the ignition on"
                )
            if upper == "?":
                raise AdapterError(f"the adapter did not understand request {payload_hex}")
            raise AdapterError(f"the adapter reported {line!r} for request {payload_hex}")
        if not data:
            raise NoData(payload_hex)
        return data


def _squash(text: str) -> str:
    return "".join(text.split()).upper()
