"""Runs the web page's own script, outside a browser, against real server responses.

This catches script errors and mismatches between what the server sends and
what the page expects. It cannot check layout or styling. It needs a JavaScript
engine: Node.js or QuickJS (`qjs`) on the PATH or next to the Python
interpreter, or one named in CARDIAG_JS_ENGINE. Without one it is skipped.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import cardiag
from cardiag.store import Store
from conftest import as_recording, geared_passes, wait_for

def _find_engine() -> str | None:
    """The first candidate that actually runs; a version-manager shim may exist but not work."""
    search = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
    candidates = [
        os.environ.get("CARDIAG_JS_ENGINE"),
        shutil.which("node", path=search),
        shutil.which("qjs", path=search),
    ]
    for candidate in filter(None, candidates):
        try:
            probe = subprocess.run(
                [candidate, "-e", "console.log('ready')"], capture_output=True, text=True, timeout=30
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0 and "ready" in probe.stdout:
            return candidate
    return None


ENGINE = _find_engine()
TESTS = Path(__file__).parent
PAGE = Path(cardiag.__file__).parent / "web" / "index.html"

pytestmark = pytest.mark.skipif(ENGINE is None, reason="needs Node.js or QuickJS to run the page's script")


def test_page_script_with_real_server_data(box, tmp_path):
    served = box
    html = PAGE.read_text(encoding="utf-8")
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)

    data = {"live": served.stream_events(12)}
    data["values"] = served.request("/api/values")[1]
    data["codes"] = served.request("/api/codes")[1]
    data["monitors"] = served.request("/api/monitors")[1]
    data["recording"] = served.request("/api/record", {"action": "start", "note": "idle check"})[1]
    wait_for(lambda: served.hub.status()["recording"]["seconds"] >= 0.1)
    served.request("/api/record", {"action": "stop"})
    data["sessions"] = served.request("/api/sessions")[1]

    data["setup"] = served.request("/api/setup")[1]
    data["profile"] = served.request("/api/setup/profile", {"engine_litres": "2.0", "transmission": "dual-clutch automatic"})[1]
    store = Store(served.db_path)
    data["drive_id"] = store.import_session("elsewhere#1", as_recording(geared_passes(), vin=served.hub.status()["vin"]))
    store.close()
    data["sessions_after"] = served.request("/api/sessions")[1]
    data["gears"] = served.request("/api/setup/gears", {"source": data["drive_id"]})[1]
    data["analysis_live"] = served.request("/api/analysis")[1]
    data["analysis_drive"] = served.request(f"/api/analysis?source={data['drive_id']}&against={data['drive_id']}")[1]

    data["simulating"] = served.request("/api/simulation", {"vehicle": "tahoe"})[1]
    wait_for(lambda: served.hub.status()["state"] == "connected")
    data["tahoe"] = served.stream_events(1)[0]
    served.request("/api/simulation", {"vehicle": None})
    wait_for(lambda: served.hub.status()["state"] == "connected")

    network = lambda body=None: served.request("/api/network", body)[1]  # noqa: E731
    data["network"] = network()
    data["scan"] = served.request("/api/network/scan")[1]
    data["network_saved"] = network({"action": "save", "ssid": "Home", "password": "correct horse"})
    data["network_joining"] = network({"action": "join"})
    wait_for(lambda: network()["mode"] == "wifi")
    data["network_joined"] = network()
    data["network_leaving"] = network({"action": "hotspot"})
    wait_for(lambda: network()["mode"] == "hotspot")
    data["network_uplink"] = network({"action": "save", "which": "uplink", "ssid": "iPad", "password": "tablet-pass"})

    data["central"] = served.request("/api/central")[1]
    data["update"] = served.request("/api/update")[1]
    box.github.publish("9.0.0", notes="Reads more codes.")
    data["update_found"] = served.request("/api/update", {"action": "check"})[1]
    data["update_installed"] = served.request("/api/update", {"action": "install"})[1]
    assert not [name for name, value in data.items() if isinstance(value, dict) and "error" in value]

    ids = re.findall(r'\bid="([^"]+)"', html)
    program = "\n".join(
        [
            f"const PAGE_IDS = {json.dumps(ids)};",
            f"const DATA = {json.dumps(data)};",
            (TESTS / "page_dom.js").read_text(encoding="utf-8"),
            script,
            (TESTS / "page_scenario.js").read_text(encoding="utf-8"),
        ]
    )
    path = tmp_path / "page_test.js"
    path.write_text(program, encoding="utf-8")
    result = subprocess.run([ENGINE, str(path)], capture_output=True, text=True, timeout=60)
    assert "PAGE-OK" in result.stdout, result.stdout + result.stderr
