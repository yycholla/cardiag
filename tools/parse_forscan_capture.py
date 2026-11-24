#!/usr/bin/env python3
"""Turn a socat capture of the serial traffic between a scan tool and an
ELM327/STN adapter into a list of the requests that were sent to the car.

The capture is what `socat -v -x` writes to stderr while it sits between the
tool and the adapter (see docs/ford-focus-2017.md for the full command).

    parse_forscan_capture.py capture.log            # how many requests, by module and service
    parse_forscan_capture.py capture.log full       # every distinct request with one reply
    parse_forscan_capture.py capture.log at         # the adapter commands, by how often they were sent

In the `full` listing the columns are: time first seen, the adapter's protocol
command in force, the module's request address, the request, how many times it
was sent, and one reply. A request with an odd number of hex digits carries the
adapter's "expect this many replies" digit at the end: 22F4461 is 22 F446.

A capture holds the car's VIN, and may hold more. Remove it before sharing.
"""

from __future__ import annotations

import collections
import re
import sys

CHUNK = re.compile(rb"^([<>]) (\S+ \S+)\s+length=")
HEX_BYTE = re.compile(rb"[0-9a-f]{2}")
# STN adapters can wrap a request: STPX H:7E0, D:22F190, R:1
WRAPPED = re.compile(r"STPX(?:H:([0-9A-F]+),)?D:([0-9A-F]+)")


def read_chunks(path: str) -> list[tuple[str, str, bytes]]:
    """Each chunk socat logged: its time, its direction, its bytes."""
    chunks: list[list] = []
    current = None
    with open(path, "rb") as capture:
        for line in capture:
            start = CHUNK.match(line)
            if start:
                current = [start.group(2).decode(), start.group(1).decode(), bytearray()]
                chunks.append(current)
            elif line.startswith(b" ") and current is not None:
                # 16 bytes of hex fill the first 49 columns; the text after them is a repeat
                for token in line[:49].split():
                    if HEX_BYTE.fullmatch(token):
                        current[2].append(int(token, 16))
    return [(time, direction, bytes(data)) for time, direction, data in chunks]


def transactions(chunks: list[tuple[str, str, bytes]]) -> list[tuple[str, bytes, bytes]]:
    """Pair what the tool sent with what the adapter said back, up to its prompt."""
    sent, received, started = bytearray(), bytearray(), None
    pairs = []
    for time, direction, data in chunks:
        if direction == ">":
            if received.strip() and sent:
                pairs.append((started, bytes(sent), bytes(received)))
                sent, received, started = bytearray(), bytearray(), None
            if started is None:
                started = time
            sent += data
        else:
            received += data
            if b">" in data:
                pairs.append((started or time, bytes(sent), bytes(received)))
                sent, received, started = bytearray(), bytearray(), None
    return pairs


def clean(data: bytes) -> str:
    return data.decode("latin1").replace(">", "").strip().replace("\r", " | ")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    mode = argv[2] if len(argv) > 2 else "summary"
    pairs = transactions(read_chunks(argv[1]))

    header = protocol = None
    adapter = collections.Counter()
    requests: dict[tuple, list] = {}  # (protocol, header, request) -> [count, reply, first seen]
    for time, sent, received in pairs:
        command = clean(sent).replace(" ", "").upper()
        reply = clean(received)
        if not command:
            continue
        wrapped = WRAPPED.match(command)
        if wrapped:
            command = wrapped.group(2)
            if wrapped.group(1):
                header = wrapped.group(1)[-3:]
        elif command.startswith(("AT", "ST")):
            adapter[command] += 1
            set_header = re.match(r"ATSH0*([0-9A-F]{3})$", command)
            if set_header:
                header = set_header.group(1)
            if re.match(r"(STP|ATSP|ATTP)[0-9A-F]+$", command):
                protocol = command
            continue
        key = (protocol, header, command)
        entry = requests.setdefault(key, [0, reply, time])
        entry[0] += 1
        if reply and "NO DATA" not in reply and (not entry[1] or "NO DATA" in entry[1]):
            entry[1] = reply

    if mode == "at":
        for command, count in adapter.most_common():
            print(count, command)
    elif mode == "full":
        for (proto, head, command), (count, reply, time) in requests.items():
            print(f"{time[11:19]} {proto or '-':8} {head or '-':4} {command:24} x{count:<4} {reply[:110]}")
    else:
        print("transactions:", len(pairs), " distinct requests:", len(requests))
        by_module: dict = collections.defaultdict(lambda: collections.defaultdict(set))
        for proto, head, command in requests:
            by_module[(proto, head)][command[:2]].add(command)
        for (proto, head), services in by_module.items():
            counts = "  ".join(f"svc {service}: {len(found)}" for service, found in sorted(services.items()))
            print(f"{proto or '-':8} {head or '-':4} {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
