"""Standard OBD-II live-data parameters (SAE J1979 service 01) and their scaling.

Every vehicle sold in the US since 1996 uses these same definitions, so this
table applies to the Focus and the Tahoe alike. Manufacturer-specific data
lives elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

Value = float | str


@dataclass(frozen=True)
class Pid:
    pid: int
    name: str
    unit: str
    size: int  # number of data bytes the vehicle returns
    decode: Callable[[bytes], Value]


def _byte(d: bytes) -> float:
    return float(d[0])


def _word(d: bytes) -> float:
    return float((d[0] << 8) | d[1])


def _percent(d: bytes) -> float:
    return d[0] * 100 / 255


def _temperature(d: bytes) -> float:
    return float(d[0] - 40)


def _trim(d: bytes) -> float:
    return (d[0] - 128) * 100 / 128


def _lambda(d: bytes) -> float:
    return ((d[0] << 8) | d[1]) * 2 / 65536


def _scaled(factor: float, offset: float = 0.0) -> Callable[[bytes], float]:
    return lambda d: ((d[0] << 8) | d[1]) * factor + offset


_FUEL_SYSTEM = {
    0x00: "not reported",
    0x01: "open loop (not yet warm)",
    0x02: "closed loop",
    0x04: "open loop (load or deceleration)",
    0x08: "open loop (system fault)",
    0x10: "closed loop (feedback fault)",
}


def _fuel_system(d: bytes) -> str:
    return _FUEL_SYSTEM.get(d[0], f"0x{d[0]:02X}")


def _signed_quarter(d: bytes) -> float:
    return int.from_bytes(d[:2], "big", signed=True) / 4


_TABLE = [
    Pid(0x03, "Fuel system status", "", 2, _fuel_system),
    Pid(0x04, "Engine load", "%", 1, _percent),
    Pid(0x05, "Coolant temperature", "°C", 1, _temperature),
    Pid(0x06, "Short-term fuel trim, bank 1", "%", 1, _trim),
    Pid(0x07, "Long-term fuel trim, bank 1", "%", 1, _trim),
    Pid(0x08, "Short-term fuel trim, bank 2", "%", 1, _trim),
    Pid(0x09, "Long-term fuel trim, bank 2", "%", 1, _trim),
    Pid(0x0A, "Fuel pressure", "kPa", 1, lambda d: d[0] * 3.0),
    Pid(0x0B, "Intake manifold pressure", "kPa", 1, _byte),
    Pid(0x0C, "Engine speed", "rpm", 2, _scaled(0.25)),
    Pid(0x0D, "Vehicle speed", "km/h", 1, _byte),
    Pid(0x0E, "Ignition timing advance", "°", 1, lambda d: d[0] / 2 - 64),
    Pid(0x0F, "Intake air temperature", "°C", 1, _temperature),
    Pid(0x10, "Mass air flow", "g/s", 2, _scaled(0.01)),
    Pid(0x11, "Throttle position", "%", 1, _percent),
    Pid(0x1F, "Time since engine start", "s", 2, _word),
    Pid(0x21, "Distance with check-engine light on", "km", 2, _word),
    Pid(0x22, "Fuel rail pressure (relative)", "kPa", 2, _scaled(0.079)),
    Pid(0x23, "Fuel rail pressure", "kPa", 2, _scaled(10)),
    Pid(0x2C, "Commanded EGR", "%", 1, _percent),
    Pid(0x2D, "EGR error", "%", 1, _trim),
    Pid(0x2E, "Commanded evaporative purge", "%", 1, _percent),
    Pid(0x2F, "Fuel level", "%", 1, _percent),
    Pid(0x30, "Warm-ups since codes cleared", "", 1, _byte),
    Pid(0x31, "Distance since codes cleared", "km", 2, _word),
    Pid(0x32, "Evaporative system vapour pressure", "Pa", 2, _signed_quarter),
    Pid(0x33, "Barometric pressure", "kPa", 1, _byte),
    Pid(0x3C, "Catalyst temperature, bank 1 sensor 1", "°C", 2, _scaled(0.1, -40)),
    Pid(0x3D, "Catalyst temperature, bank 2 sensor 1", "°C", 2, _scaled(0.1, -40)),
    Pid(0x3E, "Catalyst temperature, bank 1 sensor 2", "°C", 2, _scaled(0.1, -40)),
    Pid(0x3F, "Catalyst temperature, bank 2 sensor 2", "°C", 2, _scaled(0.1, -40)),
    Pid(0x42, "Control module voltage", "V", 2, _scaled(0.001)),
    Pid(0x43, "Absolute load", "%", 2, _scaled(100 / 255)),
    Pid(0x44, "Commanded air-fuel ratio (lambda)", "λ", 2, _lambda),
    Pid(0x45, "Relative throttle position", "%", 1, _percent),
    Pid(0x46, "Ambient air temperature", "°C", 1, _temperature),
    Pid(0x47, "Throttle position B", "%", 1, _percent),
    Pid(0x49, "Accelerator pedal position D", "%", 1, _percent),
    Pid(0x4A, "Accelerator pedal position E", "%", 1, _percent),
    Pid(0x4C, "Commanded throttle", "%", 1, _percent),
    Pid(0x4D, "Run time with check-engine light on", "min", 2, _word),
    Pid(0x4E, "Time since codes cleared", "min", 2, _word),
    Pid(0x52, "Ethanol in fuel", "%", 1, _percent),
    Pid(0x5C, "Engine oil temperature", "°C", 1, _temperature),
    Pid(0x5E, "Fuel rate", "L/h", 2, _scaled(0.05)),
    Pid(0x61, "Driver demand torque", "%", 1, lambda d: float(d[0] - 125)),
    Pid(0x62, "Actual engine torque", "%", 1, lambda d: float(d[0] - 125)),
    Pid(0x63, "Engine reference torque", "N·m", 2, _word),
]

# Oxygen sensors come in three families of eight consecutive PIDs.
for _n in range(8):
    _TABLE.append(Pid(0x14 + _n, f"Oxygen sensor {_n + 1} voltage", "V", 2, lambda d: d[0] / 200))
    _TABLE.append(Pid(0x24 + _n, f"Oxygen sensor {_n + 1} lambda", "λ", 4, _lambda))
    _TABLE.append(Pid(0x34 + _n, f"Oxygen sensor {_n + 1} lambda (wide range)", "λ", 4, _lambda))

PIDS: dict[int, Pid] = {entry.pid: entry for entry in _TABLE}
