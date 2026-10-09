"""The SQLite database: connection settings and schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    kind     TEXT    NOT NULL,
    id       TEXT    NOT NULL,
    version  INTEGER NOT NULL,
    deleted  INTEGER NOT NULL DEFAULT 0,
    data     TEXT    NOT NULL,
    PRIMARY KEY (kind, id)
);

CREATE TABLE IF NOT EXISTS sequences (
    kind TEXT    PRIMARY KEY,
    next INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger (
    seq       INTEGER PRIMARY KEY AUTOINCREMENT,
    at        TEXT    NOT NULL,
    changeset TEXT,
    request   TEXT,
    op        TEXT    NOT NULL,
    kind      TEXT    NOT NULL,
    record_id TEXT    NOT NULL,
    version   INTEGER NOT NULL,
    field     TEXT,
    before    TEXT,
    after     TEXT,
    actor     TEXT    NOT NULL,
    trust     TEXT    NOT NULL,
    evidence  TEXT
);
CREATE INDEX IF NOT EXISTS ledger_record ON ledger (kind, record_id, version);

CREATE TABLE IF NOT EXISTS leases (
    name      TEXT PRIMARY KEY,
    holder    TEXT NOT NULL,
    host      TEXT NOT NULL,
    heartbeat TEXT NOT NULL,
    expires   TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    """Open the workspace database, creating its schema on first use."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    elif version > SCHEMA_VERSION:
        conn.close()
        raise RuntimeError(
            f"The database is format {version}, newer than this program understands ({SCHEMA_VERSION}). "
            "Upgrade the program before using this workspace."
        )
    return conn
