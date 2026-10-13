"""Mail set aside as not work (design 6.5): the folder's contents, the person's corrections, and confirming.

Mail a triage rule sets aside, or the person sets aside by hand, is marked on its snapshot (`set_aside`) and never
queued for the assistant. The person can put it back ("This is work"), which hands it in like a change a rule closed. Or
they can confirm it was rightly set aside: the app then deletes the message's content (its subject, text, sender name
and any stored copy) once the undo window has passed, and keeps only a marker so the next read doesn't hand it in
again. Nothing here changes the mailbox itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from engine.storage import StoreError, WriteContext
from engine.triage import sender_address
from engine.yaml_load import load_yaml

SECTIONS = ("personal", "sales")
#: The domains the core ships as public mail domains (see `is_public_domain`).
PUBLIC_DOMAINS_FILE = Path(__file__).parent / "defaults" / "public_mail_domains.yaml"
#: The rule name shown for mail the person set aside by hand.
BY_PERSON = "Set aside by you"
_PM = WriteContext(actor="pm", trust="trusted", op="set_aside.correct")
_CONFIRM = WriteContext(actor="pm", trust="trusted", op="set_aside.confirm")
_DELETE = WriteContext(actor="pm", trust="trusted", op="set_aside.delete")
#: The fields of a deleted message's records whose earlier values the ledger gives up.
_SNAPSHOT_FIELDS = ["title", "author", "link", "content_hash", "message"]
_SOURCE_FIELDS = ["title", "content_hash", "url", "watched"]

SECTION_WORDS = {"personal": "personal mail", "sales": "sales mail"}

#: The op that deletes a confirmed item's content, and the fields it redacts in the ledger, by record kind.
DELETE_OP = _DELETE.op
REDACTED_FIELDS = {"snapshot": _SNAPSHOT_FIELDS, "source": _SOURCE_FIELDS}


def domain_of(address: str) -> str:
    return address.rpartition("@")[2] if "@" in address else ""


def _normal_domain(domain: str) -> str:
    return str(domain).strip().lower().removeprefix("@").rstrip(".")


@cache
def shipped_public_domains() -> frozenset[str]:
    """The public mail domains the core ships, lower case."""
    data = load_yaml(PUBLIC_DOMAINS_FILE.read_text(encoding="utf-8")) or {}
    return frozenset(_normal_domain(d) for d in data.get("domains") or [])


def public_domains(cfg: Any) -> frozenset[str]:
    """The shipped public mail domains plus the person's own (`watch.public_mail_domains_extra`)."""
    extra = {_normal_domain(d) for d in cfg.watch.public_mail_domains_extra}
    return shipped_public_domains() | extra - {""}


def is_public_domain(domain: str, cfg: Any) -> bool:
    """Whether this is a public mail domain, where anyone may have an address. It must be listed exactly, in any case:
    a subdomain of a listed domain is not public, because a company can run its own mail on one. No sorting rule is
    ever offered or saved for a whole public domain, only for a sender."""
    return _normal_domain(domain) in public_domains(cfg)


def offerable_domain(address: str, cfg: Any) -> str | None:
    """The sender's domain when a rule for the whole domain may be offered: None when the address has no domain or
    the domain is a public mail domain."""
    domain = domain_of(address)
    return None if not domain or is_public_domain(domain, cfg) else domain


def address_of(snapshot: Any, ws: Any = None) -> str:
    """The sender's address of a mail snapshot, lower case: from what the snapshot holds, else (with the workspace)
    from the head of its saved text; empty when none holds an address."""
    data = snapshot.data
    head = ""
    if ws is not None and data.get("content_hash"):
        path = ws.sources_dir / f"{data['content_hash']}.txt"
        head = path.read_text(encoding="utf-8")[:1000] if path.exists() else ""
    return sender_address({"message": data.get("message"), "author": data.get("author"), "now": head})


def _mail_snapshot(tx: Any, snapshot_id: str) -> Any:
    snap = tx.get("snapshot", snapshot_id)
    if snap is None or not snap.data.get("message") or snap.data.get("deleted"):
        raise StoreError("That isn't a message the app is holding.")
    return snap


def requests_of(tx: Any, snap: Any) -> list[Any]:
    """The requests made for this mail item, oldest first."""
    ids = {
        s.id
        for s in tx.list("source")
        if (s.data.get("watched") or {}).get("source") == snap.data["source"]
        and (s.data.get("watched") or {}).get("key") == snap.data["key"]
    }
    found = [r for r in tx.list("request") if r.data.get("source") in ids]
    return sorted(found, key=lambda r: str(r.data["created_at"]))


def is_set_aside(record: Any) -> bool:
    """Whether a request or snapshot is marked as set aside (by a rule or by the person, confirmed or not)."""
    return bool(record.data.get("set_aside"))


def learnable(view: Any, kind: str) -> list[Any]:
    """The requests or snapshots learning may read: every one of the kind not marked set aside. Learning reads these
    two kinds only through here, so mail set aside as not work is never taught from."""
    if kind not in ("request", "snapshot"):
        raise ValueError('learning reads "request" or "snapshot" records')
    return [r for r in view.list(kind) if not is_set_aside(r)]


def set_aside_item(store: Any, snapshot_id: str, section: str) -> list[str]:
    """Set a mail item aside by hand. A request for it that hasn't started (queued, or stopped for the person) is
    closed, remembering what it was so putting the item back restores it. Returns the ids of the requests closed."""
    if section not in SECTIONS:
        raise StoreError("Choose personal or sales.")
    reason = f"you set it aside as {SECTION_WORDS[section]}"
    closed_ids: list[str] = []
    with store.transaction() as tx:
        snap = _mail_snapshot(tx, snapshot_id)
        mark = {"section": section, "rule": BY_PERSON, "reason": reason, "by": "person"}
        tx.update("snapshot", snap.id, {"set_aside": mark, "closed_by": None}, _PM, read_version=snap.version)
        for req in requests_of(tx, snap):
            d = req.data
            if d.get("dismissed") or d.get("set_aside") or d.get("changeset"):
                continue
            if d["state"] not in ("queued", "needs_you", "failed"):
                continue
            closed = {**mark, "from_state": d["state"], "from_waiting": d.get("waiting")}
            tx.update(
                "request",
                req.id,
                {"state": "done", "waiting": f"Set aside: {reason}", "set_aside": closed},
                _PM,
                read_version=req.version,
            )
            closed_ids.append(req.id)
    return closed_ids


def put_back(
    ws: Any, store: Any, cfg: Any, snapshot_id: str, *, hand_in: bool, now: datetime | None = None
) -> str | None:
    """Take a mail item out of the folder. Its request goes back to where it was (when the person had set it aside
    after it was handed in) or is queued for the assistant (when a rule had set it aside), and an item that was never
    handed in is handed in now when `hand_in` is set. Returns the request that is waiting, or None."""
    from engine.watch import hand_in_snapshot

    waiting = None
    with store.transaction() as tx:
        snap = _mail_snapshot(tx, snapshot_id)
        if (snap.data.get("set_aside") or {}).get("confirmed_at"):
            raise StoreError("That was confirmed and is being deleted.")
        tx.update("snapshot", snap.id, {"set_aside": None, "closed_by": None}, _PM, read_version=snap.version)
        asides = [r for r in requests_of(tx, snap) if r.data.get("set_aside")]
        any_request = bool(requests_of(tx, snap))
        for req in asides:
            mark = req.data["set_aside"]
            if req is asides[-1] and mark.get("from_state"):
                changes: dict[str, Any] = {
                    "state": mark["from_state"],
                    "waiting": mark.get("from_waiting"),
                    "set_aside": None,
                }
                waiting = req.id
            elif req is asides[-1]:
                changes = {"state": "queued", "waiting": "With the assistant, starting now", "set_aside": None}
                waiting = req.id
            else:
                changes = {"set_aside": None}
            tx.update("request", req.id, changes, _PM, read_version=req.version)
    if waiting is None and hand_in and not any_request:
        made = hand_in_snapshot(ws, store, cfg, snapshot_id, now)
        waiting = made
    return waiting


def confirm_items(store: Any, snapshot_ids: list[str], now: datetime | None = None) -> list[Any]:
    """Confirm these set-aside items were rightly set aside: they leave the folder and are deleted from the app once
    `watch.set_aside_keep_seconds` has passed. Returns the snapshots confirmed."""
    now = now or datetime.now(UTC)
    done = []
    with store.transaction() as tx:
        for snapshot_id in snapshot_ids:
            snap = _mail_snapshot(tx, snapshot_id)
            mark = snap.data.get("set_aside")
            if not mark:
                raise StoreError("That isn't set aside.")
            if mark.get("confirmed_at"):
                continue
            tx.update(
                "snapshot",
                snap.id,
                {"set_aside": {**mark, "confirmed_at": now.isoformat()}},
                _CONFIRM,
                read_version=snap.version,
            )
            done.append(snap)
    return done


def unconfirm_items(store: Any, snapshot_ids: list[str]) -> int:
    """Undo a confirmation while the copy is still held. Raises StoreError when it has been deleted already."""
    brought_back = 0
    with store.transaction() as tx:
        for snapshot_id in snapshot_ids:
            snap = tx.get("snapshot", snapshot_id)
            if snap is None:
                raise StoreError("That message isn't here any more.")
            if snap.data.get("deleted"):
                raise StoreError("That message was deleted from the app after its undo time.")
            mark = dict(snap.data.get("set_aside") or {})
            if not mark.pop("confirmed_at", None):
                continue
            tx.update("snapshot", snap.id, {"set_aside": mark}, _CONFIRM, read_version=snap.version)
            brought_back += 1
    return brought_back


def purge_due(ws: Any, store: Any, cfg: Any, now: datetime | None = None) -> int:
    """Delete the content of every confirmed item whose undo time has passed. Returns how many were deleted."""
    now = now or datetime.now(UTC)
    wait = timedelta(seconds=cfg.watch.set_aside_keep_seconds)
    due = []
    for snap in store.read().list("snapshot"):
        mark = snap.data.get("set_aside") or {}
        if snap.data.get("deleted") or not mark.get("confirmed_at"):
            continue
        if datetime.fromisoformat(mark["confirmed_at"]) + wait <= now:
            due.append(snap.id)
    return purge(ws, store, due) if due else 0


def purge(ws: Any, store: Any, snapshot_ids: list[str]) -> int:
    """Delete these mail items' content from the app: the snapshot keeps only a marker (its source and key, the
    sender's address, the date, the section and the rule), the saved source records and the requests set aside with
    it lose their text, their saved text files go unless something else holds the same text, and the ledger gives up
    the earlier values of the fields that held it. The mailbox is untouched."""
    removed = 0
    with store.transaction() as tx:
        hashes: set[str] = set()
        redact: list[tuple[str, str, list[str]]] = []
        for snapshot_id in snapshot_ids:
            snap = tx.get("snapshot", snapshot_id)
            if snap is None or snap.data.get("deleted") or not snap.data.get("message"):
                continue
            data = snap.data
            if data.get("content_hash"):
                hashes.add(data["content_hash"])
            mark = data.get("set_aside") or {}
            message = data["message"]
            tx.update(
                "snapshot",
                snap.id,
                {
                    "title": "",
                    "author": None,
                    "link": None,
                    "content_hash": "",
                    "closed_by": None,
                    "deleted": True,
                    "message": {"sender": address_of(snap, ws) or None, "received": message.get("received")},
                    "set_aside": {"section": mark.get("section", ""), "rule": mark.get("rule", "")},
                },
                _DELETE,
                read_version=snap.version,
            )
            redact.append(("snapshot", snap.id, _SNAPSHOT_FIELDS))
            for req in requests_of(tx, snap):
                source = tx.get("source", req.data["source"]) if req.data.get("source") else None
                if source is not None and source.data.get("content_hash"):
                    hashes.add(source.data["content_hash"])
                    tx.update(
                        "source",
                        source.id,
                        {"title": "", "content_hash": "", "url": None, "watched": None},
                        _DELETE,
                        read_version=source.version,
                    )
                    redact.append(("source", source.id, _SOURCE_FIELDS))
                if req.data.get("set_aside") and not req.data.get("changeset"):
                    tx.update(
                        "request",
                        req.id,
                        {"waiting": "Set aside and deleted", "set_aside": {"section": mark.get("section", "")}},
                        _DELETE,
                        read_version=req.version,
                    )
            removed += 1
        for kind, record_id, fields in redact:
            tx.redact_ledger(kind, record_id, fields)
        still_held = {s.data.get("content_hash") for s in tx.list("snapshot")} | {
            s.data.get("content_hash") for s in tx.list("source")
        }
        gone_texts = hashes - still_held
    for digest in gone_texts:
        path = ws.sources_dir / f"{digest}.txt"
        if path.exists():
            path.unlink()
    if removed:
        _refresh_export(ws, store)
    return removed


def _refresh_export(ws: Any, store: Any) -> None:
    """Write the readable export again when the workspace keeps one, so it doesn't hold the deleted text."""
    from engine.storage.export import export_data

    if any(ws.data_dir.glob("*.json")):
        export_data(store, ws.data_dir)


def folder(ws: Any, store: Any, cfg: Any) -> list[dict[str, Any]]:
    """The items in the Set aside folder, newest first: those set aside and not yet confirmed."""
    labels = {s.id: s.label or s.id for s in cfg.watch.sources}
    rows = []
    for snap in store.read().list("snapshot"):
        data = snap.data
        mark = data.get("set_aside")
        if not mark or data.get("gone") or data.get("deleted") or mark.get("confirmed_at"):
            continue
        address = address_of(snap, ws)
        message = data["message"]
        rows.append(
            {
                "id": snap.id,
                "version": snap.version,
                "section": mark["section"],
                "title": data["title"],
                "sender": message.get("sender"),
                "source": labels.get(data["source"], data["source"]),
                "received": message.get("received"),
                "reason": mark["reason"],
                "address": address,
                "domain": offerable_domain(address, cfg),
            }
        )
    rows.sort(key=lambda r: str(r["received"] or ""), reverse=True)
    return rows


def deleted_count(store: Any) -> int:
    return sum(1 for s in store.read().list("snapshot") if s.data.get("deleted"))
