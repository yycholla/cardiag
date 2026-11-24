"""Configuration ("as-built") blocks and the settings known to live in them.

A module keeps its configuration in a few blocks, each read with `22 DExx`. One
setting is some bits of one block. This file holds the blocks as they were read
from the captured car and the settings mapped onto them so far, and turns a
block's bytes into each setting's value.

It only describes and reads. Nothing here builds a write request: a changed
value is shown as the block it would make, for comparison with FORScan.

A setting is a span of bytes in one block, big-endian, with a mask over it. The
bits under the mask, shifted down, are its raw value. What the raw value means
depends on the kind:

- toggle: one state or the other. When which state means "on" is not known,
  the states carry no names.
- choice: one of a list of values, such as a colour or a logo.
- number: a quantity, raw times scale plus offset, such as a time or a volume.
- flags: several independent bits, such as which lamps act as running lights.
- hex: bytes whose meaning is not split up further, shown as they are.
"""

from __future__ import annotations

from dataclasses import dataclass, field

KINDS = ("toggle", "choice", "number", "flags", "hex")

# How sure a setting is: seen changing on this car, reported elsewhere, or made up to show the page.
STATUSES = ("observed", "reported", "example")


@dataclass(frozen=True)
class Module:
    name: str
    label: str
    bus: str  # HS or MS CAN
    request: str  # address the requests go to, hex
    reply: str
    blocks: tuple[tuple[str, int, str | None], ...]  # identifier, FORScan block number, captured bytes (None: withheld)


@dataclass(frozen=True)
class Setting:
    id: str
    name: str
    module: str
    did: str
    kind: str
    byte: int  # first byte of the span, counting from 0
    mask: int  # over the span, big-endian
    size: int = 1  # bytes in the span
    status: str = "observed"
    evidence: str = ""
    unknown: str = ""
    states: tuple[str, str] | None = None  # toggle: (name when the bits are set, name when clear)
    options: tuple[tuple[int, str], ...] = ()  # choice: raw value, name
    bits: tuple[tuple[int, str], ...] = ()  # flags: bit of the raw value, name
    scale: float = 1.0  # number: value = raw * scale + offset
    offset: float = 0.0
    unit: str = ""
    group: str = ""

    @property
    def shift(self) -> int:
        return (self.mask & -self.mask).bit_length() - 1

    @property
    def width(self) -> int:
        """Bits in the raw value."""
        return (self.mask >> self.shift).bit_length()

    def raw(self, block: bytes) -> int:
        span = int.from_bytes(block[self.byte:self.byte + self.size], "big")
        return (span & self.mask) >> self.shift

    def describe(self, raw: int) -> str:
        """The raw value in words."""
        if self.kind == "toggle":
            on = raw == self.mask >> self.shift
            if self.states and (on or raw == 0):
                return self.states[0 if on else 1]
            word = "Bit" if self.width == 1 else "Bits"
            return f"{word} set" if on else (f"{word} clear" if raw == 0 else f"Mixed ({raw:X})")
        if self.kind == "choice":
            return dict(self.options).get(raw, f"Unlisted value {raw:X}")
        if self.kind == "number":
            value = raw * self.scale + self.offset
            text = f"{value:g}"
            return f"{text} {self.unit}".strip()
        if self.kind == "flags":
            named = [name for bit, name in self.bits if raw & bit]
            return ", ".join(named) if named else "None"
        return format(raw, f"0{self.size * 2}X")

    def as_json(self) -> dict:
        out = {
            "id": self.id, "name": self.name, "module": self.module, "did": self.did, "kind": self.kind,
            "byte": self.byte, "size": self.size, "mask": self.mask, "status": self.status,
            "evidence": self.evidence, "unknown": self.unknown, "group": self.group,
        }
        if self.kind == "toggle":
            out["states"] = list(self.states) if self.states else None
        elif self.kind == "choice":
            out["options"] = [{"value": value, "label": label} for value, label in self.options]
        elif self.kind == "number":
            out.update(scale=self.scale, offset=self.offset, unit=self.unit)
        elif self.kind == "flags":
            out["bits"] = [{"bit": bit, "label": label} for bit, label in self.bits]
        return out


# As read by FORScan from the captured 2017 Focus 2.0 GDI (docs/data/focus-2017-asbuilt.txt).
# Blocks that hold the VIN are withheld.
MODULES: tuple[Module, ...] = (
    Module("BdyCM", "body control", "HS", "726", "72E", (
            ("DE00", 1, "0100018463000000001241385300F51932010E3C0900000B0B924000004040037D00000A0000000000000000000000000000"),
            ("DE01", 2, "00042424"),
            ("DE02", 3, "0101"),
            ("DE03", 4, "0100"),
            ("DE04", 5, "00"),
            ("DE05", 6, "00"),
    )),
    Module("PCM", "engine", "HS", "7E0", "7E8", (
            ("DE00", 1, "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF2AFFFFFFFFFFFFFFFFFFFFFFFF0FFFFFFFFF1FFFF21FFFFFFFFFFFFFFFFFFF"),
            ("DE01", 2, "261E803F1CC17F3F4C22803F00BE7F3FC0EB7F3F3B15803FD7AC7F3F7A1E803FAF18803FDCCD7F3F6C1E803FEFC37F3F00000000"),
    )),
    Module("APIM", "SYNC", "HS", "7D0", "7D8", (
            ("DE00", 1, "1065880002404000"),
            ("DE01", 2, "045553000000"),
            ("DE02", 3, "0000000000"),
    )),
    Module("ABS", "anti-lock brakes", "HS", "760", "768", (
            ("DE00", 1, None),
    )),
    Module("RCM", "restraints", "HS", "737", "73F", (
            ("DE00", 1, None),
            ("DE01", 2, "C76ACF3B100C6600"),
            ("DE02", 3, "8165"),
            ("DE03", 4, "0F50"),
            ("DE05", 6, "00"),
    )),
    Module("PSCM", "power steering", "HS", "730", "738", (
            ("DE00", 1, "14"),
    )),
    Module("FCDIM", "display", "MS", "7A5", "7AD", (
            ("DE00", 1, "22220008000010"),
            ("DE01", 2, "000155538000"),
            ("DE02", 3, "00010000"),
            ("DE03", 4, "0000"),
    )),
    Module("ACM", "audio", "MS", "727", "72F", (
            ("DE00", 1, "78002C000007"),
            ("DE01", 2, "2E"),
            ("DE02", 3, "30"),
            ("DE03", 4, "0001025553"),
            ("DE04", 5, "12040B5722763E572F12"),
            ("DE05", 6, "16001A001C001F002200380048005A0005000700"),
            ("DE06", 7, "00000A00330035005C0064005C00350033000A00"),
            ("DE07", 8, "9799009826009A9B00009A9B000000000000FFFF00FFFFFFFFFFFFFFFF00"),
    )),
    Module("IPC", "instrument cluster", "MS", "720", "728", (
            ("DE00", 1, "43010000"),
            ("DE01", 2, "001E9C1F0A062452101F"),
            ("DE02", 3, "BFCB0402"),
            ("DE03", 4, "07040302"),
            ("DE04", 5, "07040302"),
            ("DE05", 6, "34000403"),
            ("DE06", 7, "011E00"),
            ("DE07", 8, "18000800"),
            ("DE08", 9, "001E053C"),
            ("DE09", 10, "FE"),
            ("DE0A", 11, "05000000"),
            ("DE0B", 12, "03FF03DA03DA03FF03FF03A203FF01FF02800300037603FF02BC0320038403B603FF"),
            ("DE0C", 13, "0403E801050A0F141A2027303B4A5D7DA6AAACAFB1B4"),
            ("DE0D", 14, "2814006450281400190A006432190A00"),
            ("DE10", 17, "FFFFFF9F"),
            ("DE11", 18, "FFFFFF3E"),
            ("DE12", 19, "FFFFFFFF"),
            ("DE13", 20, "FFFEFFFF"),
            ("DE14", 21, "FF7FFFFF"),
            ("DE15", 22, "FFFFFFFF"),
            ("DE16", 23, "BFFFFF0F"),
            ("DE1A", 27, "E0"),
            ("DE1B", 28, "FF3F1900"),
            ("DE1C", 29, "7F1E0000"),
            ("DE1D", 30, "FFFF0F00"),
            ("DE1E", 31, "FFFF7F00"),
            ("DE1F", 32, "F0"),
            ("DE21", 34, "16010000"),
            ("DE22", 35, "FBFFFF47"),
            ("DE23", 36, "00000000"),
    )),
    Module("GPSM", "GPS", "MS", "701", "709", (
            ("DE00", 1, "20"),
            ("DE01", 2, "00000000000000"),
    )),
)

SETTINGS: tuple[Setting, ...] = (
    Setting(
        "ipc.key_in_ignition_beep", "Key-in-ignition beep", "IPC", "DE11", "toggle", byte=2, mask=0x80,
        group="Chimes",
        evidence="Named by the operator; FORScan cleared this bit and set it again, and both writes were accepted.",
        unknown="which state turns the beep on.",
    ),
)

# Made up, in a block of their own, to show each kind of setting with the simulated car. Not the car's.
EXAMPLE_MODULE = Module("EXAMPLE", "made-up examples", "MS", "000", "008", (("DE01", 1, "A50C2A0258017F"),))
EXAMPLES: tuple[Setting, ...] = (
    Setting(
        "example.chime", "Seat belt chime", "EXAMPLE", "DE01", "toggle", byte=0, mask=0x80, status="example",
        states=("On", "Off"), group="Chimes", evidence="Made up to show an on/off setting.",
    ),
    Setting(
        "example.splash", "Startup logo", "EXAMPLE", "DE01", "choice", byte=0, mask=0x0F, status="example",
        options=((1, "Ford"), (5, "Ford Performance"), (0xB, "ST"), (0xC, "RS")), group="Display",
        evidence="Made up to show a list of choices.",
    ),
    Setting(
        "example.drl", "Daytime running lights", "EXAMPLE", "DE01", "flags", byte=1, mask=0xFF, status="example",
        bits=((0x01, "Master disable"), (0x02, "Low beams"), (0x04, "Fog lamps"), (0x08, "Turn lamps"),
              (0x10, "Dedicated DRL"), (0x20, "High beams")),
        group="Lighting", evidence="Made up to show several independent switches in one byte.",
    ),
    Setting(
        "example.lamps", "Courtesy lamp fade", "EXAMPLE", "DE01", "number", byte=2, mask=0xFF, status="example",
        scale=0.5, unit="s", group="Lighting", evidence="Made up to show a number with a unit.",
    ),
    Setting(
        "example.tank", "Fuel tank size", "EXAMPLE", "DE01", "number", byte=3, size=2, mask=0x0FFF,
        status="example", scale=0.1, unit="L", group="Gauges",
        evidence="Made up to show a number spread over two bytes.",
    ),
    Setting(
        "example.raw", "Unsplit bytes", "EXAMPLE", "DE01", "hex", byte=5, size=2, mask=0xFFFF, status="example",
        group="Other", evidence="Made up to show bytes whose meaning is not split up.",
    ),
)


def _block(modules: tuple[Module, ...], module: str, did: str) -> tuple[int, str | None] | None:
    for each in modules:
        if each.name == module:
            for name, number, data in each.blocks:
                if name == did:
                    return number, data
    return None


def check(settings: tuple[Setting, ...] = SETTINGS, modules: tuple[Module, ...] = MODULES) -> None:
    """Raise ValueError if a setting does not fit the block it names, or two overlap."""
    seen: dict[str, Setting] = {}
    taken: dict[tuple[str, str, int], str] = {}
    for setting in settings:
        where = f"setting {setting.id}"
        if setting.id in seen:
            raise ValueError(f"{where} is listed twice")
        seen[setting.id] = setting
        if setting.kind not in KINDS or setting.status not in STATUSES:
            raise ValueError(f"{where} has an unknown kind or status")
        found = _block(modules, setting.module, setting.did)
        if found is None:
            raise ValueError(f"{where} names {setting.module} {setting.did}, which is not a known block")
        data = found[1]
        if data is None:
            raise ValueError(f"{where} is in a withheld block")
        if not 1 <= setting.size <= 6 or setting.byte < 0 or setting.byte + setting.size > len(data) // 2:
            raise ValueError(f"{where} runs past the end of its block")
        if setting.mask <= 0 or setting.mask >> (8 * setting.size):
            raise ValueError(f"{where} has a mask that does not fit its bytes")
        limit = 1 << setting.width
        if setting.kind == "choice" and (not setting.options or any(not 0 <= v < limit for v, _ in setting.options)):
            raise ValueError(f"{where} has a choice that does not fit its bits")
        if setting.kind == "flags" and (not setting.bits or any(b <= 0 or b & (b - 1) or b >= limit for b, _ in setting.bits)):
            raise ValueError(f"{where} names a flag that is not one of its bits")
        if setting.kind == "flags" and setting.width > 31:
            raise ValueError(f"{where} has more flags than the page can handle")
        if setting.kind == "number" and setting.scale == 0:
            raise ValueError(f"{where} has a scale of zero")
        for index in range(setting.size):
            bits = (setting.mask >> (8 * (setting.size - 1 - index))) & 0xFF
            for bit in range(8):
                if bits & (1 << bit):
                    key = (setting.module, setting.did, (setting.byte + index) * 8 + bit)
                    if key in taken:
                        raise ValueError(f"{where} overlaps {taken[key]}")
                    taken[key] = setting.id


def report(simulation: str | None = None) -> dict:
    """Every block with its bytes and the settings mapped onto it, for the page.

    With a simulated car the made-up examples are added, so each kind of setting can be seen.
    """
    modules, settings = MODULES, SETTINGS
    if simulation:
        modules, settings = modules + (EXAMPLE_MODULE,), settings + EXAMPLES
    out = []
    for module in modules:
        blocks = []
        for did, number, data in module.blocks:
            block = bytes.fromhex(data) if data else None
            mapped = []
            for setting in settings:
                if setting.module == module.name and setting.did == did and block is not None:
                    raw = setting.raw(block)
                    mapped.append({**setting.as_json(), "raw": raw, "text": setting.describe(raw)})
            blocks.append({
                "did": did, "block": number, "hex": data, "withheld": data is None,
                "size": len(block) if block is not None else None, "settings": mapped,
            })
        out.append({
            "name": module.name, "label": module.label, "bus": module.bus,
            "request": module.request, "reply": module.reply, "blocks": blocks,
        })
    return {
        "car": "2017 Ford Focus 2.0 GDI",
        "source": "capture",
        "examples": bool(simulation),
        "modules": out,
    }
