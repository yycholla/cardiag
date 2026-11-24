"""Maker-specific values: reading them, defining them, scanning for them, and the polling rate."""

import pytest

from cardiag import analysis, garage
from cardiag.elm import Elm327
from cardiag.maker import MakerValue, parse
from cardiag.obd import Obd
from cardiag.sim import _DCT_STEP, SimElm, SimTransport, _dct_states, make_focus_dct, make_tahoe

from conftest import wait_for

SLIP_A = {"module": "7E9", "id": "1EBB", "name": "Clutch A slip", "unit": "rpm", "size": 2, "signed": True, "scale": 0.25, "offset": 0}


def connect(vehicle, at: float = 0.0) -> Obd:
    obd = Obd(Elm327(SimTransport(SimElm(vehicle, clock=lambda: at))))
    obd.elm.transport._sim._started = 0.0
    obd.elm.initialise()
    obd.connect()
    return obd


def slipping_moment() -> tuple[float, int, float]:
    """A time in the lap when third gear is slipping: (seconds, gear, slip rpm)."""
    index, state = next((i, s) for i, s in enumerate(_dct_states()) if s[4] == 3 and s[5] > 100)
    return index * _DCT_STEP + 0.01, state[4], state[5]


def test_a_value_is_read_from_the_module_asked_and_no_other():
    at, gear, slip = slipping_moment()
    obd = connect(make_focus_dct(), at)
    assert obd.read_identifier(0x7E9, 0x1E12) == bytes([gear])
    raw = obd.read_identifier(0x7E9, 0x1EBB)  # third gear is on the odd clutch
    assert int.from_bytes(raw, "big", signed=True) / 4 == pytest.approx(slip, abs=0.25)
    other = int.from_bytes(obd.read_identifier(0x7E9, 0x1EBC), "big", signed=True) / 4
    assert other > 100  # the even clutch holds fourth ready, so its shaft turns slower than the engine
    assert obd.read_identifier(0x7E9, 0x1234) is None  # refused: the module has no such value
    assert obd.read_identifier(0x7E8, 0x1E12) is None  # the engine computer does not have the gearbox's


def test_standard_requests_reach_every_module_again_afterwards():
    obd = connect(make_focus_dct(), 30.0)
    assert obd.read_identifier(0x7E9, 0x1E12) is not None
    assert obd.read_pid(0x0C).value > 700  # the engine answers although the last request went to the gearbox
    assert obd.read_pid(0x0D, ecu=0x7E9) is not None
    sent = obd.elm.transport._sim
    assert sent.header is None


def test_older_networks_are_refused_plainly():
    obd = connect(make_tahoe())
    assert not obd.maker_values
    with pytest.raises(ValueError, match="11-bit CAN"):
        obd.read_identifier(0x7E9, 0x1E12)


def test_bytes_become_numbers_by_the_definition():
    (slip,) = parse([SLIP_A])
    assert slip.key == "22:7E9:1EBB"
    assert slip.decode(bytes.fromhex("0190")) == 100.0 and slip.decode(bytes.fromhex("FE70")) == -100.0
    assert slip.decode(b"\x01") is None  # fewer bytes than the definition needs
    temperature = MakerValue(0x7E9, 0x1E1F, "Clutch temperature", "C", 1, False, 1.0, -40.0)
    assert temperature.decode(bytes([110, 99])) == 70.0  # only the first byte counts


@pytest.mark.parametrize("change", [
    {"module": "123"}, {"module": "7F0"}, {"id": "XYZ"}, {"id": "12345"}, {"name": ""}, {"name": "x" * 61},
    {"size": 5}, {"size": True}, {"scale": 0}, {"scale": "lots"}, {"offset": float("nan")}, {"unit": "x" * 13},
])
def test_definitions_that_cannot_work_are_refused(change):
    with pytest.raises(ValueError):
        parse([{**SLIP_A, **change}])


def test_a_value_cannot_be_listed_twice_or_without_end():
    with pytest.raises(ValueError, match="listed twice"):
        parse([SLIP_A, {**SLIP_A, "name": "Again"}])
    with pytest.raises(ValueError, match="at most 24"):
        parse([{**SLIP_A, "id": f"{n:04X}"} for n in range(25)])
    for bad in ("values", [3], None):
        with pytest.raises(ValueError):
            parse(bad)


def geared(served) -> None:
    served.request("/api/simulation", {"vehicle": "focus_dct"})
    wait_for(lambda: served.hub.status()["state"] == "connected")


def test_values_are_set_up_per_car_and_join_the_live_readings(served):
    status, report = served.request("/api/maker")
    assert status == 200 and report["supported"] and report["values"] == []
    assert report["modules"] == [{"reply": "7E8", "name": "Engine (7E8)"}, {"reply": "7E9", "name": "Transmission (7E9)"}]
    assert [candidate["id"] for candidate in report["candidates"]] == ["1EBB", "1EBC"]

    geared(served)
    status, report = served.request("/api/maker/values", {"values": report["candidates"]})
    assert status == 200 and [value["key"] for value in report["values"]] == ["22:7E9:1EBB", "22:7E9:1EBC"]
    assert report["candidates"] == []  # nothing left to suggest

    def live() -> dict:
        return {reading["key"]: reading for reading in served.stream_events(1)[0]["readings"]}

    wait_for(lambda: "22:7E9:1EBB" in live())
    assert live()["22:7E9:1EBB"]["name"] == "Clutch A slip" and live()["22:7E9:1EBB"]["unit"] == "rpm"
    assert "01:0C" in live() and "adapter:voltage" in live()  # alongside the standard values, not instead

    served.request("/api/simulation", {"vehicle": None})  # the plain Focus is a different car
    wait_for(lambda: served.hub.status()["state"] == "connected")
    assert served.request("/api/maker")[1]["values"] == []
    geared(served)  # and the geared one remembers
    assert len(served.request("/api/maker")[1]["values"]) == 2
    wait_for(lambda: "22:7E9:1EBC" in live())

    status, report = served.request("/api/maker/values", {"values": []})
    assert status == 200 and report["values"] == [] and len(report["candidates"]) == 2


def test_maker_values_are_recorded_and_traced(served):
    geared(served)
    served.request("/api/maker/values", {"values": [SLIP_A]})
    served.request("/api/record", {"action": "start"})
    wait_for(lambda: served.hub.status()["recording"]["seconds"] >= 0.2)
    served.request("/api/record", {"action": "stop"})
    status, report = served.request("/api/analysis?source=1")
    assert status == 200
    (trace,) = report["maker"]
    assert trace["key"] == "22:7E9:1EBB" and trace["name"] == "Clutch A slip" and len(trace["trace"]) >= 2
    assert analysis.maker_traces([(0.0, {"01:0C": 800.0})], {}) == []


def test_scanning_finds_what_a_module_has(served):
    geared(served)
    status, first = served.request("/api/maker/scan", {"module": "7E9", "first": "1E00", "count": 64})
    assert status == 200 and [found["id"] for found in first["found"]] == ["1E01", "1E12", "1E1F", "1E30"] and first["next"] == "1E40"
    assert first["found"][1]["data"] in ("01", "02")  # one byte, as hex: the gear, early in the lap
    status, later = served.request("/api/maker/scan", {"module": "7E9", "first": "1E80", "count": 64})
    assert [found["id"] for found in later["found"]] == ["1EBB", "1EBC"]
    status, engine = served.request("/api/maker/scan", {"module": "7E8", "first": "1E00", "count": 64})
    assert status == 200 and engine["found"] == []
    status, end = served.request("/api/maker/scan", {"module": "7E9", "first": "FFF0", "count": 64})
    assert status == 200 and end["next"] is None
    assert served.stream_events(1)[0]["status"]["state"] == "connected"  # live values carry on afterwards

    for bad in ({"module": "7E9", "first": "1E00", "count": 500}, {"module": "ZZZ", "first": "1E00"},
                {"module": "7E9", "first": "nope"}, {"module": "7E9"}):
        status, body = served.request("/api/maker/scan", bad)
        assert status == 400 and body["error"]


def test_a_car_on_an_older_network_cannot_have_maker_values(served):
    served.request("/api/simulation", {"vehicle": "tahoe"})
    wait_for(lambda: served.hub.status()["state"] == "connected")
    assert not served.request("/api/maker")[1]["supported"]
    status, body = served.request("/api/maker/values", {"values": [SLIP_A]})
    assert status == 400 and "11-bit CAN" in body["error"]
    status, body = served.request("/api/maker/scan", {"module": "7E9", "first": "1E00", "count": 8})
    assert status == 400 and "11-bit CAN" in body["error"]


def test_the_polling_rate_can_be_changed_and_is_kept(served):
    wait_for(lambda: served.hub.status()["rate"] is not None)
    before = served.hub.status()
    assert before["interval"] == 0.02 and before["rate"] > 5 and before["values"] >= 10

    status, after = served.request("/api/interval", {"seconds": 0.2})
    assert status == 200 and after["interval"] == 0.2
    assert garage.saved_interval(served.db_path) == 0.2
    wait_for(lambda: len(served.hub.history()[0]) >= 25 and served.hub.status()["rate"] < 7, timeout=15)

    for bad in ({"seconds": -1}, {"seconds": 60}, {"seconds": "fast"}, {"seconds": True}, {}):
        status, body = served.request("/api/interval", bad)
        assert status == 400 and "between 0 and 10" in body["error"]
    assert served.hub.status()["interval"] == 0.2


def test_no_rate_has_been_chosen_until_one_is(tmp_path):
    assert garage.saved_interval(str(tmp_path / "fresh.db")) is None
