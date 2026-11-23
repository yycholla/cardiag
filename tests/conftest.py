import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cardiag.service import Hub
from cardiag.sim import SimElm, SimTransport, make_focus
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
        request = urllib.request.Request(self.base + path, data=data)
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


@pytest.fixture
def served(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    hub = Hub(lambda: SimTransport(SimElm(make_focus())), db_path=db_path, interval=0.02, retry_delay=0.05)
    server = make_server(hub, "127.0.0.1", 0, db_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    hub.start()
    thread.start()
    try:
        wait_for(lambda: hub.status()["state"] == "connected")
        yield Served(f"http://127.0.0.1:{server.server_address[1]}", hub, db_path)
    finally:
        hub.stop()
        server.shutdown()
        server.server_close()
