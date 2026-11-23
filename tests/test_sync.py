"""Sending recordings from the box in the car to a central server."""

import gzip
import json
import urllib.error
import urllib.request

import pytest

from cardiag.store import Store
from cardiag.sync import Uploader, clean_url

from conftest import as_recording, geared_passes, wait_for


def record(served, note: str) -> None:
    served.request("/api/record", {"action": "start", "note": note})
    wait_for(lambda: served.hub.status()["recording"]["seconds"] >= 0.1)
    served.request("/api/record", {"action": "stop"})


def test_recordings_reach_the_central_server_once(served, central):
    record(served, "before the address was set")
    status, state = served.request("/api/central")
    assert status == 200 and state == {"managed": True, "url": None, "waiting": 1, "problem": None, "sent_at": None, "name": "testbox"}

    status, state = served.request("/api/central", {"url": central.base + "/"})
    assert status == 200 and state["url"] == central.base
    wait_for(lambda: served.request("/api/central")[1]["waiting"] == 0)
    record(served, "sent as soon as it ended")
    wait_for(lambda: len(central.request("/api/sessions")[1]) == 2)

    arrived = central.request("/api/sessions")[1]
    assert [(s["origin"], s["note"]) for s in arrived] == [
        ("testbox#1", "before the address was set"), ("testbox#2", "sent as soon as it ended")]
    assert all(s["vin"] == "1FADP3F2XHL123456" and s["passes"] >= 2 for s in arrived)
    assert all(s["sent"] for s in served.request("/api/sessions")[1])
    status, report = central.request("/api/analysis?source=1")
    assert status == 200 and report["passes"] >= 2  # the central server can analyse what it was sent
    assert Store(central.db_path).unsent() == []  # and does not try to send it on again


def test_a_recording_sent_twice_is_kept_once(central):
    body = {"box": "pi", "id": 7, **as_recording(geared_passes(1))}
    first = central.request("/api/ingest", body)
    second = central.request("/api/ingest", body)
    assert first[0] == second[0] == 200
    assert [s["origin"] for s in central.request("/api/sessions")[1]] == ["pi#7"]


def test_compressed_uploads_are_unpacked(central):
    body = gzip.compress(json.dumps({"box": "pi", "id": 1, **as_recording(geared_passes(1))}).encode())
    request = urllib.request.Request(
        central.base + "/api/ingest", data=body, headers={"Content-Type": "application/json", "Content-Encoding": "gzip"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        assert json.loads(response.read())["stored"] == 1


@pytest.mark.parametrize("damage", [
    lambda body: body.pop("box"),
    lambda body: body.update(id="seven"),
    lambda body: body["session"].update(started_at="yesterday"),
    lambda body: body["samples"].append([0, 1.0, "not-a-signal", 1.0, None]),
    lambda body: body.update(samples="lots"),
])
def test_malformed_uploads_are_refused_whole(central, damage):
    body = {"box": "pi", "id": 1, **as_recording(geared_passes(1)[:20])}
    damage(body)
    status, answer = central.request("/api/ingest", body)
    assert status == 400 and answer["error"]
    assert central.request("/api/sessions")[1] == []


def test_a_box_that_is_not_central_takes_no_uploads(served):
    status, _ = served.request("/api/ingest", {"box": "pi", "id": 1, **as_recording(geared_passes(1)[:20])})
    assert status == 404


def test_problems_are_said_plainly_and_nothing_is_lost(served, tmp_path):
    record(served, "kept until it can go")
    served.request("/api/central", {"url": served.base})  # this box does not accept uploads
    wait_for(lambda: served.request("/api/central")[1]["problem"] is not None)
    state = served.request("/api/central")[1]
    assert "--accept-uploads" in state["problem"] and state["waiting"] == 1

    served.request("/api/central", {"url": "http://127.0.0.1:9"})  # nothing listens there
    wait_for(lambda: "could not reach" in (served.request("/api/central")[1]["problem"] or ""))
    assert served.request("/api/central")[1]["waiting"] == 1

    status, state = served.request("/api/central", {"url": ""})
    assert status == 200 and state["url"] is None and state["problem"] is None


def test_addresses_are_tidied_or_refused():
    assert clean_url("cardiag-home:8000/") == "http://cardiag-home:8000"
    assert clean_url("https://car.example.ts.net") == "https://car.example.ts.net"
    assert clean_url("") is None and clean_url(None) is None
    for bad in ("ftp://host", "http://", "http://host/some/path", 12, "x" * 300):
        with pytest.raises(ValueError):
            clean_url(bad)


def test_a_recording_in_progress_is_not_sent(tmp_path):
    db = str(tmp_path / "s.db")
    store = Store(db)
    store.start_session(vin=None, adapter=None, protocol=None)
    store.set_setting("central_url", "http://127.0.0.1:9")
    assert store.unsent() == []
    store.close()
    assert Uploader(db).send_waiting() == 0
