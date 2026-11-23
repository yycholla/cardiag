"""The background worker that owns the adapter: connecting, retrying, recording."""

import pytest

from cardiag.service import VOLTAGE_KEY, Hub, NotConnected
from cardiag.sim import SimElm, SimTransport, make_focus
from cardiag.store import Store
from cardiag.transport import LinkError

from conftest import wait_for


def state(hub: Hub) -> str:
    return hub.status()["state"]


@pytest.fixture
def hub_factory(tmp_path):
    hubs = []

    def make(open_transport) -> Hub:
        hub = Hub(open_transport, db_path=str(tmp_path / "s.db"), interval=0.01, retry_delay=0.03)
        hubs.append(hub)
        hub.start()
        return hub

    yield make
    for hub in hubs:
        hub.stop()


def test_connects_and_publishes_live_values(hub_factory):
    hub = hub_factory(lambda: SimTransport(SimElm(make_focus())))
    wait_for(lambda: state(hub) == "connected")
    status = hub.status()
    assert status["vin"] == "1FADP3F2XHL123456"
    assert status["modules"] == ["Engine (7E8)", "Transmission (7E9)"]

    version, payload = hub.wait_for_update(-1, timeout=2)
    assert version >= 0
    readings = {reading["key"]: reading for reading in payload["readings"]}
    assert 700 < readings["01:0C"]["value"] < 900
    assert readings[VOLTAGE_KEY] == {"key": VOLTAGE_KEY, "name": "Battery voltage at the port", "value": 12.6, "unit": "V"}


def test_waits_for_the_ignition_then_connects(hub_factory):
    car = {"vehicle": None}  # adapter plugged in, car not answering yet
    hub = hub_factory(lambda: SimTransport(SimElm(car["vehicle"])))
    wait_for(lambda: state(hub) == "no_vehicle")
    status = hub.status()
    assert "ignition" in status["message"]
    assert "OBDLink EX" in status["adapter"]  # the adapter itself was found
    with pytest.raises(NotConnected):
        hub.read_codes()

    car["vehicle"] = make_focus()
    wait_for(lambda: state(hub) == "connected")


def test_reports_a_missing_adapter_and_keeps_retrying(hub_factory):
    attempts = []

    def open_transport():
        attempts.append(1)
        raise LinkError("no OBD adapter found")

    hub = hub_factory(open_transport)
    wait_for(lambda: state(hub) == "no_adapter" and len(attempts) >= 3)
    assert hub.status()["message"] == "no OBD adapter found"
    assert hub.status()["adapter"] is None


def test_notices_when_the_car_is_switched_off(hub_factory):
    vehicle = make_focus()
    hub = hub_factory(lambda: SimTransport(SimElm(vehicle)))
    wait_for(lambda: state(hub) == "connected")
    hub.start_recording("drive home")
    vehicle.ecus.clear()  # every request now goes unanswered

    wait_for(lambda: state(hub) == "no_vehicle")
    status = hub.status()
    assert status["recording"] is None  # the recording was closed, not left dangling
    assert status["vin"] is None
    store = Store(hub._db_path)
    assert store.sessions()[0]["ended_at"] is not None
    store.close()


def test_choosing_which_values_to_watch(hub_factory):
    hub = hub_factory(lambda: SimTransport(SimElm(make_focus())))
    wait_for(lambda: state(hub) == "connected")
    offered = [value["pid"] for value in hub.values()["available"]]
    assert "0C" in offered and "01" not in offered and "00" not in offered

    hub.set_watch(["0d", "05", "0D"])
    assert hub.values()["watched"] == ["0D", "05"]

    def only_chosen_values() -> bool:
        _, payload = hub.wait_for_update(-1, timeout=1)
        return [r["key"] for r in payload["readings"]] == ["01:0D", "01:05", VOLTAGE_KEY]

    wait_for(only_chosen_values)
    with pytest.raises(ValueError, match="does not offer PID 99"):
        hub.set_watch(["99"])
    with pytest.raises(ValueError):
        hub.set_watch(["zz"])


def test_codes_and_readiness_reports(hub_factory):
    hub = hub_factory(lambda: SimTransport(SimElm(make_focus())))
    wait_for(lambda: state(hub) == "connected")
    codes = hub.read_codes()
    assert codes["mil_on"] is True
    assert codes["modules"][0] == {
        "label": "Engine (7E8)", "stored": ["P0171"], "pending": ["P0456"], "permanent": ["P0171"],
    }
    assert codes["freeze_frame"]["dtc"] == "P0171"
    (engine,) = hub.read_monitors()
    assert {"name": "Evaporative system", "complete": False} in engine["monitors"]


def test_recording_writes_a_session(hub_factory):
    hub = hub_factory(lambda: SimTransport(SimElm(make_focus())))
    wait_for(lambda: state(hub) == "connected")
    started = hub.start_recording("cold start")
    assert started["recording"]["session"] == 1 and started["recording"]["note"] == "cold start"
    wait_for(lambda: hub.status()["recording"]["seconds"] >= 0.1)
    assert hub.stop_recording()["recording"] is None
    assert hub.stop_recording()["recording"] is None  # stopping twice is harmless

    store = Store(hub._db_path)
    (session,) = store.sessions()
    store.close()
    assert session["note"] == "cold start" and session["vin"] == "1FADP3F2XHL123456"
    assert session["cycles"] >= 3 and session["ended_at"] is not None
