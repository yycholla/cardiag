"""A small web server so a phone, tablet or laptop browser can use the app.

It uses only the standard library, so the box in the car needs nothing beyond
Python and pyserial. There is no login: run it on networks you trust.

Besides the car, the page can switch to a simulated vehicle, and on the box in
the car it can manage the box's Wi-Fi and install updates. Those two are only
offered when the server was started with them (see `cardiag serve --help`).
"""

from __future__ import annotations

import io
import json
import re
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import __version__, garage
from .elm import AdapterError
from .frames import FrameError
from .network import NetworkError, Wifi
from .service import Hub, NotConnected
from .store import Store
from .sync import Uploader
from .update import UpdateError, Updater

_STATIC = Path(__file__).parent / "web"
_KEEP_ALIVE_SECONDS = 10
_MAX_BODY = 64 * 1024 * 1024  # a long recording, compressed, is a few megabytes
_MAX_UNPACKED = 512 * 1024 * 1024


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    hub: Hub
    db_path: str | None
    wifi: Wifi | None
    updater: Updater | None
    uploader: Uploader | None
    accept_uploads: bool  # whether other boxes may send their recordings here
    restarting = False  # set when the server was stopped so that a new version can start

    def restart_soon(self) -> None:
        """Stop serving once the current reply has gone out; whoever runs the app starts it again."""
        self.restarting = True
        threading.Timer(1.0, self.shutdown).start()


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
        elif path == "/api/glance":
            # The one reply other origins may read: the glasses app runs inside another app's page.
            # It only reports values, so nothing that changes the box is opened up with it.
            body = json.dumps(garage.glance(hub, self.server.db_path)).encode()
            self._send(200, body, "application/json", {"Access-Control-Allow-Origin": "*"})
        elif path == "/glasses":
            self._send(301, b"", "text/plain", {"Location": "/glasses/"})
        elif match := re.fullmatch(r"/glasses/((?:[\w-]+/)?[\w.-]*)", path):
            self._glasses(match.group(1) or "index.html")
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
        elif path == "/api/network":
            wifi = self.server.wifi
            self._job(wifi.status if wifi else lambda: {"managed": False})
        elif path == "/api/network/scan":
            self._job(lambda: {"networks": self._wifi().scan()})
        elif path == "/api/update":
            updater = self.server.updater
            self._json(updater.status() if updater else {"managed": False, "current": __version__})
        elif path == "/api/setup":
            self._job(lambda: garage.setup_report(hub, self.server.db_path))
        elif path == "/api/analysis":
            query = parse_qs(urlsplit(self.path).query)
            source, against = query.get("source", ["live"])[0], query.get("against", [""])[0]
            self._job(lambda: garage.report(hub, self.server.db_path, source, against))
        elif path == "/api/central":
            uploader = self.server.uploader
            self._json({"managed": True, **uploader.status()} if uploader else {"managed": False})
        elif path == "/api/presets":
            self._json(garage.presets(hub))
        elif path == "/api/maker":
            self._json(garage.maker_report(hub))
        elif path == "/api/discoveries":
            self._json(garage.discoveries(hub, self.server.db_path))
        elif match := re.fullmatch(r"/api/discoveries/(\d+)(\.csv)?", path):
            number = int(match.group(1))
            if match.group(2):
                self._discovery_csv(number)
            else:
                self._job(lambda: garage.discovery_report(self.server.db_path, number))
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        hub = self.server.hub
        # Browsers only send JSON across sites after asking permission, which this server
        # never gives. Insisting on it keeps other web pages from pressing these buttons.
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            self._json({"error": "the request body must be sent as application/json"}, 415)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 <= length <= _MAX_BODY:
                self._json({"error": "the request body is too large"}, 413)
                return
            raw = self.rfile.read(length)
            if self.headers.get("Content-Encoding", "").lower() == "gzip":
                unpacker = zlib.decompressobj(wbits=31)
                raw = unpacker.decompress(raw, _MAX_UNPACKED)
                if unpacker.unconsumed_tail:
                    self._json({"error": "the request body is too large"}, 413)
                    return
            body = json.loads(raw or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, zlib.error):
            self._json({"error": "the request body must be a JSON object"}, 400)
            return

        if path == "/api/watch":
            def change() -> dict:
                hub.set_watch(body.get("pids"))
                return hub.values()

            self._job(change)
        elif path == "/api/record":
            self._job(lambda: garage.record(hub, body))
        elif path == "/api/simulation":
            self._job(lambda: hub.set_simulation(body.get("vehicle")))
        elif path == "/api/network":
            self._job(lambda: self._change_network(body))
        elif path == "/api/update":
            self._job(lambda: self._update(body.get("action")))
        elif path == "/api/setup/profile":
            self._job(lambda: garage.save_profile(hub, self.server.db_path, body))
        elif path == "/api/setup/baseline":
            self._job(lambda: garage.take_baseline(hub, self.server.db_path, body.get("known_good")))
        elif path == "/api/setup/gears":
            self._job(
                lambda: garage.learn_gears(hub, self.server.db_path, body.get("source"), clear=body.get("action") == "clear")
            )
        elif path == "/api/central":
            self._job(lambda: self._central(body))
        elif path == "/api/maker/values":
            self._job(lambda: garage.save_maker(hub, self.server.db_path, body))
        elif path == "/api/maker/scan":
            self._job(lambda: garage.scan(hub, body))
        elif path == "/api/discover":
            self._job(lambda: garage.change_discovery(hub, self.server.db_path, body))
        elif path == "/api/interval":
            self._job(lambda: garage.set_interval(hub, self.server.db_path, body.get("seconds")))
        elif path == "/api/ingest" and self.server.accept_uploads:
            self._job(lambda: self._ingest(body))
        else:
            self._json({"error": "not found"}, 404)

    # ---- the box itself -------------------------------------------------------

    def _wifi(self) -> Wifi:
        if self.server.wifi is None:
            raise ValueError("Wi-Fi is not managed from this page on this machine")
        return self.server.wifi

    def _change_network(self, body: dict) -> dict:
        wifi = self._wifi()
        action = body.get("action")
        which = body.get("which", "home")
        if action == "save":
            wifi.save(body.get("ssid"), body.get("password"), which)
        elif action == "join":
            wifi.join(which)
        elif action == "hotspot":
            wifi.use_hotspot()
        elif action == "forget":
            wifi.forget(which)
        else:
            raise ValueError("action must be 'save', 'join', 'hotspot' or 'forget'")
        return wifi.status()

    def _update(self, action: object) -> dict:
        updater = self.server.updater
        if updater is None:
            raise ValueError("updates are not installed from this page on this machine")
        if action == "check":
            return updater.check()
        if action == "install":
            result = updater.install()
            self.server.restart_soon()
            return result
        raise ValueError("action must be 'check' or 'install'")

    def _central(self, body: dict) -> dict:
        uploader = self.server.uploader
        if uploader is None:
            raise ValueError("recordings are not sent on from this machine")
        if body.get("action") == "send":
            uploader.wake()
            return {"managed": True, **uploader.status()}
        return {"managed": True, **uploader.set_url(body.get("url"))}

    def _ingest(self, body: dict) -> dict:
        """Keep a recording that another box made."""
        box, number = body.get("box"), body.get("id")
        if not isinstance(box, str) or not 1 <= len(box) <= 64 or isinstance(number, bool) or not isinstance(number, int):
            raise ValueError("a recording must say which box it came from and its number there")
        store = Store(self.server.db_path)
        try:
            return {"stored": store.import_session(f"{box}#{number}", body)}
        finally:
            store.close()

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

    def _glasses(self, name: str) -> None:
        """The app for Even G2 glasses, as it was built into the package (see glasses/ in the repository)."""
        kinds = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
                 ".png": "image/png", ".json": "application/json"}
        target = _STATIC / "glasses" / name
        if ".." in name or target.suffix not in kinds or not target.is_file():
            self._json({"error": "not found"}, 404)
        else:
            self._send(200, target.read_bytes(), kinds[target.suffix])

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
        except KeyError as exc:
            self._json({"error": str(exc.args[0]) if exc.args else "not found"}, 404)
        except (AdapterError, FrameError, NetworkError, UpdateError) as exc:
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
                    "origin": row["origin"],
                    "sent": row["uploaded_at"] is not None,
                }
                for row in store.sessions()
            ]
        finally:
            store.close()

    def _discovery_csv(self, number: int) -> None:
        store = Store(self.server.db_path)
        out = io.StringIO(newline="")
        try:
            store.export_discovery_csv(number, out)
        except KeyError:
            self._json({"error": f"there is no discovery run {number}"}, 404)
            return
        finally:
            store.close()
        self._send(
            200,
            out.getvalue().encode("utf-8"),
            "text/csv; charset=utf-8",
            {"Content-Disposition": f'attachment; filename="discovery-{number}.csv"'},
        )

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


def make_server(
    hub: Hub,
    host: str,
    port: int,
    db_path: str | None = None,
    *,
    wifi: Wifi | None = None,
    updater: Updater | None = None,
    uploader: Uploader | None = None,
    accept_uploads: bool = False,
) -> _Server:
    server = _Server((host, port), _Handler)
    server.hub = hub
    server.db_path = db_path
    server.wifi = wifi
    server.updater = updater
    server.uploader = uploader
    server.accept_uploads = accept_uploads
    return server
