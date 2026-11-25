#!/usr/bin/env python3
"""A relay between FORScan (under Wine) and an ELM327/STN adapter that lets
reads through and never lets a change reach the car.

It takes the place of the logging socat relay in docs/ford-focus-2017.md:
FORScan talks to the pseudo-terminal at /tmp/obd (Wine's COM5), the relay
talks to the adapter.

Requests that only read (OBD modes, 19, 22, 23, 27, 3E, and the default and
extended sessions) go to the car. Requests that would change something are
answered by the relay itself and never sent:

    2E WriteDataByIdentifier   answered 6E <id>          (as if accepted)
    3B WriteDataByLocalId      answered 7B <id>
    11 ECUReset                answered 51 <type>
    14 / 04 clear fault codes  answered 54 / 44
    31 RoutineControl          answered 71 <sub> <routine>
    28 / 85 comms / DTC setting answered 68 / C5 <sub>
    anything else              refused 7F <service> 22   (conditions not correct)
    10 02 programming session  refused 7F 10 22

So when FORScan's named view writes a setting, it believes the write worked,
and the relay logs which bytes and bits of the block it would have changed.
The comparison is with the block as FORScan last believed it: the last value
read from the car, or the last write the relay blocked, whichever came later.
Change one setting per write and each log entry places that setting.

    forscan_dryrun_relay.py [--port /dev/ttyUSB0] [--baud 115200]
                            [--link /tmp/obd] [--log-dir DIR]
                            [--replay RECORDING ...]

With --replay there is no adapter and no car: the relay answers FORScan from
earlier recordings (its own transcript.log, or a socat capture), keyed by the
protocol, header and request in force. A security-access key is always
accepted. Anything not recorded gets OK (adapter commands) or NO DATA.

Writes in DIR: transcript.log (every line both ways) and writes.jsonl (one
entry per blocked block write, with the diff). Both can hold the VIN.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import sys
import termios
import time
import tty
from dataclasses import dataclass, field

PROMPT = b">"
DATA_PROMPT = b"DATA>"

# Services that only read, sent on to the car.
READ_SERVICES = {0x01, 0x02, 0x03, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A,
                 0x19, 0x22, 0x23, 0x27, 0x3E}
SAFE_SESSIONS = {0x01, 0x03}  # default and extended; not 02 (programming)

STPX = re.compile(r"^STPX\s*(.*)$", re.I)
HEX = re.compile(r"^[0-9A-Fa-f]+$")


@dataclass
class Request:
    """One request to the car, however FORScan wrapped it."""
    header: int | None
    data: bytes


def parse_stpx(line: str) -> dict[str, str]:
    """STPXh:7E0,d:22F190,r:1 -> {'h': '7E0', 'd': '22F190', 'r': '1'}."""
    m = STPX.match(line.strip())
    if not m:
        return {}
    fields = {}
    for part in m.group(1).split(","):
        if ":" in part:
            key, value = part.split(":", 1)
            fields[key.strip().lower()] = value.strip().replace(" ", "")
    return fields


def plain_request(line: str) -> bytes | None:
    """A bare hex request. An odd digit count carries the adapter's reply-count digit at the end."""
    text = line.strip().replace(" ", "")
    if not text or not HEX.match(text) or len(text) < 2:
        return None
    if len(text) % 2:
        text = text[:-1]
    return bytes.fromhex(text)


def decide(data: bytes) -> tuple[str, bytes | None]:
    """('pass', None), ('fake', reply) or ('fake', b'') for an expected silence."""
    service = data[0]
    sub = data[1] if len(data) > 1 else 0
    if service in READ_SERVICES:
        return "pass", None
    if service == 0x10:
        if sub & 0x7F in SAFE_SESSIONS:
            return "pass", None
        return "fake", bytes([0x7F, 0x10, 0x22])
    if service == 0x2E:
        return "fake", bytes([0x6E]) + data[1:3]
    if service == 0x3B:
        return "fake", bytes([0x7B]) + data[1:2]
    if service in (0x11, 0x28, 0x85):
        if sub & 0x80:  # suppress-positive-response bit: the car would stay quiet
            return "fake", b""
        return "fake", bytes([service + 0x40, sub])
    if service in (0x14, 0x04):
        return "fake", bytes([service + 0x40])
    if service == 0x31:
        return "fake", bytes([0x71]) + data[1:4]
    return "fake", bytes([0x7F, service, 0x22])


def format_reply(reply: bytes, spaces: bool) -> bytes:
    if not reply:
        return b"NO DATA\r\r>"
    text = (" " if spaces else "").join(f"{b:02X}" for b in reply)
    return text.encode() + b"\r\r>"


def diff_block(old: bytes | None, new: bytes) -> list[dict]:
    """Each changed byte, with the bits that flipped (bit 7 = 0x80)."""
    if old is None:
        return []
    changes = []
    for i in range(max(len(old), len(new))):
        a = old[i] if i < len(old) else None
        b = new[i] if i < len(new) else None
        if a != b:
            flipped = [] if a is None or b is None else [bit for bit in range(7, -1, -1) if (a ^ b) >> bit & 1]
            changes.append({"byte": i, "old": None if a is None else f"{a:02X}",
                            "new": None if b is None else f"{b:02X}", "bits": flipped})
    return changes


def replies_for(response: bytes, request: bytes) -> list[bytes]:
    """Positive replies to a 22 read in the adapter's text: lines that start 62 <id>."""
    want = (bytes([request[0] + 0x40]) + request[1:3]).hex().upper()
    found = []
    for line in response.decode(errors="replace").replace(" ", "").split("\r"):
        line = line.strip().lstrip(">")
        if line.upper().startswith(want) and HEX.match(line) and len(line) % 2 == 0:
            found.append(bytes.fromhex(line))
    return found


def open_serial(port: str, baud: int) -> int:
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY)
    tty.setraw(fd)
    attrs = termios.tcgetattr(fd)
    speed = getattr(termios, f"B{baud}")
    attrs[4] = attrs[5] = speed
    attrs[2] |= termios.CLOCAL | termios.CREAD
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def open_pty(link: str) -> tuple[int, int]:
    """A pseudo-terminal with its slave name linked at `link`. The slave is kept
    open so the master survives FORScan closing and reopening the port."""
    master, slave = os.openpty()
    tty.setraw(slave)
    name = os.ttyname(slave)
    if os.path.lexists(link):
        if not os.path.islink(link):
            raise SystemExit(f"{link} exists and is not a symlink; not replacing it")
        os.unlink(link)
    os.symlink(name, link)
    return master, slave


@dataclass
class Relay:
    tool: int                      # fd FORScan's side
    adapter: int                   # fd the adapter's side
    transcript: object = None      # text file or None
    writes: object = None          # text file or None
    echo: callable = print
    timeout: float = 20.0
    header: int | None = None
    spaces: bool = False
    last_read: dict = field(default_factory=dict)   # (header, id) -> bytes
    _buffer: bytes = b""

    # --- low level -------------------------------------------------------
    def _note(self, direction: str, data: bytes) -> None:
        if self.transcript:
            stamp = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
            text = data.decode(errors="replace").replace("\r", "\\r")
            self.transcript.write(f"{stamp} {direction} {text}\n")
            self.transcript.flush()

    def _to_tool(self, data: bytes) -> None:
        self._note("R>F", data)
        os.write(self.tool, data)

    def _to_adapter(self, data: bytes) -> None:
        self._note("F>A", data)
        os.write(self.adapter, data)

    def _read_tool_line(self) -> bytes | None:
        """One CR-terminated line from FORScan; None if nothing came within a second."""
        while b"\r" not in self._buffer:
            ready, _, _ = select.select([self.tool], [], [], 1.0)
            if not ready:
                return None
            try:
                chunk = os.read(self.tool, 4096)
            except OSError:          # FORScan closed the port
                time.sleep(0.2)
                return None
            if not chunk:
                return None
            self._buffer += chunk
        line, self._buffer = self._buffer.split(b"\r", 1)
        return line + b"\r"

    def _read_adapter(self, until: bytes) -> bytes:
        data = b""
        deadline = time.monotonic() + self.timeout
        while not data.endswith(until) and time.monotonic() < deadline:
            ready, _, _ = select.select([self.adapter], [], [], 0.2)
            if ready:
                chunk = os.read(self.adapter, 4096)
                if chunk:
                    data += chunk
        self._note("A>R", data)
        return data

    # --- one command -----------------------------------------------------
    def step(self) -> bool:
        raw = self._read_tool_line()
        if raw is None:
            return False
        self._note("F>R", raw)
        line = raw.decode(errors="replace").strip()
        upper = line.upper().replace(" ", "")

        if upper.startswith("ATSH"):
            self.header = int(upper[4:], 16) & 0x1FFFFFFF if HEX.match(upper[4:]) else None
        elif upper in ("ATS0", "ATS1"):
            self.spaces = upper == "ATS1"
        elif upper == "ATH1":
            self.echo("warning: FORScan turned headers on; faked replies are sent without them")

        stpx = parse_stpx(line)
        if stpx and "l" in stpx:
            return self._long_request(raw, stpx)
        if stpx and "d" in stpx:
            header = int(stpx["h"], 16) if "h" in stpx else self.header
            return self._request(raw, Request(header, bytes.fromhex(stpx["d"])))
        if not upper.startswith(("AT", "ST")):
            data = plain_request(line)
            if data:
                return self._request(raw, Request(self.header, data))
        # adapter command, or something not understood: send it on
        self._to_adapter(raw)
        self._to_tool(self._read_adapter(PROMPT))
        return True

    def _long_request(self, raw: bytes, stpx: dict) -> bool:
        """STPX l:<n>: the adapter prompts DATA>, then takes n bytes as hex."""
        self._to_tool(DATA_PROMPT)
        length = int(stpx["l"])
        while len(self._buffer) < 2 * length + 1:
            ready, _, _ = select.select([self.tool], [], [], self.timeout)
            if not ready:
                break
            self._buffer += os.read(self.tool, 65536)
        payload, self._buffer = self._buffer[:2 * length], self._buffer[2 * length:].lstrip(b"\r")
        self._note("F>R", payload)
        header = int(stpx["h"], 16) if "h" in stpx else self.header
        request = Request(header, bytes.fromhex(payload.decode()))
        verdict, reply = decide(request.data)
        if verdict == "pass":
            self._to_adapter(raw)
            self._read_adapter(DATA_PROMPT)
            self._to_adapter(payload + b"\r")
            self._to_tool(self._read_adapter(PROMPT))
        else:
            self._blocked(request, reply)
        return True

    def _request(self, raw: bytes, request: Request) -> bool:
        verdict, reply = decide(request.data)
        if verdict == "pass":
            self._to_adapter(raw)
            response = self._read_adapter(PROMPT)
            if request.data[0] == 0x22 and len(request.data) >= 3:
                for found in replies_for(response, request.data):
                    self.last_read[(request.header, found[1:3].hex().upper())] = found[3:]
            self._to_tool(response)
        else:
            self._blocked(request, reply)
        return True

    def _blocked(self, request: Request, reply: bytes) -> None:
        where = f"{request.header:03X}" if request.header is not None else "???"
        self._note("BLK", request.data.hex().upper().encode())
        entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "module": where,
                 "request": request.data.hex().upper(), "answered": reply.hex().upper() or "NO DATA"}
        if request.data[0] == 0x2E and len(request.data) >= 3:
            ident = request.data[1:3].hex().upper()
            old = self.last_read.get((request.header, ident))
            new = request.data[3:]
            entry.update({"id": ident, "before": None if old is None else old.hex().upper(),
                          "after": new.hex().upper(), "changes": diff_block(old, new)})
            if old is None:
                self.echo(f"BLOCKED write {where} {ident} (block not read this session, no diff): {new.hex().upper()}")
            else:
                parts = [f"byte {c['byte']}: {c['old']}->{c['new']} bits {c['bits']}" for c in entry["changes"]]
                self.echo(f"BLOCKED write {where} {ident}: " + ("; ".join(parts) or "no change"))
            if self.writes:
                self.writes.write(json.dumps(entry) + "\n")
                self.writes.flush()
            # FORScan keeps its edits, so its next write of this block repeats this
            # one; diff that against what FORScan now believes, not the car.
            self.last_read[(request.header, ident)] = new
        else:
            self.echo(f"blocked {where} {entry['request']} -> answered {entry['answered']}")
        self._to_tool(format_reply(reply, self.spaces))

    def run(self) -> None:
        while True:
            self.step()


# --- replaying a recorded car ----------------------------------------------

def _context_step(cmd: str, proto, header):
    up = cmd.upper().replace(" ", "")
    if up.startswith(("ATTP", "ATSP")) or (up.startswith("STP") and up[3:].isdigit()):
        proto = up
    elif up.startswith("ATSH"):
        header = up[4:]
    return proto, header


def load_recording(paths: list[str]) -> dict:
    """(protocol, header, command) -> reply text, from relay transcripts and/or
    socat captures. Later recordings win."""
    table: dict = {}

    def add(pairs):
        proto = header = None
        for cmd, reply in pairs:
            proto, header = _context_step(cmd, proto, header)
            table[(proto, header, cmd)] = reply
            table[(None, None, cmd)] = reply

    for path in paths:
        with open(path, "rb") as f:
            head = f.read(200)
        if head[:2] in (b"> ", b"< "):                      # socat -v -x capture
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import parse_forscan_capture as capture
            pairs, cmd, reply = [], None, b""
            for _, direction, data in capture.read_chunks(path):
                if direction == ">":
                    if cmd is not None and reply.endswith(b">"):
                        pairs.append((cmd, reply))
                    text = bytes(data).decode(errors="replace")
                    if text.endswith("\r"):
                        cmd, reply = text.rstrip("\r"), b""
                    else:
                        cmd, reply = None, b""      # STPX data line or stray bytes
                else:
                    reply += bytes(data)
            add(pairs)
        else:                                                # relay transcript
            pairs, cmd = [], None
            for line in open(path, encoding="utf-8", errors="replace"):
                parts = line.rstrip("\n").split(" ", 2)
                if len(parts) < 3:
                    continue
                text = parts[2].replace("\\r", "\r")
                if parts[1] == "F>A":
                    cmd = text.rstrip("\r")
                elif parts[1] == "A>R" and cmd is not None and text.endswith(">") and not text.endswith("DATA>"):
                    pairs.append((cmd, text.encode()))
                    cmd = None
            add(pairs)
    return table


class Replay:
    """Answers like the adapter and the car did when recorded."""

    def __init__(self, table: dict, echo=print):
        self.table, self.echo = table, echo
        self.proto = self.header = None
        self.misses: set = set()

    def answer(self, cmd: str) -> bytes:
        self.proto, self.header = _context_step(cmd, self.proto, self.header)
        reply = self.table.get((self.proto, self.header, cmd)) or self.table.get((None, None, cmd))
        if reply is not None:
            return reply
        up = cmd.upper().replace(" ", "")
        data = plain_request(up) if not up.startswith(("AT", "ST")) else None
        if data and data[0] == 0x27 and len(data) > 1 and data[1] % 2 == 0:
            return f"67{data[1]:02X}\r\r>".encode()      # any key unlocks a replayed seed
        if (self.proto, self.header, cmd) not in self.misses:
            self.misses.add((self.proto, self.header, cmd))
            self.echo(f"replay: nothing recorded for {self.header or ''} {cmd}")
        if up.startswith(("AT", "ST")):
            return b"OK\r\r>"
        return b"NO DATA\r\r>"


def serve_replay(fd: int, replay: Replay) -> None:
    buffer = b""
    while True:
        chunk = os.read(fd, 4096)
        if not chunk:
            return
        buffer += chunk
        while b"\r" in buffer:
            line, buffer = buffer.split(b"\r", 1)
            os.write(fd, replay.answer(line.decode(errors="replace")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--link", default="/tmp/obd")
    parser.add_argument("--log-dir", default=".")
    parser.add_argument("--replay", nargs="+", metavar="RECORDING",
                        help="answer from these recordings (relay transcripts or socat captures) instead of an adapter")
    args = parser.parse_args(argv)

    os.makedirs(args.log_dir, exist_ok=True)
    if args.replay:
        import threading
        table = load_recording(args.replay)
        master, slave = os.openpty()
        tty.setraw(master)
        tty.setraw(slave)
        threading.Thread(target=serve_replay, args=(slave, Replay(table, echo=lambda s: print(s, flush=True))),
                         daemon=True).start()
        adapter = master
        args.port = f"replay of {len(args.replay)} recording(s), {len(table)} entries"
    else:
        adapter = open_serial(args.port, args.baud)
    tool, _slave = open_pty(args.link)
    with open(os.path.join(args.log_dir, "transcript.log"), "a") as transcript, \
         open(os.path.join(args.log_dir, "writes.jsonl"), "a") as writes:
        print(f"dry-run relay: {args.link} <-> {args.port} at {args.baud}. Nothing that changes the car is sent.",
              flush=True)
        relay = Relay(tool, adapter, transcript, writes, echo=lambda s: print(s, flush=True))
        try:
            relay.run()
        except KeyboardInterrupt:
            pass
        finally:
            if os.path.islink(args.link):
                os.unlink(args.link)
    return 0


if __name__ == "__main__":
    sys.exit(main())
