"""Command-line front end."""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import IO, Iterator

import serial
from serial.tools import list_ports

from . import __version__
from .elm import AdapterError, AdapterInfo, Elm327, NoVehicle
from .network import Wifi
from .frames import FrameError
from .obd import DTC_SERVICES, Obd, Reading, ecu_label
from .service import DEFAULT_LIVE_PIDS, Hub
from .sim import VEHICLES, PtyAdapter, SimElm, SimTransport
from .store import Store
from .transport import LinkError, SerialTransport
from .update import Updater
from .web import make_server

_FTDI_VENDOR_ID = 0x0403  # the USB chip in the OBDLink EX and most USB adapters
_CONFIRM_AFTER_SECONDS = 10


def _likely_adapters() -> list:
    return [
        port
        for port in list_ports.comports()
        if port.vid == _FTDI_VENDOR_ID
        or "obd" in f"{port.description} {port.product or ''} {port.manufacturer or ''}".lower()
    ]


def find_port() -> str:
    likely = _likely_adapters()
    if len(likely) == 1:
        return likely[0].device
    if not likely:
        raise LinkError(
            "no OBD adapter found; plug it in, or name its port with --port "
            "(run 'cardiag ports' to list serial ports, or use --sim focus to try without one)"
        )
    names = ", ".join(port.device for port in likely)
    raise LinkError(f"several possible adapters found ({names}); pick one with --port")


@contextmanager
def open_adapter(args: argparse.Namespace) -> Iterator[tuple[Elm327, AdapterInfo]]:
    if args.sim:
        transport = SimTransport(SimElm(VEHICLES[args.sim]()))
    else:
        transport = SerialTransport(args.port or find_port(), args.baud)
    try:
        elm = Elm327(transport)
        yield elm, elm.initialise()
    finally:
        transport.close()


@contextmanager
def open_vehicle(args: argparse.Namespace) -> Iterator[tuple[Obd, AdapterInfo]]:
    with open_adapter(args) as (elm, info):
        obd = Obd(elm)
        obd.connect()
        yield obd, info


def _fmt(value: float | str) -> str:
    if isinstance(value, str):
        return value
    if float(value).is_integer() or abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.1f}" if abs(value) >= 10 else f"{value:.2f}"


def _reading_line(reading: Reading) -> str:
    return f"  {reading.name:<38} {_fmt(reading.value):>8} {reading.unit}".rstrip()


def cmd_info(args: argparse.Namespace) -> int:
    with open_adapter(args) as (elm, info):
        print(f"Adapter   {info.label}")
        if info.voltage is not None:
            print(f"Battery   {info.voltage:.1f} V at the diagnostic port")
        obd = Obd(elm)
        try:
            protocol = obd.connect()
        except NoVehicle as exc:
            print(f"Vehicle   not detected: {exc}")
            return 1
        print(f"Network   {protocol.name}")
        print(f"VIN       {obd.vin() or 'not reported'}")
        print(f"Modules   {', '.join(ecu_label(ecu, protocol) for ecu in obd.ecus)}")
    return 0


def cmd_codes(args: argparse.Namespace) -> int:
    with open_vehicle(args) as (obd, _):
        status = obd.monitor_status()
        found = {kind: obd.read_dtcs(kind) for kind in DTC_SERVICES}
        ecus = sorted({ecu for by_ecu in found.values() for ecu in by_ecu})
        if status:
            print(f"Check-engine light: {'ON' if any(s.mil_on for s in status) else 'off'}")
        if not ecus:
            print("No module answered the trouble-code requests.")
        for ecu in ecus:
            print()
            print(ecu_label(ecu, obd.protocol))
            for kind in DTC_SERVICES:
                if ecu in found[kind]:
                    codes = ", ".join(found[kind][ecu]) or "none"
                else:
                    codes = "not reported by this module"
                print(f"  {kind.capitalize():<10} {codes}")
        frame = obd.freeze_frame()
        if frame:
            print()
            print(f"Freeze frame saved with {frame.dtc}, {ecu_label(frame.ecu, obd.protocol)}")
            for reading in frame.readings:
                print(_reading_line(reading))
    return 0


def cmd_monitors(args: argparse.Namespace) -> int:
    with open_vehicle(args) as (obd, _):
        statuses = obd.monitor_status()
        if not statuses:
            print("No module reported readiness status.")
            return 1
        for status in statuses:
            lamp = "ON" if status.mil_on else "off"
            codes = f"{status.dtc_count} code{'' if status.dtc_count == 1 else 's'}"
            print(f"{ecu_label(status.ecu, obd.protocol)}: check-engine light {lamp}, {codes}, {status.ignition} ignition")
            for monitor in status.monitors:
                print(f"  {monitor.name:<24} {'complete' if monitor.complete else 'NOT complete'}")
    return 0


def cmd_pids(args: argparse.Namespace) -> int:
    with open_vehicle(args) as (obd, _):
        for ecu, pids in sorted(obd.supported_pids().items()):
            print(ecu_label(ecu, obd.protocol))
            for pid in sorted(pids):
                if pid == 0x01:
                    continue  # readiness status; `monitors` shows it decoded
                reading = obd.read_pid(pid, ecu)
                if reading is not None:
                    print(f"  {pid:02X}{_reading_line(reading)}")
            print()
    return 0


class _LiveView:
    """Redraws a small table in a terminal; prints one line per pass elsewhere."""

    def __init__(self, out: IO[str]) -> None:
        self.out = out
        self.in_place = out.isatty()
        self.drawn = 0

    def show(self, elapsed: float, readings: list[Reading]) -> None:
        if self.in_place:
            lines = [f"  {elapsed:.1f} s   (Ctrl-C to stop)"] + [_reading_line(r) for r in readings]
            if self.drawn:
                self.out.write(f"\x1b[{self.drawn}A")
            for line in lines:
                self.out.write("\x1b[2K" + line + "\n")
            self.drawn = len(lines)
        else:
            cells = (f"{r.name}={_fmt(r.value)}{' ' + r.unit if r.unit else ''}" for r in readings)
            self.out.write(f"{elapsed:.1f}s  " + "; ".join(cells) + "\n")
        self.out.flush()


def _pid_list(text: str) -> list[int]:
    try:
        return [int(part, 16) for part in text.split(",") if part.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError("expected hex PIDs separated by commas, e.g. 0C,0D,05") from None


def cmd_live(args: argparse.Namespace) -> int:
    with open_vehicle(args) as (obd, info):
        supported = set().union(*obd.supported_pids().values())
        if args.pids:
            unsupported = [pid for pid in args.pids if pid not in supported]
            if unsupported:
                skipped = ", ".join(f"{pid:02X}" for pid in unsupported)
                print(f"note: this vehicle does not report PID {skipped}; skipping", file=sys.stderr)
            watched = [pid for pid in args.pids if pid in supported]
        else:
            watched = [pid for pid in DEFAULT_LIVE_PIDS if pid in supported]
        if not watched:
            print("error: none of the requested values are available on this vehicle", file=sys.stderr)
            return 1

        store = session_id = None
        if args.log:
            store = Store(args.db)
            session_id = store.start_session(
                vin=obd.vin(), adapter=info.label, protocol=obd.protocol.name, note=args.note
            )

        view = _LiveView(sys.stdout)
        started = time.monotonic()
        cycle = 0
        try:
            while args.seconds is None or time.monotonic() - started < args.seconds:
                cycle_started = time.monotonic()
                samples = []
                for pid in watched:
                    reading = obd.read_pid(pid)
                    if reading is not None:
                        samples.append((time.time(), reading))
                view.show(cycle_started - started, [reading for _, reading in samples])
                if store:
                    store.add_samples(session_id, cycle, samples)
                cycle += 1
                spare = args.interval - (time.monotonic() - cycle_started)
                if spare > 0:
                    time.sleep(spare)
        except KeyboardInterrupt:
            pass
        finally:
            if store:
                store.end_session(session_id)
                store.close()
                print(f"Saved session {session_id} ({cycle} passes) to {store.path}")
    return 0


def cmd_sessions(args: argparse.Namespace) -> int:
    store = Store(args.db)
    rows = store.sessions()
    store.close()
    if not rows:
        print("No sessions recorded yet. Record one with: cardiag live --log")
        return 0
    print(f"{'ID':>4}  {'Started':<16}  {'Length':>8}  {'Passes':>6}  {'VIN':<17}  Note")
    for row in rows:
        started = datetime.fromtimestamp(row["started_at"]).strftime("%Y-%m-%d %H:%M")
        if row["ended_at"] is None:
            length = "unknown"
        else:
            seconds = int(row["ended_at"] - row["started_at"])
            length = f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
        print(
            f"{row['id']:>4}  {started:<16}  {length:>8}  {row['cycles']:>6}  "
            f"{row['vin'] or '-':<17}  {row['note'] or ''}".rstrip()
        )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    store = Store(args.db)
    try:
        if args.out:
            with open(args.out, "w", newline="", encoding="utf-8") as out:
                rows = store.export_csv(args.session, out)
            print(f"Wrote {rows} rows to {args.out}")
        else:
            store.export_csv(args.session, sys.stdout)
    except KeyError:
        print(f"error: there is no session {args.session}; see 'cardiag sessions'", file=sys.stderr)
        return 1
    finally:
        store.close()
    return 0


def cmd_ports(args: argparse.Namespace) -> int:
    ports = sorted(list_ports.comports(), key=lambda port: port.device)
    if not ports:
        print("No serial ports found.")
        return 0
    likely = {port.device for port in _likely_adapters()}
    for port in ports:
        marker = "  <- looks like an OBD adapter" if port.device in likely else ""
        print(f"{port.device}  {port.description}{marker}")
    return 0


def cmd_sim_serve(args: argparse.Namespace) -> int:
    adapter = PtyAdapter(SimElm(VEHICLES[args.vehicle]()))
    print(f"Simulated {args.vehicle} adapter is listening on {adapter.path} (Ctrl-C to stop)")
    print(f"In another terminal:  cardiag --port {adapter.path} info")
    try:
        adapter.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        adapter.close()
    return 0


def _lan_address() -> str | None:
    """This machine's address on the local network, for telling other devices where to look."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # picks the outgoing interface; nothing is sent
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def cmd_serve(args: argparse.Namespace) -> int:
    def open_transport():
        return SerialTransport(args.port or find_port(), args.baud)

    # One of each simulated vehicle for as long as the server runs, so switching away
    # and back finds the same car. The page can swap between these and the adapter.
    vehicles = {name: make() for name, make in VEHICLES.items()}
    simulators = {name: (lambda v=vehicle: SimTransport(SimElm(v))) for name, vehicle in vehicles.items()}

    hub = Hub(open_transport, db_path=args.db, interval=args.interval, simulators=simulators, simulation=args.sim)
    wifi = Wifi() if args.manage_wifi else None
    updater = Updater(args.update_dir) if args.update_dir else None
    try:
        server = make_server(hub, args.host, args.web_port, args.db, wifi=wifi, updater=updater)
    except OSError as exc:
        print(f"error: cannot listen on {args.host}:{args.web_port}: {exc}", file=sys.stderr)
        return 1
    port = server.server_address[1]
    if args.host in ("0.0.0.0", "::"):
        address = _lan_address()
        print(f"Serving on this machine at http://localhost:{port}")
        where = f"http://{address}:{port}" if address else f"http://<this machine's address>:{port}"
        print(f"From a phone or tablet on the same network, open {where}")
    else:
        print(f"Serving at http://{args.host}:{port}  (add --host 0.0.0.0 to reach it from other devices)")
    print("Ctrl-C to stop.", flush=True)
    hub.start()
    if wifi:
        wifi.start()
    confirm = None
    if updater:
        # Still running after a few seconds: an update that was just installed is sound.
        confirm = threading.Timer(_CONFIRM_AFTER_SECONDS, updater.confirm)
        confirm.daemon = True
        confirm.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if confirm:
            confirm.cancel()
        server.server_close()
        hub.stop()
        if wifi:
            wifi.stop()
    if server.restarting:
        print("Stopping so that the new version can start.", flush=True)
    return 0


def _connection_options(default) -> argparse.ArgumentParser:
    link = argparse.ArgumentParser(add_help=False)
    group = link.add_argument_group("connection")
    group.add_argument("--port", default=default, help="serial port of the adapter, e.g. /dev/ttyUSB0 (found automatically if omitted)")
    group.add_argument("--baud", type=int, default=default, help="serial speed (found automatically if omitted)")
    group.add_argument("--sim", choices=sorted(VEHICLES), default=default, help="use a simulated vehicle instead of a real adapter")
    group.add_argument("--db", default=default, help="session database file (default: ~/.local/share/cardiag/cardiag.db)")
    return link


def build_parser() -> argparse.ArgumentParser:
    # Connection options are accepted before or after the command name. The
    # subcommands get their own copies defaulting to SUPPRESS, so an option left
    # unset after the command cannot overwrite one given before it.
    parser = argparse.ArgumentParser(
        prog="cardiag", description="Car diagnostics over OBD-II.", parents=[_connection_options(None)]
    )
    parser.add_argument("--version", action="version", version=f"cardiag {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="command", required=True)
    after_command = _connection_options(argparse.SUPPRESS)

    def add(name: str, run, help: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help, description=help, parents=[after_command])
        sub.set_defaults(run=run)
        return sub

    add("info", cmd_info, "show the adapter, the vehicle network, the VIN and the modules that answer")
    add("codes", cmd_codes, "read stored, pending and permanent trouble codes and the freeze frame")
    add("monitors", cmd_monitors, "show the check-engine light state and emissions readiness monitors")
    add("pids", cmd_pids, "list every standard live value the vehicle offers, with current readings")

    live = add("live", cmd_live, "watch live values, optionally recording them")
    live.add_argument("--pids", type=_pid_list, help="hex PIDs to watch, e.g. 0C,0D,05 (default: a common set)")
    live.add_argument("--interval", type=float, default=0.25, help="minimum seconds between passes (default 0.25; 0 for as fast as possible)")
    live.add_argument("--seconds", type=float, help="stop after this long (default: run until Ctrl-C)")
    live.add_argument("--log", action="store_true", help="record this run as a session")
    live.add_argument("--note", help="a note to store with the session, e.g. 'cold start rattle'")

    add("sessions", cmd_sessions, "list recorded sessions")
    export = add("export", cmd_export, "export a recorded session as CSV")
    export.add_argument("session", type=int, help="session ID from 'cardiag sessions'")
    export.add_argument("--out", help="file to write (default: print to the terminal)")

    serve = add("serve", cmd_serve, "run the web interface for a browser, phone or tablet")
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on (default 127.0.0.1; use 0.0.0.0 for other devices)")
    serve.add_argument("--web-port", type=int, default=8000, help="port for the web interface (default 8000)")
    serve.add_argument("--interval", type=float, default=0.25, help="minimum seconds between updates (default 0.25)")
    serve.add_argument("--manage-wifi", action="store_true", help="let the page switch this machine between its hotspot and a Wi-Fi network (for the box in the car; needs NetworkManager)")
    serve.add_argument("--update-dir", metavar="DIR", help="let the page install new releases into DIR, where this copy was installed (for the box in the car)")

    add("ports", cmd_ports, "list serial ports and flag likely OBD adapters")
    serve = add("sim-serve", cmd_sim_serve, "run a simulated adapter as a serial device for testing")
    serve.add_argument("vehicle", nargs="?", choices=sorted(VEHICLES), default="focus")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except KeyboardInterrupt:
        return 130
    except (AdapterError, LinkError, FrameError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except serial.SerialException as exc:
        print(f"error: {exc}", file=sys.stderr)
        if "permission denied" in str(exc).lower():
            print(
                "hint: add yourself to the serial-port group, then log out and back in:\n"
                "      sudo usermod -aG dialout $USER     (the group is 'uucp' on Arch)",
                file=sys.stderr,
            )
        return 1
