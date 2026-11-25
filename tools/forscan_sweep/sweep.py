#!/usr/bin/env python3
"""Drive FORScan's named configuration view through agentdesk, one setting at a
time, with the dry-run relay in between. For each setting: filter the table to
it, open its editor, OCR the option list, pick a different option, Write,
confirm, and record what the relay says FORScan tried to write.

    sweep.py MODULE NAMES_FILE OUT_JSONL WRITES_JSONL [--start N]

NAMES_FILE: the view's rows in table order, one per line.
Coordinates are for FORScan maximised on agentdesk's 1280x800 desktop.
"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import png

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT = os.path.join(HERE, "shot.png")
BLUE = (12, 94, 151)

FILTER = (183, 38)
ROW_X, ROW_Y0, ROW_H = 128, 88, 20
OPT_X, OPT_Y0, OPT_H = 490, 384, 20
EDIT_OK = (614, 476)
WRITE = (196, 681)
CONFIRM = (614, 442)
NOCHANGE_X = (639, 414)
DONE_OK = (638, 432)


def ad(*args):
    subprocess.run(["agentdesk", *map(str, args)], check=True, stdout=subprocess.DEVNULL)


def shot():
    ad("screenshot", "-o", SHOT)
    return png.read(SHOT)


def is_blue(img, xy):
    r, g, b = png.pixel(img, *xy)
    return abs(r - BLUE[0]) < 30 and abs(g - BLUE[1]) < 30 and abs(b - BLUE[2]) < 30


KEYS = {" ": "space", "-": "minus", ".": "period", ",": "comma", "/": "slash",
        "#": "shift+3", "(": "shift+9", ")": "shift+0", "*": "shift+8", "'": "apostrophe", ":": "shift+semicolon"}


def filter_text(name):
    """The longest leading run of the name that types cleanly."""
    out = ""
    for ch in name:
        if ch.isalnum() or ch in KEYS:
            out += ch
        else:
            break
    return out.rstrip()


TYPABLE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -")


def pick_filter(name, names):
    """Shortest typable run of the name (letters, digits, spaces, hyphens) that
    leaves at most 8 rows. Symbols like # and ( do not reach Wine."""
    segments, cur = [], ""
    for ch in name:
        if ch in TYPABLE:
            cur += ch
        else:
            segments.append(cur); cur = ""
    segments.append(cur)
    best = None
    for seg in segments:
        for i in range(len(seg)):
            for j in range(i + 3, len(seg) + 1):
                cand = seg[i:j]
                if cand != cand.strip():
                    continue
                count = sum(cand.lower() in n.lower() for n in names)
                if count <= 8 and (best is None or len(cand) < len(best)):
                    best = cand
                if count <= 8:
                    break
    return best or filter_text(name)


def type_filter(text):
    ad("click", *FILTER, "--count", 3)
    time.sleep(0.15)
    ad("key", "BackSpace")
    for ch in text:
        if ch in KEYS:
            ad("key", KEYS[ch])
        elif ch.isupper():
            ad("key", ch.lower())          # the filter ignores case
        else:
            ad("key", ch)
    time.sleep(0.5)


def editor_geometry(img):
    """(ok_y, list_top, list_bottom) of an open option editor, or None."""
    ok_y = next((y for y in range(420, 620) if is_blue(img, (614, y))), None)
    if ok_y is None:
        return None
    grey = (245, 245, 245)
    top = bottom = None
    for y in range(260, ok_y):
        p = png.pixel(img, 800, y)
        if top is None and p != grey and png.pixel(img, 800, y - 1) == grey:
            top = y
        elif top is not None and p == grey:
            bottom = y
            break
    if top is None or bottom is None:
        return None
    mid = (top + bottom) // 2
    left = next((x for x in range(380, 640) if png.pixel(img, x, mid) != grey and png.pixel(img, x - 1, mid) == grey), 442)
    right = next((x for x in range(900, 640, -1) if png.pixel(img, x, mid) != grey and png.pixel(img, x + 1, mid) == grey), 837)
    return ok_y, top, bottom, left, right


def ocr_description(img, geom, tag):
    ok_y, top, bottom, left, right = geom
    crop = os.path.join(HERE, "opts", f"{tag}_desc.png")
    box = (left, top - 66, right, top - 46)
    w, h, bpp, rows = img
    gray = (box[2] - box[0], box[3] - box[1], 3,
            [bytes(b"".join((b"\x00\x00\x00" if sum(rows[y][x*bpp:x*bpp+3]) < 420 else b"\xff\xff\xff")
                            for x in range(box[0], box[2]))) for y in range(box[1], box[3])])
    png.write_crop(gray, (0, 0, gray[0], gray[1]), crop, scale=3)
    text = subprocess.run(["tesseract", crop, "-", "--psm", "7"], capture_output=True, text=True).stdout.strip()
    return text.split(":", 1)[-1].strip()


def ocr_options(img, tag, geom=None):
    crop = os.path.join(HERE, "opts", f"{tag}.png")
    os.makedirs(os.path.dirname(crop), exist_ok=True)
    _, top, bottom, left, right = geom or (476, 375, 454, 442, 837)
    clean = png.binarize(img, (left + 2, top + 1, right - 2, bottom))
    png.write_crop(clean, (0, 0, clean[0], clean[1]), crop, scale=3)
    text = subprocess.run(["tesseract", crop, "-", "--psm", "6"], capture_output=True, text=True).stdout
    return [line.strip() for line in text.splitlines() if line.strip()], crop


def read_new(path, offset):
    if not os.path.exists(path):
        return [], offset
    with open(path) as f:
        f.seek(offset)
        lines = f.readlines()
        return [json.loads(l) for l in lines if l.strip()], f.tell()


def wait_for_writes(path, offset, timeout=25):
    deadline = time.time() + timeout
    got = []
    while time.time() < deadline:
        new, offset = read_new(path, offset)
        got += new
        if got:
            time.sleep(0.5)               # catch a second block in the same write
            new, offset = read_new(path, offset)
            return got + new, offset
        time.sleep(0.3)
    return got, offset


def one(module, names, index, writes_path, offset):
    import difflib
    name = names[index]
    text = pick_filter(name, names)
    matches = [i for i, n in enumerate(names) if text.lower() in n.lower()]
    row = matches.index(index)
    type_filter(text)
    record = {"module": module, "index": index, "name": name, "filter": text, "row": row}

    # 1. find the row whose editor describes this setting (the filter also matches values)
    for _ in range(10):
        ad("click", ROW_X, ROW_Y0 + ROW_H * row, "--count", 2)
        ad("move", 1200, 720)              # keep the row tooltip off the option list
        time.sleep(0.6)
        img = shot()
        geom = editor_geometry(img)
        if geom is None:
            if not forscan_alive():
                raise RuntimeError("FORScan is not running")
            ad("key", "Escape")
            record["skipped"] = "editor is not a list"
            return record, offset
        described = ocr_description(img, geom, f"{module}_{index:03d}")
        similar = difflib.SequenceMatcher(None, described.lower(), name.lower()).ratio()
        if similar >= 0.75:
            break
        ad("key", "Escape")
        time.sleep(0.3)
        row += 1
    else:
        record["skipped"] = "no row matched the name"
        return record, offset
    record["described"], record["row"] = described, row
    for attempt in range(3):
        record["options"], record["options_image"] = ocr_options(img, f"{module}_{index:03d}", geom)
        if record["options"] and all(o[:1].isdigit() for o in record["options"]):
            break
        time.sleep(0.4)
        img = shot()
        geom = editor_geometry(img) or geom

    # 2. pick options in turn until one differs from the current value
    for choice in range(6):
        if choice:
            ad("click", ROW_X, ROW_Y0 + ROW_H * row, "--count", 2)
            ad("move", 1200, 720)
            time.sleep(0.6)
            geom = editor_geometry(shot()) or geom
        ok_y, top = geom[0], geom[1]
        ad("click", OPT_X, top + 10 + OPT_H * choice)
        time.sleep(0.15)
        ad("click", 614, ok_y)
        time.sleep(0.3)
        ad("click", *WRITE)
        time.sleep(0.5)
        img = shot()
        if is_blue(img, CONFIRM):
            ad("click", *CONFIRM)
            writes, offset = wait_for_writes(writes_path, offset)
            if not writes:
                record["error"] = "no write reached the relay"
                return record, offset
            record["chosen_option"] = choice
            record["writes"] = writes
            time.sleep(1.2)               # reset, then the success dialog
            ad("click", *DONE_OK)
            time.sleep(0.4)
            return record, offset
        ad("click", *NOCHANGE_X)          # "No changes": that option was already the value
        time.sleep(0.4)
    record["skipped"] = "no option changed the value"
    return record, offset


def forscan_alive():
    listing = subprocess.run(["agentdesk", "windows", "list"], capture_output=True, text=True).stdout
    return "FORScan" in listing


VIEW_ROW = {"BdyCM": 341, "IPC": 461, "APIM": 141, "ABS": 201, "PSCM": 281}


def reopen_view(module):
    ad("click", 131, 737)          # stop the procedure
    time.sleep(2)
    ad("click", 170, 18)
    ad("click", 184, VIEW_ROW[module])
    ad("click", 89, 737)
    time.sleep(10)


def recover(module):
    """Bring FORScan back to the module's named view after a crash."""
    print("recovering: relaunching FORScan", flush=True)
    subprocess.run(["agentdesk", "status"], stdout=subprocess.DEVNULL)
    if not forscan_alive():
        subprocess.run(["pkill", "-f", "FORScan.exe"])
        time.sleep(2)
        ad("open", "--cmd", 'bash -c \'cd ~/.wine/drive_c/"Program Files (x86)"/FORScan && wine FORScan.exe\'')
        time.sleep(15)
    subprocess.run(["agentdesk", "windows", "maximize", "FORScan"], stdout=subprocess.DEVNULL)
    time.sleep(1)
    ad("click", 30, 30)            # vehicle info page
    ad("click", 89, 737)           # connect
    time.sleep(8)
    ad("click", 522, 440)          # load the saved profile
    time.sleep(8)
    ad("click", 30, 330)           # configuration and programming
    time.sleep(1)
    ad("click", 170, 18)
    ad("click", 184, VIEW_ROW[module])
    ad("click", 89, 737)           # run it
    time.sleep(15)


def main():
    module, names_file, out_path, writes_path = sys.argv[1:5]
    start = int(sys.argv[sys.argv.index("--start") + 1]) if "--start" in sys.argv else 0
    names = [l.rstrip("\n") for l in open(names_file) if l.strip()]
    stop = int(sys.argv[sys.argv.index("--stop") + 1]) if "--stop" in sys.argv else len(names)
    offset = os.path.getsize(writes_path) if os.path.exists(writes_path) else 0
    done_already = set()
    if os.path.exists(out_path):
        for line in open(out_path):
            r = json.loads(line)
            if r.get("writes"):
                done_already.add(r["index"])
    with open(out_path, "a") as out:
        only = [int(x) for x in sys.argv[sys.argv.index("--only") + 1].split(",")] if "--only" in sys.argv else None
        todo = only if only else [i for i in range(start, stop) if i not in done_already]
        for count, index in enumerate(todo):
            done = count
            if done and done % 40 == 0:          # FORScan dies after ~50 writes; restart it first
                subprocess.run(["agentdesk", "windows", "close", "FORScan"], stdout=subprocess.DEVNULL)
                time.sleep(3)
                subprocess.run(["pkill", "-f", "FORScan.exe"])
                time.sleep(3)
                recover(module)
            if only:
                reopen_view(module)
            for attempt in range(3):
                try:
                    record, offset = one(module, names, index, writes_path, offset)
                    break
                except Exception as exc:
                    print(f"[{index}] failed ({exc}); attempt {attempt + 1}", flush=True)
                    time.sleep(5)
                    try:
                        recover(module)
                    except Exception as exc2:
                        print(f"recovery failed: {exc2}", flush=True)
            else:
                print("giving up", flush=True)
                return 1
            out.write(json.dumps(record) + "\n")
            out.flush()
            summary = record.get("skipped") or record.get("error") or "; ".join(
                f"{w['module']} {w.get('id')} " + ",".join(f"b{c['byte']}:{c['old']}->{c['new']}{c['bits']}" for c in w.get("changes", []))
                for w in record["writes"] if w.get("id"))
            print(f"[{index}] {record['name']}: {summary}", flush=True)
            if record.get("error"):
                print("stopping: unexpected state", flush=True)
                return 1
    ad("click", *FILTER, "--count", 3)
    ad("key", "BackSpace")
    return 0


if __name__ == "__main__":
    sys.exit(main())
