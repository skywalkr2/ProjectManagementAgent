"""The record store.

Every write happens in a transaction, states the record version it read, and writes one ledger entry per field it
changes in the same transaction. A write against an older version is merged field by field when the fields differ and
refused when the same field changed in between. Ids come from per-kind sequences and are never reused.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from engine.records import model_for
from engine.storage.db import connect

Trust = Literal["trusted", "untrusted"]
_ID = re.compile(r"^(?P<prefix>[A-Z]+)-(?P<n>[1-9][0-9]*)$")


class StoreError(Exception):
    """A write can't be made as asked."""


class ConflictError(StoreError):
    """Another write changed the same field since this one read the record."""

    def __init__(self, kind: str, record_id: str, fields: list[str]):
        self.kind, self.record_id, self.fields = kind, record_id, fields
        super().__init__(f"{kind} {record_id}: {', '.join(fields)} changed since it was read")


class InvalidRecord(StoreError):
    """The record would not be valid for its kind."""


@dataclass(frozen=True)
class Stored:
    kind: str
    id: str
    version: int
    deleted: bool
    data: dict[str, Any]


@dataclass(frozen=True)
class WriteContext:
    """Who is writing and on what grounds; copied into every ledger entry."""

    actor: str
    trust: Trust
    op: str
    changeset: str | None = None
    request: str | None = None
    evidence: dict[str, Any] | None = None


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def id_number(record_id: str) -> int | None:
    match = _ID.match(record_id)
    return int(match["n"]) if match else None


class Store:
    """Access to a workspace's records, sequences and ledger."""

    def __init__(self, path: Path, *, clock: Callable[[], str] = utc_now):
        self.path = path
        self.clock = clock
        self._conn = connect(path)
        self._lock = threading.RLock()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[Tx]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield Tx(self._conn, self.clock)
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def read(self) -> Tx:
        """A read-only view outside a transaction, for simple lookups."""
        return Tx(self._conn, self.clock)


class Tx:
    """Operations inside one transaction."""

    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], str]):
        self._c = conn
        self._clock = clock

    def sql(self, query: str, args: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Run a statement in this transaction, for storage modules that own their own tables (leases)."""
        return self._c.execute(query, args)

    # ---- reading -----------------------------------------------------------------------------------------------------

    def get(self, kind: str, record_id: str, *, include_deleted: bool = False) -> Stored | None:
        row = self._c.execute("SELECT * FROM records WHERE kind=? AND id=?", (kind, record_id)).fetchone()
        if row is None or (row["deleted"] and not include_deleted):
            return None
        return _stored(row)

    def list(self, kind: str, *, include_deleted: bool = False) -> list[Stored]:
        rows = self._c.execute("SELECT * FROM records WHERE kind=?", (kind,)).fetchall()
        items = [_stored(r) for r in rows if include_deleted or not r["deleted"]]
        return sorted(items, key=lambda s: (id_number(s.id) or 0, s.id))

    def kinds(self) -> list[str]:
        return [r[0] for r in self._c.execute("SELECT DISTINCT kind FROM records ORDER BY kind")]

    def sequences(self) -> dict[str, int]:
        return {r["kind"]: r["next"] for r in self._c.execute("SELECT kind, next FROM sequences ORDER BY kind")}

    def ledger(self, *, kind: str | None = None, record_id: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM ledger", []
        if kind is not None:
            sql += " WHERE kind=?" + (" AND record_id=?" if record_id else "")
            args = [kind] + ([record_id] if record_id else [])
        rows = self._c.execute(sql + " ORDER BY seq", args).fetchall()
        return [_ledger_row(r) for r in rows]

    # ---- ids ---------------------------------------------------------------------------------------------------------

    def new_id(self, kind: str) -> str:
        prefix = model_for(kind).prefix
        row = self._c.execute("SELECT next FROM sequences WHERE kind=?", (kind,)).fetchone()
        n = row["next"] if row else 1
        self._c.execute(
            "INSERT INTO sequences(kind, next) VALUES(?, ?) ON CONFLICT(kind) DO UPDATE SET next=excluded.next",
            (kind, n + 1),
        )
        return f"{prefix}-{n}"

    def _reserve(self, kind: str, record_id: str) -> None:
        """Make sure a given id is never handed out again."""
        prefix = model_for(kind).prefix
        match = _ID.match(record_id)
        if not match or match["prefix"] != prefix:
            raise InvalidRecord(f"{record_id!r} is not a {kind} id (expected {prefix}-<number>)")
        n = int(match["n"])
        self._c.execute(
            "INSERT INTO sequences(kind, next) VALUES(?, ?) "
            "ON CONFLICT(kind) DO UPDATE SET next=MAX(next, excluded.next)",
            (kind, n + 1),
        )

    def set_sequence(self, kind: str, next_value: int) -> None:
        self._c.execute(
            "INSERT INTO sequences(kind, next) VALUES(?, ?) "
            "ON CONFLICT(kind) DO UPDATE SET next=MAX(next, excluded.next)",
            (kind, next_value),
        )

    # ---- writing -----------------------------------------------------------------------------------------------------

    def create(self, kind: str, data: dict[str, Any], ctx: WriteContext, *, record_id: str | None = None) -> Stored:
        """Add a new record. Without an id, the next one in the kind's sequence is used."""
        if record_id is None:
            record_id = self.new_id(kind)
        else:
            if self._c.execute("SELECT 1 FROM records WHERE kind=? AND id=?", (kind, record_id)).fetchone():
                raise StoreError(f"{kind} {record_id} already exists (ids are never reused)")
            self._reserve(kind, record_id)
        clean = _validate(kind, {**data, "id": record_id})
        self._c.execute(
            "INSERT INTO records(kind, id, version, deleted, data) VALUES(?, ?, 1, 0, ?)",
            (kind, record_id, dumps(clean)),
        )
        at = self._clock()
        for field in sorted(k for k in clean if k != "id"):
            self._log(at, ctx, kind, record_id, 1, field, None, clean[field])
        return Stored(kind, record_id, 1, False, clean)

    def update(
        self, kind: str, record_id: str, changes: dict[str, Any], ctx: WriteContext, *, read_version: int
    ) -> Stored:
        """Change fields of a record, stating the version that was read before deciding on the change."""
        current = self.get(kind, record_id)
        if current is None:
            raise StoreError(f"{kind} {record_id} doesn't exist")
        if "id" in changes and changes["id"] != record_id:
            raise StoreError("a record's id can't change")
        if read_version > current.version or read_version < 1:
            raise StoreError(f"{kind} {record_id} has no version {read_version}")
        if read_version < current.version:
            changed_since = self._fields_changed_since(kind, record_id, read_version)
            clash = sorted(changed_since & set(changes))
            if clash:
                raise ConflictError(kind, record_id, clash)
        merged = _validate(kind, {**current.data, **changes})
        diff = {k: merged.get(k) for k in set(merged) | set(current.data) if merged.get(k) != current.data.get(k)}
        if not diff:
            return current
        version = current.version + 1
        self._c.execute(
            "UPDATE records SET version=?, data=? WHERE kind=? AND id=?", (version, dumps(merged), kind, record_id)
        )
        at = self._clock()
        for field in sorted(diff):
            self._log(at, ctx, kind, record_id, version, field, current.data.get(field), merged.get(field))
        return Stored(kind, record_id, version, False, merged)

    def delete(self, kind: str, record_id: str, ctx: WriteContext, *, read_version: int) -> None:
        """Mark a record deleted. Its id stays retired and its history stays in the ledger."""
        current = self.get(kind, record_id)
        if current is None:
            raise StoreError(f"{kind} {record_id} doesn't exist")
        if read_version != current.version:
            raise ConflictError(kind, record_id, ["(record changed since it was read)"])
        version = current.version + 1
        self._c.execute("UPDATE records SET version=?, deleted=1 WHERE kind=? AND id=?", (version, kind, record_id))
        self._log(self._clock(), ctx, kind, record_id, version, None, None, None)

    # ---- import support ----------------------------------------------------------------------------------------------

    def restore_record(self, stored: Stored) -> None:
        """Put a record back exactly as exported (used by import only; writes no ledger entries)."""
        clean = _validate(stored.kind, {**stored.data, "id": stored.id})
        self._reserve(stored.kind, stored.id)
        self._c.execute(
            "INSERT INTO records(kind, id, version, deleted, data) VALUES(?, ?, ?, ?, ?)",
            (stored.kind, stored.id, stored.version, int(stored.deleted), dumps(clean)),
        )

    def restore_ledger(self, entry: dict[str, Any]) -> None:
        """Append an exported ledger entry as it was (used by import only)."""
        self._c.execute(
            "INSERT INTO ledger(seq, at, changeset, request, op, kind, record_id, version, field, before, after, "
            "actor, trust, evidence) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                entry["seq"],
                entry["at"],
                entry.get("changeset"),
                entry.get("request"),
                entry["op"],
                entry["kind"],
                entry["record_id"],
                entry["version"],
                entry.get("field"),
                _opt_dumps(entry, "before"),
                _opt_dumps(entry, "after"),
                entry["actor"],
                entry["trust"],
                _opt_dumps(entry, "evidence"),
            ),
        )

    # ---- internals ---------------------------------------------------------------------------------------------------

    def _fields_changed_since(self, kind: str, record_id: str, version: int) -> set[str]:
        rows = self._c.execute(
            "SELECT field FROM ledger WHERE kind=? AND record_id=? AND version>? AND field IS NOT NULL",
            (kind, record_id, version),
        ).fetchall()
        return {r["field"] for r in rows}

    def _log(
        self,
        at: str,
        ctx: WriteContext,
        kind: str,
        record_id: str,
        version: int,
        field: str | None,
        before: Any,
        after: Any,
    ) -> None:
        self._c.execute(
            "INSERT INTO ledger(at, changeset, request, op, kind, record_id, version, field, before, after, actor, "
            "trust, evidence) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                at,
                ctx.changeset,
                ctx.request,
                ctx.op,
                kind,
                record_id,
                version,
                field,
                None if field is None else dumps(before),
                None if field is None else dumps(after),
                ctx.actor,
                ctx.trust,
                None if ctx.evidence is None else dumps(ctx.evidence),
            ),
        )


def _validate(kind: str, data: dict[str, Any]) -> dict[str, Any]:
    model = model_for(kind)
    try:
        return model.model_validate(data).model_dump(mode="json", exclude_defaults=False)
    except ValidationError as err:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or kind}: {e['msg']}" for e in err.errors())
        raise InvalidRecord(f"{kind} {data.get('id', '(new)')}: {problems}") from None


def _stored(row: sqlite3.Row) -> Stored:
    return Stored(row["kind"], row["id"], row["version"], bool(row["deleted"]), json.loads(row["data"]))


def _ledger_row(row: sqlite3.Row) -> dict[str, Any]:
    entry = dict(row)
    for key in ("before", "after", "evidence"):
        if entry[key] is not None:
            entry[key] = json.loads(entry[key])
    return entry


def _opt_dumps(entry: dict[str, Any], key: str) -> str | None:
    if key not in entry:
        return None
    if key in ("before", "after") and entry.get("field") is None:
        return None
    if key == "evidence" and entry.get("evidence") is None:
        return None
    return dumps(entry[key])
