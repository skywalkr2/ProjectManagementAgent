"""Why an add-on didn't load is said in plain words: manifest validation, registration errors and settings errors, each
produced by a broken add-on and passed through the wording check (api/screen_text.py)."""

import ast
from pathlib import Path

import pytest
import yaml

from api.screen_text import problems
from engine.plugin_host import BUNDLED
from engine.storage import Store
from tests.test_plugins import config, make_plugin

ROOT = Path(__file__).resolve().parents[1]


def reason_of(tmp_path, *, edits=None, source=None, settings=None) -> str:
    root = make_plugin(tmp_path, edits=edits, source=source)
    if source is None and settings is not None:
        code = root / "__init__.py"
        code.write_text(settings(code.read_text()))
    store = Store(tmp_path / "db", cfg=config(tmp_path, ["scratch"]))
    try:
        status = store.plugins.status["scratch"]
        assert status.state == "disabled"
        return status.reason
    finally:
        store.close()


def update(section, **values):
    def edit(raw):
        (raw[section] if section else raw).update(values)

    return edit


MANIFEST_CASES = [
    ("a key the app doesn't know", update(None, typo=True), "'typo': isn't something this app knows"),
    ("a key under requires", update("requires", typo=True), "what it may reach and needs (typo): isn't something"),
    ("a key under provides", update("provides", typo=[]), "what it provides (typo): isn't something"),
    ("a range that isn't one", update(None, plugin_api="not a range"), "the versions of the app it works with:"),
    ("a version that isn't one", update(None, version="not a version"), "its version: Invalid version"),
    ("a name with capitals", update(None, name="Bad Name"), "its name: String should match"),
    ("a missing part", lambda raw: raw.pop("entry"), "where it starts: is missing"),
    ("an id outside the namespace", update("provides", ops=["wrong/add"]), "must be namespaced scratch/<name>"),
    ("an id listed twice", update("provides", ops=["scratch/a", "scratch/a"]), "duplicate ops"),
    ("a wildcard beside others", update("provides", ops=["scratch/*", "scratch/a"]), "stands alone"),
    ("an event handled twice", update(None, subscribes=["record.changed", "record.changed"]), "duplicate event"),
    ("a host that isn't one", update("requires", network=["not a host"]), "isn't a host name"),
    ("a secret name that isn't one", update("requires", secrets=["Bad_Name"]), "isn't a secret name"),
    ("a data level that doesn't exist", update("requires", data_levels=["secret"]), "item 1"),
    (
        "an interface used in the wrong shape",
        update("interfaces", uses=[{"interface": "nonsense"}]),
        "use an interface as",
    ),
    (
        "connector reads for an unlisted connector",
        update("provides", connector_reads={"scratch/c": "mail"}),
        "names only connectors listed in connectors",
    ),
    ("a help path outside the add-on", update("provides", help=["../x.md"]), "a help file is a .md path"),
    (
        "a wording path outside the add-on",
        update("provides", wording=["../x.yaml"]),
        "a wording file must be a YAML file inside the plugin",
    ),
    ("an entry that isn't module:symbol", update(None, entry="no symbol"), "where it starts: expected module:symbol"),
    ("a dependency range that isn't one", update(None, depends_on=[{"name": "x", "version": "??"}]), "item 1"),
]


@pytest.mark.parametrize("edits,expected", [case[1:] for case in MANIFEST_CASES], ids=[c[0] for c in MANIFEST_CASES])
def test_a_manifest_the_app_refuses_is_explained_in_plain_words(tmp_path, edits, expected):
    reason = reason_of(tmp_path, edits=edits)
    assert expected in reason
    assert problems(reason) == []
    for jargon in ("validation error", "pydantic", "[type=", "input_value", "Value error"):
        assert jargon not in reason


REGISTRATION_CASES = [
    ("ids registered but not declared", update("provides", ops=[]), "registered ops does not match"),
    ("a handler without its event", update(None, subscribes=[]), "events it registers handlers for don't match"),
    (
        "interfaces defined but not registered",
        update("interfaces", defines=["scratch/shape"]),
        "to define don't match the ones it says it defines",
    ),
    (
        "interfaces provided but not registered",
        update("interfaces", provides=["scratch/shape@1"]),
        "to provide don't match the ones it says it provides",
    ),
    ("a data folder that is missing", update("provides", data="nowhere"), "that this add-on ships is missing"),
    ("a plugin that needs one that isn't there", update(None, depends_on=[{"name": "gone", "version": ">=1"}]), "gone"),
    ("something this version doesn't offer", update("provides", playbook="playbook"), "doesn't provide yet"),
    ("an event no interface gives", update(None, subscribes=["nonsense.event"]), "unsupported event subscription"),
    (
        "a program that is listed twice",
        update("requires", tools=[{"name": "t", "min_version": "", "probe": "t --version"}] * 2),
        "same program more than once",
    ),
]


@pytest.mark.parametrize(
    "edits,expected", [case[1:] for case in REGISTRATION_CASES], ids=[c[0] for c in REGISTRATION_CASES]
)
def test_a_registration_the_app_refuses_is_explained_in_plain_words(tmp_path, edits, expected):
    reason = reason_of(tmp_path, edits=edits)
    assert expected in reason
    assert problems(reason) == []


def test_a_setting_without_a_description_is_explained_in_plain_words(tmp_path):
    reason = reason_of(
        tmp_path,
        settings=lambda code: code.replace(
            "class Config(Settings):", "class Config(Settings):\n    bare: str = 'x'", 1
        ),
    )
    assert "the setting bare needs a default and a description" in reason
    assert problems(reason) == []


def test_a_data_form_with_a_pattern_the_app_refuses_is_explained_in_plain_words(tmp_path):
    def add_form(code: str) -> str:
        form = "    registrar.data_form('scratch/form', label='Form', folder='forms', schema=Config, pattern='x.txt')\n"
        return code.replace(
            "def register(registrar: Registrar) -> None:\n", "def register(registrar: Registrar) -> None:\n" + form, 1
        )

    reason = reason_of(tmp_path, settings=add_form)
    assert "pattern names YAML files" in reason
    assert problems(reason) == []


def test_a_settings_file_with_a_value_the_add_on_doesnt_have_is_explained_in_plain_words(tmp_path):
    make_plugin(tmp_path)
    folder = tmp_path / "config" / "plugins"
    folder.mkdir(parents=True)
    (folder / "scratch.yaml").write_text(yaml.safe_dump({"unknown": True, "ask_on_add": "not a switch"}))
    store = Store(tmp_path / "db", cfg=config(tmp_path, ["scratch"]))
    try:
        reason = store.plugins.status["scratch"].reason
    finally:
        store.close()
    assert "the setting 'unknown': isn't a setting it has" in reason
    assert "the setting 'ask_on_add'" in reason
    assert problems(reason) == []
    assert "Extra inputs" not in reason and "errors.pydantic" not in reason


def test_a_manifest_that_is_not_a_mapping_is_explained_in_plain_words(tmp_path):
    root = make_plugin(tmp_path)
    (root / "plugin.yaml").write_text("- just\n- a list\n")
    store = Store(tmp_path / "db", cfg=config(tmp_path, ["scratch"]))
    try:
        reason = store.plugins.status["scratch"].reason
    finally:
        store.close()
    assert problems(reason) == []
    assert "validation error" not in reason


# ---- every message an add-on author's mistake can raise -------------------------------------------------------------


def raised_messages(path: Path) -> list[tuple[int, str]]:
    """The text of every error raised with a literal message in a file; a placeholder in it becomes a short word."""
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args):
            continue
        arg = node.exc.args[0]
        if isinstance(arg, ast.JoinedStr):
            found.append((node.lineno, "".join(v.value if isinstance(v, ast.Constant) else "x" for v in arg.values)))
        elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            found.append((node.lineno, arg.value))
    return found


@pytest.mark.parametrize(
    "name", ["engine/plugin_host.py", "engine/plugin_manifest.py", "engine/plugin_api/__init__.py"]
)
def test_no_error_an_add_on_can_raise_names_the_insides_of_the_product(name):
    leaks = {(line, text): problems(text) for line, text in raised_messages(ROOT / name) if problems(text)}
    assert leaks == {}, name


def test_the_bundled_example_still_loads_so_the_cases_above_start_from_a_good_add_on(tmp_path):
    make_plugin(tmp_path)
    store = Store(tmp_path / "db", cfg=config(tmp_path, ["scratch"]))
    try:
        assert store.plugins.active("scratch")
        assert (BUNDLED / "example" / "plugin.yaml").is_file()
    finally:
        store.close()
