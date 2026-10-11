"""The scans must catch what they are for. Each test plants a violation in a scratch tree and checks it is found.

Planted values are read from the fixtures and the vendor list, or assembled from parts, so this file itself stays
clean under the scans it tests.
"""

import shutil
from pathlib import Path

import yaml

from engine.selfcheck import FIXTURES, run
from engine.selfcheck.scans import (
    ADAPTERS,
    REPO,
    scan_boundary,
    scan_patterns,
    scan_providers,
    scan_specificity,
)
from tests.conftest import fixture_records


def tree(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    (root / ADAPTERS).mkdir(parents=True)
    shutil.copy(REPO / ADAPTERS / "known_vendors.yaml", root / ADAPTERS / "known_vendors.yaml")
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def a_vendor() -> str:
    return yaml.safe_load((REPO / ADAPTERS / "known_vendors.yaml").read_text())["vendors"][0]


def test_the_repository_passes(capsys):
    assert run(out=lambda line: None) == 0


def test_specificity_catches_a_fixture_name_in_code(tmp_path):
    name = fixture_records(FIXTURES[0], "person")[0]["full_name"]
    root = tree(tmp_path, {"engine/x.py": f"OWNER = {name!r}\n", "engine/ok.py": "OWNER = None\n"})
    found = scan_specificity(list(FIXTURES), root=root)
    assert [(f.path, f.line) for f in found] == [("engine/x.py", 1)]


def test_specificity_hides_private_values(tmp_path):
    private = tmp_path / "private"
    (private / "config").mkdir(parents=True)
    secret = "Zebulon" + "Quartermaine"
    (private / "config" / "workspace.yaml").write_text(f"name: {secret}\n")
    root = tree(tmp_path, {"api/y.py": f"# talks to {secret}\n"})
    found = scan_specificity([], private, root=root)
    assert len(found) == 1 and secret not in str(found[0])


def test_specificity_ignores_fixture_folders(tmp_path):
    name = fixture_records(FIXTURES[1], "person")[0]["full_name"]
    root = tree(tmp_path, {"tests/fixtures/case.py": f"WHO = {name!r}\n"})
    assert scan_specificity(list(FIXTURES), root=root) == []


def test_provider_names_only_inside_adapters(tmp_path):
    vendor = a_vendor()
    files = {"engine/router.py": f"DEFAULT = '{vendor}'\n", f"{ADAPTERS}/thing.py": f"NAME = '{vendor}'\n"}
    root = tree(tmp_path, files)
    found = scan_providers(root=root)
    assert [f.path for f in found] == ["engine/router.py"]


def test_urls_and_dated_comments_are_caught(tmp_path):
    url = "https://" + "docs" + ".example" + ".net/page"
    who = "Jor" + "dan"
    root = tree(
        tmp_path,
        {
            "engine/a.py": f"LINK = '{url}'\n",
            "engine/b.py": f"x = 1  # per {who}, keep this\n",
            "engine/c.py": "x = 1  # retries the request once\n",
        },
    )
    found = {(f.path, f.line) for f in scan_patterns(root=root)}
    assert found == {("engine/a.py", 1), ("engine/b.py", 1)}


def test_core_must_not_import_plugins_and_plugins_only_the_api(tmp_path):
    root = tree(
        tmp_path,
        {
            "engine/core.py": "import plugins.publishing\n",
            "plugins/p/ok.py": "from engine.plugin_api import PLUGIN_API_VERSION\n",
            "plugins/p/bad.py": "from engine.storage import Store\nimport subprocess\n",
        },
    )
    found = sorted((f.path, f.line) for f in scan_boundary(root=root))
    assert found == [("engine/core.py", 1), ("plugins/p/bad.py", 1), ("plugins/p/bad.py", 2)]


def test_the_network_scan_flags_reaching_modules_not_pure_helpers():
    from engine.selfcheck.scans import reaches_network

    assert reaches_network("urllib.parse") is None and reaches_network("http") is None
    assert reaches_network("urllib.request") == "urllib.request" and reaches_network("http.client") == "http.client"
    assert reaches_network("httpx") == "httpx" and reaches_network("subprocess") == "subprocess"
