"""Working copies (design 5.0): long text handed out as a file for the person's own tool, and taken back.

Handing out runs the format's `hand_out` on a version, keeps the file through the file channel and records what went
out (the version, the file's hash). Taking back runs `take_back` on the returned file with the handed-out version's
text and files the result as a `text.propose` made from that version, so the review is three-way when the text moved
on; whatever couldn't be mapped is kept beside the proposal. A file that comes back unchanged proposes nothing, and a
file that wouldn't read back to the text it was made from isn't handed out. All of it is deterministic: no AI, nothing
to estimate or pay for.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from engine.config import Config
from engine.storage import Store, StoreError, WriteContext

_PM = WriteContext(actor="pm", trust="trusted", op="working_copy")


def formats_for(store: Store, kind: str, field: str) -> list[Any]:
    """The working-copy formats of running plugins that can take this long text field."""
    from engine.texts import long_text_fields

    model = store.plugins.records.get(kind)
    fmt = long_text_fields(model).get(field) if model is not None else None
    if fmt is None:
        return []
    found = []
    for name, registrar in store.plugins.registrars.items():
        if store.plugins.active(name):
            found += [w for w in registrar.working_copies.values() if not w.text_formats or fmt in w.text_formats]
    return sorted(found, key=lambda w: w.label)


def _format(store: Store, name: str) -> tuple[str, Any]:
    plugin = name.split("/", 1)[0]
    registrar = store.plugins.registrars.get(plugin)
    if registrar is None or name not in registrar.working_copies or not store.plugins.active(plugin):
        raise StoreError(f"there is no working-copy format {name} running now")
    return plugin, registrar.working_copies[name]


def _context(store: Store, plugin: str, record: Any, field: str, version: int | None) -> Any:
    from engine.plugin_api import WorkingCopyContext

    config = store.plugins.registrars[plugin].config
    return store.plugins._with_files(WorkingCopyContext(store.read(), plugin, config, record, field, version))


def _call(store: Store, plugin: str, what: str, fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except StoreError:
        raise
    except Exception as err:
        store.plugins.disable(plugin, f"working copy {what} failed: {err}")
        raise StoreError("the add-on that makes this kind of file failed, and was turned off") from None


def hand_out(store: Store, cfg: Config, format_name: str, kind: str, record_id: str, field: str) -> Any:
    """Make a working copy of a field's current text and record it. Returns the `working_copy` record."""
    from engine.files import add_file
    from engine.plugin_api import TakeBack
    from engine.projects import project_of
    from engine.texts import current, read_text

    plugin, fmt = _format(store, format_name)
    if fmt not in formats_for(store, kind, field):
        raise StoreError(f"{fmt.label} can't take {kind}.{field}")
    view = store.read()
    record = view.get(kind, record_id)
    if record is None:
        raise StoreError(f"there is no {kind} {record_id}")
    now = current(view, kind, record_id, field)
    base = now.data["number"] if now else None
    text = read_text(store, now.data["sha256"]) if now else ""
    data = _call(store, plugin, "hand-out", fmt.hand_out, text, _context(store, plugin, record, field, base))
    if not isinstance(data, bytes):
        store.plugins.disable(plugin, f"working copy {format_name} hand_out returned something other than bytes")
        raise StoreError("the add-on that makes this kind of file failed, and was turned off")
    back = _call(store, plugin, "take-back", fmt.take_back, data, text, _context(store, plugin, record, field, base))
    if not isinstance(back, TakeBack) or back.text != text or back.unmapped:
        raise StoreError(f"{fmt.label} wouldn't bring this text back unchanged, so it wasn't handed out")
    title = record.data.get("title") or record.data.get("name") or record_id
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(title)).strip("-")[:60] or record_id
    name = f"{slug}-{field}-v{base or 0}{fmt.extension}"
    made = add_file(
        store,
        cfg,
        data,
        name=name,
        media_type=fmt.media_type,
        project=project_of(record),
        origin="tool",
        context=_PM,
    )
    with store.transaction() as tx:
        return tx.create(
            "working_copy",
            {
                "owner_kind": kind,
                "owner_id": record_id,
                "field": field,
                "format": format_name,
                "base": base,
                "file": made.id,
                "sha256": hashlib.sha256(data).hexdigest(),
                "status": "out",
                "handed_at": store.clock(),
            },
            _PM,
        )


def take_back(
    store: Store, cfg: Config, copy_id: str, data: bytes, name: str | None = None, *, outside: bool = False
) -> dict[str, Any]:
    """Read a returned file back and file it as a proposal made from the handed-out version. Returns what happened:
    {"unchanged": True} for an untouched file, else the new text version's id and what couldn't be mapped. `outside`:
    the file was found in the synced folder; when that folder is shared it is filed as untrusted content, not as the
    person's own work."""
    from engine.applier import apply_as_person
    from engine.files import add_file
    from engine.plugin_api import TakeBack
    from engine.projects import project_of
    from engine.texts import read_text, versions

    view = store.read()
    copy = view.get("working_copy", copy_id)
    if copy is None or copy.data["status"] == "dropped":
        raise StoreError(f"{copy_id} isn't a working copy that's out")
    if hashlib.sha256(data).hexdigest() == copy.data["sha256"]:
        return {"unchanged": True, "version": None, "unmapped": []}
    plugin, fmt = _format(store, copy.data["format"])
    kind, record_id, field, base = (copy.data[k] for k in ("owner_kind", "owner_id", "field", "base"))
    record = view.get(kind, record_id)
    if record is None:
        raise StoreError(f"there is no {kind} {record_id} any more")
    by_number = {v.data["number"]: v for v in versions(view, kind, record_id, field)}
    base_text = read_text(store, by_number[base].data["sha256"]) if base in by_number else ""
    result = _call(
        store, plugin, "take-back", fmt.take_back, data, base_text, _context(store, plugin, record, field, base)
    )
    if not isinstance(result, TakeBack) or not isinstance(result.text, str):
        store.plugins.disable(plugin, f"working copy {fmt.name} take_back returned something other than TakeBack")
        raise StoreError("the add-on that reads this kind of file failed, and was turned off")
    returned = add_file(
        store,
        cfg,
        data,
        name=name or f"returned{fmt.extension}",
        media_type=fmt.media_type,
        project=project_of(record),
        context=_PM,
    )
    op = {
        "op": "text.propose",
        "record": {"kind": kind, "id": record_id},
        "field": field,
        "text": result.text,
        "base": base,
        "note": f"handed back from a working copy ({fmt.label})",
        "unmapped": [" ".join(str(u).split()) for u in result.unmapped],
    }
    summary = f"Took back {fmt.label} for {kind} {record_id}"
    from engine.outside import file_ops, shared

    if outside and shared(cfg):
        filed = file_ops(store, cfg, summary, [op])
        if "version" not in filed:
            raise StoreError(filed.get("problem") or "that couldn't be done")
        proposal = filed["version"]
    else:
        cs_id = apply_as_person(store, cfg, [op], summary)
        made = store.read().get("changeset", cs_id).data["ops"][0]["records"]
        proposal = next(r["id"] for r in made if r["kind"] == "text_version")
    with store.transaction() as tx:
        fresh = tx.get("working_copy", copy_id)
        changes = {
            "status": "returned",
            "returned_file": returned.id,
            "proposal": proposal,
            "returned_at": store.clock(),
        }
        tx.update("working_copy", copy_id, changes, _PM, read_version=fresh.version)
    return {"unchanged": False, "version": proposal, "unmapped": op["unmapped"]}


def drop(store: Store, copy_id: str) -> None:
    """Set a working copy aside; the record and its text don't change."""
    with store.transaction() as tx:
        copy = tx.get("working_copy", copy_id)
        if copy is None:
            raise StoreError(f"there is no working copy {copy_id}")
        tx.update("working_copy", copy_id, {"status": "dropped"}, _PM, read_version=copy.version)


def stale(store: Store, copy: Any) -> bool:
    """Whether the field moved on since this copy was handed out (taking it back then merges three ways)."""
    from engine.texts import current

    now = current(store.read(), copy.data["owner_kind"], copy.data["owner_id"], copy.data["field"])
    return (now.data["number"] if now else None) != copy.data["base"]
