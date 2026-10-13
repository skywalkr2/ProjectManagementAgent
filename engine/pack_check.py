"""Checking a pack before it is published: `cockpit pack check <plugin folder> [--entry <catalog entry>]`.

Publishing a pack (the process every plugin repository follows; the catalog's PUBLISHING.md says the same):

1. **Release it in its own repository.** Raise the version in `plugin.yaml` (and the package's own metadata), say
   what changed, run its tests, tag the release, and let its own checks build the package from the tag.

2. **Write its catalog entry** as `catalog/pack.yaml` in that repository, in the catalog's format (the catalog
   repository's README): `provides` and `requires` copied exactly from `plugin.yaml`, its price, how to get it, and
   its typical AI jobs.

3. **Check it:** `cockpit pack check <its plugin folder> --entry catalog/pack.yaml`, with the host at the version the
   pack declares. Every line must pass. A pack whose plugins share a helper package from the same distribution is
   checked installed: install the built package beside the host and name the plugin instead of its folder
   (`cockpit pack check <plugin name> --entry catalog/pack.yaml`). An entry file listing several packs is matched
   to the plugin by its id.

4. **Ask for it to be published:** add a "Publish request" to its `docs/host-questions.md` (the pack, the version and
   tag, what changed, the check's output, and whether the owner has said it may be listed publicly) and tell the
   host's session. A plugin repository never writes to the catalog itself.

5. **The host verifies and proposes:** the host's session checks the release again itself (the same check, the
   pack's tests, a run in the demo sandbox) and opens a pull request on the catalog with the entry, saying what the
   pack adds, reaches and keeps, and what changed in what it asks for since its last listing.

6. **The owner decides:** the pack is listed only once the owner has said it may be, and the pull request is merged
   (by the owner, or by the host's session when the owner has handed it that). Updates follow the same path.

A pack that ships files its source control ignores (an app registration written by the release build, say) builds
its wheel straight from the checkout: a wheel built from the source archive leaves such files out. Check the built
package holds them before publishing.

The check reports each finding in plain words and passes only when every one does.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from engine.yaml_load import load_yaml


@dataclass
class Report:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed

    def lines(self) -> list[str]:
        return [f"PASS  {p}" for p in self.passed] + [f"FAIL  {f}" for f in self.failed]


def _declared(values: dict[str, Any]) -> dict[str, Any]:
    """The parts of `provides` or `requires` that say something, lists compared as sets."""
    out = {}
    for key, value in values.items():
        if value in (None, [], {}, ""):
            continue
        if isinstance(value, list):
            items = [yaml.safe_dump(v, sort_keys=True) if isinstance(v, dict) else str(v) for v in value]
            out[key] = sorted(items)
        else:
            out[key] = value
    return out


def check(plugin: Path | str, entry_path: Path | None = None) -> Report:
    """Check a pack, given its plugin folder (the one holding plugin.yaml) or an installed plugin's name."""
    from packaging.specifiers import InvalidSpecifier, SpecifierSet

    from engine.plugin_api import PLUGIN_API_VERSION
    from engine.plugin_manifest import read_manifest

    report = Report()
    folder = Path(plugin).expanduser()
    installed = not (folder / "plugin.yaml").is_file()
    if installed:
        found = _installed(str(plugin))
        if found is None:
            report.failed.append(f"{plugin} isn't a plugin folder (no plugin.yaml in it) or an installed plugin's name")
            return report
        folder = found
    folder = folder.resolve()
    try:
        manifest = read_manifest(folder / "plugin.yaml")
    except (OSError, ValueError) as err:
        report.failed.append(f"plugin.yaml can't be read: {err}")
        return report
    report.passed.append(f"plugin.yaml reads: {manifest.name} {manifest.version}")
    try:
        works = SpecifierSet(manifest.plugin_api).contains(PLUGIN_API_VERSION, prereleases=True)
    except InvalidSpecifier:
        works = False
    (report.passed if works else report.failed).append(
        f"plugin_api {manifest.plugin_api} {'includes' if works else 'excludes'} this host's {PLUGIN_API_VERSION}"
    )
    _load_in_demo(manifest.name if installed else str(folder), manifest.name, report)
    if entry_path is not None:
        _check_entry(entry_path, manifest, report, folder)
    return report


def _installed(name: str) -> Path | None:
    """The folder of an installed plugin with this name, found without importing it."""
    from importlib.metadata import entry_points

    from engine.plugin_manifest import installed_manifest

    for ep in entry_points(group="pm_cockpit.plugins"):
        if ep.name == name:
            path = installed_manifest(ep)
            return path.parent if path.is_file() else None
    return None


def _load_in_demo(plugin: str, name: str, report: Report) -> None:
    """Turn the pack on in a throwaway demo workspace (its folder linked, or installed by name) and see whether it
    loads."""
    from engine.cli import add_plugin
    from engine.config import load_config
    from engine.shipped import demo
    from engine.storage import Store
    from engine.workspace import Workspace, init_workspace

    with tempfile.TemporaryDirectory(prefix="cockpit-pack-check-") as tmp:
        ws = init_workspace(Path(tmp) / "demo", template=demo("demo-b"), git=False)
        add_plugin(Workspace(ws.root), plugin)
        try:
            cfg = load_config(ws.config_dir, env={})
        except Exception as err:  # noqa: BLE001 - any refusal is the finding
            report.failed.append(f"the demo workspace refused its settings with the pack on: {err}")
            return
        store = Store(ws.db_path, cfg=cfg)
        try:
            status = store.plugins.status.get(name)
            if store.plugins.active(name):
                report.passed.append("it loads and registers in a demo workspace")
                for note in status.notes if status else []:
                    report.failed.append(f"it loads, with a note: {note}")
            else:
                reason = status.reason if status else "it wasn't found"
                report.failed.append(f"it doesn't load in a demo workspace: {reason}")
        finally:
            store.close()


def _check_entry(entry_path: Path, manifest: Any, report: Report, manifest_folder: Path) -> None:
    from engine import packs

    try:
        raw = load_yaml(entry_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        report.failed.append(f"the catalog entry can't be read: {err}")
        return
    if isinstance(raw, dict) and "packs" in raw:
        listed = [p for p in raw.get("packs") or [] if isinstance(p, dict)]
        raw = next((p for p in listed if p.get("id") == manifest.name), None)
        if raw is None:
            report.failed.append(f"the catalog entry file lists no pack with the id {manifest.name}")
            return
    feed = packs.parse(str(entry_path), yaml.safe_dump({"version": 1, "packs": [raw]}))
    if feed.error or feed.notes or not feed.entries:
        report.failed.append(f"the catalog entry doesn't fit the catalog's format: {feed.error or feed.notes}")
        return
    entry = feed.entries[0]
    report.passed.append("the catalog entry fits the catalog's format")
    for label, ours, theirs in (
        ("id", entry.id, manifest.name),
        ("version", entry.version, manifest.version),
        ("plugin_api", entry.plugin_api, manifest.plugin_api),
    ):
        (report.passed if ours == theirs else report.failed).append(
            f"its {label} matches plugin.yaml ({ours})"
            if ours == theirs
            else f"its {label} is {ours!r}, plugin.yaml says {theirs!r}"
        )
    # Compared with plugin.yaml as written, since the entry is copied from it.
    data = load_yaml((Path(manifest_folder) / "plugin.yaml").read_text(encoding="utf-8")) or {}
    for part in ("provides", "requires"):
        ours, theirs = _declared(getattr(entry, part)), _declared(data.get(part) or {})
        if ours == theirs:
            report.passed.append(f"its {part} matches plugin.yaml exactly")
        else:
            differ = sorted({k for k in {*ours, *theirs} if ours.get(k) != theirs.get(k)})
            report.failed.append(f"its {part} differs from plugin.yaml in: {', '.join(differ)}")
