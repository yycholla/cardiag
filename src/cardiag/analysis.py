"""Figures for the Diagnosis and Drive pages, worked out from recorded or live passes.

A pass is `(seconds, {signal key: value})`: one sweep over the watched values.
Everything here is a pure function of passes, so the same code serves the live
view, a recording, and the tests. Standard OBD-II reports no gear and no clutch
state; the drive figures are inferred from engine speed against road speed.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Iterable

Pass = tuple[float, dict[str, float]]

RPM, SPEED, LOAD, COOLANT = "01:0C", "01:0D", "01:04", "01:05"
STFT, LTFT, MAP, TIMING, IAT, MAF = "01:06", "01:07", "01:0B", "01:0E", "01:0F", "01:10"
THROTTLE, OIL, MODULE_VOLTS, PEDAL = "01:11", "01:5C", "01:42", "01:49"
ADAPTER_VOLTS = "adapter:voltage"
# What this gearbox calls the slip of its two clutches, where it has been set up to report them (see maker.py).
CLUTCH_A = "22:7E9:1EBB"
CLUTCH_B = "22:7E9:1EBC"

RPM_EDGES = [0, 1000, 1500, 2000, 2500, 3000, 4000, 7000]
LOAD_EDGES = [0, 20, 35, 50, 65, 80, 101]
AIR_FLOW_BAND = (70.0, 95.0)  # percent of displaced air; a general guide, not a Ford figure
TRIM_LIMIT = 10.0  # percent of correction beyond which fuel trim is worth a look
_GAS_CONSTANT_AIR = 287.05  # J/(kg K)
_PETROL_AIR_FUEL = 14.7
_PETROL_GRAMS_PER_LITRE = 745.0
_MIN_GEAR_SPEED = 8.0  # km/h; below this, whole-number speeds make the ratio too coarse
_MAX_SLIP = 15.0  # percent above a gear line still counted as that gear
_SHIFT_WINDOW = 5.0  # seconds a change of gear may take and still be one shift
_PULL_SPANS = [(0, 30), (30, 50), (50, 80), (80, 110)]


def _missing(*names: str) -> dict:
    return {"available": False, "needs": list(names)}


def _has(passes: list[Pass], key: str) -> bool:
    return any(key in values for _, values in passes)


def _dwell(passes: list[Pass]) -> list[float]:
    """Seconds each pass stands for: the time to the next one, with long gaps cut short."""
    if len(passes) < 2:
        return [0.0] * len(passes)
    gaps = [min(2.0, max(0.0, later[0] - earlier[0])) for earlier, later in zip(passes, passes[1:])]
    return gaps + [median(gaps)]


def _thin(points: list, limit: int = 160) -> list:
    if len(points) <= limit:
        return points
    step = len(points) / limit
    picked = [points[int(i * step)] for i in range(limit - 1)]
    return picked + [points[-1]]


def _bin(edges: list[float], value: float) -> int | None:
    for index in range(len(edges) - 1):
        if edges[index] <= value < edges[index + 1]:
            return index
    return None


def _round(value: float, places: int = 2) -> float:
    return round(value, places)


# ---- diagnosis ---------------------------------------------------------------


def trim_map(passes: list[Pass]) -> dict:
    """Mean fuel correction (short-term plus long-term, bank 1) by engine speed and load."""
    if not (_has(passes, RPM) and _has(passes, LOAD)):
        return _missing("Engine speed", "Engine load")
    if not (_has(passes, STFT) or _has(passes, LTFT)):
        return _missing("Fuel trim, bank 1")
    rows = len(LOAD_EDGES) - 1
    columns = len(RPM_EDGES) - 1
    total = [[0.0] * columns for _ in range(rows)]
    seconds = [[0.0] * columns for _ in range(rows)]
    for (_, values), dwell in zip(passes, _dwell(passes)):
        if RPM not in values or LOAD not in values or not (STFT in values or LTFT in values):
            continue
        column, row = _bin(RPM_EDGES, values[RPM]), _bin(LOAD_EDGES, values[LOAD])
        if column is None or row is None or dwell <= 0:
            continue
        total[row][column] += (values.get(STFT, 0.0) + values.get(LTFT, 0.0)) * dwell
        seconds[row][column] += dwell
    cells = [
        [
            {"mean": _round(total[r][c] / seconds[r][c]), "seconds": _round(seconds[r][c], 1)} if seconds[r][c] else None
            for c in range(columns)
        ]
        for r in reversed(range(rows))  # highest load first, the way a map is read
    ]
    visited = [cell for row in cells for cell in row if cell]
    return {
        "available": True,
        "rpm_edges": RPM_EDGES,
        "load_edges": LOAD_EDGES,
        "cells": cells,
        "visited": len(visited),
        "beyond": sum(1 for cell in visited if abs(cell["mean"]) >= TRIM_LIMIT),
        "limit": TRIM_LIMIT,
    }


def air_share(rpm: float, map_kpa: float, maf: float, litres: float, intake_c: float = 20.0) -> float:
    """Measured air flow as a percentage of what the engine displaces at this speed and pressure."""
    density = map_kpa * 1000 / (_GAS_CONSTANT_AIR * (intake_c + 273.15))  # kg per cubic metre in the manifold
    displaced = (litres / 1000) * (rpm / 120) * density * 1000  # grams per second, four-stroke
    return 100 * maf / displaced


def air_flow(passes: list[Pass], litres: float | None) -> dict:
    if not (_has(passes, RPM) and _has(passes, MAP) and _has(passes, MAF)):
        return _missing("Engine speed", "Intake manifold pressure", "Mass air flow")
    if not litres:
        return {"available": False, "needs": ["Engine size, entered in Setup"]}
    series = [
        (t, air_share(v[RPM], v[MAP], v[MAF], litres, v.get(IAT, 20.0)))
        for t, v in passes
        if RPM in v and MAP in v and MAF in v and v[RPM] > 400 and v[MAP] > 5
    ]
    if not series:
        return _missing("A running engine")
    shares = [share for _, share in series]
    return {
        "available": True,
        "litres": litres,
        "now": _round(shares[-1], 1),
        "low": _round(min(shares), 1),
        "high": _round(max(shares), 1),
        "mean": _round(sum(shares) / len(shares), 1),
        "band": list(AIR_FLOW_BAND),
        "series": [[_round(t - passes[0][0], 1), _round(share, 1)] for t, share in _thin(series)],
    }


def warm_up(passes: list[Pass]) -> dict:
    if not _has(passes, COOLANT):
        return _missing("Coolant temperature")

    def reached(key: str) -> float | None:
        found = next((t - passes[0][0] for t, v in passes if v.get(key, -math.inf) >= 80), None)
        return None if found is None else _round(found, 1)

    def curve(key: str) -> list:
        return [[_round(t - passes[0][0], 1), v[key]] for t, v in _thin([p for p in passes if key in p[1]])]

    coolant = curve(COOLANT)
    return {
        "available": True,
        "seconds": _round(passes[-1][0] - passes[0][0], 1),
        "coolant": coolant,
        "oil": curve(OIL),
        "began_warm": coolant[0][1] >= 70,
        "coolant_at_80": reached(COOLANT),
        "oil_at_80": reached(OIL) if _has(passes, OIL) else None,
    }


def speed_bands(passes: list[Pass]) -> dict:
    if not _has(passes, RPM):
        return _missing("Engine speed")
    seconds = [0.0] * (len(RPM_EDGES) - 1)
    still = moving = 0.0
    for (_, values), dwell in zip(passes, _dwell(passes)):
        column = _bin(RPM_EDGES, values[RPM]) if RPM in values else None
        if column is not None:
            seconds[column] += dwell
        if SPEED in values:
            if values[SPEED] < 1:
                still += dwell
            else:
                moving += dwell
    total = sum(seconds) or 1.0
    return {
        "available": True,
        "rpm_edges": RPM_EDGES,
        "share": [_round(100 * s / total, 1) for s in seconds],
        "stationary": _round(100 * still / (still + moving), 1) if still + moving else None,
    }


def fuel_used(passes: list[Pass], fuel: str | None = "petrol") -> dict:
    """An estimate from mass air flow, assuming the engine runs at 14.7 parts air to one of petrol."""
    if not (_has(passes, MAF) and _has(passes, SPEED)):
        return _missing("Mass air flow", "Vehicle speed")
    if fuel not in (None, "petrol"):
        return {"available": False, "needs": ["A petrol engine; this estimate does not hold for other fuels"]}
    grams = km = 0.0
    rate = None
    for (_, values), dwell in zip(passes, _dwell(passes)):
        if MAF in values:
            grams += values[MAF] / _PETROL_AIR_FUEL * dwell
            rate = values[MAF] / _PETROL_AIR_FUEL / _PETROL_GRAMS_PER_LITRE * 3600
        km += values.get(SPEED, 0.0) / 3600 * dwell
    litres = grams / _PETROL_GRAMS_PER_LITRE
    return {
        "available": True,
        "litres": _round(litres, 3),
        "km": _round(km, 2),
        "per_100_km": _round(litres / km * 100, 1) if km >= 0.2 else None,
        "litres_per_hour": _round(rate, 2) if rate is not None else None,
    }


def _idle(passes: list[Pass]) -> list[tuple[float, dict[str, float]]]:
    """The most recent stretch of idling: stopped, engine turning slowly, foot off."""
    found: list[tuple[float, dict[str, float]]] = []
    for t, values in reversed(passes):
        idling = 400 < values.get(RPM, 0) < 1200 and values.get(SPEED, 0) < 1 and values.get(THROTTLE, 0) < 25
        if idling:
            found.append((t, values))
            if len(found) >= 480:
                break
        elif found:
            break
    return found[::-1]


def _mean(rows: Iterable[dict[str, float]], key: str) -> float | None:
    values = [row[key] for row in rows if key in row]
    return sum(values) / len(values) if values else None


def idle_summary(passes: list[Pass]) -> dict:
    """What a parked, idling engine is doing: the figures a baseline is made of."""
    idle = _idle(passes)
    rows = [values for _, values in idle]
    recent = [values for _, values in passes[-240:]]
    running = [values for values in recent if values.get(RPM, 0) > 400]
    summary = {
        "idle_seconds": idle[-1][0] - idle[0][0] if idle else 0.0,
        "idle_rpm": _mean(rows, RPM),
        "idle_map": _mean(rows, MAP),
        "idle_maf": _mean(rows, MAF),
        "coolant": passes[-1][1].get(COOLANT) if passes else None,
        "stft": _mean(recent, STFT),
        "ltft": passes[-1][1].get(LTFT) if passes else None,
        "module_volts": _mean(running, MODULE_VOLTS),
        "adapter_volts": _mean(running, ADAPTER_VOLTS),
    }
    return {key: (_round(value) if isinstance(value, float) else value) for key, value in summary.items()}


# (summary key, name, when it is measured, unit, band low, band high, scale low, scale high, baseline tolerance)
_HEALTHY = [
    ("idle_rpm", "Idle speed", "warm, last idle", "rpm", 600, 900, 400, 1200, 75),
    ("idle_map", "Manifold pressure at idle", "last idle, near sea level", "kPa", 25, 45, 10, 70, 5),
    ("idle_maf", "Mass air flow at idle", "last idle", "g/s", 2, 5, 0, 8, 0.8),
    ("coolant", "Coolant temperature", "engine warm", "°C", 85, 105, 60, 120, None),
    ("stft", "Short-term fuel trim", "mean of the last minute", "%", -TRIM_LIMIT, TRIM_LIMIT, -25, 25, None),
    ("ltft", "Long-term fuel trim", "now", "%", -TRIM_LIMIT, TRIM_LIMIT, -25, 25, None),
    ("module_volts", "Control module voltage", "engine running", "V", 13.2, 14.8, 11, 16, None),
    ("adapter_volts", "Battery voltage at the port", "engine running", "V", 13.2, 14.8, 11, 16, None),
]


def healthy(passes: list[Pass], baseline: dict | None = None) -> dict:
    """Each figure against a band: this car's own baseline where there is one, else a general guide."""
    summary = idle_summary(passes)
    warm = summary["coolant"] is None or summary["coolant"] >= 70
    rows = []
    for key, name, when, unit, low, high, scale_low, scale_high, tolerance in _HEALTHY:
        value = summary.get(key)
        if value is None:
            continue
        if key == "coolant" and not warm:
            continue  # a cold engine is not out of band, just not there yet
        source = "general"
        if baseline and tolerance is not None and baseline.get(key) is not None:
            low, high, source = baseline[key] - tolerance, baseline[key] + tolerance, "baseline"
        result = "below" if value < low else "above" if value > high else "inside"
        rows.append(
            {"key": key, "name": name, "when": when, "unit": unit, "value": value, "low": _round(low),
             "high": _round(high), "scale": [scale_low, scale_high], "result": result, "source": source}
        )
    return {"available": bool(rows), "needs": ["A running engine"], "warm": warm, "rows": rows,
            "outside": sum(1 for row in rows if row["result"] != "inside")}


def compare(passes: list[Pass], other: list[Pass], signals: dict[str, dict]) -> list[dict]:
    """Mean and peak of every value the two sets of passes share."""
    rows = []
    for key, signal in signals.items():
        mine = [v[key] for _, v in passes if key in v]
        theirs = [v[key] for _, v in other if key in v]
        if not mine or not theirs:
            continue
        mean, other_mean = sum(mine) / len(mine), sum(theirs) / len(theirs)
        rows.append(
            {"key": key, "name": signal["name"], "unit": signal["unit"], "mean": _round(mean), "other_mean": _round(other_mean),
             "change": _round(mean - other_mean), "max": _round(max(mine)), "other_max": _round(max(theirs))}
        )
    return rows


# ---- drive: gears, shifts, slip ----------------------------------------------


def _effort(values: dict[str, float]) -> float | None:
    """How hard the engine is being asked to work, from the best signal on offer."""
    for key in (PEDAL, THROTTLE, LOAD):
        if key in values:
            return values[key]
    return None


def _steady(series: Iterable[tuple[float, float | None, float]]) -> list[tuple[float, float]]:
    """Stretches where a ratio held still, as (ratio, seconds). `series` is (time, ratio or None, km/h)."""
    runs: list[tuple[float, float]] = []
    current: list[tuple[float, float]] = []  # (time, ratio)

    def close() -> None:
        if len(current) >= 3 and current[-1][0] - current[0][0] >= 1.5:
            runs.append((median(r for _, r in current), current[-1][0] - current[0][0]))
        current.clear()

    for t, ratio, speed in series:
        if ratio is None:
            close()
            continue
        if current:
            centre = sum(r for _, r in current) / len(current)
            # Speed arrives in whole km/h, so at low speed the ratio wobbles without the gear changing.
            if abs(ratio - centre) / centre > max(0.03, _tolerance(speed) / 100) or t - current[-1][0] > 2.0:
                close()
        current.append((t, ratio))
    close()
    return runs


def _clusters(runs: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Steady stretches gathered into gears, as (ratio, seconds), highest ratio first."""
    clusters: list[list[tuple[float, float]]] = []
    for ratio, seconds in sorted(runs, reverse=True):
        if clusters:
            weight = sum(s for _, s in clusters[-1])
            centre = sum(r * s for r, s in clusters[-1]) / weight
            if abs(ratio - centre) / centre < 0.06:
                clusters[-1].append((ratio, seconds))
                continue
        clusters.append([(ratio, seconds)])
    found = []
    for cluster in clusters:
        seconds = sum(s for _, s in cluster)
        if seconds >= 3.0:
            found.append((sum(r * s for r, s in cluster) / seconds, seconds))
    return found


def _carrying(values: dict[str, float]) -> tuple[str, float] | None:
    """Which clutch is passing the drive, and its slip in rpm, when the gearbox reports both clutches.

    The clutch nearer to turning with the engine is the one in use. When neither is
    within 15 % of engine speed the car is pulling away or between gears.
    """
    rpm, a, b = values.get(RPM), values.get(CLUTCH_A), values.get(CLUTCH_B)
    if rpm is None or a is None or b is None or rpm < 300:
        return None
    name, slip = ("A", a) if abs(a) <= abs(b) else ("B", b)
    return (name, slip) if abs(slip) <= 0.15 * rpm else None


def _shaft(values: dict[str, float], clutch: str) -> float | None:
    """Rpm per km/h of one clutch's shaft: engine speed less that clutch's slip, over road speed."""
    rpm, speed, slip = values.get(RPM), values.get(SPEED), values.get(CLUTCH_A if clutch == "A" else CLUTCH_B)
    if rpm is None or speed is None or slip is None or speed < _MIN_GEAR_SPEED:
        return None
    return (rpm - slip) / speed


def _learn_from_clutches(passes: list[Pass]) -> list[dict]:
    """The gears, from the shaft speed of whichever clutch is carrying the drive.

    Shaft speed already leaves the slip out, so every moment in gear counts, gentle or
    hard, and each gear is known to belong to one clutch. That is why this needs no
    steady stretches: readings are gathered by ratio, and a gear is wherever enough of
    them agree.
    """
    gears = []
    spent = _dwell(passes)
    step = math.log(1.02)
    for clutch in ("A", "B"):
        seen: list[tuple[int, float, float]] = []  # (which 2 % band the ratio falls in, ratio, seconds)
        before: float | None = None
        for (_, values), seconds in zip(passes, spent):
            carrying = _carrying(values)
            ratio = _shaft(values, clutch) if carrying and carrying[0] == clutch else None
            ratio = ratio if ratio and ratio > 0 else None
            # The values of one pass are read a moment apart, so while the car is gaining or losing
            # speed quickly the ratio is off. Two readings in a row that agree are not.
            if ratio and before and abs(ratio / before - 1) < 0.06:
                seen.append((round(math.log(ratio) / step), ratio, min(seconds, 2.0)))
            before = ratio
        while seen:
            weight: dict[int, float] = {}
            for band, _, seconds in seen:
                for near in range(band - 3, band + 4):
                    weight[near] = weight.get(near, 0.0) + seconds
            centre = max(weight, key=lambda band: weight[band])
            members = sorted((ratio, seconds) for band, ratio, seconds in seen if abs(band - centre) <= 3)
            if len(members) < 4 or weight[centre] < 3.0:
                break
            gears.append({"ratio": _round(members[len(members) // 2][0]), "seconds": _round(weight[centre], 1), "clutch": clutch})
            seen = [item for item in seen if abs(item[0] - centre) > 8]  # nothing within 17 % is another gear of this clutch
    gears.sort(key=lambda gear: -gear["ratio"])
    if gears:
        # First gear is held for moments, while pulling away, and rarely steadily enough to be found
        # above. A clutch seen driving well above the highest gear found is first gear all the same.
        top = gears[0]
        other = "B" if top["clutch"] == "A" else "A"
        above = sorted(
            ratio for _, values in passes
            if (carrying := _carrying(values)) and carrying[0] == other
            and (ratio := _shaft(values, other)) and 1.3 * top["ratio"] < ratio < 4 * top["ratio"]
        )
        if len(above) >= 5:
            gears.insert(0, {"ratio": _round(above[len(above) // 2]), "seconds": 0.0, "clutch": other, "rough": True})
    return gears


def learn_gears(passes: list[Pass]) -> list[dict]:
    """Find the gears as steady engine-speed-to-road-speed ratios, highest ratio (first gear) first.

    Where the gearbox reports the slip of its two clutches, the gears come from those: see
    `_learn_from_clutches`. Otherwise only light-effort stretches count, because a clutch
    that slips under load would otherwise be learned as a gear of its own.
    """
    if _has(passes, CLUTCH_A) and _has(passes, CLUTCH_B):
        gears = _learn_from_clutches(passes)
        if len(gears) >= 2:
            return gears
    series = []
    for t, values in passes:
        speed, rpm, effort = values.get(SPEED), values.get(RPM), _effort(values)
        light = effort is None or effort < (35 if PEDAL in values or THROTTLE in values else 50)
        steady = speed is not None and rpm is not None and speed >= _MIN_GEAR_SPEED and rpm >= 500 and light
        series.append((t, rpm / speed if steady else None, speed or 1.0))
    return [{"ratio": _round(ratio), "seconds": _round(seconds, 1)} for ratio, seconds in _clusters(_steady(series))]


def _tolerance(speed: float) -> float:
    """Percent of ratio error to expect from the car reporting speed in whole km/h."""
    return 2.0 + 60.0 / speed


def _by_clutch(gears: list[dict]) -> bool:
    """Whether these gears were learned with the clutch each belongs to."""
    return bool(gears) and all(gear.get("clutch") for gear in gears)


def _assign(values: dict[str, float], gears: list[dict]) -> tuple[int | None, float]:
    """Which gear a pass is in (index into gears), and the percent the engine turns faster than that gear accounts for."""
    speed, rpm = values.get(SPEED), values.get(RPM)
    if speed is None or rpm is None or speed < _MIN_GEAR_SPEED or not gears:
        return None, 0.0
    if _by_clutch(gears) and CLUTCH_A in values and CLUTCH_B in values:
        carrying = _carrying(values)
        if carrying is None:
            return None, 0.0
        clutch, slip = carrying
        shaft = (rpm - slip) / speed
        own = [index for index, gear in enumerate(gears) if gear["clutch"] == clutch]
        if not own or shaft <= 0:
            return None, 0.0
        gear = min(own, key=lambda index: abs(math.log(shaft / gears[index]["ratio"])))
        if abs(shaft / gears[gear]["ratio"] - 1) * 100 > _tolerance(speed) + 4:
            return None, 0.0
        return gear, slip / (rpm - slip) * 100
    ratio = rpm / speed
    gear = min(range(len(gears)), key=lambda index: abs(math.log(ratio / gears[index]["ratio"])))
    slip = (ratio / gears[gear]["ratio"] - 1) * 100
    if slip > _MAX_SLIP or slip < -(_tolerance(speed) + 2):
        return None, 0.0
    return gear, slip


def gear_now(values: dict[str, float], gears: list[dict]) -> tuple[int | None, float | None]:
    """The gear one pass is in, counted from 1, and the percent it sits above that gear's line."""
    gear, slip = _assign(values, gears)
    return (None, None) if gear is None else (gear + 1, _round(slip, 1))


def _working(values: dict[str, float]) -> bool:
    """Whether the engine is pulling hard enough for a weak clutch to show."""
    if LOAD in values:
        return values[LOAD] >= 60
    effort = _effort(values)
    return effort is not None and effort >= 40


def _slip_rpm(values: dict[str, float], gear: dict) -> float | None:
    """Slip of the clutch this gear belongs to, in rpm, where the gearbox reports it."""
    key = {"A": CLUTCH_A, "B": CLUTCH_B}.get(gear.get("clutch") or "")
    return values.get(key) if key else None


def _middle(numbers: list[float]) -> float | None:
    return _round(median(numbers), 0) if numbers else None


def clutch_report(moving: list[Pass], assigned: list[tuple[int | None, float]], gears: list[dict], dwell: list[float], start: float) -> dict:
    """What the gearbox's own clutch figures show: slip against load and engine speed, and the gear waiting on the idle shaft."""
    if not (_by_clutch(gears) and _has(moving, CLUTCH_A) and _has(moving, CLUTCH_B)):
        return {"available": False}
    by_gear = []
    for number, gear in enumerate(gears):
        light, hard, seconds = [], [], 0.0
        for (index, _), (_, values), spent in zip(assigned, moving, dwell):
            slip = _slip_rpm(values, gear)
            if index != number or slip is None or LOAD not in values:
                continue
            if values[LOAD] >= 60:
                hard.append(slip)
                seconds += spent
            elif values[LOAD] < 40:
                light.append(slip)
        by_gear.append({"gear": number + 1, "clutch": gear["clutch"], "light": _middle(light), "working": _middle(hard),
                        "peak": _round(max(hard), 0) if hard else None, "seconds": _round(seconds, 1)})
    by_rpm = []
    for low, high in zip(RPM_EDGES[1:], RPM_EDGES[2:]):
        slips = [
            slip for (index, _), (_, values) in zip(assigned, moving)
            if index is not None and values.get(LOAD, 0) >= 60 and low <= values[RPM] < high
            and (slip := _slip_rpm(values, gears[index])) is not None
        ]
        if len(slips) >= 3:
            by_rpm.append({"from": low, "to": high, "median": _middle(slips), "over": _round(sum(s > 50 for s in slips) / len(slips), 2), "passes": len(slips)})

    # Each shaft holds one of its own gears, in use or ready for the next shift. A change of
    # that gear should be quick; a shaft that sits between gears is one that is not engaging.
    changes = []
    for clutch in ("A", "B"):
        own = [n for n, gear in enumerate(gears) if gear["clutch"] == clutch]
        last: tuple[float, int] | None = None  # when this shaft was last seen in a gear, and which
        for t, values in moving:
            shaft = _shaft(values, clutch)
            if shaft is None or not own:
                last = None  # too slow to tell: whatever happens here is not timed
                continue
            if shaft <= 0:
                continue
            near = min(own, key=lambda n: abs(math.log(shaft / gears[n]["ratio"])))
            if abs(shaft / gears[near]["ratio"] - 1) * 100 > _tolerance(values[SPEED]) + 4:
                continue
            if last is not None and near + 1 != last[1]:
                changes.append({"at": _round(last[0] - start, 1), "clutch": clutch, "from": last[1], "to": near + 1, "took": _round(t - last[0], 1)})
            last = (t, near + 1)
    changes.sort(key=lambda change: change["at"])
    typical = median(dwell) if dwell else 0.25
    for change in changes:
        change["slow"] = change["took"] > max(2.0, 4 * typical)
    return {"available": True, "by_gear": by_gear, "by_rpm": by_rpm, "changes": changes,
            "slow_changes": sum(change["slow"] for change in changes)}


def drive_report(passes: list[Pass], gears: list[dict]) -> dict:
    """Gear by gear: where the engine sat against each gear line, every shift, and slip under load."""
    if not (_has(passes, RPM) and _has(passes, SPEED)):
        return _missing("Engine speed", "Vehicle speed")
    moving = [(t, v) for t, v in passes if RPM in v and SPEED in v]
    points = [[v[SPEED], v[RPM], 2] for _, v in moving]
    start = passes[0][0]
    clutched = _by_clutch(gears) and _has(moving, CLUTCH_A) and _has(moving, CLUTCH_B)
    report = {
        "available": True,
        "gears": gears,
        "learned": bool(gears),
        "by_clutch": clutched,
        "top_speed": max((v[SPEED] for _, v in moving), default=0),
        "top_rpm": max((v[RPM] for _, v in moving), default=0),
        "rpm": [[_round(t - start, 1), v[RPM]] for t, v in _thin(moving, 240)],
        "seconds": _round(passes[-1][0] - start, 1),
        "points": _thin(points, 500),
        "timeline": [],
        "shifts": [],
        "slip": [],
        "clutches": {"available": False},
        "coarse": False,
        "rate": None,
    }
    if not gears:
        return report

    ratios = [gear["ratio"] for gear in gears]
    assigned = [_assign(v, gears) for _, v in moving]
    dwell = _dwell(moving)
    for point, (gear, slip), (_, values) in zip(points, assigned, moving):
        if gear is not None:
            point[2] = 1 if slip > _tolerance(values[SPEED]) + 1 else 0
    report["points"] = _thin(points, 500)

    timeline: list[dict] = []
    for (t, _), (gear, _), seconds in zip(moving, assigned, dwell):
        if gear is None:
            continue
        if timeline and timeline[-1]["gear"] == gear + 1 and t - start - timeline[-1]["to"] < 2.5:
            timeline[-1]["to"] = _round(t - start + seconds, 1)
        else:
            timeline.append({"gear": gear + 1, "from": _round(t - start, 1), "to": _round(t - start + seconds, 1)})
    report["timeline"] = timeline

    typical = median(dwell) if dwell else 0.25
    shifts = []
    last: int | None = None  # index of the latest pass sitting cleanly in a gear
    disturbed = False  # whether anything but a clean pass in that gear has been seen since
    run: int | None = None  # where the present unbroken run of clean passes in one gear began
    for index, (gear, slip) in enumerate(assigned):
        if gear is None:
            disturbed, run = True, None
            continue
        allowed = _tolerance(moving[index][1][SPEED]) + 1
        locked = slip <= allowed and (not clutched or slip >= -allowed)
        if not locked:
            run = None
        elif run is None or assigned[run][0] != gear:
            run = index
        if last is not None and assigned[last][0] != gear:
            began, ended = moving[last], moving[index]
            took = ended[0] - began[0]
            if took <= _SHIFT_WINDOW:
                was = assigned[last][0]
                up = gear > was
                peak = max(v[RPM] for _, v in moving[last : index + 1])
                flare = peak - began[1][RPM] if up else 0.0
                flare = flare if flare >= 75 else 0.0
                slow = took > max(1.5, 3 * typical)
                found = {"flare": flare, "slow": slow}
                shift = {"from": was + 1, "to": gear + 1, "at": _round(began[0] - start, 1), "rpm": round(began[1][RPM]),
                         "speed": round(began[1][SPEED]), "effort": _effort(began[1]), "took": _round(took, 1),
                         "flare": round(flare), "index": [last, index]}
                if clutched:
                    # Both clutches open at once is the engine driving nothing; the new one still
                    # slipping after it has taken over is a gear that has not bitten.
                    between = moving[last + 1 : index]
                    gap = max((min(v[CLUTCH_A], v[CLUTCH_B]) for _, v in between if CLUTCH_A in v and CLUTCH_B in v), default=0.0)
                    gap = max(0.0, gap)  # the engine turning faster than both shafts: neither clutch holding it
                    after = [
                        abs(slip_rpm) for (t, v), (now, _) in zip(moving[index + 1 : index + 9], assigned[index + 1 : index + 9])
                        if now == gear and t - ended[0] <= 3.0 and (slip_rpm := _slip_rpm(v, gears[gear])) is not None
                    ]
                    settle = max(after, default=0.0)
                    shift.update(gap=round(gap), after=round(settle))
                    found["neither clutch holding"] = gap >= 300
                    found["slipping in"] = settle >= 250
                shift["result"] = " and ".join(word for word, on in found.items() if on) or "clean"
                shifts.append(shift)
            last, disturbed = (index if locked else None), False
        elif last is None:
            last, disturbed = index, not locked
        elif not locked:
            disturbed = True
        elif not (clutched and disturbed):
            last = index
        elif run is not None and index > run and moving[index][0] - moving[run][0] >= 0.5:
            # With the clutch figures, an engine falling back through the old shaft's speed on its way to
            # the next gear reads as locked for a moment. Only a run that lasts is the gear holding again.
            last, disturbed = index, False
    for shift in shifts:
        first, final = shift.pop("index")
        lo, hi = max(0, first - 12), min(len(moving), final + 13)
        was, now = ratios[shift["from"] - 1], ratios[shift["to"] - 1]
        shift["trace"] = [
            [_round(t - start, 1), v[RPM], round(v[SPEED] * (was if position + lo <= first else now)),
             *([v.get(CLUTCH_A), v.get(CLUTCH_B)] if clutched else [])]
            for position, (t, v) in enumerate(moving[lo:hi])
        ]
    report["shifts"] = shifts
    # Below about three readings a second a shift is one or two readings long, and the values
    # of one pass are read too far apart to compare: the figures above are then rough.
    report["coarse"] = typical > 0.35
    report["rate"] = _round(1 / typical, 1) if typical else None

    for number in range(len(ratios)):
        total = seconds_in = 0.0
        for (gear, slip), (_, values), seconds in zip(assigned, moving, dwell):
            if gear == number and values[SPEED] >= 25 and _working(values):
                total += slip * seconds
                seconds_in += seconds
        report["slip"].append(
            {"gear": number + 1, "seconds": _round(seconds_in, 1),
             "mean": _round(total / seconds_in, 1) if seconds_in >= 2 else None}
        )
    report["clutches"] = clutch_report(moving, assigned, gears, dwell, start)
    return report


def pull_times(passes: list[Pass]) -> dict:
    """The quickest run through each speed span, and how hard the car was being asked to work."""
    if not _has(passes, SPEED):
        return _missing("Vehicle speed")
    spans = []
    for low, high in _PULL_SPANS:
        best = None
        began: float | None = None
        efforts: list[float] = []
        previous: float | None = None
        for t, values in passes:
            speed = values.get(SPEED)
            if speed is None:
                continue
            if speed <= low:
                began, efforts = t, []  # the latest moment at or below the bottom of the span
            elif began is not None:
                effort = _effort(values)
                if effort is not None:
                    efforts.append(effort)
                if previous is not None and speed < previous - 3:
                    began = None  # lifted off: not a pull
                elif speed >= high:
                    took = t - began
                    if best is None or took < best["seconds"]:
                        best = {"seconds": _round(took, 1), "effort": _round(sum(efforts) / len(efforts), 0) if efforts else None}
                    began = None
            previous = speed
        spans.append({"from": low, "to": high, **(best or {"seconds": None, "effort": None})})

    def trace(key: str) -> list:
        return [[_round(t - passes[0][0], 1), v[key]] for t, v in _thin([p for p in passes if key in p[1]], 240)]

    asked = next((key for key in (PEDAL, THROTTLE) if _has(passes, key)), None)
    return {
        "available": True,
        "spans": spans,
        "asked": asked,
        "asked_trace": trace(asked) if asked else [],
        "load_trace": trace(LOAD),
        "speed_trace": trace(SPEED),
        "timing_trace": trace(TIMING),
        "seconds": _round(passes[-1][0] - passes[0][0], 1) if passes else 0,
    }


def maker_traces(passes: list[Pass], signals: dict[str, dict]) -> list[dict]:
    """The maker-specific values in these passes, each as a trace with its range."""
    traces = []
    for key in sorted({key for _, values in passes for key in values if key.startswith("22:")}):
        points = [(t - passes[0][0], values[key]) for t, values in passes if key in values]
        numbers = [value for _, value in points]
        signal = signals.get(key, {"name": key, "unit": ""})
        traces.append(
            {"key": key, "name": signal["name"], "unit": signal["unit"], "low": _round(min(numbers)),
             "high": _round(max(numbers)), "trace": [[_round(t, 1), _round(value)] for t, value in _thin(points, 240)]}
        )
    return traces


def analyse(passes: list[Pass], signals: dict[str, dict], profile: dict, other: list[Pass] | None = None) -> dict:
    """Everything the Diagnosis and Drive pages show for one set of passes."""
    if not passes:
        return {"passes": 0, "seconds": 0}
    gears = profile.get("gears") or []
    baseline = profile.get("baseline") or {}
    report = {
        "passes": len(passes),
        "seconds": _round(passes[-1][0] - passes[0][0], 1),
        "healthy": healthy(passes, baseline.get("values") if baseline.get("good") else None),
        "trim_map": trim_map(passes),
        "air_flow": air_flow(passes, profile.get("engine_litres")),
        "warm_up": warm_up(passes),
        "speed_bands": speed_bands(passes),
        "fuel": fuel_used(passes, profile.get("fuel")),
        "drive": drive_report(passes, gears),
        "pull": pull_times(passes),
        "compare": None,
        "other_pull": None,
        "maker": maker_traces(passes, signals),
    }
    if other:
        report["compare"] = compare(passes, other, signals)
        report["other_pull"] = pull_times(other)
    return report
