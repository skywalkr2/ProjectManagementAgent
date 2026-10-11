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
