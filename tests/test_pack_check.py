"""`cockpit pack check`: a pack is checked before it is published. Its manifest reads and fits this host, it loads in
a throwaway demo workspace, and its catalog entry matches its plugin.yaml exactly."""

import yaml

from engine.cli import main
from tests.test_today_panels_jobs import FIXTURE, MANIFEST


def pack(tmp_path):
    folder = tmp_path / "p18"
    folder.mkdir()
    (folder / "fixture.py").write_text(FIXTURE)
    (folder / "plugin.yaml").write_text(yaml.safe_dump(MANIFEST))
    entry = {
        "id": "p18",
        "name": "Goals",
        "version": MANIFEST["version"],
        "plugin_api": MANIFEST["plugin_api"],
        "price": {"model": "free"},
        "provides": dict(MANIFEST["provides"]),
        "requires": {},
    }
    return folder, entry


def test_a_pack_that_matches_its_entry_passes(tmp_path, capsys):
    folder, entry = pack(tmp_path)
    (tmp_path / "pack.yaml").write_text(yaml.safe_dump(entry))
    assert main(["pack", "check", str(folder), "--entry", str(tmp_path / "pack.yaml")]) == 0
    out = capsys.readouterr().out
    assert "it loads and registers in a demo workspace" in out and "All checks pass." in out


def test_an_entry_that_promises_less_than_the_pack_asks_fails(tmp_path, capsys):
    folder, entry = pack(tmp_path)
    entry["provides"]["jobs"] = []  # hides its scheduled work
    entry["version"] = "9.9.9"
    (tmp_path / "pack.yaml").write_text(yaml.safe_dump(entry))
    assert main(["pack", "check", str(folder), "--entry", str(tmp_path / "pack.yaml")]) == 1
    out = capsys.readouterr().out
    assert "its provides differs from plugin.yaml in: jobs" in out and "its version is '9.9.9'" in out


def test_a_pack_that_doesnt_load_fails(tmp_path, capsys):
    folder, _ = pack(tmp_path)
    (folder / "fixture.py").write_text(
        FIXTURE.replace("def register(registrar):", "def register(registrar):\n    raise")
    )
    assert main(["pack", "check", str(folder)]) == 1
    assert "it doesn't load in a demo workspace" in capsys.readouterr().out


def shared(tmp_path, monkeypatch, installed):
    """A distribution with a plugin package and a helper package beside it, installed or not."""
    import importlib.metadata
    from types import SimpleNamespace

    import engine.plugin_host as host

    src = tmp_path / "src"
    (src / "p19common").mkdir(parents=True)
    (src / "p19common" / "__init__.py").write_text("LABEL = 'shared'\n")
    package = src / "p19pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from engine.plugin_api import Settings\n"
        "from p19common import LABEL\n"
        "class Config(Settings):\n    pass\n"
        "def register(registrar):\n    assert LABEL\n"
    )
    manifest = {
        "name": "p19",
        "version": "0.2.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Shared helper fixture",
        "entry": "p19pkg:register",
        "config_schema": "p19pkg:Config",
    }
    (package / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    entries = {"version": 1, "packs": []}
    for pack_id in ("other", "p19"):
        entries["packs"].append(
            {
                "id": pack_id,
                "name": pack_id,
                "version": "0.2.0",
                "plugin_api": ">=0.3,<0.4",
                "price": {"model": "free"},
                "provides": {},
                "requires": {},
            }
        )
    (tmp_path / "pack.yaml").write_text(yaml.safe_dump(entries))
    if installed:
        monkeypatch.syspath_prepend(str(src))
        site = tmp_path / "site-packages"
        ep = SimpleNamespace(name="p19", value="p19pkg:register", dist=SimpleNamespace(locate_file=lambda m: site / m))
        monkeypatch.setattr(importlib.metadata, "entry_points", lambda group: [ep])
        monkeypatch.setattr(host, "entry_points", lambda group: [ep])
    return package


def test_a_pack_with_a_shared_helper_is_checked_installed_by_name(tmp_path, monkeypatch, capsys):
    shared(tmp_path, monkeypatch, installed=True)
    assert main(["pack", "check", "p19", "--entry", str(tmp_path / "pack.yaml")]) == 0, capsys.readouterr().out
    out = capsys.readouterr().out
    assert "it loads and registers in a demo workspace" in out and "its id matches plugin.yaml (p19)" in out


def test_its_folder_linked_over_the_installed_copy_is_the_same_plugin(tmp_path, monkeypatch, capsys):
    package = shared(tmp_path, monkeypatch, installed=True)
    assert main(["pack", "check", str(package), "--entry", str(tmp_path / "pack.yaml")]) == 0
    assert "with a note" not in capsys.readouterr().out


def test_an_unknown_name_says_what_it_expected(tmp_path, capsys):
    assert main(["pack", "check", "no-such-pack"]) == 1
    assert "isn't a plugin folder" in capsys.readouterr().out
