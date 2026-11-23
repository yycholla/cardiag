"""Wire-format decoding, checked against hand-built examples rather than the simulator."""

import pytest

from cardiag.dtc import decode_dtc, encode_dtc, parse_dtcs
from cardiag.frames import FrameError, Message, parse_can, parse_legacy
from cardiag.obd import decode_monitor_status
from cardiag.pids import PIDS


def test_can_single_frame():
    assert parse_can(["7E8064100BE3FA813"]) == [Message(0x7E8, bytes.fromhex("4100BE3FA813"))]


def test_can_accepts_spaces_and_ignores_padding():
    assert parse_can(["7E8 03 41 0D 3C AA AA AA AA"]) == [Message(0x7E8, bytes.fromhex("410D3C"))]


def test_can_multi_frame_reply_is_reassembled():
    # Service 09 PID 02 reply carrying the VIN 1FADP3F2XHL123456 (20 bytes over three frames).
    lines = ["7E81014490201314641", "7E82144503346325848", "7E8224C313233343536"]
    (message,) = parse_can(lines)
    assert message.ecu == 0x7E8
    assert message.data[:3] == bytes.fromhex("490201")
    assert message.data[3:] == b"1FADP3F2XHL123456"


def test_can_replies_from_two_modules_can_interleave():
    lines = [
        "7E81014490201314641",
        "7E90641008000000100",
        "7E82144503346325848",
        "7E8224C313233343536",
    ]
    engine, transmission = parse_can(lines)
    assert (engine.ecu, len(engine.data)) == (0x7E8, 20)
    assert transmission == Message(0x7E9, bytes.fromhex("410080000001"))


def test_can_29_bit_identifiers():
    assert parse_can(["18DAF110064100BE3FA813"], id_bits=29) == [
        Message(0x18DAF110, bytes.fromhex("4100BE3FA813"))
    ]


def test_can_incomplete_long_reply_is_an_error():
    with pytest.raises(FrameError, match="incomplete"):
        parse_can(["7E81014490201314641", "7E82144503346325848"])


def test_legacy_line_drops_header_and_checksum():
    assert parse_legacy(["486B104100BE3FA811C4"]) == [Message(0x10, bytes.fromhex("4100BE3FA811"))]


@pytest.mark.parametrize(
    "raw, code",
    [("0133", "P0133"), ("0171", "P0171"), ("3400", "P3400"), ("4123", "C0123"), ("8123", "B0123"), ("C123", "U0123")],
)
def test_trouble_codes_round_trip(raw, code):
    data = bytes.fromhex(raw)
    assert decode_dtc(data[0], data[1]) == code
    assert encode_dtc(code) == data


def test_zero_pairs_are_padding_not_codes():
    assert parse_dtcs(bytes.fromhex("017100000420")) == ["P0171", "P0420"]


@pytest.mark.parametrize(
    "pid, raw, expected",
    [
        (0x04, "FF", 100.0),
        (0x05, "7B", 83.0),
        (0x06, "80", 0.0),
        (0x07, "90", 12.5),
        (0x07, "70", -12.5),
        (0x0B, "65", 101.0),
        (0x0C, "1AF8", 1726.0),
        (0x0D, "3C", 60.0),
        (0x0E, "98", 12.0),
        (0x0F, "28", 0.0),
        (0x10, "0190", 4.0),
        (0x14, "5A80", 0.45),
        (0x1F, "012C", 300.0),
        (0x23, "02B8", 6960.0),
        (0x32, "FFFC", -1.0),
        (0x3C, "1194", 410.0),
        (0x42, "3714", 14.1),
        (0x44, "8000", 1.0),
        (0x5C, "82", 90.0),
    ],
)
def test_standard_pid_scaling(pid, raw, expected):
    assert PIDS[pid].decode(bytes.fromhex(raw)) == pytest.approx(expected)


def test_fuel_system_status_is_reported_in_words():
    assert PIDS[0x03].decode(bytes.fromhex("0200")) == "closed loop"


def test_monitor_status_for_a_petrol_engine():
    # Light on with 3 codes; catalyst and evaporative monitors present, evaporative unfinished.
    status = decode_monitor_status(0x7E8, bytes.fromhex("83070504"))
    assert (status.mil_on, status.dtc_count, status.ignition) == (True, 3, "spark")
    assert {m.name: m.complete for m in status.monitors} == {
        "Misfire": True,
        "Fuel system": True,
        "Components": True,
        "Catalyst": True,
        "Evaporative system": False,
    }


def test_monitor_status_for_a_diesel_engine():
    status = decode_monitor_status(0x7E8, bytes.fromhex("000F4840"))
    assert (status.mil_on, status.dtc_count, status.ignition) == (False, 0, "compression")
    assert {m.name: m.complete for m in status.monitors} == {
        "Misfire": True,
        "Fuel system": True,
        "Components": True,
        "Boost pressure": True,
        "Particulate filter": False,
    }
