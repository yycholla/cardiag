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
from conftest import wait_for

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


def test_page_script_with_real_server_data(served, tmp_path):
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
