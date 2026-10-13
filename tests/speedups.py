"""Test-run speedups that change no result: the same data comes back, only sooner. Each one keys what it keeps on
everything the answer depends on, and falls back to the real call whenever it can't. `install()` runs once, from
conftest, before the product's modules are imported."""

from __future__ import annotations

import atexit
import shutil
import sys
import tempfile
import typing
from pathlib import Path


def install() -> None:
    _use_the_c_yaml_parser()
    _remember_installed_plugins()
    _share_route_validators()
    _copy_prepared_workspaces()


# ---- parsing ---------------------------------------------------------------------------------------------------------


def _use_the_c_yaml_parser() -> None:
    """Settings, manifests and records are many small YAML files for every workspace a test builds. The C parser gives
    the same data as the pure-Python one several times faster; it is used when it is installed."""
    import yaml

    if getattr(yaml, "CSafeLoader", None) is None:
        return

    def safe_load(stream):
        return yaml.load(stream, Loader=yaml.CSafeLoader)

    yaml.safe_load = safe_load


# ---- installed plugins -----------------------------------------------------------------------------------------------


def _remember_installed_plugins() -> None:
    """Every settings load and every plugin host asks which add-ons are installed, and each ask reads every installed
    package's entry-point file. The answer is kept until a folder on the import path, or an installed package's entry
    file, changes (a test that installs one gets a fresh answer)."""
    import importlib.metadata as metadata
    import os

    original = metadata.entry_points
    kept: dict = {}

    def signature() -> tuple:
        parts = []
        for entry in sys.path:
            try:
                parts.append((entry, os.stat(entry or ".").st_mtime_ns))
                with os.scandir(entry or ".") as children:
                    for child in children:
                        if child.name.endswith((".dist-info", ".egg-info")):
                            try:
                                parts.append(
                                    (child.name, os.stat(os.path.join(child.path, "entry_points.txt")).st_mtime_ns)
                                )
                            except OSError:
                                parts.append((child.name, None))
            except OSError:
                parts.append((entry, None))
        return tuple(parts)

    def entry_points(**params):
        if set(params) != {"group"}:
            return original(**params)
        key = (params["group"], signature())
        if key not in kept:
            kept.clear()
            kept[key] = original(**params)
        return kept[key]

    metadata.entry_points = entry_points


# ---- the web framework's validators ----------------------------------------------------------------------------------


def _share_route_validators() -> None:
    """Every test that builds the app registers the same few hundred routes, and the web framework builds a validator
    for each parameter and response again. A validator holds no per-app state, so one built for the same type, field
    settings and config is reused for the rest of the process. A type or setting that can't be keyed is built afresh."""
    try:
        from fastapi._compat import v2
        from pydantic import TypeAdapter
        from pydantic.fields import FieldInfo
    except ImportError:
        return
    if getattr(v2, "TypeAdapter", None) is not TypeAdapter:
        return
    kept: dict = {}

    def keyed(part):
        if isinstance(part, FieldInfo):
            return ("field", repr(part))
        hash(part)
        return part

    def shared_adapter(tp, *args, config=None, **kwargs):
        if args or kwargs or typing.get_origin(tp) is not typing.Annotated:
            return TypeAdapter(tp, *args, config=config, **kwargs)
        try:
            key = (tuple(keyed(part) for part in typing.get_args(tp)), None if config is None else repr(config))
            hash(key)
        except TypeError:
            return TypeAdapter(tp, config=config)
        if key not in kept:
            kept[key] = TypeAdapter(tp, config=config)
        return kept[key]

    v2.TypeAdapter = shared_adapter


# ---- workspaces ------------------------------------------------------------------------------------------------------


def _copy_prepared_workspaces() -> None:
    """A workspace made from a template is the same every time: config and data copied, then the data loaded and
    written back. The first one for a template (and git setting) is made for real; later ones are copies of its folder.
    The template's files are part of the key, so a test that changes the template gets a new one."""
    import engine.workspace as module

    original = module.init_workspace
    scratch = tempfile.TemporaryDirectory(prefix="cockpit-prepared-")
    atexit.register(scratch.cleanup)
    prepared: dict = {}

    def template_files(template: Path) -> tuple:
        return tuple(
            (str(path.relative_to(template)), path.stat().st_mtime_ns, path.stat().st_size)
            for path in sorted(template.rglob("*"))
            if path.is_file()
        )

    def init_workspace(path, *, template=None, git=True, you=None, name=None, assistant=None):
        if template is None or you or name or assistant:
            return original(path, template=template, git=git, you=you, name=name, assistant=assistant)
        root = Path(path).expanduser().resolve()
        if root.exists() and any(root.iterdir()):
            return original(path, template=template, git=git)
        key = (Path(template).resolve(), git, template_files(Path(template)))
        if key not in prepared:
            prepared[key] = original(Path(scratch.name) / f"ws{len(prepared)}", template=template, git=git).root
        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(prepared[key], root, dirs_exist_ok=True, symlinks=True)
        return module.Workspace(root)

    module.init_workspace = init_workspace
    for loaded in list(sys.modules.values()):
        if getattr(loaded, "init_workspace", None) is original:
            loaded.init_workspace = init_workspace
