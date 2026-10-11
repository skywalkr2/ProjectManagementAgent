"""Plugin API 0.3.29: lints that know the run, skip the person's own changes and honor per-project severities; an
action clock; requests about records a proposal creates; handler requests refused one at a time; staged ops that say
where they came from; note levels and candidate records; plugin help for asks; setup steps that suggest settings; and
agent accounts with a fresh home folder."""

import json
import sys

import yaml

from engine.ai.adapters.stub import set_responder
from tests.test_today_panels_jobs import FIXTURE, MANIFEST, goals, workspace


def with_manifest(ws, **provides):
    path = ws.root / "plugins" / "p18" / "plugin.yaml"
    manifest = yaml.safe_load(path.read_text())
    for key, value in provides.items():
        manifest["provides"][key] = value
    path.write_text(yaml.safe_dump(manifest))


def reopen(ws, cfg):
    from engine.config import load_config
    from engine.storage import Store

    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p18"), store.plugins.status["p18"].reason
    return cfg, store


# ---- lints -----------------------------------------------------------------------------------------------------------

LINTED = FIXTURE.replace(
    "def register(registrar):\n",
    "SEEN = []\n\n"
    "def shouty(op, view, settings, origin):\n"
    "    SEEN.append(origin)\n"
    "    return [LintFinding('Too loud.')] if op.title.isupper() else []\n\n"
    "def register(registrar):\n"
    '    registrar.lint("p18/shouty", shouty, ops=("p18/add-goal",), severity="warn")\n',
).replace("TodayLine\n", "TodayLine, LintFinding\n")


def test_lints_get_the_runs_origin_and_skip_the_persons_own_changes(tmp_path):
    from engine.applier import Context, Inputs, check
    from engine.names import People
    from engine.ops import CHANGESET

    ws, cfg, store = workspace(tmp_path, LINTED)
    store.close()
    with_manifest(ws, lints=["p18/shouty"])
    cfg, store = reopen(ws, cfg)
    try:
        cs = CHANGESET.validate_python(
            {"summary": "x", "ops": [{"op": "p18/add-goal", "title": "LOUD"}]}, context={"op_models": store.plugins.ops}
        )
        people = People(store, cfg)
        assistant = Context(store, cfg, people, tuple(store.plugins.ops), Inputs("", None, "", "", "untrusted"))
        found = [p for p in check(cs, assistant) if p.check == "p18/shouty"]
        assert found and found[0].severity == "warn"
        seen = next(m for n, m in sys.modules.items() if n.endswith(".fixture") and hasattr(m, "SEEN")).SEEN
        assert seen[-1]["actor"] == "assistant"
        person = Context(store, cfg, people, tuple(store.plugins.ops), Inputs("", None, "", "", "trusted"), actor="pm")
        assert not [p for p in check(cs, person) if p.check == "p18/shouty"]
    finally:
        store.close()


def test_a_lint_switched_off_is_not_called_and_a_project_can_switch_one_off(tmp_path):
    from engine.applier import Context, Inputs, apply_as_person, check
    from engine.names import People
    from engine.ops import CHANGESET

    ws, cfg, store = workspace(tmp_path, LINTED.replace('ops=("p18/add-goal",)', 'ops=("note",)'))
    store.close()
    with_manifest(ws, lints=["p18/shouty"])
    cfg, store = reopen(ws, cfg)
    try:
        apply_as_person(store, cfg, [{"op": "project.add", "name": "Quiet work"}], "A project")
        project = [p for p in store.read().list("project") if p.data["name"] == "Quiet work"][0]
        checks = yaml.safe_load((ws.config_dir / "checks.yaml").read_text())
        checks["projects"] = {project.id: {"p18/shouty": "off"}}
        (ws.config_dir / "checks.yaml").write_text(yaml.safe_dump(checks))
        store.close()
        cfg, store = reopen(ws, cfg)
        seen = next(m for n, m in sys.modules.items() if n.endswith(".fixture") and hasattr(m, "SEEN")).SEEN
        before = len(seen)
        cs = CHANGESET.validate_python({"summary": "x", "ops": [{"op": "note", "text": "hi", "project": project.id}]})
        ctx = Context(store, cfg, People(store, cfg), ("note",), Inputs("", None, "", "", "untrusted"))
        check(cs, ctx)
        assert len(seen) == before  # off for this project: never called
    finally:
        store.close()


# ---- actions ---------------------------------------------------------------------------------------------------------

CREATING = FIXTURE.replace(
    "def close(target, context, choices):\n",
    "STAMPS = []\n\n"
    "def make_goals(target, context, choices):\n"
    "    STAMPS.append(context.today)\n"
    "    items = [Item('a', 'Add A', [{'op': 'p18/add-goal', 'title': 'A'}]),\n"
    "             Item('b', 'Add B', [{'op': 'p18/add-goal', 'title': 'B'}], kept=False)]\n"
    "    asks = [{'task': 'p18/plan', 'about': {'item': 'a'}}, {'task': 'p18/plan', 'about': {'item': 'b'}},\n"
    "            {'task': 'p18/plan', 'about': {'op': 0}}]\n"
    "    return Proposal('Add goals', ops=[{'op': 'p18/add-goal', 'title': 'Loose'}], items=items, requests=asks)\n\n"
    "def close(target, context, choices):\n",
).replace("TodayLine\n", "TodayLine, Item\n")
CREATING = CREATING.replace(
    '    registrar.action("p18/close", label="Close", run=close, on="p18/goal")\n',
    '    registrar.action("p18/close", label="Close", run=close, on="p18/goal")\n'
    '    registrar.action("p18/make", label="Make goals", run=make_goals)\n',
)


def test_requests_can_be_about_records_the_proposal_creates(tmp_path):
    from engine import actions

    ws, cfg, store = workspace(tmp_path, CREATING)
    store.close()
    with_manifest(ws, actions=["p18/close", "p18/make"])
    cfg, store = reopen(ws, cfg)
    try:
        pending = actions.preview(store, cfg, "p18/make")
        stamps = next(m for n, m in sys.modules.items() if n.endswith(".fixture") and hasattr(m, "STAMPS")).STAMPS
        assert stamps[-1] is not None
        actions.apply(store, cfg, pending.token, {})
        goals_by_title = {g.data["title"]: g.id for g in store.read().list("p18/goal")}
        planned = [r.data["about"]["id"] for r in store.read().list("request") if r.data["task"] == "p18/plan"]
        assert sorted(planned) == sorted([goals_by_title["A"], goals_by_title["Loose"]])  # B was dropped
    finally:
        store.close()


# ---- handlers --------------------------------------------------------------------------------------------------------

STAGING = FIXTURE.replace(
    "def tidy(context):\n",
    "def tidy(context):\n"
    '    for goal in context.list("p18/goal"):\n'
    '        context.queue_request("p18/plan", "Plan it", ("p18/goal", "GOL-999"))\n'
    '        context.queue_request("p18/plan", "Plan it", goal)\n'
    "    return\n",
)


def test_one_refused_request_is_skipped_and_the_rest_go_ahead(tmp_path):
    ws, cfg, store = workspace(tmp_path, STAGING)
    try:
        goals(cfg, store, "Finish the map")
        assert store.plugins.run_job("p18/tidy") == "ok"
        planned = [r for r in store.read().list("request") if r.data["task"] == "p18/plan"]
        assert len(planned) == 1
        assert any("was skipped" in n for n in store.plugins.status["p18"].notes)
    finally:
        store.close()


def test_staged_ops_say_they_came_from_a_job(tmp_path):
    marked = FIXTURE.replace(
        "def tidy(context):\n",
        "ORIGINS = []\n\n"
        "def watch(op, view, origin):\n"
        "    ORIGINS.append(origin)\n"
        "    return []\n\n"
        "def tidy(context):\n"
        '    context.apply_op({"op": "p18/add-goal", "title": "From a job"})\n'
        "    return\n",
    ).replace(
        "    registrar.job(",
        '    registrar.op_validator("p18/add-goal", watch)\n    registrar.job(',
    )
    ws, cfg, store = workspace(tmp_path, marked)
    store.close()
    with_manifest(ws, op_validators=["p18/add-goal"])
    cfg, store = reopen(ws, cfg)
    try:
        store.plugins.run_job("p18/tidy")
        origins = next(m for n, m in sys.modules.items() if n.endswith(".fixture") and hasattr(m, "ORIGINS")).ORIGINS
        assert origins[-1]["via"] == "job" and origins[-1]["actor"] == "plugin"
    finally:
        store.close()


# ---- setup steps that suggest settings -------------------------------------------------------------------------------


def test_a_setup_step_suggests_core_settings_the_person_applies(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from engine.config import load_config

    suggesting = FIXTURE.replace(
        "    registrar.job(",
        '    registrar.setup_step("p18/careful", label="Ask before every run", done=lambda v, s: False,\n'
        '                         settings={"ai.budgets.confirm_unpriced": True})\n'
        '    registrar.setup_step("p18/greedy", label="Take the accounts", done=lambda v, s: False,\n'
        '                         settings={"ai.tiers.routine.use": "x/y"})\n'
        "    registrar.job(",
    )
    ws, cfg, store = workspace(tmp_path, suggesting)
    store.close()
    with_manifest(ws, setup_steps=["p18/careful", "p18/greedy"])
    cfg, store = reopen(ws, cfg)
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    steps = {s["id"]: s for s in c.get(f"{api}/setup").json()["steps"]}
    assert steps["p18/careful"]["settings"] == {"ai.budgets.confirm_unpriced": True}
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    done = c.post(f"{api}/setup/p18/careful/apply-settings", json={"fingerprint": fingerprint})
    assert done.status_code == 200, done.text
    assert load_config(ws.config_dir, env={}).ai.budgets.confirm_unpriced is True
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    refused = c.post(f"{api}/setup/p18/greedy/apply-settings", json={"fingerprint": fingerprint})
    assert refused.status_code == 400


# ---- help for asks ---------------------------------------------------------------------------------------------------


def test_a_plugins_help_is_material_for_asks(tmp_path):
    ws, cfg, store = workspace(tmp_path)
    store.close()
    folder = ws.root / "plugins" / "p18"
    (folder / "help.md").write_text("# Goals help\n\n## Closing goals\n\nA closed goal stays in the list as done.\n")
    path = folder / "plugin.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["provides"]["help"] = ["help.md"]
    path.write_text(yaml.safe_dump(manifest))
    cfg, store = reopen(ws, cfg)
    try:
        from engine.help import chosen_sections, guide_sections

        sections = [*guide_sections(), *store.plugins.help_sections()]
        assert chosen_sections("What happens when I close a goal?", sections=sections)[0].title == "p18: Closing goals"
    finally:
        store.close()


# ---- note levels -----------------------------------------------------------------------------------------------------


def test_a_note_never_feeds_records_more_sensitive_than_it_is(tmp_path):
    from engine.dispatcher import ops_for_level

    secret = FIXTURE.replace(
        'record_kind: ClassVar[str] = "p18/goal"',
        'record_kind: ClassVar[str] = "p18/goal"\n    data_level: ClassVar[str] = "restricted"',
    ).replace('registrar.op(AddGoal, "data", add_goal)', 'registrar.op(AddGoal, "data", add_goal, notes=True)')
    manifest = {**MANIFEST, "requires": {"data_levels": ["open", "internal", "restricted"]}}
    ws, cfg, store = workspace(tmp_path, secret)
    store.close()
    (ws.root / "plugins" / "p18" / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    cfg, store = reopen(ws, cfg)
    try:
        notes = store.plugins.task_kind("notes").ops
        assert "p18/add-goal" in notes
        assert "p18/add-goal" not in ops_for_level(store, notes, "internal")
        assert "p18/add-goal" in ops_for_level(store, notes, "restricted")
    finally:
        store.close()


# ---- agent accounts with a fresh home --------------------------------------------------------------------------------

AGENT = r"""
import os, sys
mode = sys.argv[1]
prompt = sys.stdin.read()
if mode == "home":
    print(os.environ["HOME"])
    print(sorted(os.listdir(os.environ["HOME"])))
elif mode == "probe":
    open(os.path.join(os.environ["HOME"], ".cockpit-memory-probe"), "w").write("ok")
"""


def test_an_agent_can_run_with_a_fresh_home_and_only_its_sign_in(tmp_path, monkeypatch):
    from engine.ai.adapters.cli_agent import CliAgentAdapter
    from engine.ai.task import AiTask
    from engine.config.schema import AgentSettings, ProviderSettings

    home = tmp_path / "home"
    (home / ".agent").mkdir(parents=True)
    (home / ".agent" / "sign-in").write_text("token")
    (home / "notes-from-last-run").write_text("memory")
    monkeypatch.setenv("HOME", str(home))
    script = tmp_path / "agent.py"
    script.write_text(AGENT)

    def account(mode):
        agent = AgentSettings(command=[sys.executable, str(script), mode], home="fresh", home_files=[".agent"])
        return CliAgentAdapter(ProviderSettings(adapter=CliAgentAdapter.name, timeout_seconds=10, agent=agent))

    out = account("home").run(AiTask("notes", "", "", "x", {}, output="text"), "m").text.splitlines()
    assert out[0] != str(home) and json.loads(out[1].replace("'", '"')) == [".agent"]
    checks = {c.name: c for c in account("probe").lockdown_test("m")}
    assert checks["memory"].ok and not (home / ".cockpit-memory-probe").exists()
    set_responder(None)


# ---- interface items -------------------------------------------------------------------------------------------------


def test_about_gets_the_task_and_a_user_can_check_before_requesting(tmp_path):
    from tests import test_interfaces as interfaces
    from tests import test_plugin_api_0323 as earlier

    provider = earlier.ITEM_PROVIDER.replace(
        '        about=lambda view, settings, item: ("p17/work", item["ref"]),\n',
        '        about=lambda view, settings, item, task: ("p17/work", item["ref"]) if task == "polish" else None,\n',
    )
    original = earlier.ITEM_PROVIDER
    earlier.ITEM_PROVIDER = provider
    try:
        ws, cfg, store = earlier.item_workspace(tmp_path)
    finally:
        earlier.ITEM_PROVIDER = original
    try:
        project = interfaces.a_project(cfg, store)
        interfaces.apply(cfg, store, [{"op": "p17/add-work", "project": project.id, "title": "Harbor map"}])
        work = store.read().list("p17/work")[-1]
        item = store.plugins.read_interface("p16", "p16/source@1")[0]
        assert store.plugins.interface_about("p16", item, "polish") == ("p17/work", work.id)
        assert store.plugins.interface_about("p16", item, "blurb") is None
    finally:
        store.close()
