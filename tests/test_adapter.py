"""The adapter driver, against scripted replies and against the simulated adapter."""

import pytest

from cardiag.elm import AdapterError, AdapterTimeout, Elm327, NoData, NoVehicle
from cardiag.obd import Obd
from cardiag.sim import PtyAdapter, SimElm, SimTransport, make_focus, make_tahoe
from cardiag.transport import SerialTransport


class Scripted:
    """A transport that answers each command with a fixed byte string."""

    def __init__(self, replies: dict[str, bytes]) -> None:
        self.replies = replies
        self.pending = b""

    def write(self, data: bytes) -> None:
        self.pending = self.replies.get(data.decode().strip(), b"")

    def read(self) -> bytes:
        data, self.pending = self.pending, b""
        return data

    def flush_input(self) -> None:
        self.pending = b""

    def close(self) -> None:
        pass


def test_echo_blank_lines_and_stray_nul_bytes_are_removed():
    elm = Elm327(Scripted({"0100": b"0100\r\x007E8064100BE3FA813\r\r>"}))
    assert elm.command("0100") == ["7E8064100BE3FA813"]


def test_progress_messages_are_not_treated_as_data():
    elm = Elm327(Scripted({"0100": b"SEARCHING...\r7E8064100BE3FA813\r\r>"}))
    assert elm.request("0100") == ["7E8064100BE3FA813"]


@pytest.mark.parametrize(
    "reply, error",
    [
        (b"NO DATA\r\r>", NoData),
        (b"SEARCHING...\rUNABLE TO CONNECT\r\r>", NoVehicle),
        (b"CAN ERROR\r\r>", AdapterError),
        (b"7E8064100BE3\r<DATA ERROR\r\r>", AdapterError),
        (b"?\r\r>", AdapterError),
    ],
)
def test_adapter_error_messages_raise(reply, error):
    with pytest.raises(error):
        Elm327(Scripted({"0100": reply})).request("0100")


def test_a_reply_that_never_finishes_times_out():
    with pytest.raises(AdapterTimeout):
        Elm327(Scripted({"0100": b"7E8064100"})).command("0100", timeout=0.05)


def test_initialise_identifies_an_obdlink_adapter():
    info = Elm327(SimTransport(SimElm(make_focus()))).initialise()
    assert info.elm_version.startswith("ELM327")
    assert "OBDLink EX" in info.device
    assert info.voltage == pytest.approx(12.6)


def test_initialise_copes_with_a_plain_elm327():
    info = Elm327(SimTransport(SimElm(make_focus(), stn=False))).initialise()
    assert info.device is None and info.firmware is None
    assert info.label == info.elm_version


def test_adapter_without_a_car_reports_no_vehicle():
    elm = Elm327(SimTransport(SimElm(None)))
    elm.initialise()
    with pytest.raises(NoVehicle):
        Obd(elm).connect()


@pytest.mark.parametrize("make, vin", [(make_focus, "1FADP3F2XHL123456"), (make_tahoe, "1GNEK13Z03J123456")])
def test_real_serial_path_through_a_pseudo_terminal(make, vin):
    """Speed detection, pyserial and the driver, end to end over a serial device."""
    with PtyAdapter(SimElm(make())) as adapter:
        transport = SerialTransport(adapter.path)
        try:
            elm = Elm327(transport)
            elm.initialise()
            obd = Obd(elm)
            obd.connect()
            assert obd.vin() == vin
        finally:
            transport.close()
