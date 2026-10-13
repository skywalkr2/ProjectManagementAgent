"""Files people add and programs write (design 5.3): bytes stored once by hash, described by a `file` record.

The bytes are never changed in place; a new version is a new file that names the one it replaces. File kinds say what a
file is for and what details it needs; the core has `attachment`, and plugins (and later templates) declare their own.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from engine.config import Config
from engine.storage import Store, Stored, StoreError, WriteContext


class AnyDetails(BaseModel):
    """The core attachment kind asks for nothing in particular; a short description is welcome."""

    model_config = ConfigDict(extra="forbid")
    description: str = ""


@dataclass(frozen=True)
class FileKind:
    name: str
    details: type[BaseModel] = AnyDetails
    accept: tuple[str, ...] = ()  # media types; empty means the workspace's accepted types
    max_mb: float | None = None  # narrower than the workspace's limit, never wider
    label: str = ""  # what to call it on screen
    data_level: str | None = None  # the level a file added under this kind gets without a choice; None is internal


CORE_KINDS: dict[str, FileKind] = {"attachment": FileKind("attachment", label="Attachment")}

_PM = WriteContext(actor="pm", trust="trusted", op="file.add")


def level_for(kind: FileKind | None, chosen: str | None) -> str:
    """The data level a new file gets: the explicit choice when there is one, else its kind's, else internal."""
    return chosen or (kind.data_level if kind is not None else None) or "internal"


def files_dir(store: Store) -> Path:
    return store.path.parent / "files"


def blob_path(store: Store, sha256: str) -> Path:
    return blob_path_in(store.path.parent, sha256)


def blob_path_in(root: Path, sha256: str) -> Path:
    """Where a workspace at `root` keeps the bytes with this hash."""
    return root / "files" / sha256[:2] / sha256


def check_file(
    store: Store,
    cfg: Config,
    view: Any,
    *,
    name: str,
    media_type: str,
    size: int,
    file_kind: str = "attachment",
    meta: dict[str, Any] | None = None,
    project: str | None = None,
    replaces: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Check a file against the limits and its kind. Returns its cleaned name and validated details; refusals say why
    in words."""
    limits = cfg.storage.files
    kind = store.plugins.file_kinds().get(file_kind)
    if kind is None:
        raise StoreError(f"there is no file kind called {file_kind}")
    name = Path(name).name.strip()
    if not name:
        raise StoreError("the file needs a name")
    # A kind narrows the workspace's accepted types; it never widens them.
    accepted = [t for t in kind.accept if t in limits.accepted_types] if kind.accept else limits.accepted_types
    if media_type not in accepted:
        raise StoreError(f"files of type {media_type} can't be added here")
    cap = min(limits.max_file_mb, kind.max_mb or limits.max_file_mb)
    if size > cap * 1024 * 1024:
        raise StoreError(f"{name} is larger than {cap:g} MB")
    used = sum(f.data["size"] for f in view.list("file"))
    if used + size > limits.max_total_mb * 1024 * 1024:
        raise StoreError(f"adding {name} would go over the {limits.max_total_mb:g} MB limit for all files")
    try:
        details = kind.details.model_validate(meta or {}).model_dump(mode="json")
    except ValidationError as err:
        first = err.errors()[0]
        raise StoreError(f"{'.'.join(map(str, first['loc'])) or 'details'}: {first['msg']}") from None
    if project is not None and view.get("project", project) is None:
        raise StoreError(f"there is no project {project}")
    if replaces is not None and view.get("file", replaces) is None:
        raise StoreError(f"there is no file {replaces} to replace")
    return name, details


def store_blob(store: Store, data: bytes) -> str:
    """Keep the bytes under their hash (once, however often they are added). Returns the hash."""
    digest = hashlib.sha256(data).hexdigest()
    path = blob_path(store, digest)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return digest


def blob_matches(store: Store, sha256: str, size: int) -> bool:
    path = blob_path(store, sha256)
    if not path.is_file() or path.stat().st_size != size:
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == sha256


def add_file(
    store: Store,
    cfg: Config,
    data: bytes,
    *,
    name: str,
    media_type: str,
    file_kind: str = "attachment",
    project: str | None = None,
    meta: dict[str, Any] | None = None,
    origin: str = "upload",
    replaces: str | None = None,
    data_level: str | None = None,
    context: WriteContext = _PM,
    now: datetime | None = None,
) -> Stored:
    """Check a file against the limits and its kind, store its bytes once, and record it. `data_level` is the person's
    explicit choice; without one the file takes its kind's level."""
    check_file(
        store, cfg, store.read(), name=name, media_type=media_type, size=len(data), file_kind=file_kind, meta=meta
    )
    digest = store_blob(store, data)
    level = level_for(store.plugins.file_kinds().get(file_kind), data_level)
    with store.transaction() as tx:
        name, details = check_file(
            store,
            cfg,
            tx,
            name=name,
            media_type=media_type,
            size=len(data),
            file_kind=file_kind,
            meta=meta,
            project=project,
            replaces=replaces,
        )
        return tx.create(
            "file",
            {
                "name": name,
                "media_type": media_type,
                "size": len(data),
                "sha256": digest,
                "file_kind": file_kind,
                "project": project,
                "meta": details,
                "origin": origin,
                "trust": "trusted" if origin == "upload" else "untrusted",
                "replaces": replaces,
                "added_at": (now or datetime.now(UTC)).isoformat(),
                "sensitivity": level,
            },
            context,
        )


def read_bytes(store: Store, file_id: str) -> tuple[Stored, bytes]:
    """A file's record and its bytes, checked against the hash it was stored under."""
    record = store.read().get("file", file_id)
    if record is None:
        raise StoreError(f"there is no file {file_id}")
    data = blob_path(store, record.data["sha256"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != record.data["sha256"]:
        raise StoreError(f"the stored bytes of {record.data['name']} don't match their hash")
    return record, data
