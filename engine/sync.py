"""The synced folder (design 5.0): the workspace written to a folder that a file-sync service keeps in step.

The folder holds two things:
- a readable layout, one folder per project (a child project's inside its parent's), with each record type that
  declares a `layout` written where it says: a Markdown file (front matter and the current long text) or a YAML file,
  every version of its long text in `.versions/`, and records in no project under `_workspace/`;
- a machine copy in `.cockpit/`: the plain export (records, texts, sequences, ledger), the config and the plugin data,
  which is what loading the folder reads.

Every file is written beside its target and renamed into place, so a half-written file never syncs, and its hash is
kept in `.cockpit/manifest.json`. A readable file whose content no longer matches what the cockpit wrote was changed
outside: it is never overwritten or removed, and is reported instead. The database and git history never live in the
folder, and the workspace may not sit inside it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MACHINE = ".cockpit"
WORKSPACE = "_workspace"
MANIFEST = f"{MACHINE}/manifest.json"
VERSIONS = ".versions"
RESERVED = {MACHINE.casefold(), WORKSPACE.casefold()}

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([^{}]*))?\}")
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


@dataclass
class SyncResult:
    written: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed_outside: list[str] = field(default_factory=list)  # readable files edited outside, left as they are


# ---- layout ----------------------------------------------------------------------------------------------------------


def check_layout(template: str, model: Any) -> None:
    """Refuse a layout template that isn't a relative path made of the record's own fields."""
    if not isinstance(template, str) or not template.strip():
        raise ValueError("a layout is a path like plan/chapters/{order:02}-{slug}")
    if template.startswith(("/", "\\")) or "\\" in template or re.match(r"^[A-Za-z]:", template):
        raise ValueError(f"layout {template!r} must be a relative path with / between folders")
    parts = template.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"layout {template!r} has an empty, '.' or '..' part")
    if parts[0].casefold() in RESERVED or any(p.startswith(".") for p in parts):
        raise ValueError(f"layout {template!r} uses a name the core keeps for itself")
    if re.search(r"\.(md|ya?ml|txt|json)$", template, re.I):
        raise ValueError(f"layout {template!r} names an extension; the core adds it")
    fields = set(getattr(model, "model_fields", {}))
    for name, _spec in _PLACEHOLDER.findall(template):
        if name not in fields:
            raise ValueError(f"layout {template!r} names {name}, which isn't a field of {model.record_kind}")
    if _PLACEHOLDER.sub("", template).count("{") or _PLACEHOLDER.sub("", template).count("}"):
        raise ValueError(f"layout {template!r} has a brace that isn't a {{field}}")


def safe_name(text: str, fallback: str) -> str:
    """One folder or file name that works on every common file system and sync service."""
    name = " ".join(_UNSAFE.sub("-", str(text)).split()).strip(" .")[:100].strip(" .")
    if not name:
        return fallback
    if name.split(".")[0].casefold() in _WINDOWS_NAMES:
        name = "_" + name
    return name


def render(template: str, record: Any) -> str:
    """A layout template filled from a record: each value made safe as a name, a missing one replaced by the id."""

    def value(match: re.Match[str]) -> str:
        name, spec = match.group(1), match.group(2) or ""
        raw = record.id if name == "id" else record.data.get(name)
        if raw is None or raw == "":
            return safe_name(record.id, record.id)
        try:
            text = format(raw, spec)
        except (TypeError, ValueError):
            text = str(raw)
        return safe_name(text, record.id)

    return _PLACEHOLDER.sub(value, template)


def _yaml(data: Any) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000)


def _fields(record: Any, model: Any, skip: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"id": record.id}
    for name in getattr(model, "model_fields", {}):
        if name == "id" or name in skip:
            continue
        value = record.data.get(name)
        if value in (None, [], {}, ""):
            continue
        out[name] = value
    return out


class _Names:
    """Taken paths, compared without case (as Windows and macOS do), so two records never share a file."""

    def __init__(self) -> None:
        self.taken: set[str] = set()

    def claim(self, path: str, record_id: str) -> str:
        if path.casefold() not in self.taken:
            self.taken.add(path.casefold())
            return path
        head, _, last = path.rpartition("/")
        unique = f"{head}/{last} ({record_id})" if head else f"{last} ({record_id})"
        self.taken.add(unique.casefold())
        return unique


def project_folders(view: Any) -> dict[str, str]:
    """{project id: its folder in the synced folder}: named after the project, inside its parent's folder."""
    projects = {p.id: p for p in view.list("project")}
    folders: dict[str, str] = {}
    names = _Names()
    for reserved in RESERVED:
        names.taken.add(reserved)

    def folder(project_id: str, depth: int = 0) -> str:
        if project_id in folders:
            return folders[project_id]
        project = projects[project_id]
        parent = project.data.get("parent")
        base = folder(parent, depth + 1) + "/" if parent in projects and depth < 50 else ""
        folders[project_id] = names.claim(base + safe_name(project.data.get("name", ""), project.id), project.id)
        return folders[project_id]

    for project_id in sorted(projects, key=_id_order):
        folder(project_id)
    return folders


def _id_order(record_id: str) -> tuple[int, str]:
    digits = record_id.rpartition("-")[2]
    return (int(digits) if digits.isdigit() else 0, record_id)


def readable_files(store: Any, view: Any) -> dict[str, bytes]:
    """The readable layout: {path in the folder: content}."""
    from engine.projects import project_of
    from engine.texts import long_text_fields

    files: dict[str, bytes] = {}
    folders = project_folders(view)
    for project in view.list("project"):
        model = store.plugins.records["project"]
        files[f"{folders[project.id]}/project.yaml"] = _yaml(_fields(project, model, set())).encode()
    names = _Names()
    for path in files:
        names.taken.add(path.casefold())
    models = {k: m for k, m in store.plugins.records.items() if getattr(m, "layout", None) and k != "project"}
    for kind in sorted(models):
        model = models[kind]
        texts = long_text_fields(model)
        for record in sorted(view.list(kind), key=lambda r: _id_order(r.id)):
            project = project_of(record)
            base = folders.get(project, WORKSPACE) if project else WORKSPACE
            path = names.claim(f"{base}/{render(model.layout, record)}", record.id)
            files.update(_record_files(store, view, record, model, texts, path))
    return files


def _record_files(store: Any, view: Any, record: Any, model: Any, texts: dict[str, str], path: str) -> dict[str, bytes]:
    from engine.texts import current, read_text, versions

    out: dict[str, bytes] = {}
    fields = _fields(record, model, set(texts))
    head, _, name = path.rpartition("/")
    if not texts:
        out[f"{path}.yaml"] = _yaml(fields).encode()
        return out
    single = len(texts) == 1
    if not single:
        out[f"{path}/record.yaml"] = _yaml(fields).encode()
    for text_field, fmt in texts.items():
        now = current(view, record.kind, record.id, text_field)
        text = read_text(store, now.data["sha256"]) if now else ""
        if single:
            out[f"{path}.md"] = ("---\n" + _yaml(fields) + "---\n\n" + text).encode()
            history = f"{head}/{VERSIONS}/{name}" if head else f"{VERSIONS}/{name}"
        else:
            out[f"{path}/{text_field}{_extension(fmt)}"] = text.encode()
            history = f"{path}/{VERSIONS}/{text_field}"
        every = versions(view, record.kind, record.id, text_field)
        listed = []
        for version in every:
            number = version.data["number"]
            out[f"{history}/v{number}{_extension(fmt)}"] = read_text(store, version.data["sha256"]).encode()
            listed.append(_version_entry(version))
        if listed:
            out[f"{history}/versions.yaml"] = _yaml(listed).encode()
    return out


def _extension(fmt: str) -> str:
    return ".txt" if fmt == "plain" else ".md"


def _version_entry(version: Any) -> dict[str, Any]:
    data = version.data
    words: dict[str, int] = {}
    for span in data.get("authorship") or []:
        words[span["kind"]] = words.get(span["kind"], 0) + int(span.get("words", 0))
    entry = {
        "number": data["number"],
        "status": data["status"],
        "source": data["source"],
        "base": data.get("base"),
        "note": data.get("note"),
        "created_at": str(data["created_at"]),
        "words": words,
        "authorship": [{k: s[k] for k in ("start", "end", "kind")} for s in data.get("authorship") or []],
        "unmapped": data.get("unmapped"),
        "questions": data.get("questions"),
    }
    return {k: v for k, v in entry.items() if v not in (None, [], {})}


# ---- machine copy ----------------------------------------------------------------------------------------------------


def machine_files(store: Any, ws: Any) -> dict[str, bytes]:
    """The plain export, the config and the plugin data, under `.cockpit/`: what loading the folder reads."""
    from engine.storage.export import export_data

    files: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="cockpit-sync-") as tmp:
        export_data(store, Path(tmp))
        for path in sorted(Path(tmp).rglob("*")):
            if path.is_file():
                files[f"{MACHINE}/export/{path.relative_to(tmp).as_posix()}"] = path.read_bytes()
    for name, root in (("config", ws.config_dir), ("plugin-data", ws.root / "plugin-data")):
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and not path.name.startswith("."):
                    files[f"{MACHINE}/{name}/{path.relative_to(root).as_posix()}"] = path.read_bytes()
    return files


# ---- writing ---------------------------------------------------------------------------------------------------------


def placement_problem(ws: Any, cfg: Any) -> str | None:
    """Why the configured synced folder may never be used with this workspace (start-up refuses), or None."""
    raw = cfg.storage.sync.folder.strip()
    if not raw:
        return None
    folder = Path(raw).expanduser()
    if not folder.is_absolute():
        return f"the synced folder {raw} must be a full path"
    folder, root = folder.resolve(), ws.root.resolve()
    if folder == root or root.is_relative_to(folder):
        return "the workspace is inside the synced folder; keep it on this computer's own disk"
    if folder.is_relative_to(root):
        return "the synced folder is inside the workspace; choose a folder outside it"
    return None


def folder_problem(ws: Any, cfg: Any) -> str | None:
    """Why the configured synced folder can't be written now, or None. Off (no folder) is never a problem."""
    placed = placement_problem(ws, cfg)
    if placed or not cfg.storage.sync.folder.strip():
        return placed
    folder = Path(cfg.storage.sync.folder).expanduser().resolve()
    if not folder.is_dir():
        return f"the synced folder {folder} isn't there (is the drive or sync service connected?)"
    return None


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.cockpit-tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _prune(folder: Path, start: Path) -> None:
    current = start
    while current != folder and current.is_relative_to(folder):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def write_folder(store: Any, ws: Any, cfg: Any) -> SyncResult:
    """Bring the synced folder up to date. Raises ValueError when the folder can't be used."""
    problem = folder_problem(ws, cfg)
    if problem:
        raise ValueError(problem)
    folder = Path(cfg.storage.sync.folder).expanduser().resolve()
    with store.snapshot() as view:
        wanted = {**readable_files(store, view), **machine_files(store, ws)}
    manifest_path = folder / MANIFEST
    try:
        manifest: dict[str, str] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    result = SyncResult()
    for rel in sorted(wanted):
        data, path = wanted[rel], folder / rel
        digest = _digest(data)
        if path.is_file():
            found = _digest(path.read_bytes())
            if found == digest:
                manifest[rel] = digest
                continue
            if not rel.startswith(MACHINE + "/") and manifest.get(rel) != found:
                result.changed_outside.append(rel)
                continue
        _write_atomic(path, data)
        manifest[rel] = digest
        result.written.append(rel)
    for rel in sorted(set(manifest) - set(wanted)):
        path = folder / rel
        if not path.is_file():
            del manifest[rel]
        elif _digest(path.read_bytes()) == manifest[rel]:
            path.unlink()
            del manifest[rel]
            result.removed.append(rel)
            _prune(folder, path.parent)
        else:
            result.changed_outside.append(rel)
    _write_atomic(manifest_path, (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode())
    return result


def load_folder(store: Any, folder: Path) -> int:
    """Load a synced folder's machine copy into an empty store. Returns the number of records loaded."""
    from engine.storage.export import import_data

    export = folder / MACHINE / "export"
    if not export.is_dir():
        raise ValueError(f"{folder} has no workspace in it ({MACHINE}/export is missing)")
    return import_data(store, export)
