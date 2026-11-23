"""Diagnostic services against the two simulated vehicles, with the clock frozen at zero."""

import pytest

from cardiag.elm import Elm327
from cardiag.obd import Obd
from cardiag.sim import SimElm, SimTransport, make_focus, make_tahoe

ENGINE, TRANSMISSION = 0x7E8, 0x7E9


def connect(vehicle) -> Obd:
    elm = Elm327(SimTransport(SimElm(vehicle, clock=lambda: 0.0)))
    elm.initialise()
    obd = Obd(elm)
    obd.connect()
    return obd


@pytest.fixture
def focus() -> Obd:
    return connect(make_focus())


@pytest.fixture
def tahoe() -> Obd:
    return connect(make_tahoe())


def test_focus_is_found_on_can_with_two_modules(focus):
    assert (focus.protocol.number, focus.protocol.family, focus.protocol.id_bits) == ("6", "can", 11)
    assert focus.ecus == [ENGINE, TRANSMISSION]


def test_focus_vin_spans_several_frames(focus):
    assert focus.vin() == "1FADP3F2XHL123456"


def test_focus_supported_pids_are_tracked_per_module(focus):
    supported = focus.supported_pids()
    assert {0x0C, 0x0D, 0x23, 0x42, 0x5C} <= supported[ENGINE]
    assert supported[TRANSMISSION] == {0x0D}
    assert not any(pid % 0x20 == 0 for pids in supported.values() for pid in pids)


def test_focus_live_values(focus):
    rpm = focus.read_pid(0x0C)
    assert (rpm.key, rpm.name, rpm.value, rpm.unit, rpm.ecu) == ("01:0C", "Engine speed", 800.0, "rpm", ENGINE)
    assert focus.read_pid(0x07).value == 12.5
    assert focus.read_pid(0x0D, ecu=TRANSMISSION).ecu == TRANSMISSION
    assert focus.read_pid(0x99) is None


def test_focus_trouble_codes_per_module(focus):
    assert focus.read_dtcs("stored") == {ENGINE: ["P0171"], TRANSMISSION: ["P0902"]}
    assert focus.read_dtcs("pending") == {ENGINE: ["P0456"], TRANSMISSION: []}
    assert focus.read_dtcs("permanent") == {ENGINE: ["P0171"], TRANSMISSION: []}


def test_focus_readiness(focus):
    (status,) = focus.monitor_status()
    assert (status.ecu, status.mil_on, status.dtc_count) == (ENGINE, True, 1)
    assert [m.name for m in status.monitors if not m.complete] == ["Evaporative system"]


def test_focus_freeze_frame(focus):
    frame = focus.freeze_frame()
    assert (frame.dtc, frame.ecu) == ("P0171", ENGINE)
    values = {reading.name: reading.value for reading in frame.readings}
    assert values["Engine speed"] == 1850.0
    assert values["Vehicle speed"] == 52.0
    assert all(reading.key.startswith("02:") for reading in frame.readings)


def test_tahoe_is_found_on_j1850_vpw(tahoe):
    assert (tahoe.protocol.number, tahoe.protocol.family) == ("2", "legacy")
    assert tahoe.ecus == [0x10]


def test_tahoe_vin_spans_several_lines(tahoe):
    assert tahoe.vin() == "1GNEK13Z03J123456"


def test_tahoe_codes_span_two_lines_and_padding_is_dropped(tahoe):
    assert tahoe.read_dtcs("stored") == {0x10: ["P0300", "P0171", "P0174", "P0420"]}
    assert tahoe.read_dtcs("pending") == {0x10: ["P0300"]}
    assert tahoe.read_dtcs("permanent") == {}


def test_tahoe_live_values_and_readiness(tahoe):
    assert tahoe.read_pid(0x0C).value == 800.0
    assert tahoe.read_pid(0x09).value == pytest.approx(4.7, abs=0.4)
    (status,) = tahoe.monitor_status()
    assert (status.mil_on, status.dtc_count) == (True, 4)


def test_tahoe_has_no_freeze_frame(tahoe):
    assert tahoe.freeze_frame() is None
