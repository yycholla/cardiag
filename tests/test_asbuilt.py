"""The configuration blocks and the settings mapped onto them."""

import re
from pathlib import Path

import pytest

from cardiag import asbuilt
from cardiag.asbuilt import Setting

CAPTURE = Path(__file__).parent.parent / "docs" / "data" / "focus-2017-asbuilt.txt"


def test_the_catalog_fits_its_blocks():
    asbuilt.check()
    asbuilt.check(asbuilt.SETTINGS + asbuilt.EXAMPLES, asbuilt.MODULES + (asbuilt.EXAMPLE_MODULE,))


def test_the_blocks_are_the_captured_ones():
    captured = {}
    module = None
    for line in CAPTURE.read_text(encoding="utf-8").splitlines():
        if match := re.match(r"(\S+).*address (\w+)", line):
            module = match.group(1)
        elif match := re.match(r"\s+(DE\w\w)\s+block (\d+)\s+\d+ bytes\s+(\S+)", line):
            data = None if match.group(3).startswith("<") else match.group(3)
            captured[(module, match.group(1))] = (int(match.group(2)), data)
    ours = {(m.name, did): (number, data) for m in asbuilt.MODULES for did, number, data in m.blocks}
    assert ours == captured
    assert len(ours) == 62 and len(asbuilt.MODULES) == 10
    assert ours[("ABS", "DE00")][1] is None and ours[("RCM", "DE00")][1] is None


def test_the_key_in_ignition_beep_reads_the_written_bit():
    beep = next(s for s in asbuilt.SETTINGS if s.id == "ipc.key_in_ignition_beep")
    assert beep.raw(bytes.fromhex("FFFFFF3E")) == 1
    assert beep.raw(bytes.fromhex("FFFF7F3E")) == 0
    # Which state turns the beep on is not known, so the states are not named.
    assert beep.describe(1) == "Bit set" and beep.describe(0) == "Bit clear"


def test_each_kind_says_its_value_in_words():
    examples = {s.id: s for s in asbuilt.EXAMPLES}
    block = bytes.fromhex(asbuilt.EXAMPLE_MODULE.blocks[0][2])
    words = {key: setting.describe(setting.raw(block)) for key, setting in examples.items()}
    assert words == {
        "example.chime": "On",
        "example.splash": "Ford Performance",
        "example.drl": "Fog lamps, Turn lamps",
        "example.lamps": "21 s",
        "example.tank": "60 L",
        "example.raw": "017F",
    }
    assert examples["example.splash"].describe(2) == "Unlisted value 2"
    assert examples["example.drl"].describe(0) == "None"


@pytest.mark.parametrize(
    "setting, problem",
    [
        (Setting("a", "A", "IPC", "DE09", "toggle", byte=1, mask=1), "runs past the end"),
        (Setting("a", "A", "IPC", "DE11", "toggle", byte=0, mask=0x100), "does not fit its bytes"),
        (Setting("a", "A", "IPC", "DE99", "toggle", byte=0, mask=1), "not a known block"),
        (Setting("a", "A", "ABS", "DE00", "toggle", byte=0, mask=1), "withheld"),
        (Setting("a", "A", "IPC", "DE11", "choice", byte=0, mask=0x03, options=((4, "x"),)), "does not fit its bits"),
        (Setting("a", "A", "IPC", "DE11", "flags", byte=0, mask=0x0F, bits=((3, "x"),)), "not one of its bits"),
        (Setting("a", "A", "IPC", "DE11", "toggle", byte=2, mask=0xC0), "overlaps"),
    ],
)
def test_a_setting_that_does_not_fit_is_refused(setting, problem):
    with pytest.raises(ValueError, match=problem):
        asbuilt.check(asbuilt.SETTINGS + (setting,))


def test_the_report_adds_examples_only_for_a_simulated_car():
    real = asbuilt.report(None)
    assert real["examples"] is False
    assert [m["name"] for m in real["modules"]][-1] == "GPSM"
    ipc = next(m for m in real["modules"] if m["name"] == "IPC")
    block = next(b for b in ipc["blocks"] if b["did"] == "DE11")
    assert block["hex"] == "FFFFFF3E" and block["size"] == 4
    assert block["settings"][0]["raw"] == 1 and block["settings"][0]["states"] is None
    simulated = asbuilt.report("focus")
    assert simulated["examples"] is True and simulated["modules"][-1]["name"] == "EXAMPLE"
    kinds = {s["kind"] for b in simulated["modules"][-1]["blocks"] for s in b["settings"]}
    assert kinds == set(asbuilt.KINDS)
