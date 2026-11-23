"""A small web server so a phone, tablet or laptop browser can use the app.

It uses only the standard library, so the box in the car needs nothing beyond
Python and pyserial. There is no login: run it on networks you trust.
"""

from __future__ import annotations

import io
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .elm import AdapterError
from .frames import FrameError
from .service import Hub, NotConnected
from .store import Store

_STATIC = Path(__file__).parent / "web"
_KEEP_ALIVE_SECONDS = 10


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    hub: Hub
    db_path: str | None


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "cardiag"
    server: _Server

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - signature fixed by the base class
        pass  # one line per request would flood the journal at four updates a second

    # ---- routing ------------------------------------------------------------

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        hub = self.server.hub
        if path == "/":
            self._send(200, (_STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/status":
            self._json(hub.status())
        elif path == "/api/values":
            self._json(hub.values())
        elif path == "/api/stream":
            self._stream()
        elif path == "/api/codes":
            self._job(hub.read_codes)
        elif path == "/api/monitors":
            self._job(hub.read_monitors)
        elif path == "/api/sessions":
            self._json(self._sessions())
        elif match := re.fullmatch(r"/api/sessions/(\d+)\.csv", path):
            self._session_csv(int(match.group(1)))
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        hub = self.server.hub
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            self._json({"error": "the request body must be a JSON object"}, 400)
            return

        if path == "/api/watch":
            def change() -> dict:
                hub.set_watch(body.get("pids"))
                return hub.values()

            self._job(change)
        elif path == "/api/record":
            action = body.get("action")
            if action == "start":
                self._job(lambda: hub.start_recording(body.get("note")))
            elif action == "stop":
                self._job(hub.stop_recording)
            else:
                self._json({"error": "action must be 'start' or 'stop'"}, 400)
        else:
            self._json({"error": "not found"}, 404)

    # ---- responses ----------------------------------------------------------

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _job(self, job) -> None:
        """Run something that needs the car, turning failures into JSON errors."""
        try:
            self._json(job())
        except NotConnected as exc:
            self._json({"error": str(exc) or "not connected to a vehicle"}, 503)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        except (AdapterError, FrameError) as exc:
            self._json({"error": str(exc)}, 502)
        except TimeoutError:
            self._json({"error": "the car took too long to answer"}, 504)

    def _stream(self) -> None:
        """Server-sent events: the latest state, pushed each time it changes."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        hub = self.server.hub
        seen = -1
        try:
            while not hub.stopped:
                seen, payload = hub.wait_for_update(seen, _KEEP_ALIVE_SECONDS)
                if payload is None:
                    self.wfile.write(b": keep-alive\n\n")
                else:
                    self.wfile.write(b"data: " + json.dumps(payload).encode() + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser went away

    # ---- recorded sessions --------------------------------------------------

    def _sessions(self) -> list[dict]:
        store = Store(self.server.db_path)
        try:
            return [
                {
                    "id": row["id"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "vin": row["vin"],
                    "note": row["note"],
                    "passes": row["cycles"],
                }
                for row in store.sessions()
            ]
        finally:
            store.close()

    def _session_csv(self, session_id: int) -> None:
        store = Store(self.server.db_path)
        out = io.StringIO(newline="")
        try:
            store.export_csv(session_id, out)
        except KeyError:
            self._json({"error": f"there is no session {session_id}"}, 404)
            return
        finally:
            store.close()
        self._send(
            200,
            out.getvalue().encode("utf-8"),
            "text/csv; charset=utf-8",
            {"Content-Disposition": f'attachment; filename="session-{session_id}.csv"'},
        )


def make_server(hub: Hub, host: str, port: int, db_path: str | None = None) -> ThreadingHTTPServer:
    server = _Server((host, port), _Handler)
    server.hub = hub
    server.db_path = db_path
    return server
