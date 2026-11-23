"""What is known about each car, and what its recordings show.

This sits between the web server and three sources: the live connection (the
hub), the recordings (the store), and the arithmetic (analysis). Setup fills in
a profile per VIN: the engine size and transmission the car cannot report, an
idle baseline, and the gear ratios learned from a gentle drive.
"""

from __future__ import annotations

import time

from . import analysis, maker
from .pids import PIDS
from .service import Hub
from .store import Store

# Seconds of unbroken idling a baseline needs. The page asks for a minute; this is the least that is worth keeping.
MIN_IDLE_SECONDS = 8.0

TRANSMISSIONS = ("dual-clutch automatic", "manual", "torque-converter automatic", "cvt")
FUELS = ("petrol", "diesel", "flex fuel")

# Values the Drive and Diagnosis pages lean on: (what, PIDs, whether all are needed, what is lost without them).
WANTED = [
    ("Engine speed and vehicle speed", (0x0C, 0x0D), True, "Required. The gear map and shift detection cannot run."),
    ("Throttle position", (0x11,), True, "Idle detection is less sure, and nothing stands in for the pedal."),
    ("Accelerator pedal position", (0x49, 0x4A), False, "Pulling power compares against throttle position instead."),
    ("Commanded throttle", (0x4C,), True, "Cannot show the engine computer holding the throttle back."),
    ("Driver demand and actual torque", (0x61, 0x62), True, "Cannot show a torque limit directly; engine load is used."),
    ("Ignition timing advance", (0x0E,), True, "Cannot show timing pulled back during shifts or under knock."),
    ("Fuel rail pressure", (0x22, 0x23), False, "Cannot show fuel supply sagging under load."),
    ("Mass air flow and manifold pressure", (0x10, 0x0B), True, "The air flow check and the fuel estimate cannot run."),
    ("Fuel trims, bank 1", (0x06, 0x07), True, "The fuel trim map cannot run."),
    ("Coolant temperature", (0x05,), True, "Warm-up cannot be shown, and a baseline cannot tell a warm engine from a cold one."),
]

# Watched during a drive capture: few values, so each is read more often.
DRIVE_PIDS = (0x0C, 0x0D, 0x49, 0x11, 0x04, 0x0E)


def setup_report(hub: Hub, db_path: str | None) -> dict:
    status = hub.status()
    offered = hub.offered()
    have = {pid for module in offered for pid in module["pids"]}
    passes, _ = hub.history()
    store = Store(db_path)
    try:
        profile = store.profile(status["vin"]) if status["state"] == "connected" else None
    finally:
        store.close()
    return {
        "status": status,
        "offered": [
            {
                "module": module["module"],
                "values": [
                    {"pid": f"{pid:02X}", "name": PIDS[pid].name if pid in PIDS else f"PID {pid:02X}"}
                    for pid in module["pids"]
                ],
            }
            for module in offered
        ],
        "wanted": [
            {
                "name": name,
                "pids": [f"{pid:02X}" for pid in pids],
                "offered": (all if need_all else any)(pid in have for pid in pids),
                "without": without,
            }
            for name, pids, need_all, without in WANTED
        ],
        "drive_pids": [f"{pid:02X}" for pid in DRIVE_PIDS if pid in have],
        "profile": profile,
        "transmissions": list(TRANSMISSIONS),
        "fuels": list(FUELS),
        "idle": analysis.idle_summary(passes) if passes else None,
        "idle_needed": MIN_IDLE_SECONDS,
        "live_seconds": round(passes[-1][0] - passes[0][0], 1) if passes else 0,
    }


def _vin(hub: Hub) -> str | None:
    status = hub.status()
    if status["state"] != "connected":
        raise ValueError("connect to the car first; setup is kept per car")
    return status["vin"]


def save_profile(hub: Hub, db_path: str | None, body: dict) -> dict:
    changes: dict = {}
    if "engine_litres" in body:
        litres = body["engine_litres"]
        if litres in (None, ""):
            changes["engine_litres"] = None
        else:
            try:
                litres = float(litres)
            except (TypeError, ValueError):
                raise ValueError("engine size must be a number of litres, such as 2.0") from None
            if not 0.3 <= litres <= 10:
                raise ValueError("engine size must be between 0.3 and 10 litres")
            changes["engine_litres"] = round(litres, 2)
    if "transmission" in body:
        if body["transmission"] not in (None, *TRANSMISSIONS):
            raise ValueError("transmission must be one of: " + ", ".join(TRANSMISSIONS))
        changes["transmission"] = body["transmission"]
    if "fuel" in body:
        if body["fuel"] not in FUELS:
            raise ValueError("fuel must be one of: " + ", ".join(FUELS))
        changes["fuel"] = body["fuel"]
    if not changes:
        raise ValueError("nothing to save")
    vin = _vin(hub)
    store = Store(db_path)
    try:
        return store.save_profile(vin, changes)
    finally:
        store.close()


def take_baseline(hub: Hub, db_path: str | None, known_good: object) -> dict:
    """Keep the idle figures from the last stretch of idling as this car's own bands."""
    vin = _vin(hub)
    passes, _ = hub.history()
    summary = analysis.idle_summary(passes) if passes else {"idle_seconds": 0.0}
    if summary["idle_seconds"] < MIN_IDLE_SECONDS:
        raise ValueError(
            f"leave the car idling, parked, for a minute first; so far it has idled for {summary['idle_seconds']:.0f} s"
        )
    if summary.get("coolant") is not None and summary["coolant"] < 70:
        raise ValueError(f"the engine is not warm yet (coolant {summary['coolant']:.0f} degrees); try again once it is")
    flags = [
        f"{name} is beyond ±{analysis.TRIM_LIMIT:.0f} %"
        for key, name in (("stft", "short-term fuel trim"), ("ltft", "long-term fuel trim"))
        if summary.get(key) is not None and abs(summary[key]) > analysis.TRIM_LIMIT
    ]
    baseline = {
        "values": {key: value for key, value in summary.items() if key != "idle_seconds" and value is not None},
        "seconds": round(summary["idle_seconds"], 1),
        "flags": flags,
        "good": bool(known_good) and not flags,
        "taken_at": time.time(),
    }
    store = Store(db_path)
    try:
        return store.save_profile(vin, {"baseline": baseline})
    finally:
        store.close()


def maker_report(hub: Hub) -> dict:
    """The maker-specific values set up for the connected car, and what could be added."""
    found = hub.modules()
    values = [value.as_json() for value in hub.maker()]
    have = {value["key"] for value in values}
    answering = {module["reply"] for module in found["modules"]}
    return {
        **found,
        "values": values,
        "candidates": [
            candidate for candidate in maker.CANDIDATES
            if candidate["module"] in answering and f"22:{candidate['module']}:{candidate['id']}" not in have
        ],
        "limit": maker.MAX_VALUES,
    }


def save_maker(hub: Hub, db_path: str | None, body: dict) -> dict:
    values = maker.parse(body.get("values"))
    vin = _vin(hub)
    if values and not hub.modules()["supported"]:
        raise ValueError("maker-specific values can only be read on an 11-bit CAN network so far")
    store = Store(db_path)
    try:
        store.save_profile(vin, {"maker": [value.as_json() for value in values]})
    finally:
        store.close()
    hub.set_maker(values)
    return maker_report(hub)


def scan(hub: Hub, body: dict) -> dict:
    """Ask one module which of a run of identifiers it has. At most 64 at a time, so the page can show progress."""
    module = maker.module_address(body.get("module"))
    first = maker.hex_number(body.get("first"), 4, "the first identifier")
    count = body.get("count", 64)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 64:
        raise ValueError("count must be between 1 and 64")
    count = min(count, 0x10000 - first)
    found = hub.scan(module, first, count)
    return {
        "found": [{"id": f"{identifier:04X}", "data": data.hex().upper()} for identifier, data in found],
        "next": f"{first + count:04X}" if first + count < 0x10000 else None,
    }


def set_interval(hub: Hub, db_path: str | None, seconds: object) -> dict:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 <= seconds <= 10:
        raise ValueError("the time between updates must be between 0 and 10 seconds")
    store = Store(db_path)
    try:
        store.set_setting("interval", repr(float(seconds)))
    finally:
        store.close()
    hub.set_interval(float(seconds))
    return hub.status()


def saved_interval(db_path: str | None) -> float | None:
    """The time between updates chosen on the page, if one was."""
    store = Store(db_path)
    try:
        text = store.setting("interval")
    finally:
        store.close()
    try:
        return float(text) if text is not None else None
    except ValueError:
        return None


def _passes(hub: Hub, store: Store, source: object) -> tuple[list, dict]:
    if source in (None, "", "live"):
        return hub.history()
    try:
        return store.passes(int(source))
    except (TypeError, ValueError):
        raise ValueError("source must be 'live' or the number of a recording") from None
    except KeyError:
        raise ValueError(f"there is no recording {source}") from None


def learn_gears(hub: Hub, db_path: str | None, source: object, clear: bool = False) -> dict:
    """Find the gear ratios in the live drive or a recording, and keep them for this car."""
    vin = _vin(hub)
    store = Store(db_path)
    try:
        if clear:
            return store.save_profile(vin, {"gears": []})
        passes, _ = _passes(hub, store, source)
        gears = analysis.learn_gears(passes)
        if len(gears) < 2:
            raise ValueError("no steady gears found there yet; drive gently and hold each gear for a few seconds")
        return store.save_profile(vin, {"gears": gears})
    finally:
        store.close()


def report(hub: Hub, db_path: str | None, source: object, against: object = None) -> dict:
    """The Diagnosis and Drive figures for the live connection or one recording."""
    store = Store(db_path)
    try:
        passes, signals = _passes(hub, store, source)
        other = _passes(hub, store, against)[0] if against not in (None, "") else None
        live = source in (None, "", "live")
        vin = hub.status()["vin"] if live else store.session(int(source))["vin"]
        profile = store.profile(vin)
        result = analysis.analyse(passes, signals, profile, other)
        result["transmission"] = profile["transmission"]
    finally:
        store.close()
    result["source"] = "live" if live else int(source)
    result["against"] = int(against) if other is not None else None
    result["vin"] = vin
    return result
