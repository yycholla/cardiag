"""Configuration snapshots: read from the car, imported from FORScan, and compared like commits.

Every read of the car and every imported FORScan backup becomes a snapshot. A
snapshot points at the car's previous one and holds the whole state after it,
so any two can be compared and the history reads like a commit log.

Reading the car sends only reads: `22 DExx` to each module, and, for a block a
module refuses in its normal session, `10 03` (extended session) and a second
read, always followed by `10 01`. Nothing here unlocks a module or writes.
"""

from __future__ import annotations

import re

from . import asbuilt
from .elm import AdapterError
from .obd import Obd
from .service import Hub
from .store import Store

# The modules the page reads from the car: the two with named settings.
READ_MODULES = ("BdyCM", "IPC")

# Refusals that may lift in the extended session: not supported in this session, conditions not
# correct, security access denied (the last will not lift without unlocking, but costs one try).
_SESSION_REASONS = {0x7F: "not in the normal session", 0x22: "conditions not right", 0x33: "needs unlocking"}
_REASONS = {
    0x11: "service not supported", 0x12: "not supported", 0x13: "bad request length", 0x31: "no such block",
    0x78: "module still busy", **_SESSION_REASONS,
}

_MAX_FILES = 20
_MAX_FILE_BYTES = 64 * 1024
_ABT_LINE = re.compile(r"([0-9A-F]{3})([G-Z][0-9A-F])([G-Z][0-9A-F])([0-9A-F]*)([0-9A-F]{2})")
_VIN_IN_NAME = re.compile(r"(?<![A-Z0-9])([A-HJ-NPR-Z0-9]{17})(?![A-Z0-9])")


# ---- FORScan .abt files ------------------------------------------------------------------


def _abt_number(code: str) -> int:
    """FORScan's two-character block and row numbers: G1 is 1, GF is 15, H0 is 16."""
    return (ord(code[0]) - ord("G")) * 16 + int(code[1], 16)


def parse_abt(text: str) -> tuple[str, dict[str, str]]:
    """One module's blocks from a FORScan as-built backup. Returns the module's name and {DExx: hex}.

    Each data line is the module address, the block, the row, up to five data bytes and a checksum:
    the low byte of the sum of the address (as two bytes), block, row and data. Blocks are numbered
    from DE00 (H1 is block 17, DE10), not by position in the file. A bad checksum or
    a gap between rows means the file was damaged, and it is refused.
    """
    address, rows = None, {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip().upper()
        if not line or line.startswith(";"):
            continue
        match = _ABT_LINE.fullmatch(line)
        if not match or len(match.group(4)) % 2:
            raise ValueError(f"line {number} is not a FORScan as-built line")
        here, block_code, row_code, data, checksum = match.groups()
        block, row, payload = _abt_number(block_code), _abt_number(row_code), bytes.fromhex(data)
        # The block and row enter the checksum as their decimal digits read as hex: row 10 counts as 0x10.
        total = sum(bytes.fromhex(here.rjust(4, "0"))) + int(str(block), 16) + int(str(row), 16) + sum(payload)
        if total & 0xFF != int(checksum, 16):
            raise ValueError(f"line {number} has a bad checksum; the file may be damaged")
        if address not in (None, here):
            raise ValueError("the file holds more than one module")
        address = here
        if (block, row) in rows:
            raise ValueError(f"line {number} repeats block {block} row {row}")
        rows[(block, row)] = payload
    if address is None:
        raise ValueError("the file holds no as-built lines")
    module = next((m for m in asbuilt.MODULES if m.request == address), None)
    if module is None:
        raise ValueError(f"module {address} is not one this app knows")
    blocks: dict[str, bytearray] = {}
    next_row: dict[int, int] = {}
    for (block, row) in sorted(rows):
        if row != next_row.get(block, 1):
            raise ValueError(f"block {block} is missing a row")
        next_row[block] = row + 1
        blocks.setdefault(f"{0xDE00 + block - 1:04X}", bytearray()).extend(rows[(block, row)])
    return module.name, {did: bytes(data).hex().upper() for did, data in blocks.items()}


def import_files(hub: Hub, db_path: str | None, body: dict) -> dict:
    """Keep FORScan backups as one snapshot. All files must be for the same car."""
    files = body.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= _MAX_FILES:
        raise ValueError(f"send between 1 and {_MAX_FILES} .abt files")
    blocks: dict[str, dict[str, str]] = {}
    vins = set()
    for item in files:
        name = item.get("name") if isinstance(item, dict) else None
        text = item.get("text") if isinstance(item, dict) else None
        if not isinstance(name, str) or not isinstance(text, str) or len(text) > _MAX_FILE_BYTES:
            raise ValueError("each file needs a name and its text, at most 64 KB")
        try:
            module, found = parse_abt(text)
        except ValueError as exc:
            raise ValueError(f"{name}: {exc}") from None
        if module in blocks:
            raise ValueError(f"two files are for {module}; send one backup per module")
        blocks[module] = found
        if match := _VIN_IN_NAME.search(name.upper()):
            vins.add(match.group(1))
    if len(vins) > 1:
        raise ValueError("the files are for different cars: " + ", ".join(sorted(vins)))
    vin = vins.pop() if vins else hub.status().get("vin")
    note = _note(body.get("note"))
    store = Store(db_path)
    try:
        number = store.add_snapshot(vin=vin, source="forscan", note=note, blocks=blocks, problems=[])
    finally:
        store.close()
    return {"snapshot": number, **history(hub, db_path, vin)}


# ---- reading the car ---------------------------------------------------------------------


def _command(obd: Obd, text: str) -> bool:
    lines = obd.elm.command(text)
    return any("OK" in line.upper() for line in lines)


def _reason(answer: bytes | None) -> str:
    if answer is None:
        return "no answer"
    return _REASONS.get(answer[2], f"refused ({answer[2]:02X})") if len(answer) >= 3 else "refused"


def _read_module(obd: Obd, module: asbuilt.Module) -> tuple[dict[str, str], list[dict]]:
    request, reply = int(module.request, 16), int(module.reply, 16)
    dids = [did for did, _, _ in module.blocks]
    found: dict[str, str] = {}
    refused: dict[str, bytes | None] = {}

    def read(did: str) -> None:
        answer = obd.ask(request, reply, bytes.fromhex("22" + did))
        if answer and answer[:3] == bytes.fromhex("62" + did):
            found[did] = answer[3:].hex().upper()
            refused.pop(did, None)
        else:
            refused[did] = answer

    for did in dids:
        read(did)
    retry = [did for did, answer in refused.items() if answer and len(answer) >= 3 and answer[2] in _SESSION_REASONS]
    if retry:
        answer = obd.ask(request, reply, b"\x10\x03")
        if answer and answer[:2] == b"\x50\x03":
            try:
                for did in retry:
                    read(did)
            finally:
                obd.ask(request, reply, b"\x10\x01")  # back to the normal session, whatever happened
    problems = [{"module": module.name, "did": did, "reason": _reason(answer)} for did, answer in refused.items()]
    return found, problems


def read_car(obd: Obd, names: tuple[str, ...] = READ_MODULES) -> tuple[dict[str, dict[str, str]], list[dict]]:
    """Read each module's configuration blocks. Returns the blocks and the ones that could not be read."""
    if obd.protocol is None or not obd.maker_values:
        raise ValueError("configuration can only be read on an 11-bit CAN network")
    blocks: dict[str, dict[str, str]] = {}
    problems: list[dict] = []
    restore = f"ATSP{obd.protocol.number}"
    for name in names:
        module = next(m for m in asbuilt.MODULES if m.name == name)
        switched = False
        try:
            if module.bus == "MS":
                switched = _command(obd, "STP53")
                if not switched or not _command(obd, "STPBR125000"):
                    problems.append({"module": name, "did": None,
                                     "reason": "the adapter cannot reach the MS bus (needs an OBDLink with STN commands)"})
                    continue
            # Only this module's replies, and flow control addressed to it, so long blocks come through.
            for setting in (f"ATCRA{module.reply}", f"ATFCSH{module.request}", "ATFCSD300000", "ATFCSM1"):
                if not _command(obd, setting):
                    raise AdapterError(f"the adapter refused {setting}")
            obd.forget_header()
            found, missing = _read_module(obd, module)
            if found:
                blocks[name] = found
            problems += missing
        finally:
            for setting in ("ATCRA", "ATFCSM0", *([restore] if switched else [])):
                try:
                    _command(obd, setting)
                except AdapterError:
                    pass
            obd.forget_header()
    return blocks, problems


def read_from_car(hub: Hub, db_path: str | None, body: dict) -> dict:
    """Read the car's configuration now and keep it as a snapshot."""
    note = _note(body.get("note"))
    status = hub.status()
    blocks, problems = hub.use_car(read_car, timeout=180.0)
    if not blocks:
        reasons = sorted({problem["reason"] for problem in problems}) or ["nothing answered"]
        raise ValueError("no configuration blocks could be read: " + "; ".join(reasons))
    store = Store(db_path)
    try:
        number = store.add_snapshot(
            vin=status.get("vin"), source="simulation" if status.get("simulation") else "car",
            note=note, blocks=blocks, problems=problems,
        )
    finally:
        store.close()
    return {"snapshot": number, "problems": problems, **history(hub, db_path, status.get("vin"))}


# ---- the history -------------------------------------------------------------------------


def _note(value: object) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value.strip()) > 200:
        raise ValueError("the note must be text of at most 200 characters")
    return value.strip() or None


def _summary(changes: list[dict]) -> dict:
    names = list(dict.fromkeys(setting["name"] for change in changes for setting in change["settings"]))
    return {"blocks": len(changes), "settings": names}


def history(hub: Hub, db_path: str | None, vin: str | None = None) -> dict:
    """The snapshot log, newest first, each with what changed since its parent."""
    vin = vin if vin is not None else hub.status().get("vin")
    store = Store(db_path)
    try:
        everything = store.snapshots()
    finally:
        store.close()
    by_id = {snapshot["id"]: snapshot for snapshot in everything}
    entries = []
    for snapshot in everything:
        parent = by_id.get(snapshot["parent"])
        changes = asbuilt.diff(parent["tree"] if parent else {}, snapshot["tree"])
        entries.append({
            "id": snapshot["id"], "parent": snapshot["parent"], "vin": snapshot["vin"],
            "created_at": snapshot["created_at"], "source": snapshot["source"], "note": snapshot["note"],
            "modules": sorted(snapshot["touched"]),
            "read": sum(len(found) for found in snapshot["touched"].values()),
            "problems": snapshot["problems"],
            "changed": _summary(changes) if parent else None,
            "against_capture": _summary(asbuilt.diff(_capture_for(snapshot["tree"]), snapshot["tree"])),
        })
    return {"vin": vin or None, "snapshots": entries}


def _capture_for(tree: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """The capture's blocks for the modules and blocks a tree has, so a partial snapshot compares fairly."""
    capture = asbuilt.capture_tree()
    return {module: {did: capture[module][did] for did in found if did in capture.get(module, {})}
            for module, found in tree.items() if module in capture}


def _tree(store: Store, which: object) -> tuple[str, dict[str, dict[str, str]]]:
    if which in (None, "", "capture"):
        return "the bundled capture", asbuilt.capture_tree()
    try:
        number = int(which)  # type: ignore[arg-type]
        return f"snapshot {number}", store.snapshot(number)["tree"]
    except (TypeError, ValueError):
        raise ValueError("compare a snapshot number or 'capture'") from None
    except KeyError:
        raise ValueError(f"there is no snapshot {which}") from None


def compare(db_path: str | None, before: object, after: object) -> dict:
    """What changed from one snapshot (or the capture) to another, block by block."""
    store = Store(db_path)
    try:
        old_label, old = _tree(store, before)
        new_label, new = _tree(store, after)
    finally:
        store.close()
    if before in (None, "", "capture"):
        old = _capture_for(new)  # only what both sides could have
    return {"before": old_label, "after": new_label, "changes": asbuilt.diff(old, new)}


def config_report(hub: Hub, db_path: str | None, snapshot: object) -> dict:
    """The Configuration page's blocks, from the capture or from one snapshot."""
    simulation = hub.status()["simulation"]
    if snapshot in (None, "", "capture"):
        return asbuilt.report(simulation)
    store = Store(db_path)
    try:
        label, tree = _tree(store, snapshot)
    finally:
        store.close()
    return asbuilt.report(simulation, tree, source=label)
