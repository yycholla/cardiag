"""Discovery runs: capturing everything a module answers, and working out what moves with what."""

import csv
import io

import pytest

from cardiag import analysis, discover, garage, service
from cardiag.sim import _DCT_RATIOS, _DCT_STEP, _dct_states
from cardiag.store import Store

from conftest import geared_passes, wait_for


@pytest.fixture(autouse=True)
def quick_passes(monkeypatch):
    """The simulated car answers at once, so the tests need not wait as long between passes as a run on a real one."""
    monkeypatch.setattr(service, "DISCOVERY_INTERVAL", 0.002)


def drive() -> tuple[dict, list]:
    """A discovery run as it would be stored for two laps of the geared Focus, each identifier read every two seconds."""
    states = _dct_states()
    samples: dict[int, list] = {0x1E01: [], 0x1E12: [], 0x1E1F: [], 0x1E30: [], 0x1EBB: [], 0x1E55: []}
    context = []
    for lap in range(2):
        for index in range(0, len(states), 5):
            rpm, speed, pedal, load, gear, slip, _ = states[index]
            t = lap * 150 + index * _DCT_STEP
            context.append((t, {analysis.RPM: rpm, analysis.SPEED: float(round(speed)), analysis.PEDAL: pedal,
                                analysis.LOAD: load, analysis.COOLANT: 90.0}))
            if index % 40:
                continue
            samples[0x1E01].append((t, bytes.fromhex("44505336")))
            samples[0x1E12].append((t, bytes([gear])))
            samples[0x1E1F].append((t, bytes([round(110 + load / 5)])))
            samples[0x1E30].append((t, bytes([0x80]) + round(speed * _DCT_RATIOS[gear - 1]).to_bytes(2, "big")))
            samples[0x1EBB].append((t, round(slip * 4 if gear % 2 else 0).to_bytes(2, "big", signed=True)))
            samples[0x1E55].append((t, round(t * 10).to_bytes(2, "big")))  # something that only counts up
    return samples, context


@pytest.fixture(scope="module")
def ranked() -> dict:
    samples, context = drive()
    return discover.rank(samples, context, analysis.learn_gears(geared_passes()))


def entry(ranked: dict, identifier: str) -> dict:
    return next(item for item in ranked["moving"] if item["id"] == identifier)


def test_the_gear_is_recognised(ranked):
    (reading,) = entry(ranked, "1E12")["readings_of"]
    assert reading["start"] == 0 and reading["size"] == 1 and reading["gear_match"] >= 0.85
    assert "likely the gear in use" in reading["guess"] and (reading["low"], reading["high"]) == (1, 6)
    assert ranked["moving"][0]["id"] == "1E12"  # and it is the strongest lead of the run


def test_slip_is_recognised_and_read_as_two_bytes(ranked):
    best = entry(ranked, "1EBB")["readings_of"][0]
    assert (best["start"], best["size"]) == (0, 2) and best["guess"] == "Rises and falls with clutch slip"
    assert best["moves_with"][0]["what"] == "clutch slip" and best["moves_with"][0]["likeness"] >= 0.75


def test_a_value_behind_a_status_byte_is_found_where_it_starts(ranked):
    best = entry(ranked, "1E30")["readings_of"][0]
    assert (best["start"], best["size"]) == (1, 2)  # the first byte never moves, so the number begins after it
    assert "input shaft speed" in best["guess"]


def test_other_shapes_are_described_for_what_they_are(ranked):
    assert entry(ranked, "1E1F")["readings_of"][0]["guess"] == "Follows the pedal"  # this one tracks load, which tracks the pedal
    assert entry(ranked, "1E55")["readings_of"][0]["guess"].startswith("Climbs steadily through the run")
    assert [item["id"] for item in ranked["still"]] == ["1E01"] and ranked["still"][0]["last"] == "44505336"
    assert ranked["gears_known"]


def test_without_learned_gears_there_is_still_something_to_go_on():
    samples, context = drive()
    ranked = discover.rank(samples, context, [])
    assert not ranked["gears_known"]
    assert entry(ranked, "1E12")["readings_of"][0]["gear_match"] is None
    assert entry(ranked, "1E55")["readings_of"][0]["guess"].startswith("Climbs steadily")


def test_too_few_readings_claim_nothing():
    ranked = discover.rank({0x1E12: [(0.0, b"\x01"), (1.0, b"\x02")]}, [(0.0, {analysis.RPM: 800.0})], [])
    (reading,) = ranked["moving"][0]["readings_of"]
    assert reading["moves_with"] == [] and reading["guess"] == "Changes, but not with anything measured here"
    assert discover.rank({}, [], []) == {"moving": [], "still": [], "gears_known": False, "passes": 0}


def geared(served) -> None:
    served.request("/api/simulation", {"vehicle": "focus_dct"})
    wait_for(lambda: served.hub.status()["state"] == "connected")


def progress(served) -> dict | None:
    return served.hub.status()["discovery"]


def test_a_run_scans_then_keeps_reading_what_answered(served):
    geared(served)
    watched_before = served.request("/api/values")[1]["watched"]
    status, state = served.request("/api/discover", {"action": "start", "module": "7E9", "first": "1E00", "count": 4096, "note": "parked"})
    assert status == 200 and state["active"]["phase"] == "scanning" and state["active"]["range"] == 4096
    status, body = served.request("/api/discover", {"action": "start", "module": "7E9", "first": "1E00", "count": 16})
    assert status == 400 and "already going" in body["error"]

    wait_for(lambda: progress(served)["phase"] == "capturing")
    assert progress(served)["found"] == 6 and progress(served)["asked"] == 4096
    before = progress(served)["readings"]
    wait_for(lambda: progress(served)["readings"] >= before + 30)
    readings = {reading["key"] for reading in served.stream_events(1)[0]["readings"]}
    assert "01:0C" in readings and "01:0D" in readings and "01:10" not in readings  # only the few standard values it needs

    status, state = served.request("/api/discover", {"action": "stop"})
    assert status == 200 and state["active"] is None
    (run,) = state["runs"]
    assert run["module"] == "7E9" and run["note"] == "parked" and run["identifiers"] == 6 and run["readings"] >= 36
    assert run["ended_at"] is not None and run["vin"] == "1FADP3F2XHL654321"
    assert served.request("/api/values")[1]["watched"] == watched_before  # the person's own choice is untouched
    wait_for(lambda: "01:10" in {reading["key"] for reading in served.stream_events(1)[0]["readings"]})

    status, report = served.request("/api/discoveries/1")
    assert status == 200 and report["run"]["id"] == 1
    assert {item["id"] for item in report["moving"]} | {item["id"] for item in report["still"]} == {"1E01", "1E12", "1E1F", "1E30", "1EBB", "1EBC"}

    status, text = served.request("/api/discoveries/1.csv")
    rows = list(csv.reader(io.StringIO(text)))
    assert status == 200 and rows[0] == ["seconds", "kind", "name", "value"]
    assert ["identifier", "1E01", "44505336"] in [row[1:] for row in rows] and any(row[1:3] == ["standard", "01:0C"] for row in rows)


def test_a_later_run_reads_the_same_identifiers_without_scanning_again(served):
    geared(served)
    served.request("/api/discover", {"action": "start", "module": "7E9", "first": "1E00", "count": 64})
    wait_for(lambda: progress(served)["phase"] == "capturing" and progress(served)["readings"] >= 8)
    served.request("/api/discover", {"action": "stop"})

    status, state = served.request("/api/discover", {"action": "start", "module": "7E9", "reuse": 1})
    assert status == 200 and state["active"]["phase"] == "capturing" and state["active"]["found"] == 4 and state["active"]["range"] == 0
    wait_for(lambda: progress(served)["readings"] >= 8)
    served.request("/api/discover", {"action": "stop"})
    assert [run["identifiers"] for run in served.request("/api/discoveries")[1]["runs"]] == [4, 4]


def test_a_range_with_nothing_in_it_ends_by_itself(served):
    geared(served)
    served.request("/api/discover", {"action": "start", "module": "7E9", "first": "4000", "count": 48})
    wait_for(lambda: progress(served) is None)
    (run,) = served.request("/api/discoveries")[1]["runs"]
    assert run["identifiers"] == 0 and run["ended_at"] is not None
    status, body = served.request("/api/discover", {"action": "start", "module": "7E9", "reuse": 1})
    assert status == 400 and "found no identifiers" in body["error"]


def test_losing_the_car_ends_the_run(served):
    geared(served)
    served.request("/api/discover", {"action": "start", "module": "7E9", "first": "1E00", "count": 64})
    wait_for(lambda: progress(served) is not None)
    served.request("/api/simulation", {"vehicle": "tahoe"})
    wait_for(lambda: served.hub.status()["state"] == "connected")
    assert progress(served) is None
    assert served.request("/api/discoveries")[1]["runs"][0]["ended_at"] is not None
    status, body = served.request("/api/discover", {"action": "start", "module": "7E9", "first": "1E00", "count": 64})
    assert status == 400 and "11-bit CAN" in body["error"]


def test_requests_that_cannot_work_are_refused(served):
    for bad in ({"action": "begin"}, {"action": "start", "module": "7E9", "first": "1E00", "count": 100000},
                {"action": "start", "module": "123", "first": "1E00"}, {"action": "start", "module": "7E9", "first": "zz"},
                {"action": "start", "module": "7E9", "reuse": 99}, {"action": "start", "module": "7E9", "reuse": "soon"},
                {"action": "start", "module": "7E9", "first": "1E00", "note": "x" * 121}):
        status, body = served.request("/api/discover", bad)
        assert status == 400 and body["error"], bad
    assert served.request("/api/discoveries/99")[0] == 404 and served.request("/api/discoveries/99.csv")[0] == 404
    assert served.request("/api/discover", {"action": "stop"})[0] == 200  # stopping nothing is harmless


def test_a_report_uses_the_gears_learned_for_that_car(tmp_path):
    db = str(tmp_path / "s.db")
    samples, context = drive()
    store = Store(db)
    store.save_profile("VIN1", {"gears": analysis.learn_gears(geared_passes())})
    number = store.start_discovery(vin="VIN1", module="7E9")
    for t, values in context:
        rows = [(t, identifier, data) for identifier, readings in samples.items() for at, data in readings if at == t]
        store.add_discovery(number, t, rows, values.items())
    store.end_discovery(number)
    store.close()
    report = garage.discovery_report(db, number)
    assert report["gears_known"] and report["moving"][0]["id"] == "1E12" and report["run"]["seconds"] > 290
