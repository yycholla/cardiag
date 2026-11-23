"""The command-line tool end to end, against simulated vehicles."""

import csv
import io

import pytest

from cardiag.cli import main
from cardiag.sim import PtyAdapter, SimElm, make_focus


@pytest.mark.parametrize("argv", [["--sim", "focus", "codes"], ["codes", "--sim", "focus"]])
def test_codes_with_options_before_or_after_the_command(argv, capsys):
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "Check-engine light: ON" in out
    assert "Stored     P0171" in out
    assert "Stored     P0902" in out
    assert "Freeze frame saved with P0171" in out


def test_tahoe_reports_permanent_codes_as_unavailable(capsys):
    assert main(["--sim", "tahoe", "codes"]) == 0
    out = capsys.readouterr().out
    assert "P0300, P0171, P0174, P0420" in out
    assert "Permanent  not reported by this module" in out


def test_info_over_a_serial_device(capsys):
    with PtyAdapter(SimElm(make_focus())) as adapter:
        assert main(["--port", adapter.path, "info"]) == 0
    out = capsys.readouterr().out
    assert "1FADP3F2XHL123456" in out
    assert "Engine (7E8), Transmission (7E9)" in out


def test_missing_port_is_reported_not_raised(capsys):
    assert main(["--port", "/dev/does-not-exist", "info"]) == 1
    assert "error:" in capsys.readouterr().err


def test_record_list_and_export_a_session(tmp_path, capsys):
    db = str(tmp_path / "sessions.db")
    recorded = main(
        ["--sim", "focus", "--db", db, "live", "--seconds", "0.3", "--interval", "0.05",
         "--pids", "0C,0D,03,99", "--log", "--note", "cold start"]
    )
    assert recorded == 0
    captured = capsys.readouterr()
    assert "Saved session 1" in captured.out
    assert "does not report PID 99" in captured.err

    assert main(["--db", db, "sessions"]) == 0
    listing = capsys.readouterr().out
    assert "1FADP3F2XHL123456" in listing and "cold start" in listing

    assert main(["--db", db, "export", "1"]) == 0
    rows = list(csv.reader(io.StringIO(capsys.readouterr().out)))
    assert rows[0] == ["seconds", "Engine speed (rpm)", "Vehicle speed (km/h)", "Fuel system status"]
    assert len(rows) >= 3
    first = rows[1]
    assert float(first[0]) >= 0
    assert 700 < float(first[1]) < 900
    assert first[3] == "closed loop"

    assert main(["--db", db, "export", "99"]) == 1
