"""The FORScan dry-run relay: reads reach the adapter, changes never do."""

import importlib.util
import io
import json
import os
import pathlib
import sys
import threading
import tty

import pytest

_path = pathlib.Path(__file__).resolve().parent.parent / "tools" / "forscan_dryrun_relay.py"
_spec = importlib.util.spec_from_file_location("forscan_dryrun_relay", _path)
relay_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = relay_mod
_spec.loader.exec_module(relay_mod)


# --- pure functions ---------------------------------------------------------

@pytest.mark.parametrize("request_hex, verdict, reply", [
    ("22DE00", "pass", None),
    ("1902", "pass", None),
    ("2703", "pass", None),
    ("1003", "pass", None),
    ("1001", "pass", None),
    ("3E00", "pass", None),
    ("0100", "pass", None),
    ("1002", "fake", "7F1022"),
    ("2EDE11FFFF7F3E", "fake", "6EDE11"),
    ("1101", "fake", "5101"),
    ("1181", "fake", ""),
    ("14FFFFFF", "fake", "54"),
    ("04", "fake", "44"),
    ("31010E06", "fake", "71010E06"),
    ("3400444000", "fake", "7F3422"),
    ("3601AB", "fake", "7F3622"),
    ("3500440000", "fake", "7F3522"),
    ("2F123403", "fake", "7F2F22"),
])
def test_decide(request_hex, verdict, reply):
    got_verdict, got_reply = relay_mod.decide(bytes.fromhex(request_hex))
    assert got_verdict == verdict
    assert (got_reply.hex().upper() if got_reply is not None else None) == reply


def test_plain_request_drops_the_reply_count_digit():
    assert relay_mod.plain_request("22F4461") == bytes.fromhex("22F446")
    assert relay_mod.plain_request("22F446") == bytes.fromhex("22F446")
    assert relay_mod.plain_request("ATRV") is None


def test_parse_stpx():
    assert relay_mod.parse_stpx("STPXh:7E0,d:22F190,r:1") == {"h": "7E0", "d": "22F190", "r": "1"}
    assert relay_mod.parse_stpx("STPX D:22DE00, R:1") == {"d": "22DE00", "r": "1"}
    assert relay_mod.parse_stpx("STPXl:544,r:1") == {"l": "544", "r": "1"}


def test_diff_block_names_bytes_and_bits():
    changes = relay_mod.diff_block(bytes.fromhex("FFFFFF3E"), bytes.fromhex("FFFF7F3E"))
    assert changes == [{"byte": 2, "old": "FF", "new": "7F", "bits": [7]}]
    assert relay_mod.diff_block(None, b"\x00") == []


def test_replies_for_finds_the_positive_reply():
    found = relay_mod.replies_for(b"62DE000102\r\r>", bytes.fromhex("22DE00"))
    assert found == [bytes.fromhex("62DE000102")]
    assert relay_mod.replies_for(b"7F2231\r\r>", bytes.fromhex("22DE00")) == []


# --- end to end over pseudo-terminals --------------------------------------

class FakeAdapter(threading.Thread):
    """Answers like an STN adapter with ATE0 ATS0 ATH0, and records every line it hears."""

    def __init__(self, fd):
        super().__init__(daemon=True)
        self.fd = fd
        self.heard = []
        self.block = {"DE00": "0102", "DE11": "FFFFFF3E"}

    def run(self):
        buffer = b""
        expecting_data = False
        while True:
            try:
                chunk = os.read(self.fd, 4096)
            except OSError:
                return
            if not chunk:
                return
            buffer += chunk
            while b"\r" in buffer:
                line, buffer = buffer.split(b"\r", 1)
                text = line.decode()
                self.heard.append(text)
                os.write(self.fd, self.answer(text, expecting_data))
                expecting_data = text.upper().startswith("STPXL:")

    def answer(self, text, expecting_data):
        upper = text.upper()
        if upper.startswith("STPXL:"):
            return b"DATA>"
        wrapped = upper.startswith("STPX") and "D:" in upper
        if upper.startswith(("AT", "ST")) and not wrapped:
            return b"12.1V\r\r>" if upper == "ATRV" else b"OK\r\r>"
        request = upper.split("D:")[1].split(",")[0] if wrapped else upper
        if expecting_data:
            return b"7601\r\r>"
        if request.startswith("22"):
            ident = request[2:6]
            return (f"62{ident}{self.block[ident]}" if ident in self.block else "7F2231").encode() + b"\r\r>"
        return b"NO DATA\r\r>"


@pytest.fixture
def wired():
    tool_master, tool_slave = os.openpty()
    adapter_master, adapter_slave = os.openpty()
    for fd in (tool_slave, adapter_slave):
        tty.setraw(fd)
    adapter = FakeAdapter(adapter_slave)
    adapter.start()
    printed, writes = [], io.StringIO()
    relay = relay_mod.Relay(tool_master, adapter_master, transcript=None, writes=writes,
                            echo=printed.append, timeout=2.0)

    def exchange(line):
        os.write(tool_slave, line.encode() + b"\r")
        relay.step()
        return _read(tool_slave)

    yield exchange, relay, adapter, printed, writes, tool_slave
    for fd in (tool_master, tool_slave, adapter_master, adapter_slave):
        os.close(fd)


def _read(fd, timeout=2.0):
    import select
    data = b""
    while not data.endswith(b">"):
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            break
        data += os.read(fd, 4096)
    return data


def test_reads_pass_and_writes_are_answered_locally(wired):
    exchange, relay, adapter, printed, writes, _ = wired
    assert exchange("ATSH000720") == b"OK\r\r>"
    assert exchange("22DE111") == b"62DE11FFFFFF3E\r\r>"
    assert exchange("1003") == b"NO DATA\r\r>"        # passed on; the fake adapter has no session
    assert exchange("2EDE11FFFF7F3E") == b"6EDE11\r\r>"
    assert exchange("1101") == b"5101\r\r>"

    assert not any(line.upper().startswith(("2E", "11")) for line in adapter.heard)
    assert "22DE111" in adapter.heard and "1003" in adapter.heard

    entry = json.loads(writes.getvalue())
    assert entry["module"] == "720" and entry["id"] == "DE11"
    assert entry["before"] == "FFFFFF3E" and entry["after"] == "FFFF7F3E"
    assert entry["changes"] == [{"byte": 2, "old": "FF", "new": "7F", "bits": [7]}]
    assert any("byte 2: FF->7F bits [7]" in line for line in printed)


def test_stpx_wrapped_write_is_blocked(wired):
    exchange, relay, adapter, printed, writes, _ = wired
    exchange("STPXh:726,d:22DE00,r:1")
    assert exchange("STPXh:726,d:2EDE000103,r:1") == b"6EDE00\r\r>"
    assert not any("2EDE00" in line.upper() for line in adapter.heard)
    entry = json.loads(writes.getvalue())
    assert entry["module"] == "726" and entry["changes"][0]["byte"] == 1


def test_long_write_never_reaches_the_adapter(wired):
    exchange, relay, adapter, printed, writes, tool_slave = wired
    exchange("ATSH000726")
    os.write(tool_slave, b"STPXl:5,r:1\r" + b"2EDE000103\r")
    relay.step()
    reply = _read(tool_slave)
    assert reply.startswith(b"DATA>") or reply == b"DATA>"
    if reply == b"DATA>":
        reply = _read(tool_slave)
    assert reply.endswith(b"6EDE00\r\r>")
    assert not any(line.upper().startswith("STPXL") or "2EDE00" in line.upper() for line in adapter.heard)


def test_long_read_still_reaches_the_adapter(wired):
    exchange, relay, adapter, printed, writes, tool_slave = wired
    os.write(tool_slave, b"STPXl:3,r:1\r" + b"22DE00\r")
    relay.step()
    reply = _read(tool_slave)
    if reply == b"DATA>":
        reply = _read(tool_slave)
    assert "STPXl:3,r:1" in adapter.heard and "22DE00" in adapter.heard


def test_each_write_is_compared_with_the_one_before(wired):
    exchange, relay, adapter, printed, writes, _ = wired
    exchange("ATSH000720")
    exchange("22DE111")
    exchange("2EDE11FFFF7F3E")          # first change: byte 2 bit 7
    exchange("2EDE11FEFF7F3E")          # FORScan repeats it and adds byte 0 bit 0
    second = json.loads(writes.getvalue().splitlines()[1])
    assert second["changes"] == [{"byte": 0, "old": "FF", "new": "FE", "bits": [0]}]


def test_replay_answers_from_a_relay_transcript(tmp_path):
    log = tmp_path / "transcript.log"
    log.write_text(
        "10:00:00.000 F>A ATSH000726\\r\n10:00:00.001 A>R OK\\r\\r>\n"
        "10:00:00.002 F>A STPXd:22DE00,r:1\\r\n10:00:00.003 A>R 62DE000102\\r\\r>\n"
        "10:00:00.004 F>A ATSH000720\\r\n10:00:00.005 A>R OK\\r\\r>\n"
        "10:00:00.006 F>A STPXd:22DE00,r:1\\r\n10:00:00.007 A>R 62DE00AABB\\r\\r>\n")
    replay = relay_mod.Replay(relay_mod.load_recording([str(log)]), echo=lambda s: None)
    assert replay.answer("ATSH000726") == b"OK\r\r>"
    assert replay.answer("STPXd:22DE00,r:1") == b"62DE000102\r\r>"     # header decides which
    replay.answer("ATSH000720")
    assert replay.answer("STPXd:22DE00,r:1") == b"62DE00AABB\r\r>"
    assert replay.answer("2704123456") == b"6704\r\r>"                 # any key unlocks
    assert replay.answer("22F1001") == b"NO DATA\r\r>"
    assert replay.answer("ATXYZ") == b"OK\r\r>"
