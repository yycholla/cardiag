#!/usr/bin/env python3
"""Sweep results -> a field map: for each named setting, the block, byte, bit
shift and width, and what each value means.

    build_map.py SETTINGS_MD OUT_JSON OUT_MD  MODULE:RESULTS:SECTION_START:SECTION_END ...
"""
import json, re, sys

ADDRESS = {"BdyCM": "726", "IPC": "720"}


def table_rows(md, start, end):
    sec = md[md.index(start):md.index(end)]
    return [(m.group(1), m.group(2)) for m in re.finditer(r"^\| (.+?) \| (.+?) \|$", sec, re.M)
            if m.group(1) not in ("Setting", "---")]


def parse_options(lines):
    """['0 - Disabled', '1 - Enabled'] -> {0: 'Disabled', 1: 'Enabled'}; renumber by
    position when OCR mangled a number."""
    out = {}
    for pos, line in enumerate(lines):
        m = re.match(r"^\s*([0-9]+)\s*[-–]\s*(.+)$", line)
        if m:
            out[int(m.group(1))] = m.group(2).strip()
        else:
            label = re.sub(r"^\W*\w?\s*[-–]\s*", "", line).strip()
            out[pos] = label
    return out


def fit_field(changes, options, car_label):
    """Find (byte, shift, width) consistent with the bytes that changed, the
    option values, and this car's current value."""
    if len(changes) != 1:
        return None
    c = changes[0]
    old, new, bits = int(c["old"], 16), int(c["new"], 16), c["bits"]
    top = max(options) if options else 1
    width = max(1, top.bit_length())
    car_value = next((v for v, label in options.items() if car_label and label.lower()[:12] == car_label.lower()[:12]), None)
    fits = []
    for shift in range(0, 9 - width):
        mask = ((1 << width) - 1) << shift
        if any(not (mask >> b) & 1 for b in bits):
            continue
        before, after = (old & mask) >> shift, (new & mask) >> shift
        if options and (before not in options or after not in options):
            continue
        score = (car_value is not None and before == car_value) * 2 + (shift == min(bits))
        fits.append((score, shift, before, after))
    if not fits:
        return {"byte": c["byte"], "shift": min(bits), "width": len(bits), "guess": True}
    fits.sort(reverse=True)
    score, shift, before, after = fits[0]
    return {"byte": c["byte"], "shift": shift, "width": width, "car_value": before,
            "checked_against_car_value": car_value is not None and before == car_value}


def main():
    md_path, out_json, out_md = sys.argv[1:4]
    md = open(md_path).read()
    fields, lines = [], []
    for spec in sys.argv[4:]:
        module, results, start, end = spec.split(":", 3)
        rows = table_rows(md, start, end)
        latest = {}
        for line in open(results):
            r = json.loads(line)
            if r.get("writes") or r["index"] not in latest:
                if not (latest.get(r["index"], {}).get("described") and not r.get("described") and r.get("writes")):
                    latest[r["index"]] = r
        lines.append(f"\n## {module} (`{ADDRESS[module]}`)\n")
        lines.append("| Setting | Block | Byte | Bits | This car | Values |")
        lines.append("|---|---|---|---|---|---|")
        for index in sorted(latest):
            r = latest[index]
            name, car_label = rows[index] if index < len(rows) else (r["name"], None)
            options = parse_options(r.get("options", []))
            entry = {"module": module, "address": ADDRESS[module], "name": name, "this_car": car_label,
                     "options": {str(k): v for k, v in sorted(options.items())}}
            writes = [w for w in r.get("writes", []) if w.get("id")]
            if not writes:
                entry["unmapped"] = r.get("skipped") or r.get("error") or "not tried"
                fields.append(entry)
                lines.append(f"| {name} | | | | {car_label} | not mapped: {entry['unmapped']} |")
                continue
            w = writes[0]
            entry["block"] = w["id"]
            fit = fit_field(w.get("changes") or [], options, car_label)
            if fit is None:
                entry["changes"] = w.get("changes")
                bits = "; ".join(f"byte {c['byte']} bits {c['bits']}" for c in w.get("changes") or [])
                lines.append(f"| {name} | {w['id']} | | {bits} (several bytes changed) | {car_label} | "
                             + ", ".join(f"{k}={v}" for k, v in sorted(options.items())) + " |")
            else:
                entry.update(fit)
                hi = fit["shift"] + fit["width"] - 1
                bits = f"{fit['shift']}" if fit["width"] == 1 else f"{hi}–{fit['shift']}"
                lines.append(f"| {name} | {w['id']} | {fit['byte']} | {bits}{' (guess)' if fit.get('guess') else ''} | "
                             f"{car_label} | " + ", ".join(f"{k}={v}" for k, v in sorted(options.items())) + " |")
            if r.get("described"):
                entry["verified_row"] = True
            fields.append(entry)
    json.dump(fields, open(out_json, "w"), indent=1)
    open(out_md, "w").write("\n".join(lines) + "\n")
    mapped = sum(1 for f in fields if "block" in f)
    print(f"{len(fields)} settings, {mapped} mapped")


if __name__ == "__main__":
    main()
