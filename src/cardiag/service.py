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
from collections import deque
from concurrent.futures import Future
from typing import Any, Callable

import serial

from . import __version__
from .elm import AdapterError, Elm327, NoVehicle
from .frames import FrameError
from .maker import MakerValue, parse as parse_maker
from .obd import DTC_SERVICES, Obd, Reading, ecu_label
from .pids import PIDS
from .store import Store
from .transport import LinkError, Transport

# Watched when no list has been chosen, where the vehicle supports them.
DEFAULT_LIVE_PIDS = (0x0C, 0x0D, 0x05, 0x04, 0x11, 0x06, 0x07, 0x0B, 0x10, 0x0E, 0x42)

VOLTAGE_KEY = "adapter:voltage"

_LINK_ERRORS = (AdapterError, LinkError, FrameError, serial.SerialException, OSError)

# Passes kept in memory for the Diagnosis and Drive pages: about an hour at four a second.
HISTORY_PASSES = 14400

# A discovery run first asks for every identifier in its range, then keeps re-reading the ones
# that answered. These are how many of each are asked per pass, between the standard values.
SCAN_PER_PASS = 24
READS_PER_PASS = 8
DISCOVERY_INTERVAL = 0.05  # least seconds between passes of a discovery run
MAX_DISCOVERED = 400
# Standard values read alongside a discovery run, to line the unknown bytes up against.
CONTEXT_PIDS = (0x0C, 0x0D, 0x49, 0x11, 0x04, 0x05)

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
        simulators: dict[str, Callable[[], Transport]] | None = None,
        simulation: str | None = None,
    ) -> None:
        self._open_transport = open_transport
        self._simulators = dict(simulators or {})
        if simulation is not None and simulation not in self._simulators:
            raise ValueError(f"there is no simulated vehicle called {simulation!r}")
        self._simulation = simulation  # None means the real adapter
        self._switch = threading.Event()  # set when the source changes, to drop the current link
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
        self._offered: list[dict] = []  # per module: its name and the PIDs it offers
        self._ecus: list[dict] = []  # per module: the address it answers from and its name
        self._maker_ok = False  # whether this network lets maker-specific values be read
        self._maker: list[MakerValue] = []  # maker-specific values read on every pass
        self._history: deque[tuple[float, dict[str, float]]] = deque(maxlen=HISTORY_PASSES)
        self._signals: dict[str, dict] = {}  # name and unit of every value seen
        self.on_recorded: Callable[[], None] | None = None  # called when a recording ends
        self._watch: list[int] | None = None  # None means the default set
        self._readings: list[Reading] = []
        self._elapsed = 0.0
        self._recording: dict | None = None
        self._recording_started = 0.0
        self._discovery: dict | None = None  # progress of a discovery run, for the page
        self._work: dict | None = None  # the run itself; touched by the worker thread only

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
        self._switch.set()
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

    def offered(self) -> list[dict]:
        """Every standard value each module offers, whether or not it is being watched."""
        with self._changed:
            return [{"module": module["module"], "pids": list(module["pids"])} for module in self._offered]

    def history(self) -> tuple[list[tuple[float, dict[str, float]]], dict[str, dict]]:
        """The numeric values of every pass since this car connected, and what they are called."""
        with self._changed:
            return list(self._history), dict(self._signals)

    def modules(self) -> dict:
        """The modules that answer, and whether maker-specific values can be read from them."""
        with self._changed:
            return {"supported": self._maker_ok, "modules": [dict(module) for module in self._ecus]}

    def maker(self) -> list[MakerValue]:
        with self._changed:
            return list(self._maker)

    def set_maker(self, values: list[MakerValue]) -> None:
        with self._changed:
            self._maker = list(values)
        self._wake.set()

    def set_interval(self, seconds: float) -> None:
        """Change the least time between passes. Zero means as fast as the car answers."""
        with self._changed:
            self.interval = seconds
            self._version += 1
            self._changed.notify_all()
        self._wake.set()

    def start_discovery(
        self, module: int, first: int, count: int, *, known: list[int] | None = None, note: str | None = None
    ) -> dict:
        """Begin recording the raw bytes of everything a module answers.

        With `known`, those identifiers are read straight away; otherwise the range is asked through once first.
        """
        self._call(lambda obd: self._begin_discovery(obd, module, first, count, known, note))
        return self.status()

    def stop_discovery(self) -> dict:
        try:
            self._call(lambda obd: self._end_discovery())
        except NotConnected:
            pass  # losing the car already ended the run
        return self.status()

    def scan(self, module: int, first: int, count: int) -> list[tuple[int, bytes]]:
        """Ask one module for a run of maker-specific identifiers; return the ones it has."""

        def job(obd: Obd) -> list[tuple[int, bytes]]:
            found = []
            for identifier in range(first, first + count):
                data = obd.read_identifier(module, identifier)
                if data is not None:
                    found.append((identifier, data))
            return found

        return self._call(job, timeout=120.0)

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

    def set_simulation(self, name: str | None) -> dict:
        """Switch between the real adapter (None) and a simulated vehicle."""
        if name is not None and (not isinstance(name, str) or name not in self._simulators):
            raise ValueError(f"there is no simulated vehicle called {name!r}")
        with self._changed:
            if name != self._simulation:
                self._simulation = name
                self._watch = None  # a different car offers different values
                self._reset("starting", "")
                self._switch.set()
            status = self._status()
        self._wake.set()
        return status

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
            "version": __version__,
            "simulation": self._simulation,
            "simulations": sorted(self._simulators),
            "interval": self.interval,
            "discovery": dict(self._discovery) if self._discovery else None,
            "rate": self._rate(),
            "values": len(self._readings),
        }

    def _rate(self) -> float | None:
        """Passes a second, measured over the latest twenty."""
        recent = list(self._history)[-21:]
        if len(recent) < 2 or recent[-1][0] <= recent[0][0]:
            return None
        return round((len(recent) - 1) / (recent[-1][0] - recent[0][0]), 1)

    def _reset(self, state: str, message: str) -> None:
        self._state, self._message = state, message
        if state != "no_vehicle":
            self._adapter = None  # with no vehicle, the adapter itself was still found
        self._network = self._vin = None
        self._modules, self._available, self._readings = [], [], []
        self._offered, self._ecus, self._maker_ok, self._maker = [], [], False, []
        self._history.clear()
        self._version += 1
        self._changed.notify_all()

    def _watched(self) -> list[int]:
        wanted = DEFAULT_LIVE_PIDS if self._watch is None else self._watch
        return [pid for pid in wanted if pid in self._available]

    # ---- worker thread ------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            transport = None
            with self._changed:
                self._switch.clear()
                simulation = self._simulation
            try:
                transport = (self._simulators[simulation] if simulation else self._open_transport)()
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
                self._end_discovery()
                if transport is not None:
                    try:
                        transport.close()
                    except OSError:
                        pass
            if self._switch.is_set():
                self._fail_jobs("the data source was changed")
            else:
                self._switch.wait(self.retry_delay)  # a change of source cuts the wait short

    def _mark_connected(self, obd: Obd) -> None:
        supported = obd.supported_pids()
        offered = set().union(*supported.values()) if supported else set()
        vin = obd.vin()
        maker = self._saved_maker(vin) if obd.maker_values else []
        with self._changed:
            if self._switch.is_set():
                return  # the source was changed while this one was connecting
            self._state, self._message = "connected", ""
            self._readings = []
            self._network = obd.protocol.name
            self._vin = vin
            self._modules = [ecu_label(ecu, obd.protocol) for ecu in obd.ecus]
            self._available = sorted(pid for pid in offered if pid in PIDS)
            self._offered = [
                {"module": ecu_label(ecu, obd.protocol), "pids": sorted(pid for pid in pids if pid != 0x01)}
                for ecu, pids in sorted(supported.items())
            ]
            self._ecus = [{"reply": f"{ecu:03X}", "name": ecu_label(ecu, obd.protocol)} for ecu in obd.ecus]
            self._maker_ok = obd.maker_values
            self._maker = maker
            self._history.clear()
            self._version += 1
            self._changed.notify_all()

    def _saved_maker(self, vin: str | None) -> list[MakerValue]:
        """The maker-specific values set up for this car, if its saved list still makes sense."""
        store = Store(self._db_path)
        try:
            return parse_maker(store.profile(vin).get("maker") or [])
        except ValueError:
            return []
        finally:
            store.close()

    def _mark_disconnected(self, state: str, message: str) -> None:
        with self._changed:
            if not self._switch.is_set():  # otherwise the state already says "starting"
                self._reset(state, message)
        self._fail_jobs(message)

    def _fail_jobs(self, message: str) -> None:
        while True:
            try:
                _, future = self._jobs.get_nowait()
            except queue.Empty:
                break
            future.set_exception(NotConnected(message))

    def _poll(self, elm: Elm327, obd: Obd) -> None:
        started = time.monotonic()
        silent_passes = 0
        while not self._stop.is_set() and not self._switch.is_set():
            pass_started = time.monotonic()
            self._run_jobs(obd)
            with self._changed:
                watched = self._watched()
                maker = list(self._maker)
                if self._work:  # a discovery run reads a fixed few standard values and nothing else
                    watched, maker = [pid for pid in CONTEXT_PIDS if pid in self._available], []
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
            for value in maker:
                data = obd.read_identifier(value.module, value.identifier)
                number = value.decode(data) if data is not None else None
                if number is not None:
                    samples.append((time.time(), Reading(value.key, value.name, number, value.unit, value.module)))
            voltage = elm.voltage()
            if voltage is not None:
                samples.append(
                    (time.time(), Reading(VOLTAGE_KEY, "Battery voltage at the port", voltage, "V", 0))
                )

            if self._store is not None:
                self._store.add_samples(self._recording["session"], self._record_cycle, samples)
                self._record_cycle += 1
            if self._work:
                self._discover(obd, samples)
            with self._changed:
                if self._switch.is_set():
                    return
                self._readings = [reading for _, reading in samples]
                self._elapsed = pass_started - started
                self._history.append(
                    (self._elapsed, {r.key: r.value for _, r in samples if not isinstance(r.value, str)})
                )
                for _, reading in samples:
                    self._signals[reading.key] = {"name": reading.name, "unit": reading.unit}
                self._version += 1
                self._changed.notify_all()

            # A discovery run ignores the chosen rate, since every pause is identifiers not read, but it
            # still leaves a gap: an adapter that answers at once must not fill the disk or starve the page.
            spare = (DISCOVERY_INTERVAL if self._work else self.interval) - (time.monotonic() - pass_started)
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

    def _begin_discovery(
        self, obd: Obd, module: int, first: int, count: int, known: list[int] | None, note: str | None
    ) -> None:
        if not obd.maker_values:
            raise ValueError("maker-specific values can only be read on an 11-bit CAN network so far")
        if self._work:
            raise ValueError("a discovery run is already going; stop it first")
        store = Store(self._db_path)
        number = store.start_discovery(vin=self._vin, module=f"{module:03X}", note=note or None)
        self._work = {
            "store": store, "id": number, "module": module, "started": time.monotonic(),
            "todo": [] if known else list(range(first, min(0x10000, first + count))),
            "found": list(known or [])[:MAX_DISCOVERED], "cursor": 0, "asked": 0, "readings": 0,
        }
        self._work["range"] = len(self._work["todo"])
        self._publish_discovery()

    def _publish_discovery(self) -> None:
        work = self._work
        with self._changed:
            self._discovery = {
                "id": work["id"], "module": f"{work['module']:03X}",
                "phase": "scanning" if work["todo"] else "capturing",
                "asked": work["asked"], "range": work["range"], "found": len(work["found"]),
                "readings": work["readings"], "seconds": round(time.monotonic() - work["started"], 1),
            }
            self._version += 1
            self._changed.notify_all()

    def _discover(self, obd: Obd, samples: list) -> None:
        """One pass of a discovery run: ask the next few identifiers and keep their bytes."""
        work = self._work
        at = time.monotonic() - work["started"]
        if work["todo"]:
            batch, work["todo"] = work["todo"][:SCAN_PER_PASS], work["todo"][SCAN_PER_PASS:]
            work["asked"] += len(batch)
        else:
            batch = [work["found"][(work["cursor"] + i) % len(work["found"])] for i in range(min(READS_PER_PASS, len(work["found"])))]
            work["cursor"] += len(batch)
        rows = []
        for identifier in batch:
            data = obd.read_identifier(work["module"], identifier)
            if data is None:
                continue
            if identifier not in work["found"] and len(work["found"]) < MAX_DISCOVERED:
                work["found"].append(identifier)
            rows.append((time.monotonic() - work["started"], identifier, data))
        work["readings"] += len(rows)
        context = [(reading.key, reading.value) for _, reading in samples if not isinstance(reading.value, str)]
        work["store"].add_discovery(work["id"], at, rows, context)
        if not work["todo"] and not work["found"]:
            self._end_discovery()  # the whole range was asked and nothing answered: there is nothing to capture
        else:
            self._publish_discovery()

    def _end_discovery(self) -> None:
        if self._work is None:
            return
        self._work["store"].end_discovery(self._work["id"])
        self._work["store"].close()
        self._work = None
        with self._changed:
            self._discovery = None
            self._version += 1
            self._changed.notify_all()

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
        if self.on_recorded:
            self.on_recorded()
