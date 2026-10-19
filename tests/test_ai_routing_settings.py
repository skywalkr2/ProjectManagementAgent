"""Which model does what, from Settings: the tier of a kind of work, a tier's second try, and the routing rules are
saved by the general settings save, validated against the schema, taken in at once, and read by the router."""

import pytest
import yaml

from engine.ai.router import route
from engine.config import load_config
from engine.tasks import TASKS
from tests.test_setup import client, make


def _saved(c, api, changes=None, reset=None):
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    return c.post(f"{api}/settings", json={"changes": changes or {}, "reset": reset or [], "fingerprint": fingerprint})


def _ai(ws):
    return yaml.safe_load((ws.config_dir / "ai.yaml").read_text(encoding="utf-8"))


# ---- a kind of work's tier -----------------------------------------------------------------------------------------


def test_a_kind_of_work_is_given_another_tier_and_the_file_and_the_loaded_config_say_so(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    done = _saved(c, api, {"ai.tasks.notes.tier": "deep"})
    assert done.status_code == 200, done.text
    [change] = done.json()["changes"]
    assert change["key"] == "ai.tasks.notes.tier" and change["before"] == "routine" and change["after"] == "deep"
    assert _ai(ws)["tasks"]["notes"]["tier"] == "deep"
    assert _ai(ws)["tasks"]["notes"]["max_output"] == 3000  # what else the entry held stays
    loaded = load_config(ws.config_dir, env={})
    assert loaded.ai.tasks["notes"].tier == "deep"
    assert done.json()["needs_restart"] is False  # read at the moment of use


def test_a_kind_of_work_with_no_entry_yet_gets_one(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    done = _saved(c, api, {"ai.tasks.sort-mail.tier": "deep"})
    assert done.status_code == 200, done.text
    assert _ai(ws)["tasks"]["sort-mail"]["tier"] == "deep"
    assert load_config(ws.config_dir, env={}).ai.tasks["sort-mail"].tier == "deep"


def test_a_kind_of_work_can_only_be_put_on_a_tier_that_exists(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    before = (ws.config_dir / "ai.yaml").read_text(encoding="utf-8")
    refused = _saved(c, api, {"ai.tasks.notes.tier": "nowhere"})
    assert refused.status_code == 400 and "nowhere" in refused.json()["detail"]
    assert (ws.config_dir / "ai.yaml").read_text(encoding="utf-8") == before


def test_a_kind_of_work_goes_back_to_what_it_was_with_a_reset(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    _saved(c, api, {"ai.tasks.sort-mail.tier": "deep"})
    back = _saved(c, api, reset=["ai.tasks.sort-mail.tier"])
    assert back.status_code == 200, back.text
    assert back.json()["changes"][0]["is_default"] is True
    assert "tier" not in (_ai(ws)["tasks"].get("sort-mail") or {})


def test_the_screens_may_change_a_tasks_tier_but_not_its_other_settings(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    for key in ("ai.tasks.notes.max_output", "ai.tasks.notes", "ai.tasks"):
        refused = _saved(c, api, {key: 5})
        assert refused.status_code == 400, key


# ---- a tier's second try -------------------------------------------------------------------------------------------


def test_a_tiers_second_try_is_chosen_and_taken_away(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    off = _saved(c, api, reset=["ai.tiers.routine.escalate_to"])
    assert off.status_code == 200, off.text
    assert "escalate_to" not in _ai(ws)["tiers"]["routine"]
    assert load_config(ws.config_dir, env={}).ai.tiers["routine"].escalate_to is None
    on = _saved(c, api, {"ai.tiers.routine.escalate_to": "deep"})
    assert on.status_code == 200, on.text
    assert load_config(ws.config_dir, env={}).ai.tiers["routine"].escalate_to == "deep"
    assert _ai(ws)["tiers"]["routine"]["use"] == "stub/default"  # the account is untouched


def test_a_second_try_must_name_a_tier_that_exists(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    before = (ws.config_dir / "ai.yaml").read_text(encoding="utf-8")
    refused = _saved(c, api, {"ai.tiers.routine.escalate_to": "nowhere"})
    assert refused.status_code == 400 and "nowhere" in refused.json()["detail"]
    assert (ws.config_dir / "ai.yaml").read_text(encoding="utf-8") == before


# ---- the routing rules ---------------------------------------------------------------------------------------------

RULES = [
    {"when": {"task": "notes", "input_chars_over": 20000}, "tier": "deep"},
    {"when": {"data_level": "restricted"}, "tier": "deep"},
]


def test_routing_rules_saved_from_the_screen_make_the_router_choose_the_stronger_tier(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    _saved(c, api, {"ai.routing": []})
    loaded = load_config(ws.config_dir, env={})
    assert route(loaded, "notes", input_chars=30000, quoted_messages=0, data_level="internal") == "routine"
    done = _saved(c, api, {"ai.routing": RULES})
    assert done.status_code == 200, done.text
    [change] = done.json()["changes"]
    assert change["key"] == "ai.routing" and change["before"] == [] and len(change["after"]) == 2
    assert done.json()["needs_restart"] is False
    assert _ai(ws)["routing"] == RULES
    loaded = load_config(ws.config_dir, env={})
    assert route(loaded, "notes", input_chars=30000, quoted_messages=0, data_level="internal") == "deep"
    assert route(loaded, "notes", input_chars=100, quoted_messages=0, data_level="internal") == "routine"
    assert route(loaded, "ask", input_chars=100, quoted_messages=0, data_level="restricted") == "deep"  # second rule


def test_the_rules_the_demo_workspace_ships_come_back_as_the_screen_saw_them(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    seen = next(i for i in c.get(f"{api}/settings").json()["items"] if i["key"] == "ai.routing")
    assert seen["value"] == [
        {
            "when": {"task": "notes", "quoted_messages_over": 3, "input_chars_over": None, "data_level": None},
            "tier": "deep",
        }
    ]
    done = _saved(c, api, {"ai.routing": seen["value"]})
    assert done.status_code == 200, done.text  # what the screen read is accepted back as it is


def test_a_rule_naming_a_tier_that_does_not_exist_or_a_wrong_level_is_refused_and_nothing_is_written(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    before = (ws.config_dir / "ai.yaml").read_text(encoding="utf-8")
    refused = _saved(c, api, {"ai.routing": [{"when": {}, "tier": "nowhere"}]})
    assert refused.status_code == 400 and "nowhere" in refused.json()["detail"]
    for rule in (
        {"when": {"data_level": "secret"}, "tier": "deep"},
        {"when": {"input_chars_over": -1}, "tier": "deep"},
    ):
        assert _saved(c, api, {"ai.routing": [rule]}).status_code == 400
    assert _saved(c, api, {"ai.routing": "deep"}).status_code == 400
    assert (ws.config_dir / "ai.yaml").read_text(encoding="utf-8") == before


def test_saving_rules_and_putting_them_back_with_undo(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    done = _saved(c, api, {"ai.routing": RULES}).json()
    undone = c.post(
        f"{api}/settings",
        json={
            "changes": {x["key"]: x["before"] for x in done["changes"]},
            "reset": [],
            "fingerprint": done["fingerprint"],
        },
    )
    assert undone.status_code == 200, undone.text
    assert [r.tier for r in load_config(ws.config_dir, env={}).ai.routing] == ["deep"]  # the shipped rule is back


def test_a_rule_set_by_an_environment_variable_is_not_changed_from_the_screen(tmp_path, monkeypatch):
    env = {"COCKPIT__AI__ROUTING": '[{"when": {"task": "ask"}, "tier": "deep"}]'}
    monkeypatch.setenv("COCKPIT__AI__ROUTING", env["COCKPIT__AI__ROUTING"])
    ws, cfg, store = make(tmp_path, env=env)
    c, api = client(ws, cfg, store)
    view = c.get(f"{api}/ai/routing").json()
    assert view["rules_source"] == "env"
    refused = _saved(c, api, {"ai.routing": []})
    assert refused.status_code == 400 and "environment variable" in refused.json()["detail"]


# ---- the screen's own view -----------------------------------------------------------------------------------------


def test_the_view_lists_each_kind_of_work_with_the_tier_it_uses_and_the_tiers_with_their_accounts(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    view = c.get(f"{api}/ai/routing").json()
    kinds = {k["name"]: k for k in view["kinds"]}
    assert set(TASKS) <= set(kinds) and "example/capture" in kinds  # the core's and an enabled add-on's
    assert kinds["notes"]["tier"] == "routine" and kinds["notes"]["custom"] is True  # the workspace sets it
    assert kinds["learn-correction"]["tier"] == "deep" and kinds["learn-correction"]["custom"] is False
    assert kinds["learn-correction"]["label"] and kinds["example/capture"]["label"] == "Capture"
    tiers = {t["name"]: t for t in view["tiers"]}
    assert tiers["routine"]["account"] == "stub" and tiers["routine"]["escalate_to"] == "deep"
    assert tiers["deep"]["escalate_to"] is None
    assert view["confirm_above_usd"] == cfg.ai.budgets.confirm_above_usd
    assert view["per_run_usd"] == cfg.ai.budgets.per_run_usd
    assert [r["tier"] for r in view["rules"]] == ["deep"] and view["rules"][0]["task"] == "notes"


def test_the_view_shows_the_tier_a_change_made_and_what_the_default_would_be(tmp_path):
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    _saved(c, api, {"ai.tasks.sort-mail.tier": "deep"})
    kinds = {k["name"]: k for k in c.get(f"{api}/ai/routing").json()["kinds"]}
    assert kinds["sort-mail"]["tier"] == "deep" and kinds["sort-mail"]["custom"] is True
    assert kinds["sort-mail"]["default_tier"] == "routine"


# ---- reaching the running app --------------------------------------------------------------------------------------


def test_a_saved_rule_and_a_changed_tier_reach_the_running_worker_without_a_restart(tmp_path):
    from engine.worker import Events, Worker

    ws, cfg, store = make(tmp_path)
    worker = Worker(ws, store, cfg, Events(), on_restart=lambda: None)
    try:
        text = (ws.config_dir / "ai.yaml").read_text(encoding="utf-8")
        from engine.config.yaml_edit import set_key

        text = set_key(text, ["routing"], RULES)
        (ws.config_dir / "ai.yaml").write_text(set_key(text, ["tasks", "ask", "tier"], "deep"), encoding="utf-8")
        assert worker.needs_restart() is False and worker.restart_for == []
        assert route(cfg, "notes", input_chars=30000, quoted_messages=0, data_level="internal") == "deep"
        assert cfg.ai.tasks["ask"].tier == "deep"
    finally:
        store.close()


def test_only_a_change_of_who_takes_the_work_lets_paused_work_try_again_at_once(tmp_path):
    """A second try comes only after a first try, so changing it lifts nothing; a change of an account, of the accounts
    of a tier, of the tier a kind of work uses or of the routing rules does."""
    from engine.config.yaml_edit import set_key
    from engine.worker import Events, Worker

    ws, cfg, store = make(tmp_path)
    worker = Worker(ws, store, cfg, Events(), on_restart=lambda: None)
    lifted = []
    import engine.worker as module

    original = module.release_paused
    module.release_paused = lambda s: lifted.append(True) or 0
    try:

        def change(path, value):
            text = (ws.config_dir / "ai.yaml").read_text(encoding="utf-8")
            (ws.config_dir / "ai.yaml").write_text(set_key(text, path, value), encoding="utf-8")
            assert worker.apply_live() is True

        change(["tiers", "deep", "escalate_to"], "routine")
        assert lifted == []
        change(["tasks", "notes", "max_output"], 2500)
        assert lifted == []
        change(["tasks", "ask", "tier"], "deep")
        assert len(lifted) == 1
        change(["routing"], RULES)
        assert len(lifted) == 2
        change(["tiers", "deep", "use"], "stub/other")
        assert len(lifted) == 3
    finally:
        module.release_paused = original
        store.close()


@pytest.mark.parametrize("key", ["ai.routing", "ai.tasks.ask.tier", "ai.tiers.routine.escalate_to"])
def test_these_keys_are_read_at_the_moment_of_use(key):
    from engine.worker import is_live

    assert is_live(key)


# ---- what the measurements say -------------------------------------------------------------------------------------


def _measured(ws, models, today=None):
    """Write the capability matrix: for each model ("account/model id"), its entries by skill as (runs, passes, cost of
    the passing runs, last day)."""
    import json
    from datetime import UTC, datetime

    last = (today or datetime.now(UTC).date()).isoformat()
    held = {
        ref: {
            skill: {"runs": runs, "passes": passes, "cost_passing_usd": cost, "last": day or last, "sets": {}}
            for skill, (runs, passes, cost, day) in entries.items()
        }
        for ref, entries in models.items()
    }
    ws.private_dir.mkdir(parents=True, exist_ok=True)
    (ws.private_dir / "ai-skills.json").write_text(json.dumps({"version": 1, "models": held}), encoding="utf-8")


def _two_models(ws):
    """The workspace with a second account for the deep tier, so two models can be told apart."""
    path = ws.config_dir / "ai.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["providers"]["strong"] = {
        "adapter": "stub",
        "models": {"default": "scripted-strong"},
        "allowed_data": ["open", "internal", "restricted"],
    }
    data["tiers"]["deep"]["use"] = "strong/default"
    data["routing"] = []
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _needed(ws, kind="notes"):
    from engine.ai import matrix
    from engine.shipped import DEMOS, demo

    found = []
    for name in DEMOS:
        found += [s for s in matrix.skills_by_kind(demo(name), ws.root).get(kind, []) if s not in found]
    return found


def _all(ws, runs, passes, cost, kind="notes", day=None):
    return {skill: (runs, passes, cost, day) for skill in _needed(ws, kind)}


def test_the_cases_that_run_a_kind_of_work_say_which_skills_measure_it(tmp_path):
    ws, cfg, store = make(tmp_path)
    notes = _needed(ws)
    assert {"dates", "owners", "new-message-only"} <= set(notes)  # the core's cases run the note-reading kind
    assert _needed(ws, "example/capture") == ["structured-answers"]  # an add-on's case runs the kind it names
    assert _needed(ws, "sort-mail") == []  # nothing measures it


def test_nothing_measured_means_no_suggestion_and_says_so(tmp_path):
    ws, cfg, store = make(tmp_path)
    _two_models(ws)
    c, api = client(ws, cfg, store)
    view = c.get(f"{api}/ai/routing").json()
    kinds = {k["name"]: k for k in view["kinds"]}
    notes = kinds["notes"]
    assert notes["suggested_tier"] is None and notes["suggestion_why_not"] == "not_measured"
    assert {f["tier"]: f["status"] for f in notes["fits"]} == {"routine": "not_measured", "deep": "not_measured"}
    assert all(f["measured"] == 0 and f["runs"] == 0 for f in notes["fits"])
    assert kinds["sort-mail"]["suggestion_why_not"] == "no_cases"
    assert view["rule_suggestions"] == [] and view["min_score"] == cfg.ai.skills.min_score


def test_the_cheapest_model_that_passed_everything_is_suggested_with_the_counts_behind_it(tmp_path):
    ws, cfg, store = make(tmp_path)
    _two_models(ws)
    _measured(
        ws,
        {
            "stub/scripted": _all(ws, 5, 5, 0.50),  # 0.10 a passing run
            "strong/scripted-strong": _all(ws, 5, 5, 0.05),  # 0.01 a passing run
        },
    )
    c, api = client(ws, cfg, store)
    notes = {k["name"]: k for k in c.get(f"{api}/ai/routing").json()["kinds"]}["notes"]
    assert notes["tier"] == "routine" and notes["suggested_tier"] == "deep" and notes["suggestion_why_not"] is None
    fits = {f["tier"]: f for f in notes["fits"]}
    n = len(_needed(ws))
    assert (fits["deep"]["runs"], fits["deep"]["passes"], fits["deep"]["skills"], fits["deep"]["measured"]) == (
        5 * n,
        5 * n,
        n,
        n,
    )
    assert fits["deep"]["status"] == "ok" and fits["deep"]["cost_per_pass_usd"] == pytest.approx(0.01)
    assert fits["routine"]["cost_per_pass_usd"] == pytest.approx(0.10)


def test_a_cheaper_model_whose_results_are_stale_or_incomplete_is_not_suggested(tmp_path):
    from datetime import date, timedelta

    ws, cfg, store = make(tmp_path)
    _two_models(ws)
    old = date.today() - timedelta(days=cfg.ai.skills.stale_days + 5)
    _measured(
        ws,
        {"stub/scripted": _all(ws, 5, 5, 0.50), "strong/scripted-strong": _all(ws, 5, 5, 0.05, day=old.isoformat())},
    )
    c, api = client(ws, cfg, store)
    notes = {k["name"]: k for k in c.get(f"{api}/ai/routing").json()["kinds"]}["notes"]
    fits = {f["tier"]: f for f in notes["fits"]}
    assert fits["deep"]["status"] == "stale" and fits["deep"]["stale"] == len(_needed(ws))
    assert notes["suggested_tier"] == "routine"  # the one in use passed; the cheaper one is only unknown
    partial = _all(ws, 5, 5, 0.05)
    partial.pop(next(iter(partial)))
    _measured(ws, {"stub/scripted": _all(ws, 5, 5, 0.50), "strong/scripted-strong": partial})
    notes = {k["name"]: k for k in c.get(f"{api}/ai/routing").json()["kinds"]}["notes"]
    assert {f["tier"]: f["status"] for f in notes["fits"]}["deep"] == "not_measured"
    assert notes["suggested_tier"] == "routine"


def test_a_models_low_score_is_never_a_pass(tmp_path):
    ws, cfg, store = make(tmp_path)
    _two_models(ws)
    _measured(ws, {"stub/scripted": _all(ws, 5, 1, 0.5), "strong/scripted-strong": _all(ws, 5, 2, 0.05)})
    c, api = client(ws, cfg, store)
    notes = {k["name"]: k for k in c.get(f"{api}/ai/routing").json()["kinds"]}["notes"]
    assert notes["suggested_tier"] is None and notes["suggestion_why_not"] == "none_passes"
    assert {f["tier"]: f["below"] for f in notes["fits"]} == {"routine": len(_needed(ws)), "deep": len(_needed(ws))}


def test_an_addons_kind_of_work_is_judged_on_the_skills_its_own_cases_name(tmp_path):
    ws, cfg, store = make(tmp_path)
    _two_models(ws)
    _measured(
        ws,
        {
            "stub/scripted": _all(ws, 4, 4, 0.40, kind="example/capture"),
            "strong/scripted-strong": _all(ws, 4, 4, 0.04, kind="example/capture"),
        },
    )
    c, api = client(ws, cfg, store)
    capture = {k["name"]: k for k in c.get(f"{api}/ai/routing").json()["kinds"]}["example/capture"]
    assert capture["suggested_tier"] == "deep" and {f["tier"]: f["skills"] for f in capture["fits"]} == {
        "routine": 1,
        "deep": 1,
    }


def test_a_rule_is_suggested_where_the_model_in_use_is_under_the_minimum_and_a_stronger_one_passes(tmp_path):
    ws, cfg, store = make(tmp_path)
    _two_models(ws)
    weak = _all(ws, 5, 5, 0.5)
    weak["new-message-only"] = (5, 1, 0.1, None)
    _measured(ws, {"stub/scripted": weak, "strong/scripted-strong": _all(ws, 5, 5, 0.5)})
    c, api = client(ws, cfg, store)
    [suggested] = c.get(f"{api}/ai/routing").json()["rule_suggestions"]
    assert suggested["rule"] == {
        "task": "notes",
        "tier": "deep",
        "input_chars_over": None,
        "quoted_messages_over": 3,
        "data_level": None,
    }
    assert suggested["skills"] == ["Acting on the new message"]
    # Added from the screen it is an ordinary save, and then it is no longer suggested.
    rule = {"when": {"task": "notes", "quoted_messages_over": 3}, "tier": "deep"}
    assert _saved(c, api, {"ai.routing": [rule]}).status_code == 200
    assert c.get(f"{api}/ai/routing").json()["rule_suggestions"] == []
