"""Keeps one connection to the car and shares it between web clients.

The adapter can only hold one conversation at a time, so a single worker thread
owns it. Everything else either reads the latest values from here or asks the
worker to run a job. The worker also keeps retrying when the adapter is
unplugged or the ignition is off, which is what a box left in the car needs.
"""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable

import serial

from .elm import AdapterError, Elm327, NoVehicle
from .frames import FrameError
from .obd import DTC_SERVICES, Obd, Reading, ecu_label
from .pids import PIDS
from .store import Store
from .transport import LinkError, Transport

# Watched when no list has been chosen, where the vehicle supports them.
DEFAULT_LIVE_PIDS = (0x0C, 0x0D, 0x05, 0x04, 0x11, 0x06, 0x07, 0x0B, 0x10, 0x0E, 0x42)

VOLTAGE_KEY = "adapter:voltage"

_LINK_ERRORS = (AdapterError, LinkError, FrameError, serial.SerialException, OSError)

# After this many passes with no answer at all, the car is treated as switched off.
_SILENT_PASSES_ALLOWED = 3


class NotConnected(Exception):
    """A request needs the car, and the car is not connected."""


def reading_json(reading: Reading) -> dict:
    value = reading.value if isinstance(reading.value, str) else round(reading.value, 3)
    return {"key": reading.key, "name": reading.name, "value": value, "unit": reading.unit}


def codes_report(obd: Obd) -> dict:
    status = obd.monitor_status()
    found = {kind: obd.read_dtcs(kind) for kind in DTC_SERVICES}
    frame = obd.freeze_frame()
    return {
        "mil_on": any(s.mil_on for s in status) if status else None,
        "modules": [
            # A kind is None when the module did not answer that request at all.
            {"label": ecu_label(ecu, obd.protocol), **{kind: found[kind].get(ecu) for kind in DTC_SERVICES}}
            for ecu in sorted({ecu for by_ecu in found.values() for ecu in by_ecu})
        ],
        "freeze_frame": None
        if frame is None
        else {
            "dtc": frame.dtc,
            "label": ecu_label(frame.ecu, obd.protocol),
            "readings": [reading_json(reading) for reading in frame.readings],
        },
    }


def monitors_report(obd: Obd) -> list[dict]:
    return [
        {
            "label": ecu_label(status.ecu, obd.protocol),
            "mil_on": status.mil_on,
            "dtc_count": status.dtc_count,
            "ignition": status.ignition,
            "monitors": [{"name": m.name, "complete": m.complete} for m in status.monitors],
        }
        for status in obd.monitor_status()
    ]


class Hub:
    def __init__(
        self,
        open_transport: Callable[[], Transport],
        *,
        db_path: str | None = None,
        interval: float = 0.25,
        retry_delay: float = 3.0,
    ) -> None:
        self._open_transport = open_transport
        self._db_path = db_path
        self.interval = interval
        self.retry_delay = retry_delay

        self._changed = threading.Condition()  # guards everything below, and announces updates
        self._version = 0
        self._state = "starting"  # starting | no_adapter | no_vehicle | connected
        self._message = ""
        self._adapter: str | None = None
        self._network: str | None = None
        self._vin: str | None = None
        self._modules: list[str] = []
        self._available: list[int] = []
        self._watch: list[int] | None = None  # None means the default set
        self._readings: list[Reading] = []
        self._elapsed = 0.0
        self._recording: dict | None = None
        self._recording_started = 0.0

        self._jobs: queue.SimpleQueue[tuple[Callable[[Obd], Any], Future]] = queue.SimpleQueue()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Touched by the worker thread only; SQLite connections are tied to their thread.
        self._store: Store | None = None
        self._record_cycle = 0

    # ---- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="cardiag-hub", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        with self._changed:
            self._changed.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    # ---- called from any thread -------------------------------------------

    def status(self) -> dict:
        with self._changed:
            return self._status()

    def values(self) -> dict:
        """The live values this vehicle offers, and which of them are being watched."""
        with self._changed:
            return {
                "available": [
                    {"pid": f"{pid:02X}", "name": PIDS[pid].name, "unit": PIDS[pid].unit}
                    for pid in self._available
                ],
                "watched": [f"{pid:02X}" for pid in self._watched()],
            }

    def set_watch(self, pids: list[str]) -> None:
        try:
            wanted = list(dict.fromkeys(int(pid, 16) for pid in pids))
        except (TypeError, ValueError):
            raise ValueError("expected a list of hex PIDs such as ['0C', '0D']") from None
        with self._changed:
            if self._state != "connected":
                raise NotConnected(self._message or "not connected to a vehicle")
            unknown = [f"{pid:02X}" for pid in wanted if pid not in self._available]
            if unknown:
                raise ValueError(f"this vehicle does not offer PID {', '.join(unknown)}")
            self._watch = wanted
        self._wake.set()

    def wait_for_update(self, seen: int, timeout: float) -> tuple[int, dict | None]:
        """Block until something changes. Returns the new version and the latest state."""
        with self._changed:
            self._changed.wait_for(lambda: self._version != seen or self._stop.is_set(), timeout)
            if self._version == seen:
                return seen, None
            return self._version, {
                "status": self._status(),
                "elapsed": round(self._elapsed, 2),
                "readings": [reading_json(reading) for reading in self._readings],
            }

    def read_codes(self) -> dict:
        return self._call(codes_report)

    def read_monitors(self) -> list[dict]:
        return self._call(monitors_report)

    def start_recording(self, note: str | None = None) -> dict:
        self._call(lambda obd: self._begin_recording(note))
        return self.status()

    def stop_recording(self) -> dict:
        try:
            self._call(lambda obd: self._end_recording())
        except NotConnected:
            pass  # losing the car already closed the recording
        return self.status()

    def _call(self, job: Callable[[Obd], Any], timeout: float = 30.0) -> Any:
        with self._changed:
            if self._state != "connected":
                raise NotConnected(self._message or "not connected to a vehicle")
        future: Future = Future()
        self._jobs.put((job, future))
        self._wake.set()
        return future.result(timeout)

    # ---- shared state; call with the lock held -------------------------------

    def _status(self) -> dict:
        recording = None
        if self._recording:
            # Elapsed time comes from this machine's steady clock, so it stays right
            # even when the wall clock is wrong, as on a Pi with no network.
            elapsed = time.monotonic() - self._recording_started
            recording = {**self._recording, "seconds": round(elapsed, 1)}
        return {
            "state": self._state,
            "message": self._message,
            "adapter": self._adapter,
            "network": self._network,
            "vin": self._vin,
            "modules": list(self._modules),
            "recording": recording,
        }

    def _watched(self) -> list[int]:
        wanted = DEFAULT_LIVE_PIDS if self._watch is None else self._watch
        return [pid for pid in wanted if pid in self._available]

    # ---- worker thread ------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            transport = None
            try:
                transport = self._open_transport()
                elm = Elm327(transport)
                info = elm.initialise()
                with self._changed:
                    self._adapter = info.label
                obd = Obd(elm)
                obd.connect()
                self._mark_connected(obd)
                self._poll(elm, obd)
            except NoVehicle as exc:
                self._mark_disconnected("no_vehicle", str(exc))
            except _LINK_ERRORS as exc:
                self._mark_disconnected("no_adapter", str(exc))
            finally:
                self._end_recording()
                if transport is not None:
                    try:
                        transport.close()
                    except OSError:
                        pass
            self._stop.wait(self.retry_delay)

    def _mark_connected(self, obd: Obd) -> None:
        supported = obd.supported_pids()
        offered = set().union(*supported.values()) if supported else set()
        vin = obd.vin()
        with self._changed:
            self._state, self._message = "connected", ""
            self._network = obd.protocol.name
            self._vin = vin
            self._modules = [ecu_label(ecu, obd.protocol) for ecu in obd.ecus]
            self._available = sorted(pid for pid in offered if pid in PIDS)
            self._version += 1
            self._changed.notify_all()

    def _mark_disconnected(self, state: str, message: str) -> None:
        with self._changed:
            self._state, self._message = state, message
            if state == "no_adapter":
                self._adapter = None
            self._network = self._vin = None
            self._modules, self._available, self._readings = [], [], []
            self._version += 1
            self._changed.notify_all()
        while True:
            try:
                _, future = self._jobs.get_nowait()
            except queue.Empty:
                break
            future.set_exception(NotConnected(message))

    def _poll(self, elm: Elm327, obd: Obd) -> None:
        started = time.monotonic()
        silent_passes = 0
        while not self._stop.is_set():
            pass_started = time.monotonic()
            self._run_jobs(obd)
            with self._changed:
                watched = self._watched()
            samples = []
            for pid in watched:
                reading = obd.read_pid(pid)
                if reading is not None:
                    samples.append((time.time(), reading))
            if watched and not samples:
                silent_passes += 1
                if silent_passes >= _SILENT_PASSES_ALLOWED:
                    raise NoVehicle("the vehicle stopped answering; is the ignition still on?")
            else:
                silent_passes = 0
            voltage = elm.voltage()
            if voltage is not None:
                samples.append(
                    (time.time(), Reading(VOLTAGE_KEY, "Battery voltage at the port", voltage, "V", 0))
                )

            if self._store is not None:
                self._store.add_samples(self._recording["session"], self._record_cycle, samples)
                self._record_cycle += 1
            with self._changed:
                self._readings = [reading for _, reading in samples]
                self._elapsed = pass_started - started
                self._version += 1
                self._changed.notify_all()

            spare = self.interval - (time.monotonic() - pass_started)
            if spare > 0 and self._jobs.empty():
                self._wake.wait(spare)
            self._wake.clear()

    def _run_jobs(self, obd: Obd) -> None:
        while True:
            try:
                job, future = self._jobs.get_nowait()
            except queue.Empty:
                return
            try:
                future.set_result(job(obd))
            except Exception as exc:  # reported to whoever asked; polling carries on
                future.set_exception(exc)

    def _begin_recording(self, note: str | None) -> None:
        if self._store is not None:
            return
        store = Store(self._db_path)
        session = store.start_session(
            vin=self._vin, adapter=self._adapter, protocol=self._network, note=note or None
        )
        self._store, self._record_cycle = store, 0
        with self._changed:
            self._recording = {"session": session, "note": note or ""}
            self._recording_started = time.monotonic()
            self._version += 1
            self._changed.notify_all()

    def _end_recording(self) -> None:
        if self._store is None:
            return
        self._store.end_session(self._recording["session"])
        self._store.close()
        self._store = None
        with self._changed:
            self._recording = None
            self._version += 1
            self._changed.notify_all()
