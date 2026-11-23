"""Recorded sessions, kept in a single SQLite file."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import IO, Iterable

from .obd import Reading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY,
    started_at  REAL NOT NULL,   -- Unix time
    ended_at    REAL,
    vin         TEXT,
    adapter     TEXT,
    protocol    TEXT,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    key   TEXT PRIMARY KEY,      -- e.g. 01:0C
    name  TEXT NOT NULL,
    unit  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS samples (
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    cycle       INTEGER NOT NULL, -- one pass over the watched signals
    t           REAL NOT NULL,    -- Unix time this value was read
    key         TEXT NOT NULL REFERENCES signals(key),
    value       REAL,             -- numeric readings
    text        TEXT              -- readings that are words, such as fuel system status
);
CREATE INDEX IF NOT EXISTS samples_by_session ON samples (session_id, cycle);
CREATE TABLE IF NOT EXISTS vehicles (
    vin      TEXT PRIMARY KEY,   -- or "unknown" for a car that does not report one
    profile  TEXT NOT NULL       -- JSON: what setup learned about this car
);
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""

# Added to "sessions" after the first release; older database files gain them on opening.
_SESSION_ADDITIONS = {
    "origin": "TEXT",        # for a recording sent here by another box: "<its name>#<its id there>"
    "uploaded_at": "REAL",   # when this box sent the recording to the central server
}

EMPTY_PROFILE = {"engine_litres": None, "transmission": None, "fuel": "petrol", "gears": [], "baseline": None}
_MAX_IMPORTED_SAMPLES = 5_000_000


def default_db_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "cardiag" / "cardiag.db"


class Store:
    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(_SCHEMA)
        have = {row["name"] for row in self._db.execute("PRAGMA table_info(sessions)")}
        for column, kind in _SESSION_ADDITIONS.items():
            if column not in have:
                try:
                    self._db.execute(f"ALTER TABLE sessions ADD COLUMN {column} {kind}")
                except sqlite3.OperationalError:
                    pass  # another connection added it a moment ago

    def close(self) -> None:
        self._db.close()

    def start_session(
        self, *, vin: str | None, adapter: str | None, protocol: str | None, note: str | None = None
    ) -> int:
        with self._db:
            cursor = self._db.execute(
                "INSERT INTO sessions (started_at, vin, adapter, protocol, note) VALUES (?, ?, ?, ?, ?)",
                (time.time(), vin, adapter, protocol, note),
            )
        return cursor.lastrowid

    def end_session(self, session_id: int) -> None:
        with self._db:
            self._db.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (time.time(), session_id))

    def add_samples(self, session_id: int, cycle: int, samples: Iterable[tuple[float, Reading]]) -> None:
        """Store one pass of readings. Each sample is (Unix time read, reading)."""
        with self._db:
            for t, reading in samples:
                self._db.execute(
                    "INSERT OR IGNORE INTO signals (key, name, unit) VALUES (?, ?, ?)",
                    (reading.key, reading.name, reading.unit),
                )
                numeric = not isinstance(reading.value, str)
                self._db.execute(
                    "INSERT INTO samples (session_id, cycle, t, key, value, text) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        cycle,
                        t,
                        reading.key,
                        reading.value if numeric else None,
                        None if numeric else reading.value,
                    ),
                )

    def sessions(self) -> list[sqlite3.Row]:
        return self._db.execute(
            """
            SELECT s.*, (SELECT COUNT(DISTINCT cycle) FROM samples WHERE session_id = s.id) AS cycles
            FROM sessions s ORDER BY s.id
            """
        ).fetchall()

    def export_csv(self, session_id: int, out: IO[str]) -> int:
        """Write one row per pass and one column per signal. Returns the row count."""
        session = self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if session is None:
            raise KeyError(f"no session {session_id}")
        columns = self._db.execute(
            """
            SELECT g.key, g.name, g.unit FROM signals g
            JOIN (SELECT key, MIN(rowid) AS first FROM samples WHERE session_id = ? GROUP BY key) seen
              ON seen.key = g.key
            ORDER BY seen.first
            """,
            (session_id,),
        ).fetchall()
        keys = [column["key"] for column in columns]
        writer = csv.writer(out)
        writer.writerow(
            ["seconds"] + [f"{c['name']} ({c['unit']})" if c["unit"] else c["name"] for c in columns]
        )

        rows = 0
        current: int | None = None
        started: float = 0.0
        cells: dict[str, object] = {}

        def flush() -> None:
            nonlocal rows
            writer.writerow([f"{started - session['started_at']:.3f}"] + [cells.get(key, "") for key in keys])
            rows += 1

        for sample in self._db.execute(
            "SELECT cycle, t, key, value, text FROM samples WHERE session_id = ? ORDER BY cycle, t",
            (session_id,),
        ):
            if sample["cycle"] != current:
                if current is not None:
                    flush()
                current, started, cells = sample["cycle"], sample["t"], {}
            cells[sample["key"]] = sample["text"] if sample["value"] is None else sample["value"]
        if current is not None:
            flush()
        return rows

    # ---- reading a session back ----------------------------------------------

    def session(self, session_id: int) -> sqlite3.Row:
        row = self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(f"no session {session_id}")
        return row

    def passes(self, session_id: int) -> tuple[list[tuple[float, dict[str, float]]], dict[str, dict]]:
        """A session as (seconds from its start, {signal: number}) per pass, plus the signals' names."""
        started = self.session(session_id)["started_at"]
        passes: list[tuple[float, dict[str, float]]] = []
        current = None
        for sample in self._db.execute(
            "SELECT cycle, t, key, value FROM samples WHERE session_id = ? AND value IS NOT NULL ORDER BY cycle, t",
            (session_id,),
        ):
            if sample["cycle"] != current:
                current = sample["cycle"]
                passes.append((sample["t"] - started, {}))
            passes[-1][1][sample["key"]] = sample["value"]
        signals = {
            row["key"]: {"name": row["name"], "unit": row["unit"]}
            for row in self._db.execute(
                "SELECT * FROM signals WHERE key IN (SELECT DISTINCT key FROM samples WHERE session_id = ?)",
                (session_id,),
            )
        }
        return passes, signals

    # ---- what setup learned about each car -------------------------------------

    def profile(self, vin: str | None) -> dict:
        row = self._db.execute("SELECT profile FROM vehicles WHERE vin = ?", (vin or "unknown",)).fetchone()
        return {**EMPTY_PROFILE, **(json.loads(row["profile"]) if row else {})}

    def save_profile(self, vin: str | None, changes: dict) -> dict:
        profile = {**self.profile(vin), **changes}
        with self._db:
            self._db.execute(
                "INSERT INTO vehicles (vin, profile) VALUES (?, ?) ON CONFLICT(vin) DO UPDATE SET profile = excluded.profile",
                (vin or "unknown", json.dumps(profile)),
            )
        return profile

    def setting(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str | None) -> None:
        with self._db:
            if value is None:
                self._db.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                self._db.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    # ---- sending recordings to a central server, and receiving them ------------

    def unsent(self) -> list[int]:
        """Finished recordings made here that have not been sent on yet, oldest first."""
        rows = self._db.execute(
            "SELECT id FROM sessions WHERE ended_at IS NOT NULL AND uploaded_at IS NULL AND origin IS NULL ORDER BY id"
        )
        return [row["id"] for row in rows]

    def mark_sent(self, session_id: int) -> None:
        with self._db:
            self._db.execute("UPDATE sessions SET uploaded_at = ? WHERE id = ?", (time.time(), session_id))

    def export_session(self, session_id: int) -> dict:
        session = self.session(session_id)
        return {
            "session": {key: session[key] for key in ("started_at", "ended_at", "vin", "adapter", "protocol", "note")},
            "signals": [
                [row["key"], row["name"], row["unit"]]
                for row in self._db.execute(
                    "SELECT * FROM signals WHERE key IN (SELECT DISTINCT key FROM samples WHERE session_id = ?)",
                    (session_id,),
                )
            ],
            "samples": [
                list(row)
                for row in self._db.execute(
                    "SELECT cycle, t, key, value, text FROM samples WHERE session_id = ? ORDER BY cycle, t", (session_id,)
                )
            ],
        }

    def import_session(self, origin: str, payload: dict) -> int:
        """Store a recording made on another box. Sending the same one again replaces the first copy."""
        session, signals, samples = _checked(payload)
        with self._db:
            self._db.execute("DELETE FROM sessions WHERE origin = ?", (origin,))
            cursor = self._db.execute(
                "INSERT INTO sessions (started_at, ended_at, vin, adapter, protocol, note, origin) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (*(session[key] for key in ("started_at", "ended_at", "vin", "adapter", "protocol", "note")), origin),
            )
            self._db.executemany("INSERT OR IGNORE INTO signals (key, name, unit) VALUES (?, ?, ?)", signals)
            self._db.executemany(
                "INSERT INTO samples (session_id, cycle, t, key, value, text) VALUES (?, ?, ?, ?, ?, ?)",
                ((cursor.lastrowid, *sample) for sample in samples),
            )
        return cursor.lastrowid


def _checked(payload: dict) -> tuple[dict, list[tuple], list[tuple]]:
    """A recording from the network, with every field the shape the tables need, or ValueError."""

    def text(value: object, limit: int, optional: bool = True) -> str | None:
        if value is None and optional:
            return None
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError
        return value

    def number(value: object, optional: bool = False) -> float | None:
        if value is None and optional:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
            raise ValueError
        return value

    try:
        given = payload["session"]
        session = {
            "started_at": number(given["started_at"]),
            "ended_at": number(given.get("ended_at"), optional=True),
            "vin": text(given.get("vin"), 32),
            "adapter": text(given.get("adapter"), 200),
            "protocol": text(given.get("protocol"), 200),
            "note": text(given.get("note"), 500),
        }
        signals = [(text(k, 40, False), text(n, 200, False), text(u, 40, False)) for k, n, u in payload["signals"]]
        if len(payload["samples"]) > _MAX_IMPORTED_SAMPLES:
            raise ValueError
        known = {key for key, _, _ in signals}
        samples = []
        for cycle, t, key, value, words in payload["samples"]:
            if isinstance(cycle, bool) or not isinstance(cycle, int) or key not in known:
                raise ValueError
            samples.append((cycle, number(t), key, number(value, optional=True), text(words, 200)))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("that is not a cardiag recording") from None
    return session, signals, samples
