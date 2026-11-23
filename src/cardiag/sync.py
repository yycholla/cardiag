"""Sends finished recordings from the box in the car to a central cardiag server.

The box always records to its own disk first. Whenever it has a way out (the
phone's or tablet's hotspot, say) this sends what the central server has not
seen yet, and keeps trying until each recording has arrived. Nothing about a
drive depends on the link being up.

There is no login here, as with the rest of the app: put both ends on a private
network such as a Tailscale tailnet, and give the central server's address on it.
"""

from __future__ import annotations

import gzip
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from . import __version__
from .store import Store

SETTING = "central_url"
_RETRY_SECONDS = 60.0


def clean_url(text: object) -> str | None:
    """A central server address as typed, tidied; None for "do not send anywhere"."""
    if text in (None, ""):
        return None
    if not isinstance(text, str) or len(text) > 200:
        raise ValueError("the central server address must be text, such as http://cardiag-home:8000")
    address = text.strip()
    if "://" not in address:
        address = "http://" + address
    try:
        parts = urlsplit(address)
        parts.port  # raises for a port that is not a number
        sound = parts.scheme in ("http", "https") and parts.hostname and parts.path in ("", "/") and not parts.query
    except ValueError:
        sound = False
    if not sound:
        raise ValueError("the central server address should look like http://cardiag-home:8000")
    return f"{parts.scheme}://{parts.netloc}"


class Uploader:
    def __init__(self, db_path: str | None, *, name: str | None = None, retry: float = _RETRY_SECONDS) -> None:
        self._db_path = db_path
        self._name = name or socket.gethostname()
        self._retry = retry
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._error: str | None = None
        self._sent_at: float | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="cardiag-upload", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def wake(self) -> None:
        """Something changed (a recording ended, the address was set): look again now."""
        self._wake.set()

    def status(self) -> dict:
        store = Store(self._db_path)
        try:
            url, waiting = store.setting(SETTING), len(store.unsent())
        finally:
            store.close()
        with self._lock:
            return {"url": url, "waiting": waiting, "problem": self._error, "sent_at": self._sent_at, "name": self._name}

    def set_url(self, text: object) -> dict:
        url = clean_url(text)
        store = Store(self._db_path)
        try:
            store.set_setting(SETTING, url)
        finally:
            store.close()
        with self._lock:
            self._error = None
        self.wake()
        return self.status()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.send_waiting()
            except Exception as exc:  # a failed upload must never stop the next attempt
                with self._lock:
                    self._error = f"could not send recordings ({exc})"
            self._wake.wait(self._retry)
            self._wake.clear()

    def send_waiting(self) -> int:
        """Send every recording the central server has not had. Returns how many went."""
        store = Store(self._db_path)
        sent = 0
        try:
            url = store.setting(SETTING)
            if not url:
                return 0
            for session_id in store.unsent():
                if self._stop.is_set():
                    break
                body = {"box": self._name, "id": session_id, **store.export_session(session_id)}
                problem = self._post(url + "/api/ingest", body)
                with self._lock:
                    self._error = problem
                if problem:
                    break
                store.mark_sent(session_id)
                sent += 1
                with self._lock:
                    self._sent_at = time.time()
        finally:
            store.close()
        return sent

    def _post(self, url: str, body: dict) -> str | None:
        """Send one recording. Returns None when it arrived, else why it did not."""
        request = urllib.request.Request(
            url,
            data=gzip.compress(json.dumps(body).encode()),
            headers={
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
                "User-Agent": f"cardiag/{__version__}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            try:
                said = json.loads(exc.read()).get("error")
            except (ValueError, AttributeError):
                said = None
            if exc.code == 404:
                return "the central server is not accepting recordings; start it with --accept-uploads"
            return f"the central server refused the recording: {said or exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError):
            return "could not reach the central server; recordings are kept here and sent when it answers"
        return None
