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

from engine.records import REGISTRY
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
    """A record as read: its kind, id, current version (state it when updating), whether it is deleted, and its
    fields in `data`."""

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
    """Access to a workspace's records, sequences and ledger.

    Each thread gets its own connection, so a reader sees committed data only, never another thread's open
    transaction. Writes from one Store are serialized; SQLite serializes writes between processes."""

    def __init__(self, path: Path, *, clock: Callable[[], str] = utc_now, cfg: Any = None):
        self.path = path
        self.clock = clock
        self._lock = threading.RLock()
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._closed = False
        _ = self._conn  # open the first connection now so a bad path fails here
        from engine.config import load_config
        from engine.plugin_host import PluginHost

        try:
            self.plugins = PluginHost(self, cfg or load_config(path.parent / "config"))
        except BaseException:
            for conn in self._all:
                conn.close()
            self._all.clear()
            self._closed = True
            raise

    @property
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            if self._closed:
                raise StoreError("the store is closed")
            conn = connect(self.path)
            self._local.conn = conn
            with self._lock:
                self._all.append(conn)
        return conn

    def close(self) -> None:
        with self._lock:
            self.plugins.close()
            self._closed = True
            for conn in self._all:
                conn.close()
            self._all.clear()

    @contextmanager
    def transaction(self, *, notify: bool = True) -> Iterator[Tx]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            tx = Tx(self._conn, self.clock, self.plugins.records)
            try:
                yield tx
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")
        if notify:
            for event, payload in tx.events():
                self.plugins.publish(event, payload, follows=tx.changeset)

    @contextmanager
    def snapshot(self) -> Iterator[Tx]:
        """A consistent read-only view: every read on this thread inside the block sees the database as it was when
        the first one ran, whatever other threads write meanwhile."""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            yield Tx(conn, self.clock, self.plugins.records)
        finally:
            conn.execute("ROLLBACK")

    def read(self) -> Tx:
        """A read-only view outside a transaction, for simple lookups."""
        return Tx(self._conn, self.clock, self.plugins.records)


class Tx:
    """Operations inside one transaction."""

    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], str], models: dict | None = None):
        self._c = conn
        self._clock = clock
        self.models = REGISTRY if models is None else models
        self.pending: list[tuple] = []
        self.emitted: list[tuple[str, dict[str, Any]]] = []  # interface events raised by ops in this transaction
        self.changeset: str | None = None  # the changeset whose ops this transaction wrote, if any

    def events(self) -> list[tuple[str, dict[str, Any]]]:
        grouped = {}
        special = []
        for kind, rid, version, field, before, after, op in self.pending:
            key = kind, rid, version, op
            data = grouped.setdefault(key, {"kind": kind, "id": rid, "version": version, "op": op, "fields": []})
            data["fields"].append(field or "_deleted")
            if field == "stage" and before != after:
                special.append(
                    (
                        "stage.moved",
                        {"kind": kind, "id": rid, "version": version, "from": before, "to": after, "op": op},
                    )
                )
            if kind == "request" and field == "state" and after == "queued" and before != after:
                special.append(("request.queued", {"id": rid}))
            if kind == "question" and field == "status" and after == "answered" and before != after:
                special.append(("question.answered", {"id": rid}))
            if kind == "file" and field == "file_kind" and version == 1:
                special.append(("file.added", {"id": rid, "kind": after}))
            if kind == "changeset" and field == "reviewed" and after is True and before is False:
                special.append(("changeset.reviewed", _reviewed(rid, "accepted", self)))
            if kind == "signal" and field == "kind" and after == "sent_back" and version == 1:
                sent = self.get("signal", rid)
                for cs_id in (sent.data.get("refs") or [])[:1] if sent is not None else []:
                    special.append(("changeset.reviewed", _reviewed(cs_id, "sent_back", self)))
            if kind == "text_version" and field == "status" and after == "accepted" and before != after:
                accepted = self.get("text_version", rid)
                if accepted is not None:
                    special.append(("text.accepted", _text_accepted(accepted, self)))
        return [("record.changed", data) for data in grouped.values()] + special + list(self.emitted)

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

    def has(self, kind: str) -> bool:
        """Whether any live record of the kind exists."""
        row = self._c.execute("SELECT 1 FROM records WHERE kind=? AND deleted=0 LIMIT 1", (kind,)).fetchone()
        return row is not None

    def find(self, kind: str, equals: dict[str, Any]) -> list[Stored]:
        """Live records of a kind whose top-level fields equal the given values, matched in the database."""
        sql, args = "SELECT * FROM records WHERE kind=? AND deleted=0", [kind]
        model = self.models.get(kind)
        for field, value in equals.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field) or (
                model is not None and field not in model.model_fields
            ):
                raise StoreError(f"{kind} has no field {field!r} to look up by")
            if isinstance(value, (list, tuple, set, dict)):
                raise StoreError(f"look up {field!r} by one value, not a list")
            if value is None:
                sql += f" AND json_extract(data, '$.{field}') IS NULL"
            else:
                sql += f" AND json_extract(data, '$.{field}') = ?"
                args.append(int(value) if isinstance(value, bool) else value)
        rows = self._c.execute(sql, args).fetchall()
        return sorted((_stored(r) for r in rows), key=lambda s: (id_number(s.id) or 0, s.id))

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

    def changed_kinds(self, after: int) -> tuple[int, list[str]]:
        """The ledger's last position, and the record kinds written after position `after` (for live updates)."""
        last = self._c.execute("SELECT COALESCE(MAX(seq), 0) AS n FROM ledger").fetchone()["n"]
        rows = self._c.execute("SELECT DISTINCT kind FROM ledger WHERE seq > ? ORDER BY kind", (after,)).fetchall()
        return int(last), [r["kind"] for r in rows]

    # ---- ids ---------------------------------------------------------------------------------------------------------

    def new_id(self, kind: str) -> str:
        prefix = self.models[kind].prefix
        row = self._c.execute("SELECT next FROM sequences WHERE kind=?", (kind,)).fetchone()
        n = row["next"] if row else 1
        self._c.execute(
            "INSERT INTO sequences(kind, next) VALUES(?, ?) ON CONFLICT(kind) DO UPDATE SET next=excluded.next",
            (kind, n + 1),
        )
        return f"{prefix}-{n}"

    def _reserve(self, kind: str, record_id: str) -> None:
        """Make sure a given id is never handed out again."""
        prefix = self.models[kind].prefix
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
        clean = _validate(self.models[kind], {**data, "id": record_id})
        self._check_lists(kind, record_id, clean, set(clean), {})
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
        merged = _validate(self.models[kind], {**current.data, **changes})
        diff = {k: merged.get(k) for k in set(merged) | set(current.data) if merged.get(k) != current.data.get(k)}
        if not diff:
            return current
        self._check_lists(kind, record_id, merged, set(diff), current.data)
        version = current.version + 1
        self._c.execute(
            "UPDATE records SET version=?, data=? WHERE kind=? AND id=?", (version, dumps(merged), kind, record_id)
        )
        at = self._clock()
        for field in sorted(diff):
            self._log(at, ctx, kind, record_id, version, field, current.data.get(field), merged.get(field))
        return Stored(kind, record_id, version, False, merged)

    def _check_lists(
        self, kind: str, record_id: str, data: dict[str, Any], changed: set[str], before: dict[str, Any]
    ) -> None:
        """Refuse a value not on its field's value list. A value the record already held stays valid (it may have
        been retired since); a list that doesn't exist yet (while a workspace is being loaded) checks nothing."""
        from engine.records import list_fields

        bound = [b for b in list_fields(self.models[kind]) if b[0] in changed]
        if not bound:
            return
        lists = {r.data["name"]: r.data for r in self.list("value_list")}
        for field, name, many in bound:
            value_list = lists.get(name)
            if value_list is None:
                continue
            values = data.get(field)
            held = before.get(field)
            for value in (values or []) if many else [values]:
                if value is None or value in value_list["values"]:
                    continue
                if value == held or (many and value in (held or [])):
                    continue
                offered = ", ".join(value_list["values"]) or "nothing yet"
                raise InvalidRecord(
                    f"{kind} {record_id}: {field}: {value!r} isn't on the list {value_list['label']} ({offered}); "
                    "add it to the list first"
                )

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

    def undelete(self, kind: str, record_id: str, ctx: WriteContext, *, read_version: int) -> None:
        """Bring back a deleted record under its own id; the ledger records it like any other write."""
        current = self.get(kind, record_id, include_deleted=True)
        if current is None or not current.deleted:
            raise StoreError(f"{kind} {record_id} isn't deleted")
        if read_version != current.version:
            raise ConflictError(kind, record_id, ["(record changed since it was read)"])
        version = current.version + 1
        self._c.execute("UPDATE records SET version=?, deleted=0 WHERE kind=? AND id=?", (version, kind, record_id))
        self._log(self._clock(), ctx, kind, record_id, version, None, None, None)

    def redact_ledger(self, kind: str, record_id: str, fields: list[str]) -> int:
        """Blank the before and after values of these fields in every ledger entry of one record, the entries of this
        transaction included, so a write that removes content leaves no copy of it in the history. The entries stay,
        with their fields, versions and who made them. Returns how many entries changed."""
        if not fields:
            return 0
        marks = ",".join("?" for _ in fields)
        cursor = self._c.execute(
            "UPDATE ledger SET before = CASE WHEN before IS NULL THEN NULL ELSE 'null' END, "
            "after = CASE WHEN after IS NULL THEN NULL ELSE 'null' END "
            f"WHERE kind=? AND record_id=? AND field IN ({marks})",
            (kind, record_id, *fields),
        )
        return cursor.rowcount

    # ---- import support ----------------------------------------------------------------------------------------------

    def restore_record(self, stored: Stored) -> None:
        """Put a record back exactly as exported (used by import only; writes no ledger entries)."""
        clean = _validate(self.models[stored.kind], {**stored.data, "id": stored.id})
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
        self.pending.append((kind, record_id, version, field, before, after, ctx.op))
        if ctx.changeset and self.changeset is None:
            self.changeset = ctx.changeset
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


def _reviewed(cs_id: str, outcome: str, view: Any) -> dict[str, Any]:
    """The changeset.reviewed payload: which answer, to which request and part, and what the person did."""
    cs = view.get("changeset", cs_id)
    request = view.get("request", cs.data["request"]) if cs is not None else None
    data = request.data if request is not None else {}
    about = data.get("about")
    return {
        "id": cs_id,
        "outcome": outcome,
        "request": request.id if request is not None else None,
        "task": data.get("task"),
        "part": data.get("part"),
        "about": {"kind": about["kind"], "id": about["id"]} if isinstance(about, dict) else None,
    }


def _text_accepted(version: Stored, view: Any) -> dict[str, Any]:
    """The text.accepted payload: which field got which version, from what, its authorship in words, and the request
    (with the part it named) whose run drafted it, when a run did."""
    run = view.get("run", version.data["run"]) if version.data.get("run") else None
    request = view.get("request", run.data["request"]) if run is not None and run.data.get("request") else None
    counts = {"person": 0, "assistant": 0, "assistant_edit": 0}
    for span in version.data.get("authorship", []):
        counts[span["kind"]] = counts.get(span["kind"], 0) + int(span.get("words", 0))
    return {
        "kind": version.data["owner_kind"],
        "id": version.data["owner_id"],
        "field": version.data["field"],
        "version": version.data["number"],
        "previous": version.data.get("replaces"),
        "source": version.data["source"],
        "authorship": counts,
        "request": request.id if request is not None else None,
        "part": request.data.get("part") if request is not None else None,
    }


def _validate(model: type, data: dict[str, Any]) -> dict[str, Any]:
    kind = model.record_kind
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
