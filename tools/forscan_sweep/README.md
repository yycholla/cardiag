# Sweeping FORScan's named settings

Drives FORScan (under Wine, in an agentdesk sandbox desktop) through every
setting of one module's "Module configuration" view, with
[`../forscan_dryrun_relay.py`](../forscan_dryrun_relay.py) between FORScan and
the car (or a replay of it), and records which bits each setting occupies.
The result of running it on a 2017 Focus is
[`docs/focus-2017-config-map.md`](../../docs/focus-2017-config-map.md).

```sh
# the relay, answering from recordings so the car is not needed
python3 tools/forscan_dryrun_relay.py --log-dir run --replay capture.log transcript.log
# FORScan connected on COM5, the module's named view open and maximised, then:
python3 tools/forscan_sweep/sweep.py IPC ipc_names.txt ipc_results.jsonl run/writes.jsonl
python3 tools/forscan_sweep/build_map.py settings.md map.json map.md "IPC:ipc_results.jsonl:<section start>:<section end>"
```

`NAMES_FILE` lists the view's rows in table order. Results append, and a rerun
skips settings already mapped; `--only 3,7,9` redoes chosen ones on a freshly
opened view.

What it works around, so the next person need not find out again:

- **Typing into Wine** through agentdesk turns every character into "v".
  `agentdesk key` works for letters, digits, space and `minus`; `#`, `(` and
  similar never arrive, so the filter text is chosen from plain words.
- **FORScan's filter also matches the Value column**, so a row can appear that
  the names alone do not predict. The editor's "Description:" line is read back
  by OCR and the next row tried until it matches.
- **Editors differ in size** with the number of options and the length of the
  description; the OK button and the list are found on the screenshot.
- **FORScan exits after about 50 writes.** The script restarts it every 40
  settings and recovers if it dies anyway (relaunch, connect, load the profile,
  reopen the view).
- Coordinates assume agentdesk's 1280×800 desktop with FORScan maximised.

Needs `agentdesk` and `tesseract`; [`png.py`](png.py) reads and writes the
screenshots without other libraries.
