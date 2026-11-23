"""The arithmetic behind the Diagnosis and Drive pages, on drives whose answers are known."""

import math

import pytest

from cardiag import analysis as a
from cardiag.sim import _drive

from conftest import geared_passes


def lean_focus(seconds: int = 300) -> list:
    """The simulated Focus's repeating drive, with its fuel trim stuck at +12.5 %."""
    passes = []
    for step in range(seconds * 2):
        t = step / 2
        rpm, speed, throttle, load = _drive(t)
        passes.append(
            (t, {a.RPM: rpm, a.SPEED: float(round(speed)), a.THROTTLE: throttle, a.LOAD: load,
                 a.STFT: 2.3 * math.sin(t / 3), a.LTFT: 12.5, a.MAP: 30 + load * 0.6, a.MAF: rpm / 200,
                 a.COOLANT: min(92, 20 + t * 0.25), a.OIL: min(98, 20 + t * 0.2), a.MODULE_VOLTS: 14.1,
                 a.ADAPTER_VOLTS: 12.6, a.IAT: 24.0})
        )
    return passes


def test_gears_are_learned_from_the_gentle_stretches():
    gears = a.learn_gears(geared_passes())
    assert [round(gear["ratio"]) for gear in gears] == [120, 70, 48, 36, 29, 24]


def test_a_clutch_slipping_under_load_is_not_learned_as_a_gear():
    hard_only = [p for p in geared_passes() if p[1][a.PEDAL] >= 40]
    assert a.learn_gears(hard_only) == []


def test_slip_shows_in_third_gear_only():
    passes = geared_passes()
    slip = a.drive_report(passes, a.learn_gears(passes))["slip"]
    assert slip[2]["mean"] == pytest.approx(7.0, abs=1.0) and slip[2]["seconds"] > 10
    assert all(gear["mean"] is None or abs(gear["mean"]) < 2.5 for gear in slip[:2] + slip[3:])


def test_the_slow_shift_is_found_and_the_clean_ones_are_not_blamed():
    passes = geared_passes()
    shifts = a.drive_report(passes, a.learn_gears(passes))["shifts"]
    faulty = [shift for shift in shifts if shift["result"] != "clean"]
    assert {(shift["from"], shift["to"], shift["effort"]) for shift in faulty} == {(2, 3, 50.0)}
    assert all(shift["flare"] > 300 and shift["took"] >= 1.2 for shift in faulty)
    gentle = [shift for shift in shifts if (shift["from"], shift["to"]) == (2, 3) and shift["effort"] == 22.0]
    assert gentle and all(shift["result"] == "clean" for shift in gentle)
    trace = faulty[0]["trace"]
    assert max(point[1] for point in trace) > faulty[0]["rpm"] + 300  # the detail view can show the flare


def test_before_gears_are_learned_the_points_are_still_there():
    report = a.drive_report(geared_passes(1), [])
    assert report["available"] and not report["learned"] and report["shifts"] == [] and len(report["points"]) > 100
    assert {point[2] for point in report["points"]} == {2}


def test_a_drive_needs_both_speeds():
    assert a.drive_report([(0.0, {a.RPM: 800.0})], [])["needs"] == ["Engine speed", "Vehicle speed"]


def test_trim_map_puts_each_pass_in_its_cell():
    trim = a.trim_map(lean_focus())
    assert trim["visited"] == trim["beyond"] > 3  # lean everywhere it went
    idle = trim["cells"][-2][0]  # 20 to 35 % load, under 1,000 rpm
    assert idle["mean"] == pytest.approx(12.5, abs=1.0) and idle["seconds"] == pytest.approx(50, abs=2)
    assert trim["cells"][0][0] is None  # never at full load and idle speed together


def test_air_flow_share_matches_a_hand_calculation():
    # 2.0 L at 2,100 rpm moves 0.035 cubic metres a second; at 52.8 kPa and 24 C that is 21.7 g/s.
    assert a.air_share(2100, 52.8, 10.5, 2.0, 24.0) == pytest.approx(48.4, abs=0.3)
    flow = a.air_flow(lean_focus(), 2.0)
    assert flow["available"] and flow["high"] < 70 and flow["band"] == [70.0, 95.0]
    assert a.air_flow(lean_focus(), None)["needs"] == ["Engine size, entered in Setup"]


def test_warm_up_times():
    warm = a.warm_up(lean_focus(seconds=320))
    assert warm["coolant_at_80"] == 240.0 and warm["oil_at_80"] == 300.0 and not warm["began_warm"]


def test_fuel_estimate_is_plausible_and_only_for_petrol():
    fuel = a.fuel_used(lean_focus())
    assert 5 < fuel["per_100_km"] < 9 and fuel["km"] == pytest.approx(3.4, abs=0.2)
    assert not a.fuel_used(lean_focus(), "diesel")["available"]


def test_healthy_bands_flag_what_is_outside():
    report = a.healthy(lean_focus())
    outside = {row["key"]: row["result"] for row in report["rows"] if row["result"] != "inside"}
    assert outside == {"ltft": "above", "adapter_volts": "below"}
    assert {row["source"] for row in report["rows"]} == {"general"}

    own = a.healthy(lean_focus(), {"idle_rpm": 700.0, "idle_map": 43.0})
    rows = {row["key"]: row for row in own["rows"]}
    assert rows["idle_rpm"]["source"] == "baseline" and rows["idle_rpm"]["result"] == "above"  # 800 against 700 +/- 75
    assert rows["idle_map"]["result"] == "inside" and rows["coolant"]["source"] == "general"


def test_a_cold_engine_is_not_called_out_of_band():
    report = a.healthy(lean_focus(seconds=60))
    assert not report["warm"] and "coolant" not in {row["key"] for row in report["rows"]}


def test_idle_summary_uses_the_latest_stretch_of_idling():
    summary = a.idle_summary(lean_focus(seconds=70))  # ends ten seconds into the second idle
    assert summary["idle_rpm"] == pytest.approx(800, abs=10) and 8 <= summary["idle_seconds"] <= 10


def test_pull_times_take_the_quickest_run():
    spans = {(span["from"], span["to"]): span for span in a.pull_times(geared_passes())["spans"]}
    assert spans[(0, 30)]["seconds"] < 8 and spans[(0, 30)]["effort"] == 50.0  # the hard run, not the gentle one
    assert spans[(80, 110)]["seconds"] is None  # never got there


def test_compare_lists_shared_values():
    first, second = lean_focus(seconds=300), lean_focus(seconds=600)[600:]
    rows = {row["key"]: row for row in a.compare(second, first, {a.COOLANT: {"name": "Coolant temperature", "unit": "C"}})}
    assert rows[a.COOLANT]["change"] > 10 and rows[a.COOLANT]["other_max"] == 92


def test_analyse_holds_together_with_nothing_and_with_everything():
    assert a.analyse([], {}, {}) == {"passes": 0, "seconds": 0}
    passes = geared_passes()
    report = a.analyse(passes, {}, {"gears": a.learn_gears(passes), "engine_litres": 2.0}, other=passes)
    assert report["drive"]["learned"] and report["other_pull"]["available"]
    assert not report["trim_map"]["available"] and not report["warm_up"]["available"]  # that drive has no trims
