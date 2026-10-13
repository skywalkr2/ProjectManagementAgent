"""Edits made outside the cockpit, picked up from the synced folder (design 5.0) and turned into proposals.

The folder's index says what each readable file holds. When one no longer matches what the cockpit wrote:
- long text (a Markdown body, or a text file) becomes a pending `text.propose` made from the version written there,
  marked as edited outside, so its review is three-way when the text moved on since;
- fields (front matter or a YAML file) become a `record.edit` held for the person;
- a collection becomes a held `record.edit` per changed entry and a held `record.delete` per removed one; an added
  entry is reported, since creating a record takes its plugin's own op;
- a working copy is taken back by its format;
- history, sources, outputs and generated files are never read back.

When the folder is shared (anyone else can change it), the edits are not the person's own words: the request is filed
as an outside input, the changeset and its writes are marked untrusted, and the notes say so. The person's review is the
same, and releasing a held change is still their decision.

Nothing applies without the person. Each change is handled once (`.cockpit/outside.json` keeps the hash it was
handled at); once the person has decided, the cockpit writes the file again from the records.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.sync import MACHINE, Entry, _write_atomic, file_digest, read_index, read_manifest, read_yaml

OUTSIDE = f"{MACHINE}/outside.json"
NOTE = "edited outside the cockpit"
HELD = "Edited outside the cockpit: check it before it applies."
NOTE_SHARED = "edited in a shared folder, so it may be someone else's change"
HELD_SHARED = "Edited in a shared folder, so it may be someone else's change: check it before it applies."


def shared(cfg: Any) -> bool:
    """Whether anyone else can change the synced folder, so what is found there is content, not the person's words."""
    return bool(cfg.storage.sync.shared)


def _handled(folder: Path) -> dict[str, dict[str, Any]]:
    try:
        return json.loads((folder / OUTSIDE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(folder: Path, handled: dict[str, dict[str, Any]]) -> None:
    _write_atomic(folder / OUTSIDE, (json.dumps(handled, sort_keys=True, indent=1) + "\n").encode())


def split_front_matter(text: str) -> tuple[Any, str]:
    """(front matter, body) of a Markdown file written by the cockpit: `---`, YAML, `---`, a blank line, the body."""
    if not text.startswith("---\n"):
        raise ValueError("the front matter at the top (between --- lines) is missing")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise ValueError("the front matter isn't closed with a --- line")
    front = read_yaml(text[4 : end + 1]) or {}
    body = text[end + 5 :]
    return front, body[1:] if body.startswith("\n") else body


def pick_up(store: Any, ws: Any, cfg: Any) -> list[str]:
    """Turn new outside edits into proposals. Returns the folder paths handled this time."""
    folder = Path(cfg.storage.sync.folder).expanduser().resolve()
    manifest, index, handled = read_manifest(folder), read_index(folder), _handled(folder)
    done = []
    for rel, entry in sorted(index.items()):
        if entry.part not in ("record", "fields", "text", "collection", "working"):
            continue
        path = folder / rel
        if not path.is_file() or rel not in manifest:
            continue
        found = file_digest(path)
        if found == manifest[rel] or handled.get(rel, {}).get("hash") == found:
            continue
        try:
            outcome = _propose(store, ws, cfg, rel, entry, path)
        except (ValueError, UnicodeDecodeError) as err:
            outcome = {"problem": str(err)}
        except Exception as err:  # noqa: BLE001 - a store refusal or a bad file is reported, never fatal
            outcome = {"problem": str(err) or type(err).__name__}
        handled[rel] = {"hash": found, **outcome}
        done.append(rel)
    if done:
        _save(folder, handled)
    return done


def settled(store: Any, cfg: Any) -> set[str]:
    """Readable files changed outside whose change the person has decided on, so the cockpit may write them again.
    Working copies stay as the person left them, and files the cockpit couldn't read stay until they change again."""
    folder = Path(cfg.storage.sync.folder).expanduser().resolve()
    handled, view = _handled(folder), store.read()
    ready = set()
    for rel, note in handled.items():
        if note.get("problem") or note.get("copy"):
            continue
        version = view.get("text_version", note["version"]) if note.get("version") else None
        changeset = view.get("changeset", note["changeset"]) if note.get("changeset") else None
        if version is not None and version.data["status"] == "pending":
            continue
        if changeset is not None and any(o["status"] == "held" for o in changeset.data["ops"]):
            continue
        ready.add(rel)
    return ready


def forget(cfg: Any) -> None:
    """Drop what was kept about files that agree with the cockpit's copy again (written again, or the person's change
    accepted as it stood) or are gone."""
    folder = Path(cfg.storage.sync.folder).expanduser().resolve()
    handled, manifest = _handled(folder), read_manifest(folder)
    keep = {
        rel: note
        for rel, note in handled.items()
        if (folder / rel).is_file() and file_digest(folder / rel) != manifest.get(rel)
    }
    if keep != handled:
        _save(folder, keep)


def pending(cfg: Any) -> dict[str, dict[str, Any]]:
    """What was picked up from the folder, by path: the proposal it became or why it couldn't be read."""
    return _handled(Path(cfg.storage.sync.folder).expanduser().resolve())


def _propose(store: Any, ws: Any, cfg: Any, rel: str, entry: Entry, path: Path) -> dict[str, Any]:
    from engine.texts import long_text_fields, read_text, versions

    if entry.part == "working":
        from engine import working

        result = working.take_back(store, cfg, entry.id, path.read_bytes(), path.name, outside=True)
        return {"copy": entry.id, "version": result.get("version")}
    view = store.read()
    if entry.part == "collection":
        return _collection(store, cfg, rel, entry, path, view)
    record = view.get(entry.kind, entry.id)
    if record is None:
        raise ValueError(f"the {entry.kind} this file holds is gone")
    model = store.plugins.records[entry.kind]
    text = path.read_bytes().decode("utf-8")
    ops: list[dict[str, Any]] = []
    if entry.part in ("record", "fields"):
        front, body = split_front_matter(text) if entry.part == "record" else (read_yaml(text) or {}, None)
        if not isinstance(front, dict):
            raise ValueError("the fields aren't a list of name: value lines")
        changes = _changes(front, record, model, set(long_text_fields(model)))
        if changes:
            ops.append(_edit(entry.kind, entry.id, changes, entry.record_version or record.version))
    else:
        body = text
    if body is not None and entry.field:
        written = {v.data["number"]: v for v in versions(view, entry.kind, entry.id, entry.field)}.get(entry.version)
        before = read_text(store, written.data["sha256"]) if written is not None else ""
        if body != before:
            ops.append(
                {
                    "op": "text.propose",
                    "record": {"kind": entry.kind, "id": entry.id},
                    "field": entry.field,
                    "text": body,
                    "base": entry.version,
                    "note": NOTE_SHARED if shared(cfg) else NOTE,
                }
            )
    if not ops:
        return {}
    return _apply(store, cfg, rel, ops)


def _changes(front: dict[str, Any], record: Any, model: Any, texts: set[str]) -> dict[str, Any]:
    if front.get("id", record.id) != record.id:
        raise ValueError("the id at the top was changed; put it back to edit this record")
    changes = {}
    for name, value in front.items():
        if name == "id":
            continue
        if name not in model.model_fields or name in texts or name in ("stage", "ext"):
            raise ValueError(f"{name} can't be changed in this file")
        if value != record.data.get(name):
            changes[name] = value
    return changes


def _edit(kind: str, record_id: str, changes: dict[str, Any], version: int) -> dict[str, Any]:
    return {"op": "record.edit", "record": {"kind": kind, "id": record_id}, "fields": changes, "read_version": version}


def _collection(store: Any, cfg: Any, rel: str, entry: Entry, path: Path, view: Any) -> dict[str, Any]:
    entries = read_yaml(path.read_bytes().decode("utf-8")) or []
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise ValueError("this file is a list of entries, each starting with - id:")
    model = store.plugins.records[entry.kind]
    versions = dict(entry.records)
    ops, added, seen = [], 0, set()
    for item in entries:
        record_id = item.get("id")
        if record_id not in versions:
            added += 1
            continue
        seen.add(record_id)
        record = view.get(entry.kind, record_id)
        if record is None:
            continue
        changes = _changes(item, record, model, set())
        if changes:
            ops.append(_edit(entry.kind, record_id, changes, versions[record_id]))
    for record_id, version in versions.items():
        if record_id not in seen and view.get(entry.kind, record_id) is not None:
            ops.append(
                {"op": "record.delete", "record": {"kind": entry.kind, "id": record_id}, "read_version": version}
            )
    outcome = _apply(store, cfg, rel, ops) if ops else {}
    if added:
        outcome["problem"] = (
            f"{added} new entr{'y' if added == 1 else 'ies'} without an id weren't added; add them in the cockpit"
        )
    return outcome


def _apply(store: Any, cfg: Any, rel: str, ops: list[dict[str, Any]]) -> dict[str, Any]:
    """File the ops from a changed file: field edits and deletes held for the person's review, long text pending."""
    where = "Edited in the shared folder" if shared(cfg) else "Edited outside the cockpit"
    return file_ops(store, cfg, f"{where}: {rel}", ops)


def file_ops(store: Any, cfg: Any, summary: str, ops: list[dict[str, Any]]) -> dict[str, Any]:
    """File ops that came from the synced folder. From a folder only the person uses they are the person's own work;
    from a shared folder they are untrusted content (the request is an outside input and every write carries the
    mark). Either way nothing applies without the person: field edits and deletes are held, long text is pending."""
    from engine.applier import Context, Inputs, Problem, apply_changeset
    from engine.names import People
    from engine.ops import CHANGESET
    from engine.storage import WriteContext

    untrusted = shared(cfg)
    trust = "untrusted" if untrusted else "trusted"
    changeset = CHANGESET.validate_python({"summary": summary, "ops": ops}, context={"op_models": store.plugins.ops})
    with store.transaction() as tx:
        request = tx.create(
            "request",
            {
                "task": "notes",
                "origin": "input" if untrusted else "pm",
                "state": "review",
                "note": summary,
                "created_at": store.clock(),
            },
            WriteContext("engine" if untrusted else "pm", trust, "sync.outside"),
        )
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request.id, None, "", "", trust),
        actor="pm",
    )
    message = HELD_SHARED if untrusted else HELD
    held = [
        Problem("outside-edit", "hold", i, message)
        for i, op in enumerate(ops)
        if op["op"] in ("record.edit", "record.delete")
    ]
    cs_id = apply_changeset(changeset, held, ctx, run=None)
    with store.transaction() as tx:
        current = tx.get("request", request.id)
        tx.update(
            "request",
            request.id,
            {"changeset": cs_id},
            WriteContext("engine", "trusted", "sync.outside"),
            read_version=current.version,
        )
    outcomes = store.read().get("changeset", cs_id).data["ops"]
    refused = [o.get("reason") for o in outcomes if o["status"] == "refused"]
    version = next(
        (
            r["id"]
            for o in outcomes
            if o["status"] == "applied"
            for r in o.get("records", [])
            if r["kind"] == "text_version"
        ),
        None,
    )
    result: dict[str, Any] = {"changeset": cs_id}
    if version:
        result["version"] = version
    if refused:
        result["problem"] = "; ".join(r for r in refused if r)
    return result
