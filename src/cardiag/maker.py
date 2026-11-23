"""Maker-specific values: figures a module keeps beyond the standard OBD-II set.

They are read with service 22 (read data by identifier), addressed to one
module. It is a read, like everything else this app sends. The makers do not
publish which identifier holds what, or how its bytes become a number, so the
definitions here are data that the person at the page supplies and checks
against their own car, not facts built into the app.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_VALUES = 24


@dataclass(frozen=True)
class MakerValue:
    module: int  # address the module answers from, e.g. 0x7E9
    identifier: int
    name: str
    unit: str
    size: int  # how many bytes make up the number
    signed: bool
    scale: float
    offset: float
    start: int = 0  # how many bytes to skip before the number begins

    @property
    def key(self) -> str:
        return f"22:{self.module:03X}:{self.identifier:04X}"

    def decode(self, data: bytes) -> float | None:
        if len(data) < self.start + self.size:
            return None
        number = int.from_bytes(data[self.start : self.start + self.size], "big", signed=self.signed)
        return number * self.scale + self.offset

    def as_json(self) -> dict:
        return {
            "module": f"{self.module:03X}", "id": f"{self.identifier:04X}", "name": self.name, "unit": self.unit,
            "size": self.size, "signed": self.signed, "scale": self.scale, "offset": self.offset, "start": self.start,
            "key": self.key,
        }


# Leads worth trying on a Ford dual-clutch (DPS6) transmission. They come from an owners' forum,
# not from Ford, and have not been confirmed on any car by this project.
CANDIDATES = [
    {"module": "7E9", "id": "1EBB", "name": "Clutch A slip", "unit": "rpm", "size": 2, "signed": True, "scale": 0.25, "offset": 0.0},
    {"module": "7E9", "id": "1EBC", "name": "Clutch B slip", "unit": "rpm", "size": 2, "signed": True, "scale": 0.25, "offset": 0.0},
]


def hex_number(text: object, digits: int, what: str) -> int:
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= digits:
        raise ValueError(f"{what} must be up to {digits} hexadecimal digits, such as {'7E9' if digits == 3 else '1EBB'}")
    try:
        return int(text.strip(), 16)
    except ValueError:
        raise ValueError(f"{what} must be up to {digits} hexadecimal digits, such as {'7E9' if digits == 3 else '1EBB'}") from None


def module_address(text: object) -> int:
    module = hex_number(text, 3, "the module")
    if not 0x7E8 <= module <= 0x7EF:
        raise ValueError("the module must be one that answers between 7E8 and 7EF")
    return module


def _number(value: object, what: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a number") from None
    if number != number or abs(number) > 1e9:
        raise ValueError(f"{what} must be a number")
    return number


def parse(given: object) -> list[MakerValue]:
    """Definitions as the page or the database holds them, checked. Raises ValueError with the reason."""
    if not isinstance(given, list) or len(given) > MAX_VALUES:
        raise ValueError(f"expected a list of at most {MAX_VALUES} values")
    values, seen = [], set()
    for item in given:
        if not isinstance(item, dict):
            raise ValueError("each value must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
            raise ValueError("each value needs a name of up to 60 characters")
        unit = item.get("unit", "")
        if not isinstance(unit, str) or len(unit) > 12:
            raise ValueError("the unit must be at most 12 characters")
        size = item.get("size", 1)
        if isinstance(size, bool) or size not in (1, 2, 3, 4):
            raise ValueError("the number of bytes must be 1, 2, 3 or 4")
        start = item.get("start", 0)
        if isinstance(start, bool) or not isinstance(start, int) or not 0 <= start <= 60:
            raise ValueError("the number of bytes to skip must be between 0 and 60")
        scale = _number(item.get("scale", 1), "the scale")
        if scale == 0:
            raise ValueError("the scale cannot be zero")
        value = MakerValue(
            module=module_address(item.get("module")),
            identifier=hex_number(item.get("id"), 4, "the identifier"),
            name=name.strip(), unit=unit.strip(), size=size, signed=bool(item.get("signed", False)),
            scale=scale, offset=_number(item.get("offset", 0), "the offset"), start=start,
        )
        if value.key in seen:
            raise ValueError(f"{value.identifier:04X} from module {value.module:03X} is listed twice")
        seen.add(value.key)
        values.append(value)
    return values
