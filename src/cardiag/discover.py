"""Makes sense of a discovery run: which of a module's unknown bytes move with what.

A run holds the raw bytes of every identifier a module answered, read over and
over through a drive, beside a few standard values. Nothing says what the bytes
mean. This tries each byte, and each pair of bytes, as a number, and measures
how closely it follows things already known: the gear and the clutch slip worked
out from engine speed against road speed, the speeds themselves, the pedal, the
coolant, and time. The result is a ranked set of leads, not a set of answers.
"""

from __future__ import annotations

from bisect import bisect_left
from math import sqrt

from . import analysis

_MIN_PAIRS = 8  # readings needed before a likeness is worth stating
_REFERENCES = [
    ("gear", "the gear"),
    ("slip", "clutch slip"),
    ("rpm", "engine speed"),
    ("speed", "road speed"),
    ("shaft", "the speed of the shaft in use"),
    ("effort", "the pedal"),
    ("coolant", "coolant temperature"),
    ("time", "time"),
]


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    count = len(xs)
    if count < _MIN_PAIRS:
        return None
    mean_x, mean_y = sum(xs) / count, sum(ys) / count
    spread_x = sum((x - mean_x) ** 2 for x in xs)
    spread_y = sum((y - mean_y) ** 2 for y in ys)
    if spread_x == 0 or spread_y == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / sqrt(spread_x * spread_y)


class _Known:
    """What was known at each moment of the run, from the standard values read beside it."""

    def __init__(self, context: list[tuple[float, dict[str, float]]], gears: list[dict]) -> None:
        self._times = [t for t, _ in context]
        ratios = [gear["ratio"] for gear in gears]
        self._rows = []
        for t, values in context:
            rpm, speed = values.get(analysis.RPM), values.get(analysis.SPEED)
            gear, _ = analysis._assign(values, gears)
            self._rows.append(
                {
                    "gear": None if gear is None else gear + 1,
                    "slip": None if gear is None else rpm - speed * ratios[gear],
                    "shaft": None if gear is None else speed * ratios[gear],
                    "rpm": rpm,
                    "speed": speed,
                    "effort": analysis._effort(values),
                    "coolant": values.get(analysis.COOLANT),
                    "time": t,
                }
            )

    def at(self, t: float) -> dict:
        """The nearest pass in time; a reading is never more than a pass away from one."""
        if not self._rows:
            return {"time": t}
        index = bisect_left(self._times, t)
        if index >= len(self._times) or (index and t - self._times[index - 1] <= self._times[index] - t):
            index -= 1
        return self._rows[max(0, index)]


def _guess(kind_bytes: int, likeness: dict[str, float], gear_match: float | None, rising: float | None, distinct: int) -> str:
    def near(name: str, least: float) -> bool:
        return abs(likeness.get(name, 0.0)) >= least

    if kind_bytes == 1 and gear_match is not None and gear_match >= 0.85:
        return f"Equals the gear worked out from the ratio in {gear_match * 100:.0f} % of readings: likely the gear in use"
    if near("slip", 0.8):
        return "Rises and falls with clutch slip"
    if near("shaft", 0.95) and abs(likeness.get("shaft", 0)) > abs(likeness.get("rpm", 0)):
        return "Follows the speed of the shaft in use more closely than engine speed: likely an input shaft speed"
    if near("gear", 0.8):
        return "Steps with the gear"
    if near("rpm", 0.9):
        return "Follows engine speed"
    if near("speed", 0.9):
        return "Follows road speed"
    if near("effort", 0.8):
        return "Follows the pedal"
    if near("coolant", 0.8):
        return "Follows coolant temperature"
    if rising is not None and abs(rising) >= 0.8 and distinct >= 4:
        return ("Climbs" if rising > 0 else "Falls") + " steadily through the run: a temperature, a counter or a clock"
    return "Changes, but not with anything measured here"


def rank(
    samples: dict[int, list[tuple[float, bytes]]], context: list[tuple[float, dict[str, float]]], gears: list[dict]
) -> dict:
    """Every identifier of a run, with the readings of its bytes that move and what each moves with."""
    known = _Known(context, gears)
    moving, still = [], []
    for identifier, readings in sorted(samples.items()):
        width = min(len(data) for _, data in readings)
        rows = [known.at(t) for t, _ in readings]
        entry = {
            "id": f"{identifier:04X}", "bytes": width, "readings": len(readings),
            "last": readings[-1][1].hex().upper(), "first": readings[0][1].hex().upper(),
        }
        varies = [len({data[position] for _, data in readings}) > 1 for position in range(min(width, 16))]
        if not any(varies):
            still.append(entry)
            continue
        tries = [(position, 1, False) for position, moves in enumerate(varies) if moves]
        # A pair is only worth reading as one number when its first byte moves; otherwise it is the second byte again.
        for position in range(len(varies) - 1):
            if varies[position]:
                tries += [(position, 2, False), (position, 2, True)]
        readings_of = []
        for position, size, signed in tries:
            numbers = [int.from_bytes(data[position : position + size], "big", signed=signed) for _, data in readings]
            likeness = {}
            for name, _ in _REFERENCES:
                pairs = [(number, row[name]) for number, row in zip(numbers, rows) if row.get(name) is not None]
                r = _pearson([a for a, _ in pairs], [b for _, b in pairs])
                if r is not None:
                    likeness[name] = round(r, 2)
            in_gear = [(number, row["gear"]) for number, row in zip(numbers, rows) if row.get("gear") is not None]
            gear_match = (
                sum(1 for number, gear in in_gear if number == gear) / len(in_gear)
                if size == 1 and len(in_gear) >= _MIN_PAIRS else None
            )
            rising = likeness.pop("time", None)
            score = max([abs(r) for r in likeness.values()] + [gear_match or 0.0, abs(rising or 0.0) * 0.9])
            readings_of.append(
                {
                    "start": position, "size": size, "signed": signed, "low": min(numbers), "high": max(numbers),
                    "distinct": len(set(numbers)),
                    "moves_with": [
                        {"what": label, "likeness": likeness[name]}
                        for name, label in _REFERENCES
                        if name in likeness and abs(likeness[name]) >= 0.5
                    ],
                    "gear_match": None if gear_match is None else round(gear_match, 2),
                    "guess": _guess(size, likeness, gear_match, rising, len(set(numbers))),
                    "score": round(score, 2),
                }
            )
        # Signed and unsigned readings of the same bytes agree unless the number goes negative; keep one.
        best: dict[tuple[int, int], dict] = {}
        for reading in readings_of:
            spot = (reading["start"], reading["size"])
            if spot not in best or reading["score"] > best[spot]["score"]:
                best[spot] = reading
        entry["readings_of"] = sorted(best.values(), key=lambda reading: -reading["score"])[:3]
        entry["score"] = entry["readings_of"][0]["score"]
        moving.append(entry)
    moving.sort(key=lambda entry: -entry["score"])
    return {"moving": moving, "still": still, "gears_known": bool(gears), "passes": len(context)}
