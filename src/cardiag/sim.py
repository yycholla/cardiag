"""A simulated ELM327 adapter and two simulated vehicles.

This exists so the rest of the app can be built and tested without a car. The
vehicles are loosely shaped like the real targets: a CAN-bus Ford Focus with an
engine and a transmission module, and an older J1850 VPW Chevrolet Tahoe. The
values are invented; only the wire formats are meant to be faithful.
"""

from __future__ import annotations

import functools
import math
import os
import re
import select
import threading
import time
import tty
from dataclasses import dataclass, field
from typing import Callable

from .dtc import encode_dtc

Live = dict[int, Callable[[float], bytes]]
Drive = Callable[[float], tuple[float, float, float, float]]


@dataclass
class SimEcu:
    address: int  # CAN identifier it replies from, or source address on older networks
    live: Live = field(default_factory=dict)  # service 01 PID -> data bytes at time t
    stored: tuple[str, ...] = ()
    pending: tuple[str, ...] = ()
    permanent: tuple[str, ...] = ()
    vin: str | None = None
    freeze_dtc: str | None = None
    freeze: dict[int, bytes] = field(default_factory=dict)


@dataclass
class SimVehicle:
    name: str
    protocol: str  # ELM327 protocol number
    ecus: list[SimEcu]
    battery_volts: float = 12.6

    @property
    def legacy(self) -> bool:
        return self.protocol in "12345"

    def respond(self, request: bytes, t: float) -> list[tuple[int, bytes]]:
        """Replies to one request as (module, payload). Older networks get one entry per line."""
        if not request:
            return []
        return [
            (ecu.address, payload)
            for ecu in self.ecus
            for payload in self._reply(ecu, request[0], request[1:], t)
        ]

    def _reply(self, ecu: SimEcu, service: int, args: bytes, t: float) -> list[bytes]:
        reply = bytes([service + 0x40])
        if service == 0x01 and args:
            pid = args[0]
            if pid % 0x20 == 0:
                if ecu.live and (pid == 0 or pid in _range_markers(ecu.live)):
                    return [reply + bytes([pid]) + _bitmap(pid, ecu.live)]
            elif pid in ecu.live:
                return [reply + bytes([pid]) + ecu.live[pid](t)]
        elif service == 0x02 and args and ecu.freeze_dtc:
            pid, frame = args[0], bytes(args[1:2] or b"\x00")
            saved = {0x02: encode_dtc(ecu.freeze_dtc), **ecu.freeze}
            if pid % 0x20 == 0:
                if pid == 0 or pid in _range_markers(saved):
                    return [reply + bytes([pid]) + frame + _bitmap(pid, saved)]
            elif pid in saved:
                return [reply + bytes([pid]) + frame + saved[pid]]
        elif service in (0x03, 0x07, 0x0A):
            if service == 0x0A and self.legacy:
                return []  # permanent codes only exist on CAN-era vehicles
            codes = {0x03: ecu.stored, 0x07: ecu.pending, 0x0A: ecu.permanent}[service]
            raw = b"".join(encode_dtc(code) for code in codes)
            if not self.legacy:
                return [reply + bytes([len(codes)]) + raw]
            # Older networks send three codes per line, padded with zeros.
            raw = raw.ljust(max(6, -(-len(raw) // 6) * 6), b"\x00")
            return [reply + raw[i : i + 6] for i in range(0, len(raw), 6)]
        elif service == 0x09 and args and ecu.vin:
            if args[0] == 0x00:
                return [reply + b"\x00\x40\x00\x00\x00"]
            if args[0] == 0x02:
                vin = ecu.vin.encode("ascii")
                if not self.legacy:
                    return [reply + b"\x02\x01" + vin]
                padded = b"\x00\x00\x00" + vin
                return [
                    reply + bytes([0x02, line + 1]) + padded[line * 4 : line * 4 + 4] for line in range(5)
                ]
        return []


def _range_markers(pids) -> set[int]:
    """The "next block exists" PIDs (0x20, 0x40, ...) implied by a set of PIDs."""
    return {marker for marker in range(0x20, 0x100, 0x20) if any(pid > marker for pid in pids)}


def _bitmap(base: int, pids) -> bytes:
    present = set(pids) | _range_markers(pids)
    bits = sum(1 << (31 - i) for i in range(32) if base + i + 1 in present)
    return bits.to_bytes(4, "big")


def _u8(value: float) -> bytes:
    return bytes([max(0, min(255, round(value)))])


def _u16(value: float) -> bytes:
    return max(0, min(65535, round(value))).to_bytes(2, "big")


def _percent(value: float) -> bytes:
    return _u8(value * 255 / 100)


def _trim(value: float) -> bytes:
    return _u8(128 + value * 128 / 100)


def _temperature(value: float) -> bytes:
    return _u8(value + 40)


def _drive(t: float) -> tuple[float, float, float, float]:
    """A repeating one-minute drive: idle, accelerate, cruise, slow down.

    Returns engine speed (rpm), road speed (km/h), throttle (%) and load (%).
    """
    phase = t % 60
    if phase < 10:
        return 800 + 25 * math.sin(t * 2), 0, 14, 22
    if phase < 25:
        ramp = (phase - 10) / 15
        return 1500 + 1500 * ramp, 70 * ramp, 35, 60
    if phase < 45:
        return 2100 + 30 * math.sin(t), 70, 22, 38
    ramp = (phase - 45) / 15
    return 2100 - 1300 * ramp, 70 * (1 - ramp), 10, 15


def _engine_live(*, long_trim: float, mass_air_flow: bool, drive: Drive = _drive) -> Live:
    live: Live = {
        0x03: lambda t: b"\x02\x00",  # closed loop
        0x04: lambda t: _percent(drive(t)[3]),
        0x05: lambda t: _temperature(min(92, 20 + t * 0.25)),
        0x06: lambda t: _trim(2.3 * math.sin(t / 3)),
        0x07: lambda t: _trim(long_trim),
        0x0B: lambda t: _u8(30 + drive(t)[3] * 0.6),
        0x0C: lambda t: _u16(drive(t)[0] * 4),
        0x0D: lambda t: _u8(drive(t)[1]),
        0x0E: lambda t: _u8((12 + 64) * 2),
        0x0F: lambda t: _temperature(24),
        0x11: lambda t: _percent(drive(t)[2]),
        0x1F: lambda t: _u16(t),
    }
    if mass_air_flow:
        live[0x10] = lambda t: _u16(drive(t)[0] / 200 * 100)
    return live


def _focus(name: str, vin: str, drive: Drive) -> SimVehicle:
    engine = _engine_live(long_trim=12.5, mass_air_flow=True, drive=drive)
    engine.update(
        {
            # Check-engine light on with one code; evaporative monitor not yet complete.
            0x01: lambda t: bytes([0x81, 0x07, 0xE5, 0x04]),
            0x23: lambda t: _u16(520 + drive(t)[3] * 8),  # direct-injection rail pressure, x10 kPa
            0x2F: lambda t: _percent(62),
            0x31: lambda t: _u16(184),
            0x33: lambda t: _u8(99),
            0x42: lambda t: _u16(14100),
            0x46: lambda t: _temperature(18),
            0x5C: lambda t: _temperature(min(98, 20 + t * 0.2)),
        }
    )
    return SimVehicle(
        name=name,
        protocol="6",
        ecus=[
            SimEcu(
                address=0x7E8,
                live=engine,
                stored=("P0171",),
                pending=("P0456",),
                permanent=("P0171",),
                vin=vin,
                freeze_dtc="P0171",
                freeze={
                    0x04: _percent(41),
                    0x05: _temperature(88),
                    0x06: _trim(9.4),
                    0x07: _trim(14.1),
                    0x0C: _u16(1850 * 4),
                    0x0D: _u8(52),
                    0x11: _percent(19),
                },
            ),
            SimEcu(address=0x7E9, live={0x0D: lambda t: _u8(drive(t)[1])}, stored=("P0902",)),
        ],
    )


def make_focus() -> SimVehicle:
    """A 2017-style Focus: CAN bus, engine and transmission modules, a lean-running fault."""
    return _focus("focus", "1FADP3F2XHL123456", _drive)


# Engine rpm per km/h in each gear of the simulated dual-clutch gearbox. Invented, not Ford's.
_DCT_RATIOS = (120.0, 70.0, 48.0, 36.0, 29.0, 24.0)
_DCT_STEP = 0.05
_DCT_LAP = 150.0


def _dct_pedal(t: float) -> tuple[float, float]:
    """Accelerator (%) and braking (km/h per second) through one lap."""
    if t < 4:
        return 0.0, 0.0
    if t < 60:
        return 22.0, 0.0  # a gentle run up through the gears
    if t < 76:
        return 0.0, 4.5
    if t < 120:
        return 50.0, 0.0  # a hard run: this is where the faults show
    if t < 133:
        return 20.0, 0.0
    return 0.0, 6.5


@functools.lru_cache(maxsize=1)
def _dct_lap() -> list[tuple[float, float, float, float]]:
    """One lap of a drive in a geared car, as (rpm, km/h, pedal %, load %) every 0.05 s.

    The gearbox has two faults, both only under a heavy foot: the clutch slips in
    third gear, and the shift from second to third is slow, with the engine
    speeding up before the next gear takes hold.
    """
    table = []
    speed, gear, load = 0.0, 0, 20.0
    shift: dict | None = None
    for step in range(round(_DCT_LAP / _DCT_STEP)):
        pedal, brake = _dct_pedal(step * _DCT_STEP)
        hard = pedal >= 40
        load += (18 + pedal * 0.9 - load) * 0.1
        locked = speed * _DCT_RATIOS[gear]
        if shift:
            shift["done"] = min(1.0, shift["done"] + _DCT_STEP / shift["takes"])
            target = speed * _DCT_RATIOS[shift["to"]]
            rpm = shift["rpm"] + (target - shift["rpm"]) * shift["done"]
            if shift["flare"]:
                rpm += 900 * math.sin(math.pi * shift["done"])
            accel = -0.3
            if shift["done"] >= 1:
                gear, shift = shift["to"], None
        else:
            slipping = gear == 2 and hard
            rpm = locked * (1.07 if slipping else 1.0)
            if gear == 0 and pedal > 0:
                rpm = max(1100.0, rpm)  # pulling away: the clutch is still taking up
            rpm = max(780.0, rpm)
            pull = pedal / 100 * _DCT_RATIOS[gear] * 0.12 * (0.75 if slipping else 1.0)
            accel = pull - 0.003 * speed - (0.2 if speed > 0 else 0.0) - brake
            if pedal > 0 and gear < 5 and rpm >= (2800 if hard else 1900):
                faulty = hard and gear == 1
                shift = {"to": gear + 1, "rpm": rpm, "done": 0.0, "takes": 1.5 if faulty else 0.4, "flare": faulty}
            elif gear > 0 and locked < 1000:
                gear -= 1
        table.append((rpm, speed, pedal, load))
        speed = max(0.0, speed + accel * _DCT_STEP)
    return table


def _dct_drive(t: float) -> tuple[float, float, float, float]:
    rpm, speed, pedal, load = _dct_lap()[int((t % _DCT_LAP) / _DCT_STEP)]
    return rpm, speed, max(8.0, pedal), load


def make_focus_dct() -> SimVehicle:
    """The Focus again, driven through its gears, with a clutch that slips in third under load."""
    vehicle = _focus("focus_dct", "1FADP3F2XHL654321", _dct_drive)
    vehicle.ecus[0].live[0x49] = lambda t: _percent(_dct_lap()[int((t % _DCT_LAP) / _DCT_STEP)][2])
    return vehicle


def make_tahoe() -> SimVehicle:
    """A pre-2007-style Tahoe: one J1850 VPW network and a single engine computer."""
    engine = _engine_live(long_trim=3.1, mass_air_flow=True)
    engine.update(
        {
            0x01: lambda t: bytes([0x84, 0x07, 0x65, 0x00]),
            0x08: lambda t: _trim(-1.6),
            0x09: lambda t: _trim(4.7),
            0x14: lambda t: bytes([round(200 * (0.45 + 0.35 * math.sin(t * 4))), 0x80]),
        }
    )
    return SimVehicle(
        name="tahoe",
        protocol="2",
        ecus=[
            SimEcu(
                address=0x10,
                live=engine,
                stored=("P0300", "P0171", "P0174", "P0420"),
                pending=("P0300",),
                vin="1GNEK13Z03J123456",
            )
        ],
        battery_volts=12.4,
    )


VEHICLES: dict[str, Callable[[], SimVehicle]] = {
    "focus": make_focus,
    "focus_dct": make_focus_dct,
    "tahoe": make_tahoe,
}

_ATDP_NAMES = {"2": "SAE J1850 VPW", "6": "ISO 15765-4 (CAN 11/500)"}
_ACCEPTED_SETTINGS = re.compile(
    r"AT[012]|ST[0-9A-F]{2}|SH[0-9A-F]{3,8}|CAF[01]|CFC[01]|CRA[0-9A-F]*|AL|NL|M[01]|PC"
)


class SimElm:
    """Answers ELM327 command text the way the real chip does."""

    def __init__(
        self,
        vehicle: SimVehicle | None,
        *,
        stn: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.vehicle = vehicle  # None behaves like an adapter that is not plugged into a car
        self.stn = stn  # False behaves like a plain ELM327 without OBDLink extensions
        self._clock = clock
        self._started = clock()
        self._reset()

    def _reset(self) -> None:
        self.echo = True
        self.linefeeds = False
        self.spaces = True
        self.headers = False
        self.chosen = "0"  # protocol the user asked for; "0" is automatic
        self.active: str | None = None  # protocol actually in use

    def handle(self, raw: str) -> str:
        """Process one command line and return the full reply, prompt included."""
        typed = raw.strip("\r\n")
        echo = self.echo
        lines = self._execute("".join(typed.split()).upper())
        eol = "\r\n" if self.linefeeds else "\r"
        return (typed + eol if echo else "") + "".join(line + eol for line in lines) + eol + ">"

    def _execute(self, command: str) -> list[str]:
        if command.startswith("AT"):
            return self._at(command[2:])
        if command.startswith("ST"):
            if self.stn and command == "STI":
                return ["STN2230 v5.6.19 (simulated)"]
            if self.stn and command == "STDI":
                return ["OBDLink EX r1.0 (simulated)"]
            return ["?"]
        if re.fullmatch(r"(?:[0-9A-F]{2})+", command):
            return self._obd(bytes.fromhex(command))
        return ["?"]

    def _at(self, command: str) -> list[str]:
        if command in ("Z", "WS"):
            self._reset()
            return ["ELM327 v1.4b"]
        if command == "D":
            self._reset()
            return ["OK"]
        if command == "I":
            return ["ELM327 v1.4b"]
        if command == "@1":
            return ["OBDII to RS232 Interpreter"]
        if command == "RV":
            return [f"{self.vehicle.battery_volts if self.vehicle else 0.0:.1f}V"]
        if command in ("DP", "DPN"):
            auto = self.chosen == "0"
            number = self.active or self.chosen
            if command == "DPN":
                return [("A" if auto else "") + number]
            name = _ATDP_NAMES.get(number, "")
            return [", ".join(part for part in ("AUTO" if auto else "", name) if part)]
        flag = re.fullmatch(r"([ELSH])([01])", command)
        if flag:
            attribute = {"E": "echo", "L": "linefeeds", "S": "spaces", "H": "headers"}[flag.group(1)]
            setattr(self, attribute, flag.group(2) == "1")
            return ["OK"]
        protocol = re.fullmatch(r"[ST]PA?([0-9A-C])", command)
        if protocol:
            self.chosen, self.active = protocol.group(1), None
            return ["OK"]
        if _ACCEPTED_SETTINGS.fullmatch(command):
            return ["OK"]
        return ["?"]

    def _obd(self, request: bytes) -> list[str]:
        searching = ["SEARCHING..."] if self.active is None and self.chosen == "0" else []
        if self.vehicle is None or self.chosen not in ("0", self.vehicle.protocol):
            return searching + ["UNABLE TO CONNECT"]
        replies = self.vehicle.respond(request, self._clock() - self._started)
        if not replies:
            return searching + ["NO DATA"]
        self.active = self.vehicle.protocol
        if self.vehicle.legacy:
            return searching + self._format_legacy(replies)
        return searching + self._format_can(replies)

    def _join(self, parts: list[str]) -> str:
        return (" " if self.spaces else "").join(parts)

    def _format_can(self, replies: list[tuple[int, bytes]]) -> list[str]:
        lines = []
        for ecu, payload in replies:
            frames = _isotp_frames(payload)
            if self.headers:
                lines += [self._join([f"{ecu:03X}"] + _hex(frame)) for frame in frames]
            elif len(frames) == 1:
                lines.append(self._join(_hex(payload)))
            else:
                # Headers off: a length line, then numbered segments.
                lines.append(f"{len(payload):03X}")
                for index, frame in enumerate(frames):
                    lines.append(f"{index & 0xF:X}: " + self._join(_hex(frame[2 if index == 0 else 1 :])))
        return lines

    def _format_legacy(self, replies: list[tuple[int, bytes]]) -> list[str]:
        lines = []
        for ecu, payload in replies:
            if self.headers:
                framed = bytes([0x48, 0x6B, ecu]) + payload
                payload = framed + bytes([_j1850_crc(framed)])
            lines.append(self._join(_hex(payload)))
        return lines


def _hex(data: bytes) -> list[str]:
    return [f"{byte:02X}" for byte in data]


def _isotp_frames(payload: bytes) -> list[bytes]:
    """Split a payload into padded eight-byte CAN frames, as a real module would."""
    if len(payload) <= 7:
        return [bytes([len(payload)]) + payload.ljust(7, b"\x00")]
    frames = [bytes([0x10 | (len(payload) >> 8), len(payload) & 0xFF]) + payload[:6]]
    rest, sequence = payload[6:], 1
    while rest:
        frames.append(bytes([0x20 | (sequence & 0xF)]) + rest[:7].ljust(7, b"\x00"))
        rest, sequence = rest[7:], sequence + 1
    return frames


def _j1850_crc(data: bytes) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1D) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc ^ 0xFF


class SimTransport:
    """Connects the driver straight to a simulated adapter, with no serial port."""

    def __init__(self, sim: SimElm) -> None:
        self._sim = sim
        self._incoming = bytearray()
        self._outgoing = bytearray()

    def write(self, data: bytes) -> None:
        self._incoming += data
        while b"\r" in self._incoming:
            line, _, rest = bytes(self._incoming).partition(b"\r")
            self._incoming = bytearray(rest)
            self._outgoing += self._sim.handle(line.decode("ascii", "replace")).encode("ascii", "replace")

    def read(self) -> bytes:
        data = bytes(self._outgoing)
        self._outgoing.clear()
        return data

    def flush_input(self) -> None:
        self._outgoing.clear()

    def close(self) -> None:
        pass


class PtyAdapter:
    """Presents a simulated adapter as a serial device, e.g. /dev/pts/5.

    This lets the real serial code path be exercised without hardware.
    """

    def __init__(self, sim: SimElm) -> None:
        self._sim = sim
        self._master, self._slave = os.openpty()
        tty.setraw(self._slave)
        self.path = os.ttyname(self._slave)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def serve_forever(self) -> None:
        pending = bytearray()
        while not self._stop.is_set():
            readable, _, _ = select.select([self._master], [], [], 0.1)
            if not readable:
                continue
            try:
                pending += os.read(self._master, 4096)
            except OSError:
                break
            while b"\r" in pending:
                line, _, rest = bytes(pending).partition(b"\r")
                pending = bytearray(rest)
                reply = self._sim.handle(line.decode("ascii", "replace"))
                os.write(self._master, reply.encode("ascii", "replace"))

    def __enter__(self) -> "PtyAdapter":
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        for fd in (self._master, self._slave):
            try:
                os.close(fd)
            except OSError:
                pass
