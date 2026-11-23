"""Recorded sessions, kept in a single SQLite file."""

from __future__ import annotations

import csv
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
"""


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
