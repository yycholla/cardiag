import json
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import serial

import cardiag
from cardiag.network import Wifi
from cardiag.service import Hub
from cardiag.sim import VEHICLES, SimElm, SimTransport, make_focus
from cardiag.sync import Uploader
from cardiag.update import Updater
from cardiag.web import make_server


def wait_for(condition, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)


class Served:
    """A running web server backed by a simulated Focus."""

    def __init__(self, base: str, hub: Hub, db_path: str) -> None:
        self.base, self.hub, self.db_path = base, hub, db_path

    def request(self, path: str, body: dict | bytes | None = None) -> tuple[int, object]:
        data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, _decode(response)
        except urllib.error.HTTPError as error:
            return error.code, _decode(error)

    def stream_events(self, count: int) -> list[dict]:
        """The next `count` updates from the live stream."""
        events = []
        with urllib.request.urlopen(self.base + "/api/stream", timeout=10) as response:
            while len(events) < count:
                line = response.readline()
                if line.startswith(b"data: "):
                    events.append(json.loads(line[6:]))
        return events


def _decode(response):
    raw = response.read()
    if "json" in response.headers.get("Content-Type", ""):
        return json.loads(raw)
    return raw.decode("utf-8")


def _simulators() -> dict:
    vehicles = {name: make() for name, make in VEHICLES.items()}
    return {name: (lambda v=vehicle: SimTransport(SimElm(v))) for name, vehicle in vehicles.items()}


def _serve(tmp_path, **parts):
    """A web server whose "real" car is a simulated Focus, so nothing here needs an adapter."""
    db_path = str(tmp_path / "sessions.db")
    hub = Hub(
        lambda: SimTransport(SimElm(make_focus())),
        db_path=db_path,
        interval=0.02,
        retry_delay=0.05,
        simulators=_simulators(),
    )
    parts.setdefault("uploader", Uploader(db_path, name="testbox", retry=0.05))
    server = make_server(hub, "127.0.0.1", 0, db_path, **parts)
    hub.on_recorded = parts["uploader"].wake
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    hub.start()
    parts["uploader"].start()
    thread.start()
    try:
        wait_for(lambda: hub.status()["state"] == "connected")
        client = Served(f"http://127.0.0.1:{server.server_address[1]}", hub, db_path)
        client.server, client.thread = server, thread
        yield client
    finally:
        hub.stop()
        parts["uploader"].stop()
        server.shutdown()
        server.server_close()


@pytest.fixture
def served(tmp_path):
    """The app as it runs on a laptop: no Wi-Fi control, no updates."""
    yield from _serve(tmp_path)


@pytest.fixture
def central(tmp_path):
    """A second copy of the app, as a central server that takes recordings from boxes."""
    home = tmp_path / "central"
    home.mkdir()
    yield from _serve(home, accept_uploads=True)


def geared_passes(laps: int = 2, every: float = 0.25) -> list:
    """Passes from the simulated geared Focus, as the adapter would report them."""
    from cardiag import analysis as a
    from cardiag.sim import _DCT_LAP, _DCT_STEP, _dct_lap

    lap, stride = _dct_lap(), round(every / _DCT_STEP)
    return [
        (
            n * _DCT_LAP + i * _DCT_STEP,
            {a.RPM: round(rpm * 4) / 4, a.SPEED: float(round(speed)), a.PEDAL: pedal, a.THROTTLE: max(8.0, pedal), a.LOAD: load},
        )
        for n in range(laps)
        for i, (rpm, speed, pedal, load) in list(enumerate(lap))[::stride]
    ]


def as_recording(passes: list, vin: str = "1FADP3F2XHL654321") -> dict:
    """Passes in the shape one box sends another."""
    keys = sorted({key for _, values in passes for key in values})
    return {
        "session": {"started_at": 1000.0, "ended_at": 1000.0 + passes[-1][0], "vin": vin, "adapter": "test", "protocol": "CAN", "note": "geared drive"},
        "signals": [[key, key, ""] for key in keys],
        "samples": [[cycle, 1000.0 + t, key, value, None] for cycle, (t, values) in enumerate(passes) for key, value in values.items()],
    }


@pytest.fixture
def nm():
    from test_network import FakeNetworkManager

    return FakeNetworkManager()


@pytest.fixture
def github():
    from test_update import FakeGitHub

    github = FakeGitHub()
    yield github
    github.server.shutdown()
    github.server.server_close()


@pytest.fixture
def home(tmp_path):
    """An installed copy of the app, at the version of this checkout."""
    package = Path(cardiag.__file__).parent
    home = tmp_path / "opt"
    skip = shutil.ignore_patterns("__pycache__")
    shutil.copytree(package, home / "releases" / cardiag.__version__ / "src" / "cardiag", ignore=skip)
    (home / "current").symlink_to(f"releases/{cardiag.__version__}")
    shutil.copytree(Path(serial.__file__).parent, home / "vendor" / "serial", ignore=skip)
    return home


@pytest.fixture
def box(tmp_path, nm, github, home):
    """The app as it runs on the box in the car: it manages Wi-Fi and installs updates."""
    wifi = Wifi(run=nm, settle=0.01, watch_interval=0.02)
    try:
        for client in _serve(tmp_path, wifi=wifi, updater=Updater(home, api=github.url)):
            client.nm, client.github, client.home = nm, github, home
            yield client
    finally:
        wifi.stop()
