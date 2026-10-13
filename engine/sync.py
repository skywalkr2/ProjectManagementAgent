"""The synced folder (design 5.0): the workspace written to a folder that a file-sync service keeps in step.

The folder holds two things:
- a readable layout, one folder per project (a child project's inside its parent's): each record type that declares a
  `layout` written where it says (a Markdown file with front matter and the current long text, a YAML file, or one
  YAML list for a collection), every version of its long text in `.versions/`, the project's sources in `sources/`,
  files the person approved from plugin actions in `outputs/`, working copies in `working/`, files plugins generate
  from their records, and records in no project under `_workspace/`;
- a machine copy in `.cockpit/`: the plain export (records, texts, sequences, ledger), the config, the plugin data and
  the bytes of every file and source, which is what loading the folder reads.

Every file is written beside its target and renamed into place, so a half-written file never syncs, and its hash is
kept in `.cockpit/manifest.json`; `.cockpit/index.json` says what each readable file holds. A readable file whose
content no longer matches what the cockpit wrote was changed outside: it is never overwritten or removed (generated
files aside, which are rebuilt), and the outside-edit pass turns the change into a proposal for the person. The
database and git history never live in the folder, and the workspace may not sit inside it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from engine.yaml_load import COMPILED_SAFE_LOADER, load_with

MACHINE = ".cockpit"
WORKSPACE = "_workspace"
MANIFEST = f"{MACHINE}/manifest.json"
INDEX = f"{MACHINE}/index.json"
VERSIONS = ".versions"
RESERVED = {MACHINE.casefold(), WORKSPACE.casefold()}
#: Folders the core writes in each project's folder; a layout may not start with one.
CORE_FOLDERS = {"sources", "outputs", "working"}

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?(?::([^{}]*))?\}")
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_HASHES: dict[str, tuple[int, int, str]] = {}  # path: (mtime_ns, size, sha256), so unchanged files aren't read again


@dataclass
class SyncResult:
    written: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed_outside: list[str] = field(default_factory=list)  # readable files edited outside, left as they are
    removed_outside: list[str] = field(default_factory=list)  # sources, outputs and working copies deleted outside
    rebuilt: list[str] = field(default_factory=list)  # generated files changed outside and written again


@dataclass(frozen=True)
class Entry:
    """What one readable file holds. `part`: record (Markdown: fields and one long text), fields (YAML), text (one
    long text field), collection (a YAML list of records), history, source, output, working, derived."""

    part: str
    kind: str | None = None
    id: str | None = None
    field: str | None = None
    version: int | None = None  # the long text version written
    record_version: int | None = None
    records: tuple[tuple[str, int], ...] = ()  # a collection's (id, version) pairs


@dataclass(frozen=True)
class Blob:
    """A file to copy into the folder from local disk, named by its hash."""

    digest: str
    path: Path = field(compare=False)


# ---- layout ----------------------------------------------------------------------------------------------------------


def check_layout(template: str, model: Any, models: dict[str, Any] | None = None) -> None:
    """Refuse a layout template that isn't a relative path made of the record's own fields (or, one level deep, the
    fields of a record it refers to), and a collection that can't be one."""
    from engine.records import ref_fields
    from engine.texts import long_text_fields

    if not isinstance(template, str) or not template.strip():
        raise ValueError("a layout is a path like plan/chapters/{order:02}-{slug}")
    if template.startswith(("/", "\\")) or "\\" in template or re.match(r"^[A-Za-z]:", template):
        raise ValueError(f"layout {template!r} must be a relative path with / between folders")
    parts = template.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"layout {template!r} has an empty, '.' or '..' part")
    if parts[0].casefold() in RESERVED | CORE_FOLDERS or any(p.startswith(".") for p in parts):
        raise ValueError(f"layout {template!r} uses a name the core keeps for itself")
    if re.search(r"\.(md|ya?ml|txt|json)$", template, re.I):
        raise ValueError(f"layout {template!r} names an extension; the core adds it")
    fields = set(getattr(model, "model_fields", {}))
    refs = {path: target for path, target in ref_fields(model) if "." not in path and "[]" not in path}
    for name, sub, _spec in _PLACEHOLDER.findall(template):
        if name not in fields:
            raise ValueError(f"layout {template!r} names {name}, which isn't a field of {model.record_kind}")
        if sub:
            target = refs.get(name)
            target_model = (models or {}).get(target) if target else None
            if target is None:
                raise ValueError(f"layout {template!r}: {name} isn't a reference to one record")
            if target_model is not None and sub not in target_model.model_fields:
                raise ValueError(f"layout {template!r}: {target} has no field {sub}")
    if _PLACEHOLDER.sub("", template).count("{") or _PLACEHOLDER.sub("", template).count("}"):
        raise ValueError(f"layout {template!r} has a brace that isn't a {{field}}")
    if getattr(model, "layout_collection", False):
        if long_text_fields(model):
            raise ValueError(f"{model.record_kind} has long text, so it can't be a collection")
        sort = getattr(model, "layout_sort", None)
        if sort is not None and sort not in fields:
            raise ValueError(f"layout_sort names {sort}, which isn't a field of {model.record_kind}")
    via = getattr(model, "layout_project", None)
    if via is not None and via not in refs:
        raise ValueError(f"layout_project names {via}, which isn't a reference to one record")


def check_derived_path(path: str) -> None:
    """Refuse a generated file's path that isn't a relative file path with an extension."""
    if not isinstance(path, str) or not re.fullmatch(r"[^/\\{}]+(/[^/\\{}]+)*\.[a-z0-9]{1,8}", path):
        raise ValueError(f"a generated file's path is relative with an extension, like views/overview.md: {path!r}")
    parts = path.split("/")
    if any(p in (".", "..") or p.startswith(".") for p in parts) or parts[0].casefold() in RESERVED | CORE_FOLDERS:
        raise ValueError(f"{path!r} uses a name the core keeps for itself")


def safe_name(text: str, fallback: str) -> str:
    """One folder or file name that works on every common file system and sync service."""
    name = " ".join(_UNSAFE.sub("-", str(text)).split()).strip(" .")[:100].strip(" .")
    if not name:
        return fallback
    if name.split(".")[0].casefold() in _WINDOWS_NAMES:
        name = "_" + name
    return name


def render(template: str, record: Any, view: Any = None, models: dict[str, Any] | None = None) -> str:
    """A layout template filled from a record (and, for `{ref.field}`, the record it refers to, found with `view` and
    the record `models`): each value made safe as a name, a missing one replaced by the id."""
    from engine.records import ref_fields

    def value(match: re.Match[str]) -> str:
        name, sub, spec = match.group(1), match.group(2), match.group(3) or ""
        raw = record.id if name == "id" else record.data.get(name)
        if sub and raw is not None:
            model = (models or {}).get(record.kind)
            kind = dict(ref_fields(model)).get(name) if model is not None else None
            other = view.get(kind, raw) if view is not None and kind else None
            raw = (other.id if sub == "id" else other.data.get(sub)) if other is not None else None
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


def _without_dates(base: type) -> type:
    """`base` reading YAML the way it was written: dates and times stay text, as the records hold them."""
    loader = type("_NoDates", (base,), {})
    loader.yaml_implicit_resolvers = {
        key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
        for key, resolvers in base.yaml_implicit_resolvers.items()
    }
    return loader


_NoDates = _without_dates(yaml.SafeLoader)
_FastNoDates = _without_dates(COMPILED_SAFE_LOADER) if COMPILED_SAFE_LOADER is not None else None


def read_yaml(text: str) -> Any:
    return load_with(text, _FastNoDates, _NoDates)


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
        stem, dot, ext = last.rpartition(".") if "." in last else (last, "", "")
        named = f"{stem} ({record_id}){dot}{ext}"
        unique = f"{head}/{named}" if head else named
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


def readable_files(store: Any, view: Any) -> tuple[dict[str, bytes | Blob], dict[str, Entry]]:
    """The readable layout: {path in the folder: content} and {path: what it holds}."""
    from engine.projects import project_of
    from engine.texts import long_text_fields

    files: dict[str, bytes | Blob] = {}
    index: dict[str, Entry] = {}
    folders = project_folders(view)
    project_model = store.plugins.records["project"]
    for project in view.list("project"):
        rel = f"{folders[project.id]}/project.yaml"
        files[rel] = _yaml(_fields(project, project_model, set())).encode()
        index[rel] = Entry("fields", "project", project.id, record_version=project.version)
    names = _Names()
    for path in files:
        names.taken.add(path.casefold())

    def base_of(record: Any) -> str:
        project = project_of(record)
        via = getattr(store.plugins.records.get(record.kind), "layout_project", None)
        if project is None and via and record.data.get(via):
            from engine.records import ref_fields

            target = dict(ref_fields(store.plugins.records[record.kind])).get(via)
            referred = view.get(target, record.data[via]) if target else None
            project = project_of(referred) if referred is not None else None
        return folders.get(project, WORKSPACE) if project else WORKSPACE

    models = {k: m for k, m in store.plugins.records.items() if getattr(m, "layout", None) and k != "project"}
    for kind in sorted(models):
        model = models[kind]
        records = sorted(view.list(kind), key=lambda r: _id_order(r.id))
        if getattr(model, "layout_collection", False):
            _collection_files(store.plugins.records, model, records, base_of, view, names, files, index)
            continue
        texts = long_text_fields(model)
        for record in records:
            rendered = render(model.layout, record, view, store.plugins.records)
            path = names.claim(f"{base_of(record)}/{rendered}", record.id)
            _record_files(store, view, record, model, texts, path, files, index)
    _file_copies(store, view, folders, names, files, index)
    _derived_files(store, view, folders, names, files, index)
    return files, index


def _collection_files(
    models: dict[str, Any],
    model: Any,
    records: list[Any],
    base_of: Any,
    view: Any,
    names: _Names,
    files: dict[str, bytes | Blob],
    index: dict[str, Entry],
) -> None:
    groups: dict[str, list[Any]] = {}
    for record in records:
        groups.setdefault(f"{base_of(record)}/{render(model.layout, record, view, models)}", []).append(record)
    sort = getattr(model, "layout_sort", None)

    def order(record: Any) -> tuple[Any, ...]:
        value = record.data.get(sort)
        if value is None:
            return (2, 0, "", _id_order(record.id))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return (0, value, "", _id_order(record.id))
        return (1, 0, str(value), _id_order(record.id))

    for path, members in groups.items():
        if sort:
            members.sort(key=order)
        rel = names.claim(path, members[0].id) + ".yaml"
        files[rel] = _yaml([_fields(r, model, set()) for r in members]).encode()
        index[rel] = Entry("collection", model.record_kind, records=tuple((r.id, r.version) for r in members))


def _record_files(
    store: Any,
    view: Any,
    record: Any,
    model: Any,
    texts: dict[str, str],
    path: str,
    files: dict[str, bytes | Blob],
    index: dict[str, Entry],
) -> None:
    from engine.texts import current, read_text, versions

    fields = _fields(record, model, set(texts))
    head, _, name = path.rpartition("/")
    if not texts:
        files[f"{path}.yaml"] = _yaml(fields).encode()
        index[f"{path}.yaml"] = Entry("fields", record.kind, record.id, record_version=record.version)
        return
    single = len(texts) == 1
    if not single:
        files[f"{path}/record.yaml"] = _yaml(fields).encode()
        index[f"{path}/record.yaml"] = Entry("fields", record.kind, record.id, record_version=record.version)
    for text_field, fmt in texts.items():
        now = current(view, record.kind, record.id, text_field)
        text = read_text(store, now.data["sha256"]) if now else ""
        number = now.data["number"] if now else None
        if single:
            rel = f"{path}.md"
            files[rel] = ("---\n" + _yaml(fields) + "---\n\n" + text).encode()
            index[rel] = Entry("record", record.kind, record.id, text_field, number, record.version)
            history = f"{head}/{VERSIONS}/{name}" if head else f"{VERSIONS}/{name}"
        else:
            rel = f"{path}/{text_field}{_extension(fmt)}"
            files[rel] = text.encode()
            index[rel] = Entry("text", record.kind, record.id, text_field, number, record.version)
            history = f"{path}/{VERSIONS}/{text_field}"
        listed = []
        for version in versions(view, record.kind, record.id, text_field):
            rel = f"{history}/v{version.data['number']}{_extension(fmt)}"
            files[rel] = read_text(store, version.data["sha256"]).encode()
            index[rel] = Entry("history", record.kind, record.id, text_field, version.data["number"])
            listed.append(_version_entry(version))
        if listed:
            files[f"{history}/versions.yaml"] = _yaml(listed).encode()
            index[f"{history}/versions.yaml"] = Entry("history", record.kind, record.id, text_field)


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


def _file_copies(
    store: Any,
    view: Any,
    folders: dict[str, str],
    names: _Names,
    files: dict[str, bytes | Blob],
    index: dict[str, Entry],
) -> None:
    """Sources (texts handed in, files the person added) in `sources/`, files the person approved from actions in
    `outputs/` (the newest of each), working copies that are out in `working/`."""
    from engine.files import blob_path

    def base(project: str | None) -> str:
        return folders.get(project, WORKSPACE) if project else WORKSPACE

    sources_dir = store.path.parent / "sources"
    for source in sorted(view.list("source"), key=lambda r: _id_order(r.id)):
        text = sources_dir / f"{source.data['content_hash']}.txt"
        if not text.is_file():
            continue
        projects = [p for p in source.data.get("projects") or [] if p in folders]
        name = safe_name(source.data.get("title") or source.id, source.id) + ".txt"
        rel = names.claim(f"{base(projects[0] if projects else None)}/sources/{name}", source.id)
        files[rel] = Blob(_file_digest(text), text)
        index[rel] = Entry("source", "source", source.id)
    copies = [c for c in view.list("working_copy")]
    working_files = {c.data["file"] for c in copies} | {c.data.get("returned_file") for c in copies}
    every = view.list("file")
    replaced = {f.data.get("replaces") for f in every if f.data.get("replaces")}
    for item in sorted(every, key=lambda r: _id_order(r.id)):
        if item.id in working_files:
            continue
        if item.data.get("origin") == "tool" and item.id in replaced:
            continue
        folder = "sources" if item.data.get("origin") == "upload" else "outputs"
        name = safe_name(item.data["name"], item.id)
        rel = names.claim(f"{base(item.data.get('project'))}/{folder}/{name}", item.id)
        files[rel] = Blob(item.data["sha256"], blob_path(store, item.data["sha256"]))
        index[rel] = Entry(folder[:-1], "file", item.id)
    for copy in sorted(copies, key=lambda r: _id_order(r.id)):
        if copy.data["status"] == "dropped":
            continue
        handed = view.get("file", copy.data["file"])
        owner = view.get(copy.data["owner_kind"], copy.data["owner_id"])
        if handed is None or owner is None:
            continue
        from engine.projects import project_of

        rel = names.claim(f"{base(project_of(owner))}/working/{safe_name(handed.data['name'], copy.id)}", copy.id)
        files[rel] = Blob(handed.data["sha256"], blob_path(store, handed.data["sha256"]))
        index[rel] = Entry("working", "working_copy", copy.id)


def _derived_files(
    store: Any,
    view: Any,
    folders: dict[str, str],
    names: _Names,
    files: dict[str, bytes | Blob],
    index: dict[str, Entry],
) -> None:
    """Files plugins generate from their records, per project that has records of the kinds they depend on."""
    from engine.plugin_api import ReadView

    in_project: dict[str, set[str]] = {}
    for kind in {k for r in store.plugins.registrars.values() for d in r.derived_files.values() for k in d.depends_on}:
        for record in view.list(kind):
            project = record.id if kind == "project" else record.data.get("project")
            if isinstance(project, str):
                in_project.setdefault(project, set()).add(kind)
    for plugin, registrar in sorted(store.plugins.registrars.items()):
        if not store.plugins.active(plugin):
            continue
        for name, derived in sorted(registrar.derived_files.items()):
            for project_id, folder in sorted(folders.items()):
                if not in_project.get(project_id, set()) & set(derived.depends_on):
                    continue
                project = view.get("project", project_id)
                reader = store.plugins._with_files(ReadView(view, plugin))
                try:
                    text = derived.render(project, reader, registrar.config.model_copy(deep=True))
                except Exception as err:
                    store.plugins.disable(plugin, f"generated file {name} failed: {err}")
                    break
                if text is None:
                    continue
                if not isinstance(text, str):
                    store.plugins.disable(plugin, f"generated file {name} returned something other than text")
                    break
                rel = names.claim(f"{folder}/{derived.path}", project_id)
                files[rel] = text.encode()
                index[rel] = Entry("derived", name, project_id)


# ---- machine copy ----------------------------------------------------------------------------------------------------


def machine_files(store: Any, ws: Any) -> dict[str, bytes | Blob]:
    """The plain export, the config, the plugin data and the bytes of every file and source, under `.cockpit/`: what
    loading the folder reads."""
    from engine.files import blob_path
    from engine.storage.export import export_data

    files: dict[str, bytes | Blob] = {}
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
    view = store.read()
    for item in view.list("file", include_deleted=True):
        blob = blob_path(store, item.data["sha256"])
        if blob.is_file():
            files[f"{MACHINE}/files/{item.data['sha256']}"] = Blob(item.data["sha256"], blob)
    for source in view.list("source", include_deleted=True):
        text = store.path.parent / "sources" / f"{source.data['content_hash']}.txt"
        if text.is_file():
            files[f"{MACHINE}/sources/{text.name}"] = Blob(_file_digest(text), text)
    return files


def restore_bytes(root: Path, files: dict[str, Path], sources: dict[str, Path]) -> None:
    """Put loaded file bytes and source texts where the workspace at `root` keeps them, each file checked against
    the hash it is named by."""
    from engine.files import blob_path_in

    for name, path in files.items():
        if _file_digest(path) != name:
            raise ValueError(f"{MACHINE}/files/{name} doesn't match its name")
        target = blob_path_in(root, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    sources_dir = root / "sources"
    for name, path in sources.items():
        sources_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, sources_dir / name)


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
    if (folder / "config" / "workspace.yaml").is_file():
        # Another workspace's folder: its own private files would read as a sync service's conflict copies, and
        # writing there would mix this workspace's copy into that one.
        return f"the synced folder {folder} is another workspace's own folder; choose an empty folder for syncing"
    return None


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_digest(path: Path) -> str:
    """A file's hash, read again only when its size or modification time changed."""
    stat = path.stat()
    key = str(path)
    cached = _HASHES.get(key)
    if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    _HASHES[key] = (stat.st_mtime_ns, stat.st_size, digest.hexdigest())
    return digest.hexdigest()


def _write_atomic(path: Path, data: bytes | Blob) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.cockpit-tmp")
    if isinstance(data, Blob):
        shutil.copyfile(data.path, tmp)
    else:
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


def read_manifest(folder: Path) -> dict[str, str]:
    try:
        return json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def read_index(folder: Path) -> dict[str, Entry]:
    try:
        raw = json.loads((folder / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    index = {}
    for rel, data in raw.items():
        data["records"] = tuple(tuple(r) for r in data.get("records", ()))
        index[rel] = Entry(**data)
    return index


def file_digest(path: Path) -> str:
    return _file_digest(path)


def write_folder(
    store: Any, ws: Any, cfg: Any, *, may_overwrite: set[str] | frozenset[str] = frozenset()
) -> SyncResult:
    """Bring the synced folder up to date. `may_overwrite` names readable files changed outside whose change the
    person has dealt with, so they are written again. Raises ValueError when the folder can't be used."""
    problem = folder_problem(ws, cfg)
    if problem:
        raise ValueError(problem)
    folder = Path(cfg.storage.sync.folder).expanduser().resolve()
    with store.snapshot() as view:
        readable, index = readable_files(store, view)
        wanted = {**readable, **machine_files(store, ws)}
    manifest = read_manifest(folder)
    result = SyncResult()
    for rel in sorted(wanted):
        data, path = wanted[rel], folder / rel
        digest = data.digest if isinstance(data, Blob) else _digest(data)
        entry = index.get(rel)
        if path.is_file():
            found = _file_digest(path)
            if found == digest:
                manifest[rel] = digest
                continue
            outside = manifest.get(rel) != found
            if outside and entry is not None and entry.part == "derived":
                result.rebuilt.append(rel)
            elif outside and not rel.startswith(MACHINE + "/") and rel not in may_overwrite:
                result.changed_outside.append(rel)
                continue
        elif rel in manifest and entry is not None and entry.part in ("source", "output", "working"):
            result.removed_outside.append(rel)
            continue
        _write_atomic(path, data)
        _HASHES.pop(str(path), None)
        manifest[rel] = digest
        result.written.append(rel)
    for rel in sorted(set(manifest) - set(wanted)):
        path = folder / rel
        if not path.is_file():
            del manifest[rel]
        elif _file_digest(path) == manifest[rel]:
            path.unlink()
            _HASHES.pop(str(path), None)
            del manifest[rel]
            result.removed.append(rel)
            _prune(folder, path.parent)
        else:
            result.changed_outside.append(rel)
    index_json = {rel: {k: v for k, v in asdict(e).items() if v not in (None, ())} for rel, e in sorted(index.items())}
    _write_atomic(folder / INDEX, (json.dumps(index_json, sort_keys=True, indent=1) + "\n").encode())
    _write_atomic(folder / MANIFEST, (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode())
    return result


def load_folder(store: Any, folder: Path) -> int:
    """Load a synced folder's machine copy into an empty store. Returns the number of records loaded."""
    from engine.storage.export import import_data

    export = folder / MACHINE / "export"
    if not export.is_dir():
        raise ValueError(f"{folder} has no workspace in it ({MACHINE}/export is missing)")
    count = import_data(store, export)
    blobs = folder / MACHINE / "files"
    texts = folder / MACHINE / "sources"
    restore_bytes(
        store.path.parent,
        {p.name: p for p in blobs.iterdir() if p.is_file()} if blobs.is_dir() else {},
        {p.name: p for p in texts.iterdir() if p.is_file()} if texts.is_dir() else {},
    )
    return count
