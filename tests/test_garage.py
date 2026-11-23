"""Setup for one car, and the reports built from it, over real HTTP."""

import pytest

from cardiag import analysis, garage
from cardiag.store import Store

from conftest import as_recording, geared_passes, wait_for


class ParkedCar:
    """Stands in for the live connection: a warm car that has been idling."""

    def __init__(self, coolant: float = 90.0, ltft: float = 2.0, seconds: int = 60) -> None:
        self.passes = [
            (t / 4, {analysis.RPM: 780.0, analysis.SPEED: 0.0, analysis.THROTTLE: 14.0, analysis.MAP: 34.0,
                     analysis.MAF: 3.1, analysis.COOLANT: coolant, analysis.STFT: 0.5, analysis.LTFT: ltft})
            for t in range(seconds * 4)
        ]

    def status(self) -> dict:
        return {"state": "connected", "vin": "TESTVIN"}

    def history(self):
        return self.passes, {}


def test_setup_says_what_the_car_offers_and_what_the_views_want(served):
    status, report = served.request("/api/setup")
    assert status == 200 and report["status"]["vin"] == "1FADP3F2XHL123456"
    engine, transmission = report["offered"]
    assert engine["module"] == "Engine (7E8)" and {"pid": "0C", "name": "Engine speed"} in engine["values"]
    assert transmission["values"] == [{"pid": "0D", "name": "Vehicle speed"}]
    wanted = {row["name"]: row for row in report["wanted"]}
    assert wanted["Engine speed and vehicle speed"]["offered"] and wanted["Fuel rail pressure"]["offered"]
    assert not wanted["Accelerator pedal position"]["offered"] and "throttle position" in wanted["Accelerator pedal position"]["without"]
    assert report["drive_pids"] == ["0C", "0D", "11", "04", "0E"]
    assert report["profile"] == {"engine_litres": None, "transmission": None, "fuel": "petrol", "gears": [], "baseline": None}


def test_profile_is_kept_per_car_and_checked(served):
    status, profile = served.request("/api/setup/profile", {"engine_litres": "2.0", "transmission": "dual-clutch automatic"})
    assert status == 200 and profile["engine_litres"] == 2.0 and profile["transmission"] == "dual-clutch automatic"
    assert served.request("/api/setup")[1]["profile"]["engine_litres"] == 2.0
    for bad in ({"engine_litres": "big"}, {"engine_litres": 40}, {"transmission": "warp drive"}, {"fuel": "coal"}, {}):
        status, body = served.request("/api/setup/profile", bad)
        assert status == 400 and body["error"]

    served.request("/api/simulation", {"vehicle": "tahoe"})  # another car has its own profile
    wait_for(lambda: served.hub.status()["state"] == "connected")
    assert served.request("/api/setup")[1]["profile"]["engine_litres"] is None


def test_a_cold_engine_cannot_give_a_baseline(served, monkeypatch):
    monkeypatch.setattr(garage, "MIN_IDLE_SECONDS", 0.2)
    wait_for(lambda: analysis.idle_summary(served.hub.history()[0])["idle_seconds"] >= 0.3)
    status, body = served.request("/api/setup/baseline", {"known_good": True})
    assert status == 400 and "not warm yet" in body["error"]


def test_baseline_needs_idling_and_knows_good_from_current(tmp_path):
    db = str(tmp_path / "s.db")
    with pytest.raises(ValueError, match="so far it has idled for 5 s"):
        garage.take_baseline(ParkedCar(seconds=5), db, True)

    profile = garage.take_baseline(ParkedCar(), db, True)
    assert profile["baseline"]["good"] and profile["baseline"]["values"]["idle_rpm"] == 780.0
    assert profile["baseline"]["flags"] == []

    lean = garage.take_baseline(ParkedCar(ltft=12.5), db, True)["baseline"]
    assert not lean["good"] and lean["flags"] == ["long-term fuel trim is beyond \xb110 %"]
    assert not garage.take_baseline(ParkedCar(), db, False)["baseline"]["good"]  # the person did not vouch for it


def test_gears_are_learned_from_a_recording_and_shape_its_report(served):
    store = Store(served.db_path)
    number = store.import_session("elsewhere#1", as_recording(geared_passes(), vin="1FADP3F2XHL123456"))
    store.close()

    status, before = served.request(f"/api/analysis?source={number}")
    assert status == 200 and not before["drive"]["learned"]
    status, profile = served.request("/api/setup/gears", {"source": number})
    assert status == 200 and [round(gear["ratio"]) for gear in profile["gears"]] == [120, 70, 48, 36, 29, 24]

    status, report = served.request(f"/api/analysis?source={number}&against={number}")
    assert status == 200 and report["source"] == number and report["against"] == number
    assert report["drive"]["slip"][2]["mean"] > 5
    assert any(shift["result"] != "clean" for shift in report["drive"]["shifts"])
    assert report["other_pull"]["spans"] == report["pull"]["spans"]

    status, cleared = served.request("/api/setup/gears", {"action": "clear"})
    assert status == 200 and cleared["gears"] == []


def test_live_report_and_its_refusals(served):
    wait_for(lambda: len(served.hub.history()[0]) >= 10)
    status, report = served.request("/api/analysis")
    assert status == 200 and report["source"] == "live" and report["passes"] >= 10
    assert report["trim_map"]["available"] and report["healthy"]["rows"]
    assert not report["air_flow"]["available"]  # no engine size entered yet
    served.request("/api/setup/profile", {"engine_litres": 2.0})
    assert served.request("/api/analysis")[1]["air_flow"]["available"]

    status, body = served.request("/api/setup/gears", {"source": "live"})
    assert status == 400 and "no steady gears" in body["error"]  # the plain Focus drive has no gears in it
    for bad in ("/api/analysis?source=99", "/api/analysis?source=soon"):
        status, body = served.request(bad)
        assert status == 400 and body["error"]


def test_history_starts_again_with_each_car(served):
    wait_for(lambda: len(served.hub.history()[0]) >= 5)
    before = served.hub.history()[0][-1][0]
    served.request("/api/simulation", {"vehicle": "tahoe"})
    wait_for(lambda: served.hub.status()["state"] == "connected" and served.hub.history()[0])
    passes, _ = served.hub.history()
    assert passes[0][0] < before  # the clock and the passes both began again
    assert "01:42" not in passes[-1][1]  # control module voltage: the Focus reports it, the Tahoe does not
    assert [module["module"] for module in served.hub.offered()] == ["Engine (10)"]
