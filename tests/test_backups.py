"""Configuration snapshots: FORScan files, reading the car, and the history between them."""

import pytest

from cardiag import asbuilt, backups
from cardiag.elm import Elm327
from cardiag.obd import Obd
from cardiag.sim import SimElm, SimTransport, make_focus
from cardiag.store import Store

from conftest import wait_for


def abt(address: str, blocks: dict[str, str]) -> str:
    """A FORScan .abt file for some blocks, five bytes to a row, checksums as FORScan writes them."""

    def code(number: int) -> str:
        return chr(ord("G") + number // 16) + f"{number % 16:X}"

    lines = []
    for did, data in blocks.items():
        block = int(did, 16) - 0xDE00 + 1
        lines.append(f";Block {block}")
        payload = bytes.fromhex(data)
        for row, start in enumerate(range(0, len(payload), 5), 1):
            part = payload[start:start + 5]
            total = sum(bytes.fromhex(address.rjust(4, "0"))) + int(str(block), 16) + int(str(row), 16) + sum(part)
            lines.append(f"{address}{code(block)}{code(row)}{part.hex().upper()}{total & 0xFF:02X}")
    return "\n".join(lines) + "\n"


def connected(**sim_options) -> tuple[Obd, SimElm]:
    sim = SimElm(make_focus(), **sim_options)
    elm = Elm327(SimTransport(sim))
    elm.initialise()
    obd = Obd(elm)
    obd.connect()
    return obd, sim


def test_lines_from_forscan_files_check_out():
    # Real lines from the car's backups: the cluster's first block, a body control row numbered 10,
    # and the cluster's DE10, which FORScan numbers 17 (H1) though it is the 15th block in the file.
    module, blocks = backups.parse_abt(";Block 1\n720G1G1430100006D\n;Block 15\n720H1G1FFFFFF9FDB\n")
    assert module == "IPC" and blocks == {"DE00": "43010000", "DE10": "FFFFFF9F"}
    # The body control module's first block, as FORScan saved it. Row 10 (GA) enters the checksum
    # as 0x10: 07 + 26 + 01 + 10 = 3E.
    body = ("726G1G1010001846318 726G1G2000000001242 726G1G341385300F5F2 726G1G41932010E3CC8 "
            "726G1G50900000B0B52 726G1G6924000004046 726G1G740037D0000F5 726G1G80A0000000040 "
            "726G1G9000000000037 726G1GA00000000003E").replace(" ", "\n")
    assert backups.parse_abt(body) == ("BdyCM", {"DE00": asbuilt.capture_tree()["BdyCM"]["DE00"]})
    with pytest.raises(ValueError, match="missing a row"):
        backups.parse_abt("726G1GA00000000003E\n")


def test_a_whole_backup_reads_back_the_same_blocks():
    capture = asbuilt.capture_tree()
    for name, request in (("BdyCM", "726"), ("IPC", "720")):
        assert backups.parse_abt(abt(request, capture[name])) == (name, capture[name])


@pytest.mark.parametrize(
    "text, problem",
    [
        ("720G1G1430100006E\n", "bad checksum"),
        ("720G1G1430100006D\n726G2G1000424247C\n", "more than one module"),
        ("hello\n", "not a FORScan as-built line"),
        (";nothing here\n", "no as-built lines"),
        ("123G1G100000026\n", "not one this app knows"),
    ],
)
def test_a_damaged_or_foreign_file_is_refused(text, problem):
    with pytest.raises(ValueError, match=problem):
        backups.parse_abt(text)


def test_reading_the_simulated_car():
    obd, sim = connected()
    blocks, problems = backups.read_car(obd)
    capture = asbuilt.capture_tree()
    assert problems == []
    assert blocks["BdyCM"] == capture["BdyCM"]  # only answered in the extended session
    assert {did for did in capture["IPC"] if blocks["IPC"][did] != capture["IPC"][did]} == {"DE11"}
    assert blocks["IPC"]["DE11"] == "FFFF7F3E"
    body = next(ecu for ecu in sim.vehicle.ecus if ecu.address == 0x72E)
    assert body.session == 0x01  # put back in the normal session
    assert sim.bus == "HS" and obd.read_pid(0x0C) is not None  # and the adapter back on the car's main bus


def test_a_plain_elm327_reads_body_control_but_not_the_cluster():
    obd, _ = connected(stn=False)
    blocks, problems = backups.read_car(obd)
    assert set(blocks) == {"BdyCM"}
    assert problems == [{"module": "IPC", "did": None,
                         "reason": "the adapter cannot reach the MS bus (needs an OBDLink with STN commands)"}]


def test_a_module_that_stays_locked_is_reported():
    obd, sim = connected()
    body = next(ecu for ecu in sim.vehicle.ecus if ecu.address == 0x72E)
    body.config_needs_session = True
    original = sim.vehicle._reply

    def deny_session(ecu, service, args, t, addressed=False):
        if ecu is body and service == 0x10:
            return [bytes([0x7F, 0x10, 0x22])]
        return original(ecu, service, args, t, addressed)

    sim.vehicle._reply = deny_session
    blocks, problems = backups.read_car(obd, ("BdyCM",))
    assert blocks == {} and {p["reason"] for p in problems} == {"not in the normal session"}
    assert len(problems) == len(asbuilt.capture_tree()["BdyCM"])


def test_snapshots_chain_like_commits(tmp_path):
    store = Store(tmp_path / "db")
    first = store.add_snapshot(vin="V", source="forscan", note=None, blocks={"IPC": {"DE11": "FFFFFF3E", "DE00": "43010000"}}, problems=[])
    second = store.add_snapshot(vin="V", source="car", note="after", blocks={"IPC": {"DE11": "FFFF7F3E"}}, problems=[])
    other = store.add_snapshot(vin="W", source="car", note=None, blocks={"BdyCM": {"DE02": "0101"}}, problems=[])
    latest = store.snapshot(second)
    assert latest["parent"] == first and store.snapshot(other)["parent"] is None
    assert latest["tree"] == {"IPC": {"DE00": "43010000", "DE11": "FFFF7F3E"}}  # the parent's blocks carried forward
    assert latest["touched"] == {"IPC": {"DE11": "FFFF7F3E"}}
    assert [s["id"] for s in store.snapshots("V")] == [second, first]
    store.close()


def test_a_diff_names_the_settings_that_moved():
    before = {"IPC": {"DE11": "FFFFFF3E"}}
    after = {"IPC": {"DE11": "FFFF7F3E"}, "BdyCM": {"DE02": "0101"}}
    changes = asbuilt.diff(before, after)
    added = next(c for c in changes if c["module"] == "BdyCM")
    assert added["before"] is None and added["settings"] == []
    chime = next(c for c in changes if c["module"] == "IPC")
    assert chime["bytes"] == [2]
    assert {"name": "Key-in-ignition beep", "before": "Enabled", "after": "Disabled"}.items() <= chime["settings"][0].items()


def test_reading_importing_and_comparing_over_the_web(served):
    status, empty = served.request("/api/config/history")
    assert status == 200 and empty == {"vin": "1FADP3F2XHL123456", "snapshots": []}

    status, read = served.request("/api/config/read", {"note": "parked"})
    assert status == 200 and read["problems"] == []
    first = read["snapshots"][0]
    assert first["source"] == "car" and first["note"] == "parked" and first["read"] == 36 and first["changed"] is None
    assert first["against_capture"] == {"blocks": 1, "settings": ["Key-in-ignition beep"]}

    capture = asbuilt.capture_tree()
    files = [{"name": "1FADP3F2XHL123456_IPC_20261125.abt", "text": abt("720", capture["IPC"])}]
    status, imported = served.request("/api/config/import", {"files": files})
    assert status == 200
    entry = imported["snapshots"][0]
    assert entry["parent"] == first["id"] and entry["source"] == "forscan" and entry["modules"] == ["IPC"]
    assert entry["changed"] == {"blocks": 1, "settings": ["Key-in-ignition beep"]}

    status, again = served.request("/api/config/read", {})
    assert again["snapshots"][0]["changed"]["blocks"] == 1

    status, diff = served.request(f"/api/config/compare?before={first['id']}&after={again['snapshot']}")
    assert status == 200 and diff["changes"] == []
    status, shown = served.request(f"/api/config?snapshot={entry['id']}")
    ipc = next(m for m in shown["modules"] if m["name"] == "IPC")
    block = next(b for b in ipc["blocks"] if b["did"] == "DE11")
    assert shown["source"] == f"snapshot {entry['id']}" and block["hex"] == "FFFFFF3E" and block["origin"] == "snapshot"
    body = next(m for m in shown["modules"] if m["name"] == "BdyCM")
    assert body["blocks"][0]["origin"] == "snapshot"  # carried forward from the first read

    assert served.request("/api/config?snapshot=99")[1] == {"error": "there is no snapshot 99"}
    bad = [{"name": "x.abt", "text": "720G1G1430100006E\n"}]
    assert served.request("/api/config/import", {"files": bad})[1] == {"error": "x.abt: line 1 has a bad checksum; the file may be damaged"}
    mixed = files + [{"name": "1FADP3F25HL309325_BdyCM.abt", "text": abt("726", capture["BdyCM"])}]
    assert "different cars" in served.request("/api/config/import", {"files": mixed})[1]["error"]
    wait_for(lambda: served.hub.status()["state"] == "connected")
