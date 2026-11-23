"""What the glasses app is given: one small reply with the latest values, and the app's own page."""

import urllib.request
from pathlib import Path

import cardiag
from cardiag import analysis
from cardiag.store import Store

from conftest import geared_passes, wait_for

BUILT = Path(cardiag.__file__).parent / "web" / "glasses"


def geared(served) -> None:
    served.request("/api/simulation", {"vehicle": "focus_dct"})
    wait_for(lambda: served.hub.status()["state"] == "connected")


def test_a_glance_holds_the_latest_values(served):
    status, glance = served.request("/api/glance")
    assert status == 200 and glance["state"] == "connected" and glance["vin"] == "1FADP3F2XHL123456"
    assert [reading["key"] for reading in glance["readings"]][:2] == ["01:0C", "01:0D"]
    assert glance["readings"][0] == {"key": "01:0C", "name": "Engine speed", "value": glance["readings"][0]["value"], "unit": "rpm"}
    assert glance["age"] is not None and glance["age"] < 2 and glance["recording"] is None and glance["discovery"] is None
    assert glance["gears_known"] is False and glance["gear"] is None and glance["slip"] is None


def test_it_is_the_one_reply_other_origins_may_read(served):
    with urllib.request.urlopen(served.base + "/api/glance", timeout=10) as response:
        assert response.headers["Access-Control-Allow-Origin"] == "*"
    for path in ("/api/status", "/api/values", "/api/setup", "/"):
        with urllib.request.urlopen(served.base + path, timeout=10) as response:
            assert response.headers["Access-Control-Allow-Origin"] is None, path


def test_gear_and_slip_come_from_the_gears_learned_for_the_car(served):
    geared(served)
    store = Store(served.db_path)
    store.save_profile("1FADP3F2XHL654321", {"gears": analysis.learn_gears(geared_passes())})
    store.close()

    def in_gear() -> bool:
        glance = served.request("/api/glance")[1]
        return glance["gears_known"] and glance["gear"] is not None

    wait_for(in_gear, timeout=12)  # the gears are read again within a few seconds, and the lap starts at a standstill
    glance = served.request("/api/glance")[1]
    if glance["gear"] is not None:  # it may have just come out of gear again
        assert 1 <= glance["gear"] <= 6 and -8 <= glance["slip"] <= 15


def test_a_glance_says_what_else_is_going_on(served):
    served.request("/api/record", {"action": "start"})
    wait_for(lambda: served.request("/api/glance")[1]["recording"] is not None)
    served.request("/api/record", {"action": "stop"})
    assert served.request("/api/glance")[1]["recording"] is None

    geared(served)
    served.request("/api/discover", {"action": "start", "module": "7E9", "first": "1E00", "count": 4096})
    assert served.request("/api/glance")[1]["discovery"] in ("scanning", "capturing")
    served.request("/api/discover", {"action": "stop"})
    assert served.request("/api/glance")[1]["discovery"] is None


def test_with_no_car_there_is_still_an_answer(served):
    served.hub.stop()
    with served.hub._changed:
        served.hub._reset("no_vehicle", "the vehicle stopped answering")
    glance = served.request("/api/glance")[1]
    assert glance["state"] == "no_vehicle" and glance["readings"] == [] and glance["age"] is None and glance["gear"] is None


def test_the_app_is_built_into_the_package():
    page = (BUILT / "index.html").read_text()
    assert "./assets/app.js" in page and (BUILT / "assets" / "app.js").stat().st_size > 10_000
    assert (BUILT / "config.json").read_text().strip() == '{"server": ""}'  # only a packaged build names an address


def test_the_app_is_served_beside_the_page(served):
    status, page = served.request("/glasses/")
    assert status == 200 and "cardiag glasses" in page
    with urllib.request.urlopen(served.base + "/glasses/assets/app.js", timeout=10) as response:
        assert response.status == 200 and response.headers["Content-Type"] == "text/javascript"
    with urllib.request.urlopen(served.base + "/glasses", timeout=10) as response:
        assert response.url.endswith("/glasses/")  # the page's own links need the slash
    for missing in ("/glasses/nothing.js", "/glasses/assets/../../web.py", "/glasses/..%2Findex.html", "/glasses/assets/app.py"):
        assert served.request(missing)[0] == 404, missing
