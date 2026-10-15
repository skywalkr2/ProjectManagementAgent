"""A plugin's own evaluation cases and scorers (design 3.3, 6.16): the folder a manifest names runs beside the core's
cases for each enabled plugin, a scorer the plugin registers judges its own ops, and one that fails fails its case
alone."""

import shutil

import pytest
import yaml

import engine.evaluate as ev
from engine.evaluate import evaluate, load_cases, load_pack_cases
from tests.conftest import DEMO_B

SCORER_OK = """
def judge(case, produced, view):
    return [] if produced == [] else ["something was produced"]
"""
SCORER_CRASHES = """
def judge(case, produced, view):
    raise RuntimeError("the scorer broke")
"""
SCORER_NOT_TEXT = """
def judge(case, produced, view):
    return [1]
"""


def make_pack(workspace, scorer_source, cases, *, listed=("probe/judge",)):
    """A plugin named `probe` in the workspace's own plugins folder, with one scorer and these cases, enabled."""
    root = workspace / "plugins" / "probe"
    (root / "evals").mkdir(parents=True)
    manifest = {
        "name": "probe",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "A pack that only brings its own cases.",
        "provides": {"scorers": list(listed), "evals": "evals"},
        "config_schema": "probe:Config",
        "entry": "probe:register",
    }
    (root / "plugin.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    (root / "__init__.py").write_text(
        "from engine.plugin_api import Settings\n\n\nclass Config(Settings):\n    pass\n"
        + scorer_source
        + "\n\ndef register(registrar):\n    registrar.scorer('probe/judge', judge)\n",
        encoding="utf-8",
    )
    for name, case in cases.items():
        (root / "evals" / f"{name}.yaml").write_text(yaml.safe_dump(case), encoding="utf-8")
    settings = workspace / "config" / "workspace.yaml"
    raw = yaml.safe_load(settings.read_text())
    raw["plugins"]["enabled"] = [*raw["plugins"]["enabled"], "probe"]
    settings.write_text(yaml.safe_dump(raw))


def a_case(**more):
    return {
        "id": "probe/nothing-to-record",
        "title": "Nothing to record",
        "received": "2026-10-14",
        "pasted": "A short line that holds nothing anyone has to do.",
        "score": "probe/judge",
        "stub_answer": {"summary": "Nothing to record.", "ops": []},
        **more,
    }


@pytest.fixture
def workspace(tmp_path):
    target = tmp_path / "ws"
    shutil.copytree(DEMO_B, target)
    return target


def run_pack(workspace, **kwargs):
    return evaluate(workspace, stub=True, runs=1, env={}, only=kwargs.pop("only", ["probe/nothing-to-record"]))


def test_a_packs_case_runs_and_its_scorer_decides(workspace):
    make_pack(workspace, SCORER_OK, {"nothing": a_case()})
    assert run_pack(workspace).results[0].passed
    produced = a_case(stub_answer={"summary": "A note.", "ops": [{"op": "note", "text": "Something."}]})
    (workspace / "plugins" / "probe" / "evals" / "nothing.yaml").write_text(yaml.safe_dump(produced), encoding="utf-8")
    # A note is the core's to score (never extra); the scorer sees only the plugin's own ops, so it still passes.
    assert run_pack(workspace).results[0].passed


def test_the_example_plugins_case_runs_with_its_scorer_and_a_wrong_word_fails_it(monkeypatch):
    cases = load_pack_cases(DEMO_B)
    if not any(c["id"] == "example/capture-reminder" for c in cases):
        pytest.skip("the example plugin is not enabled in this fixture run")
    assert evaluate(DEMO_B, stub=True, runs=1, env={}, only=["example/capture-reminder"]).results[0].passed
    monkeypatch.setattr(
        ev, "load_pack_cases", lambda w: [{**c, "words": [*c["words"], "zebra"]} for c in load_pack_cases(w)]
    )
    failed = evaluate(DEMO_B, stub=True, runs=1, env={}, only=["example/capture-reminder"]).results[0]
    assert not failed.passed and failed.missing == ["no reminder mentions zebra"]


@pytest.mark.parametrize("source", [SCORER_CRASHES, SCORER_NOT_TEXT])
def test_a_scorer_that_fails_fails_its_case_and_nothing_else(workspace, source):
    make_pack(workspace, source, {"nothing": a_case()})
    core = load_cases(workspace)[0]["id"]
    report = evaluate(workspace, stub=True, runs=1, env={}, only=[core, "probe/nothing-to-record"])
    by_case = {r.case: r for r in report.results}
    assert by_case[core].passed
    assert not by_case["probe/nothing-to-record"].passed
    assert by_case["probe/nothing-to-record"].missing == ["the scorer probe/judge failed (" + type_of(source) + ")"]


def type_of(source):
    return "RuntimeError" if "RuntimeError" in source else "ValueError"


def test_a_case_that_expects_a_plugin_op_must_name_a_scorer(workspace):
    case = a_case(expect=[{"op": "probe/thing.add"}])
    del case["score"]
    make_pack(workspace, SCORER_OK, {"nothing": case})
    with pytest.raises(ValueError, match="needs score"):
        load_pack_cases(workspace)


def test_a_cases_id_task_and_scorer_must_belong_to_its_plugin(workspace):
    make_pack(workspace, SCORER_OK, {"nothing": a_case(id="nothing-to-record")})
    with pytest.raises(ValueError, match="probe/<name>"):
        load_pack_cases(workspace)
    make_pack_again = workspace / "plugins" / "probe" / "evals" / "nothing.yaml"
    make_pack_again.write_text(yaml.safe_dump(a_case(score="probe/other")), encoding="utf-8")
    with pytest.raises(ValueError, match="isn't a scorer the plugin lists"):
        load_pack_cases(workspace)
    make_pack_again.write_text(yaml.safe_dump(a_case(task="notes")), encoding="utf-8")
    with pytest.raises(ValueError, match="task kind of the plugin"):
        load_pack_cases(workspace)


def test_a_core_case_cannot_name_a_plugins_scorer(tmp_path):
    target = tmp_path / "ws"
    shutil.copytree(DEMO_B, target)
    first = sorted((target / "evals").glob("*.yaml"))[0]
    case = yaml.safe_load(first.read_text())
    if isinstance(case, list):
        pytest.skip("the first file is a shared starting state")
    first.write_text(yaml.safe_dump({**case, "score": "probe/judge"}), encoding="utf-8")
    with pytest.raises(ValueError, match="only the plugin's own cases"):
        load_cases(target)


def test_a_plugin_that_is_not_enabled_brings_no_cases(workspace):
    make_pack(workspace, SCORER_OK, {"nothing": a_case()})
    settings = workspace / "config" / "workspace.yaml"
    raw = yaml.safe_load(settings.read_text())
    raw["plugins"]["enabled"].remove("probe")
    settings.write_text(yaml.safe_dump(raw))
    assert not [c for c in load_pack_cases(workspace) if c["id"].startswith("probe/")]


def test_the_cases_of_the_plugins_in_another_workspace_run_on_the_templates_cases(workspace, tmp_path):
    other = tmp_path / "mine"
    shutil.copytree(DEMO_B, other)
    make_pack(other, SCORER_OK, {"nothing": a_case()})
    report = evaluate(workspace, stub=True, runs=1, env={}, only=["probe/nothing-to-record"], packs_of=other)
    assert [(r.passed, r.error, r.missing) for r in report.results] == [(True, None, [])]


def test_a_plugin_whose_scorers_are_not_the_ones_it_lists_does_not_start(workspace, tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    make_pack(workspace, SCORER_OK, {"nothing": a_case()}, listed=())
    ws = init_workspace(tmp_path / "started", template=workspace, git=False)
    store = Store(ws.db_path)
    try:
        status = store.plugins.status["probe"]
        assert status.state == "disabled" and "scorers" in status.reason
    finally:
        store.close()
