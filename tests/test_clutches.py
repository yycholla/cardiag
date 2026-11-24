"""Gears, shifts and slip from the gearbox's own clutch figures, and the ways of recording that read them fast."""

import pytest

from cardiag import analysis, garage
from cardiag.sim import _DCT_LAP, _DCT_RATIOS, _DCT_STEP, SimElm, SimTransport, _dct_clutch_slip, _dct_states, make_focus_dct
from cardiag.elm import Elm327
from cardiag.obd import Obd

from conftest import wait_for

A, B = analysis.CLUTCH_A, analysis.CLUTCH_B


def clutch_passes(laps: int = 2, every: float = 0.1) -> list:
    """The geared Focus as an adapter reading its two clutches would report it."""
    states, stride = _dct_states(), round(every / _DCT_STEP)
    return [
        (
            lap * _DCT_LAP + index * _DCT_STEP,
            {analysis.RPM: round(state[0] * 4) / 4, analysis.SPEED: float(round(state[1])), analysis.PEDAL: state[2], analysis.LOAD: state[3],
             A: round(_dct_clutch_slip(state, True) * 4) / 4, B: round(_dct_clutch_slip(state, False) * 4) / 4},
        )
        for lap in range(laps)
        for index, state in list(enumerate(states))[::stride]
    ]


@pytest.fixture(scope="module")
def passes() -> list:
    return clutch_passes()


@pytest.fixture(scope="module")
def gears(passes) -> list:
    return analysis.learn_gears(passes)


def test_every_gear_is_found_with_the_clutch_it_belongs_to(gears):
    assert [gear["clutch"] for gear in gears] == ["A", "B", "A", "B", "A", "B"]
    for gear, ratio in zip(gears, _DCT_RATIOS):
        assert gear["ratio"] == pytest.approx(ratio, rel=0.03)


def test_a_slipping_clutch_is_not_learned_as_a_gear(gears):
    # Third slips 7 % under a heavy foot. From engine speed alone that looks like a gear of its own.
    assert not [gear for gear in gears if 49.5 < gear["ratio"] < 54]


def test_without_the_clutch_figures_the_old_way_still_works(passes):
    bare = [(t, {key: value for key, value in values.items() if key not in (A, B)}) for t, values in passes]
    gears = analysis.learn_gears(bare)
    assert len(gears) >= 5 and not any("clutch" in gear for gear in gears)


def test_first_gear_is_found_even_when_it_is_only_ever_passed_through(passes):
    brisk = [(t, values) for t, values in passes if 76 <= t % _DCT_LAP <= 133]  # only the hard run: first lasts moments
    gears = analysis.learn_gears(brisk)
    assert gears[0]["clutch"] == "A" and gears[0]["ratio"] == pytest.approx(_DCT_RATIOS[0], rel=0.12)


def test_the_gear_in_use_and_its_slip(gears):
    states = _dct_states()
    hard_third = next(state for index, state in enumerate(states) if state[4] == 3 and state[2] >= 40 and state[5] > 50 and index * _DCT_STEP > 80)
    values = {analysis.RPM: hard_third[0], analysis.SPEED: float(round(hard_third[1])),
              A: _dct_clutch_slip(hard_third, True), B: _dct_clutch_slip(hard_third, False)}
    gear, slip = analysis.gear_now(values, gears)
    assert gear == 3 and slip == pytest.approx(7.0, abs=0.3)
    stopped = {analysis.RPM: 780.0, analysis.SPEED: 0.0, A: 780.0, B: 780.0}
    assert analysis.gear_now(stopped, gears) == (None, None)
    between = {analysis.RPM: 3000.0, analysis.SPEED: 40.0, A: 900.0, B: -700.0}  # neither clutch near the engine
    assert analysis.gear_now(between, gears) == (None, None)


def test_the_report_names_the_faults(passes, gears):
    drive = analysis.drive_report(passes, gears)
    assert drive["by_clutch"] and not drive["coarse"] and drive["rate"] == pytest.approx(10, abs=0.5)
    bad = [shift for shift in drive["shifts"] if shift["result"] != "clean"]
    assert bad and all((shift["from"], shift["to"]) == (2, 3) for shift in bad)
    assert all("neither clutch holding" in shift["result"] and shift["gap"] >= 300 for shift in bad)
    assert len(bad[0]["trace"][0]) == 5  # time, engine speed, the gear line, and both clutches

    clutches = drive["clutches"]
    third = clutches["by_gear"][2]
    assert third["clutch"] == "A" and third["working"] >= 100  # rpm of slip under load
    assert all(gear["working"] is None or gear["working"] < 20 for gear in clutches["by_gear"] if gear["gear"] != 3)
    slow = [change for change in clutches["changes"] if change["slow"]]
    assert slow and all((change["clutch"], change["to"]) == ("A", 5) and change["took"] >= 2.0 for change in slow)
    assert clutches["slow_changes"] == len(slow)


def test_a_slow_recording_says_its_shift_figures_are_rough(gears):
    drive = analysis.drive_report(clutch_passes(every=0.75), gears)
    assert drive["coarse"] and drive["rate"] == pytest.approx(1.3, abs=0.1)


def connect(at: float = 0.0) -> Obd:
    obd = Obd(Elm327(SimTransport(SimElm(make_focus_dct(), clock=lambda: at))))
    obd.elm.transport._sim._started = 0.0
    obd.elm.initialise()
    obd.connect()
    return obd


def test_several_values_come_back_from_one_request():
    obd = connect(at=20.0)
    together = obd.read_pids([0x0C, 0x0D, 0x49, 0x04])
    assert [reading.key for reading in together] == ["01:0C", "01:0D", "01:49", "01:04"]
    for reading in together:
        assert reading.value == obd.read_pid(int(reading.key[3:], 16)).value
    assert obd.read_pids([0x0C]) is None and obd.read_pids([0x0C, 0x99]) is None
    assert obd.read_pids([0x0C, 0x0D, 0x04, 0x05, 0x06, 0x07, 0x0B]) is None  # six at most


def geared(served) -> None:
    served.request("/api/simulation", {"vehicle": "focus_dct"})
    wait_for(lambda: served.hub.status()["state"] == "connected")
    values = [{"module": "7E9", "id": "1EBB", "name": "Clutch A slip", "unit": "rpm", "size": 2, "signed": True, "scale": 0.25},
              {"module": "7E9", "id": "1EBC", "name": "Clutch B slip", "unit": "rpm", "size": 2, "signed": True, "scale": 0.25},
              {"module": "7E9", "id": "1E1F", "name": "Clutch temperature", "unit": "C", "size": 1, "offset": -40}]
    assert served.request("/api/maker/values", {"values": values})[0] == 200


def keys(served) -> set:
    return {reading["key"] for reading in served.stream_events(1)[0]["readings"]}


def test_the_ways_to_record_are_listed_for_the_car(served):
    geared(served)
    presets = {preset["id"]: preset for preset in served.request("/api/presets")[1]["presets"]}
    assert list(presets) == ["all", "shifts", "drive", "fuel"] and presets["all"]["reads"] is None
    assert presets["shifts"]["reads"] == ["Engine speed", "Vehicle speed", "Accelerator pedal position D", "Engine load", "Clutch A slip", "Clutch B slip"]
    assert "Clutch temperature" in presets["drive"]["reads"] and "Clutch temperature" not in presets["fuel"]["reads"]


def test_a_shifts_recording_reads_only_what_shifts_need_and_then_puts_things_back(served):
    geared(served)
    wait_for(lambda: "22:7E9:1E1F" in keys(served))
    before = keys(served)
    status, state = served.request("/api/record", {"action": "start", "preset": "shifts"})
    assert status == 200 and state["recording"]["preset"] == "shifts" and state["recording"]["note"] == "Shifts capture"
    wait_for(lambda: keys(served) == {"01:0C", "01:0D", "01:49", "01:04", A, B})
    wait_for(lambda: served.hub.status()["recording"]["seconds"] >= 0.3)
    served.request("/api/record", {"action": "stop"})
    wait_for(lambda: keys(served) == before)
    assert served.request("/api/values")[1]["watched"][:2] == ["0C", "0D"]  # the person's own choice was never touched

    session = served.request("/api/sessions")[1][-1]
    report = served.request(f"/api/analysis?source={session['id']}")[1]
    assert {trace["key"] for trace in report["maker"]} == {A, B}


def test_recording_requests_that_cannot_work_are_refused(served):
    for bad in ({"action": "begin"}, {"action": "start", "preset": "everything"}, {"action": "start", "note": 5}):
        status, body = served.request("/api/record", bad)
        assert status == 400 and body["error"], bad
    assert served.request("/api/record", {"action": "stop"})[0] == 200  # stopping nothing is harmless


def test_gears_learned_through_the_page_use_the_clutches(served):
    geared(served)
    from cardiag.store import Store
    from conftest import as_recording

    store = Store(served.db_path)
    number = store.import_session("elsewhere#1", as_recording(clutch_passes(laps=1), vin="1FADP3F2XHL654321"))
    store.close()
    status, profile = served.request("/api/setup/gears", {"source": number})
    assert status == 200 and [gear["clutch"] for gear in profile["gears"]] == ["A", "B", "A", "B", "A", "B"]
    drive = served.request(f"/api/analysis?source={number}")[1]["drive"]
    assert drive["by_clutch"] and drive["clutches"]["available"]

    def in_gear() -> bool:
        glance = served.request("/api/glance")[1]
        return glance["gear"] is not None

    wait_for(in_gear, timeout=12)
