"""The web server's endpoints, over real HTTP against a simulated Focus."""

import csv
import io
import os
import threading
import urllib.error
import urllib.request

import pytest

import cardiag

from cardiag.service import Hub
from cardiag.sim import SimElm, SimTransport
from cardiag.web import make_server

from conftest import Served, wait_for


def test_page_is_served(served):
    status, page = served.request("/")
    assert status == 200
    assert "<title>cardiag</title>" in page


def test_status_and_values(served):
    status, body = served.request("/api/status")
    assert status == 200 and body["state"] == "connected" and body["vin"] == "1FADP3F2XHL123456"
    status, values = served.request("/api/values")
    assert status == 200
    assert {"pid": "0C", "name": "Engine speed", "unit": "rpm"} in values["available"]
    assert values["watched"][:2] == ["0C", "0D"]


def test_live_stream_pushes_updates(served):
    first, second = served.stream_events(2)
    assert first["status"]["state"] == "connected"
    assert [r["key"] for r in first["readings"]][:2] == ["01:0C", "01:0D"]
    assert second["elapsed"] > first["elapsed"]


def test_codes_and_monitors(served):
    status, codes = served.request("/api/codes")
    assert status == 200
    assert [m["stored"] for m in codes["modules"]] == [["P0171"], ["P0902"]]
    status, monitors = served.request("/api/monitors")
    assert status == 200 and monitors[0]["dtc_count"] == 1


def test_changing_the_watched_values(served):
    status, values = served.request("/api/watch", {"pids": ["05", "0C"]})
    assert status == 200 and values["watched"] == ["05", "0C"]
    status, body = served.request("/api/watch", {"pids": ["99"]})
    assert status == 400 and "does not offer PID 99" in body["error"]
    status, body = served.request("/api/watch", {})
    assert status == 400


def test_record_then_list_and_download(served):
    status, body = served.request("/api/record", {"action": "start", "note": "idle check"})
    assert status == 200 and body["recording"]["session"] == 1
    wait_for(lambda: served.hub.status()["recording"]["seconds"] >= 0.15)
    status, body = served.request("/api/record", {"action": "stop"})
    assert status == 200 and body["recording"] is None

    status, sessions = served.request("/api/sessions")
    assert status == 200
    (session,) = sessions
    assert session["note"] == "idle check" and session["passes"] >= 3 and session["ended_at"] is not None

    status, text = served.request("/api/sessions/1.csv")
    assert status == 200
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][:3] == ["seconds", "Engine speed (rpm)", "Vehicle speed (km/h)"]
    assert rows[0][-1] == "Battery voltage at the port (V)"
    assert len(rows) >= 4

    status, body = served.request("/api/sessions/7.csv")
    assert status == 404 and "no session 7" in body["error"]


def test_bad_requests_get_clear_errors(served):
    assert served.request("/nope")[0] == 404
    assert served.request("/api/nope", {})[0] == 404
    status, body = served.request("/api/record", {"action": "pause"})
    assert status == 400 and "start" in body["error"]
    status, body = served.request("/api/record", b"not json")
    assert status == 400


def test_car_requests_fail_cleanly_when_nothing_is_connected(tmp_path):
    hub = Hub(lambda: SimTransport(SimElm(None)), db_path=str(tmp_path / "s.db"), retry_delay=0.05)
    server = make_server(hub, "127.0.0.1", 0, str(tmp_path / "s.db"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    hub.start()
    try:
        wait_for(lambda: hub.status()["state"] == "no_vehicle")
        client = Served(f"http://127.0.0.1:{server.server_address[1]}", hub, "")
        status, body = client.request("/api/codes")
        assert status == 503 and "ignition" in body["error"]
        status, body = client.request("/api/record", {"action": "start"})
        assert status == 503
        assert client.request("/api/record", {"action": "stop"})[0] == 200
        assert client.request("/api/sessions") == (200, [])
    finally:
        hub.stop()
        server.shutdown()
        server.server_close()


# ---- settings: simulation, Wi-Fi and updates --------------------------------

def test_switching_to_a_simulated_vehicle(served):
    status, body = served.request("/api/simulation", {"vehicle": "tahoe"})
    assert status == 200 and body["simulation"] == "tahoe" and body["simulations"] == ["focus", "tahoe"]
    wait_for(lambda: served.hub.status()["network"] == "SAE J1850 VPW")
    status, body = served.request("/api/simulation", {"vehicle": None})
    assert status == 200 and body["simulation"] is None
    status, body = served.request("/api/simulation", {"vehicle": "delorean"})
    assert status == 400 and "no simulated vehicle" in body["error"]


def test_changes_must_be_sent_as_json(served):
    request = urllib.request.Request(served.base + "/api/simulation", data=b'{"vehicle": "tahoe"}')
    with pytest.raises(urllib.error.HTTPError) as refused:  # what a form on another web page would send
        urllib.request.urlopen(request, timeout=10)
    assert refused.value.code == 415
    assert served.hub.status()["simulation"] is None


def test_a_laptop_does_not_offer_wifi_or_updates(served):
    assert served.request("/api/network") == (200, {"managed": False})
    assert served.request("/api/update") == (200, {"managed": False, "current": cardiag.__version__})
    for path, body in [("/api/network/scan", None), ("/api/network", {"action": "join"}), ("/api/update", {"action": "install"})]:
        status, answer = served.request(path, body)
        assert status == 400 and "on this machine" in answer["error"]


def test_saving_and_joining_a_network_from_the_page(box):
    status, body = box.request("/api/network")
    assert status == 200 and body["managed"] and body["mode"] == "hotspot" and body["saved"] is None
    status, body = box.request("/api/network/scan")
    assert status == 200 and body["networks"][0] == {"ssid": "Home", "signal": 82, "security": "WPA2"}

    status, body = box.request("/api/network", {"action": "save", "ssid": "Home", "password": "short"})
    assert status == 400 and "8 to 63 characters" in body["error"]
    status, body = box.request("/api/network", {"action": "save", "ssid": "Home", "password": "correct horse"})
    assert status == 200 and body["saved"] == "Home" and body["mode"] == "hotspot"
    assert "correct horse" not in str(body)  # the password is never sent back

    status, body = box.request("/api/network", {"action": "join"})
    assert status == 200 and body["switching"] == "Home"
    wait_for(lambda: box.request("/api/network")[1]["mode"] == "wifi")
    status, body = box.request("/api/network", {"action": "hotspot"})
    assert status == 200
    wait_for(lambda: box.request("/api/network")[1]["mode"] == "hotspot")
    status, body = box.request("/api/network", {"action": "forget"})
    assert status == 200 and body["saved"] is None

    status, body = box.request("/api/network", {"action": "reboot"})
    assert status == 400 and "'save', 'join', 'hotspot' or 'forget'" in body["error"]
    box.nm.broken = True
    status, body = box.request("/api/network")
    assert status == 502 and "not running" in body["error"]


def test_installing_an_update_from_the_page_restarts_the_app(box):
    assert box.request("/api/update") == (200, {"managed": True, "current": cardiag.__version__, "rolled_back": None})
    status, body = box.request("/api/update", {"action": "check"})
    assert status == 502 and "no release has been published yet" in body["error"]

    box.github.publish("9.0.0", notes="Reads more codes.")
    status, body = box.request("/api/update", {"action": "check"})
    assert status == 200 and body["available"] and body["latest"] == "9.0.0" and body["notes"] == "Reads more codes."
    status, body = box.request("/api/update", {"action": "nonsense"})
    assert status == 400

    assert not box.server.restarting
    status, body = box.request("/api/update", {"action": "install"})
    assert (status, body) == (200, {"installed": "9.0.0"})
    assert os.readlink(box.home / "current") == "releases/9.0.0"
    box.thread.join(timeout=10)  # the server stops itself, so that it can be started again as 9.0.0
    assert box.server.restarting and not box.thread.is_alive()
