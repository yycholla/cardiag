"""Generic OBD-II services: live data, trouble codes, readiness, VIN, freeze frame.

Everything here is the legally mandated layer, so it behaves the same on any
make. Only read requests are sent.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dtc import decode_dtc, parse_dtcs
from .elm import BusProtocol, Elm327, NoData, NoVehicle
from .frames import Message, parse_can, parse_legacy
from .pids import PIDS, Value

DTC_SERVICES = {"stored": 0x03, "pending": 0x07, "permanent": 0x0A}
_EVERY_MODULE = "7DF"  # the 11-bit CAN address that all modules listen on


@dataclass(frozen=True)
class Reading:
    key: str  # stable signal id, e.g. "01:0C"
    name: str
    value: Value
    unit: str
    ecu: int


@dataclass(frozen=True)
class Monitor:
    name: str
    complete: bool


@dataclass(frozen=True)
class MonitorStatus:
    ecu: int
    mil_on: bool  # check-engine light commanded on
    dtc_count: int
    ignition: str  # "spark" or "compression"
    monitors: list[Monitor]


@dataclass(frozen=True)
class FreezeFrame:
    dtc: str
    ecu: int
    readings: list[Reading]


_COMMON_MONITORS = ("Misfire", "Fuel system", "Components")
_SPARK_MONITORS = (
    "Catalyst",
    "Heated catalyst",
    "Evaporative system",
    "Secondary air system",
    "A/C refrigerant",
    "Oxygen sensor",
    "Oxygen sensor heater",
    "EGR / VVT system",
)
_COMPRESSION_MONITORS = (
    "NMHC catalyst",
    "NOx / SCR aftertreatment",
    None,
    "Boost pressure",
    None,
    "Exhaust gas sensor",
    "Particulate filter",
    "EGR / VVT system",
)


def decode_monitor_status(ecu: int, data: bytes) -> MonitorStatus:
    """Decode the four data bytes of service 01 PID 01."""
    a, b, c, d = data[:4]
    compression = bool(b & 0x08)
    monitors = [
        Monitor(name, complete=not b & (1 << (bit + 4)))
        for bit, name in enumerate(_COMMON_MONITORS)
        if b & (1 << bit)
    ]
    monitors += [
        Monitor(name, complete=not d & (1 << bit))
        for bit, name in enumerate(_COMPRESSION_MONITORS if compression else _SPARK_MONITORS)
        if name and c & (1 << bit)
    ]
    return MonitorStatus(
        ecu=ecu,
        mil_on=bool(a & 0x80),
        dtc_count=a & 0x7F,
        ignition="compression" if compression else "spark",
        monitors=monitors,
    )


def ecu_label(ecu: int, protocol: BusProtocol) -> str:
    """A readable name for a responding module."""
    if protocol.family == "legacy":
        code, role = f"{ecu:02X}", ecu
    elif protocol.id_bits == 11:
        code, role = f"{ecu:03X}", {0x7E8: 0x10, 0x7E9: 0x18}.get(ecu)
    else:
        code, role = f"{ecu:08X}", ecu & 0xFF
    name = {0x10: "Engine", 0x18: "Transmission"}.get(role)
    return f"{name} ({code})" if name else f"Module {code}"


class Obd:
    def __init__(self, elm: Elm327) -> None:
        self.elm = elm
        self.protocol: BusProtocol | None = None
        self.ecus: list[int] = []
        self._supported: dict[int, dict[int, set[int]]] = {}
        self._header: str | None = None  # the module requests are addressed to; None means all of them

    def connect(self) -> BusProtocol:
        """Find the vehicle's network and note which modules answer."""
        try:
            # The first request triggers the protocol search, which can take a while.
            lines = self.elm.request("0100", timeout=20)
        except NoData:
            raise NoVehicle(
                "the vehicle did not answer; turn the ignition on (the engine can stay off)"
            ) from None
        self.protocol = self.elm.protocol()
        self.ecus = sorted({message.ecu for message in self._parse(lines)})
        return self.protocol

    def _parse(self, lines: list[str]) -> list[Message]:
        assert self.protocol is not None, "connect() first"
        if self.protocol.family == "can":
            return parse_can(lines, self.protocol.id_bits)
        return parse_legacy(lines)

    def _query(self, service: int, *params: int) -> list[Message]:
        """Send a request and return the positive replies to it, ordered by module."""
        self._address(None)
        try:
            lines = self.elm.request(bytes([service, *params]).hex().upper())
        except NoData:
            return []
        replies = [
            message
            for message in self._parse(lines)
            if len(message.data) > len(params[:1])
            and message.data[0] == service + 0x40
            and (not params or message.data[1] == params[0])
        ]
        return sorted(replies, key=lambda message: message.ecu)

    def _address(self, header: str | None) -> None:
        if header != self._header:
            self.elm.set_header(header or _EVERY_MODULE)
            self._header = header

    @property
    def maker_values(self) -> bool:
        """Whether maker-specific values can be read here. Only 11-bit CAN is handled so far."""
        return self.protocol is not None and self.protocol.family == "can" and self.protocol.id_bits == 11

    def read_identifier(self, module: int, identifier: int) -> bytes | None:
        """One maker-specific value (service 22, a read) from one module, or None if it has no such value.

        `module` is the address the module answers from, such as 0x7E9 for the transmission.
        """
        if not self.maker_values:
            raise ValueError("maker-specific values can only be read on an 11-bit CAN network so far")
        self._address(f"{module - 8:03X}")
        try:
            lines = self.elm.request(f"22{identifier:04X}")
        except NoData:
            return None
        wanted = bytes([0x62]) + identifier.to_bytes(2, "big")
        for message in self._parse(lines):
            if message.ecu == module and message.data[:3] == wanted:
                return bytes(message.data[3:])
        return None  # a refusal (7F 22 ..), which is how a module says it has no such value

    def supported_pids(self, service: int = 0x01) -> dict[int, set[int]]:
        """Which parameters each module offers, for live data (01) or freeze frame (02)."""
        if service in self._supported:
            return self._supported[service]
        extra = (0x00,) if service == 0x02 else ()  # freeze-frame requests carry a frame number
        offset = 2 + len(extra)
        supported: dict[int, set[int]] = {}
        base = 0x00
        while base <= 0xE0:
            more = False
            for message in self._query(service, base, *extra):
                if len(message.data) < offset + 4:
                    continue
                bits = int.from_bytes(message.data[offset : offset + 4], "big")
                found = supported.setdefault(message.ecu, set())
                found.update(base + i + 1 for i in range(32) if bits & (1 << (31 - i)))
                more = more or bool(bits & 1)  # last bit: the next block of 32 exists
            if not more:
                break
            base += 0x20
        # Multiples of 0x20 are the "what do you support" requests themselves.
        result = {ecu: {pid for pid in pids if pid % 0x20} for ecu, pids in supported.items()}
        self._supported[service] = result
        return result

    def read_pid(self, pid: int, ecu: int | None = None) -> Reading | None:
        """Current value of one live parameter, or None if nothing answers.

        Several modules can report the same parameter. Without ``ecu`` the
        lowest-numbered one wins, which is the engine computer.
        """
        replies = [m for m in self._query(0x01, pid) if ecu is None or m.ecu == ecu]
        if not replies:
            return None
        return _reading(0x01, pid, replies[0].data[2:], replies[0].ecu)

    def monitor_status(self) -> list[MonitorStatus]:
        """Check-engine light state and emissions readiness, per module."""
        return [
            decode_monitor_status(message.ecu, message.data[2:6])
            for message in self._query(0x01, 0x01)
            if len(message.data) >= 6
        ]

    def read_dtcs(self, kind: str = "stored") -> dict[int, list[str]]:
        """Trouble codes of one kind, per module. A module with none maps to []."""
        collected: dict[int, bytearray] = {}
        for message in self._query(DTC_SERVICES[kind]):
            body = message.data[1:]
            if self.protocol.family == "can" and body:
                # CAN replies start with a count; older networks send bare pairs.
                count, body = body[0], body[1:]
                if count * 2 <= len(body):
                    body = body[: count * 2]
            collected.setdefault(message.ecu, bytearray()).extend(body)
        return {ecu: parse_dtcs(bytes(data)) for ecu, data in sorted(collected.items())}

    def vin(self) -> str | None:
        """The 17-character vehicle identification number, if the vehicle reports it."""
        replies = self._query(0x09, 0x02)
        if not replies:
            return None
        ecu = replies[0].ecu
        if self.protocol.family == "can":
            raw = replies[0].data[2:]
        else:
            # Older networks split the VIN over numbered lines of four characters.
            lines = sorted(
                (m for m in replies if m.ecu == ecu and len(m.data) > 3), key=lambda m: m.data[2]
            )
            raw = b"".join(m.data[3:] for m in lines)
        text = "".join(ch for ch in raw[-17:].decode("ascii", "replace") if ch.isalnum())
        return text or None

    def freeze_frame(self) -> FreezeFrame | None:
        """The snapshot the engine computer saved when it set a code, if there is one."""
        trigger = next(
            (m for m in self._query(0x02, 0x02, 0x00) if len(m.data) >= 5 and any(m.data[3:5])),
            None,
        )
        if trigger is None:
            return None
        readings = []
        for pid in sorted(self.supported_pids(0x02).get(trigger.ecu, ())):
            if pid == 0x02:
                continue  # the triggering code itself, already read
            for reply in self._query(0x02, pid, 0x00):
                if reply.ecu == trigger.ecu:
                    readings.append(_reading(0x02, pid, reply.data[3:], reply.ecu))
                    break
        return FreezeFrame(decode_dtc(trigger.data[3], trigger.data[4]), trigger.ecu, readings)


def _reading(service: int, pid: int, data: bytes, ecu: int) -> Reading:
    key = f"{service:02X}:{pid:02X}"
    spec = PIDS.get(pid)
    if spec is None or len(data) < spec.size:
        # Not in the table yet: keep the raw bytes so nothing is lost.
        return Reading(key, f"PID {pid:02X}", data.hex().upper(), "", ecu)
    return Reading(key, spec.name, spec.decode(data), spec.unit, ecu)
