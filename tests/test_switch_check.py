"""The check that comes with a switch of a tier's account or model (design 6.16, 6.22): offered with its cost, run on
the new choice in the background, and a failure is a Today line with Switch back and Keep it. The cases and their
scoring are the real harness with the stand-in AI; only which cases run and which one is made to fail is set here."""

from __future__ import annotations

from copy import deepcopy

import pytest
import yaml
from fastapi.testclient import TestClient

import engine.evaluate as ev
from api.app import create_app
from engine.ai import switch_check
from engine.config import load_config
from engine.evaluate import Report, estimate_cases, evaluate, load_cases
from engine.storage import Store
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

REAL_ESTIMATE = switch_check.estimate

OTHER = "other"
CASES = ("close-action",)


def case_title(case_id):
    case = next(c for c in load_cases(DEMO_B) if c["id"] == case_id)
    return str(case.get("title") or case["id"])


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A workspace with two accounts, `stub` doing the work and `other` ready to take it, and a client on its app."""
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    path = ws.config_dir / "ai.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["providers"][OTHER] = {
        "adapter": "stub",
        "models": {"default": "other-a", "harder": "other-b"},
        "allowed_data": ["open", "internal", "restricted"],
    }
    raw["prices"] = {f"{OTHER}/default": {"input_per_million": 1.0, "output_per_million": 1.0}}
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    store.close()
    app = create_app(ws, cfg, "t", start_worker=False)
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer t"
    # The estimate prices a few real packets; its own test covers that, here it is a number.
    monkeypatch.setattr(switch_check, "estimate", lambda cfg, ws, ref, env=None, ai_config=None: (0.5, 40))
    return ws, app, client


def passing(account, cfg, ws, env):
    return evaluate(DEMO_B, stub=True, runs=1, env={}, only=list(CASES))


def failing_one(monkeypatch, case_id):
    """Evaluate the same cases, with one made to expect what nothing produces."""
    original = ev.load_cases

    def corrupted(template):
        return [
            {**c, "expect": [*c.get("expect", []), {"op": "action.add", "text_has": ["never-present"]}]}
            if c["id"] == case_id
            else c
            for c in original(template)
        ]

    monkeypatch.setattr(ev, "load_cases", corrupted)
    return passing


def api(client, ws):
    return load_config(ws.config_dir, env={}).server.base_path.rstrip("/") + "/api"


def fingerprint(client, ws):
    return client.get(f"{api(client, ws)}/settings").json()["fingerprint"]


def switch_body(client, ws, **more):
    return {"fingerprint": fingerprint(client, ws), "use": {"routine": "default", "deep": "harder"}, **more}


def used(ws):
    tiers = load_config(ws.config_dir, env={}).ai.tiers
    return {name: tier.use for name, tier in tiers.items()}


def today_lines(client, ws):
    return [x for x in client.get(f"{api(client, ws)}/today/queue").json() if x["kind"] == "switch_failed"]


def finish(app):
    thread = app.state.worker._switching
    if thread is not None:
        thread.join(timeout=60)
        assert not thread.is_alive()


def start_check(client, ws, app, evaluator, **more):
    switch_check_route = f"{api(client, ws)}/ai/accounts/{OTHER}/switch-check"
    mp = more.pop("monkeypatch")
    mp.setattr(switch_check, "evaluate_on", evaluator)
    done = client.post(switch_check_route, json=switch_body(client, ws, **more))
    assert done.status_code == 200, done.text
    finish(app)
    return done.json()


# ---- what is a switch ----------------------------------------------------------------------------


def test_only_a_tier_that_had_an_account_and_now_has_another_account_or_model_is_switching(env):
    ws, _app, _client = env
    before = load_config(ws.config_dir, env={})
    after = deepcopy(before)
    assert switch_check.switches(before, after) == []
    after.ai.tiers["routine"].use = f"{OTHER}/default"
    assert [(s.tier, s.after) for s in switch_check.switches(before, after)] == [("routine", f"{OTHER}/default")]
    again = deepcopy(before)
    short = again.ai.tiers["deep"].use.partition("/")[2]
    again.ai.providers["stub"].models[short] = "another-model-id"
    assert sorted(s.tier for s in switch_check.switches(before, again)) == ["deep", "routine"]
    fresh = deepcopy(before)
    fresh.ai.tiers["routine"].use = ""
    assert switch_check.switches(fresh, after) == [], "a tier that had no account is being set up, not switched"


# ---- offered with its cost -----------------------------------------------------------------------


def test_a_change_that_switches_is_offered_a_check_with_its_cost_and_one_that_does_not_is_not(env):
    ws, _app, client = env
    base = api(client, ws)
    offer = client.post(f"{base}/ai/accounts/{OTHER}/switch-estimate", json=switch_body(client, ws)).json()
    assert offer["offered"] is True and offer["usd"] == 0.5 * 2 and offer["cases"] == 40
    key = {"fingerprint": fingerprint(client, ws), "key_ref": "env:SOME_KEY"}
    assert client.post(f"{base}/ai/accounts/{OTHER}/switch-estimate", json=key).json()["offered"] is False


def test_the_offer_is_off_when_checks_on_a_switch_are_off(env):
    ws, _app, client = env
    base = api(client, ws)
    saved = client.post(
        f"{base}/settings",
        json={
            "changes": {"dispatch.knowledge.check_on_switch": False},
            "reset": [],
            "fingerprint": fingerprint(client, ws),
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["needs_restart"] is False, "the setting is read at the moment of use"
    offer = client.post(f"{base}/ai/accounts/{OTHER}/switch-estimate", json=switch_body(client, ws)).json()
    assert offer["offered"] is False


def test_the_estimate_prices_a_few_real_packets_and_scales_with_the_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "ESTIMATE_SAMPLE", 2)
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    path = ws.config_dir / "ai.yaml"
    path.write_text(
        path.read_text().replace(
            "prices: {}", "prices: {stub/default: {input_per_million: 100, output_per_million: 100}}"
        )
    )
    once, cases = estimate_cases(DEMO_B, account="stub/default", runs=1, ai_config=path, env={})
    twice, _ = estimate_cases(DEMO_B, account="stub/default", runs=2, ai_config=path, env={})
    assert once and once > 0 and twice == pytest.approx(once * 2)
    assert cases >= len(load_cases(DEMO_B))
    unpriced, _ = estimate_cases(DEMO_B, account="stub/default", runs=1, env={})
    assert unpriced is None, "a choice with no known price is estimated as none, never as free"


# ---- the person's path ---------------------------------------------------------------------------


def test_a_check_that_passes_keeps_the_switch_and_leaves_nothing_on_today(env, monkeypatch):
    ws, app, client = env
    done = start_check(client, ws, app, passing, monkeypatch=monkeypatch)
    assert done["checking"] is True
    assert used(ws) == {"routine": f"{OTHER}/default", "deep": f"{OTHER}/harder"}
    assert today_lines(client, ws) == []
    assert {t: e["state"] for t, e in switch_check.read(app.state.worker.store).items()} == {
        "routine": "passed",
        "deep": "passed",
    }


def test_a_check_that_fails_is_a_line_naming_what_failed_and_switch_back_restores_the_earlier_choice(env, monkeypatch):
    ws, app, client = env
    before = used(ws)
    start_check(client, ws, app, failing_one(monkeypatch, CASES[0]), monkeypatch=monkeypatch)
    assert used(ws) != before, "the switch is made at once; the check follows it"
    lines = today_lines(client, ws)
    assert {x["tier"] for x in lines} == {"routine", "deep"}
    line = next(x for x in lines if x["tier"] == "routine")
    assert (line["group"], line["account"], line["text"], line["count"]) == ("risk", OTHER, "stub", 1)
    assert line["names"] == [case_title(CASES[0])] and not line["check_failed"]
    base = api(client, ws)
    back = client.post(f"{base}/ai/switch/routine/back", json={"fingerprint": fingerprint(client, ws)})
    assert back.status_code == 200, back.text
    assert used(ws)["routine"] == before["routine"] and used(ws)["deep"] == f"{OTHER}/harder"
    assert [x["tier"] for x in today_lines(client, ws)] == ["deep"], "only the tier switched back is settled"


def test_keep_it_leaves_the_switch_and_clears_the_line(env, monkeypatch):
    ws, app, client = env
    start_check(client, ws, app, failing_one(monkeypatch, CASES[0]), monkeypatch=monkeypatch)
    now = used(ws)
    base = api(client, ws)
    assert client.post(f"{base}/ai/switch/routine/keep").status_code == 200
    assert client.post(f"{base}/ai/switch/deep/keep").status_code == 200
    assert today_lines(client, ws) == [] and used(ws) == now
    assert client.post(f"{base}/ai/switch/routine/keep").status_code == 404


def test_switch_without_checking_changes_it_at_once_and_runs_nothing(env, monkeypatch):
    ws, app, client = env
    ran = []
    monkeypatch.setattr(switch_check, "evaluate_on", lambda *a: ran.append(a))
    done = client.post(f"{api(client, ws)}/ai/accounts/{OTHER}", json=switch_body(client, ws))
    assert done.status_code == 200, done.text
    finish(app)
    assert used(ws) == {"routine": f"{OTHER}/default", "deep": f"{OTHER}/harder"}
    assert ran == [] and switch_check.read(app.state.worker.store) == {} and today_lines(client, ws) == []


def test_a_new_switch_supersedes_an_earlier_failed_one(env, monkeypatch):
    ws, app, client = env
    start_check(client, ws, app, failing_one(monkeypatch, CASES[0]), monkeypatch=monkeypatch)
    assert today_lines(client, ws)
    done = client.post(
        f"{api(client, ws)}/ai/accounts/stub",
        json={"fingerprint": fingerprint(client, ws), "use": {"routine": "default", "deep": "default"}},
    )
    assert done.status_code == 200, done.text
    assert today_lines(client, ws) == []


def test_a_change_of_a_used_accounts_model_is_a_switch_and_back_restores_the_model(env, monkeypatch):
    ws, app, client = env
    stub_models = dict(load_config(ws.config_dir, env={}).ai.providers["stub"].models)
    changed = {k: f"{v}-next" for k, v in stub_models.items()}
    route = f"{api(client, ws)}/ai/accounts/stub"
    offer = client.post(
        f"{route}/switch-estimate", json={"fingerprint": fingerprint(client, ws), "models": changed}
    ).json()
    assert offer["offered"] is True
    monkeypatch.setattr(switch_check, "evaluate_on", failing_one(monkeypatch, CASES[0]))
    done = client.post(f"{route}/switch-check", json={"fingerprint": fingerprint(client, ws), "models": changed})
    assert done.status_code == 200, done.text
    finish(app)
    assert load_config(ws.config_dir, env={}).ai.providers["stub"].models == changed
    assert today_lines(client, ws)
    back = client.post(f"{api(client, ws)}/ai/switch/routine/back", json={"fingerprint": fingerprint(client, ws)})
    assert back.status_code == 200, back.text
    assert load_config(ws.config_dir, env={}).ai.providers["stub"].models == stub_models


def test_a_check_that_cannot_finish_is_a_failed_line_never_a_pass(env, monkeypatch):
    ws, app, client = env

    def broken(account, cfg, ws, env):
        raise RuntimeError("the account went away")

    start_check(client, ws, app, broken, monkeypatch=monkeypatch)
    lines = today_lines(client, ws)
    assert lines and all(x["check_failed"] and x["names"] == [] for x in lines)


def test_a_check_cut_short_by_a_restart_runs_again_from_the_start(env, monkeypatch):
    ws, app, client = env
    worker = app.state.worker
    before = load_config(ws.config_dir, env={})
    after = deepcopy(before)
    after.ai.tiers["routine"].use = f"{OTHER}/default"
    switch_check.begin(worker.store, switch_check.switches(before, after), [], check=True)
    monkeypatch.setattr(switch_check, "evaluate_on", passing)
    thread = worker.check_switch_soon()
    assert thread is not None
    thread.join(timeout=60)
    assert switch_check.read(worker.store)["routine"]["state"] == "passed"
    assert worker.check_switch_soon() is None, "nothing waits any more"


def test_a_failed_line_waits_across_a_restart_because_it_is_kept_on_this_computer(env, monkeypatch):
    ws, app, client = env
    start_check(client, ws, app, failing_one(monkeypatch, CASES[0]), monkeypatch=monkeypatch)
    assert (ws.root / ".cockpit" / switch_check.STATE_FILE).is_file()
    fresh = Store(ws.db_path, cfg=ws.config(env={}))
    try:
        assert sorted(switch_check.failed(fresh)) == ["deep", "routine"]
    finally:
        fresh.close()


def test_a_check_is_a_report_of_the_same_cases_cockpit_evaluate_runs():
    report = evaluate(DEMO_B, stub=True, runs=1, env={}, only=list(CASES))
    assert isinstance(report, Report) and report.pass_rate() == 1.0


def test_the_check_runs_the_learning_pairs_with_the_cases_and_prices_them(env, monkeypatch):
    import engine.pairs as pairs
    from engine.evaluate import RunResult

    ws = env[0]
    cfg = load_config(ws.config_dir, env={})
    monkeypatch.setattr(ev, "evaluate", lambda *a, **k: Report("acct/m", 1, [RunResult("case-a", 1, True)]))
    monkeypatch.setattr(pairs, "evaluate_pairs", lambda *a, **k: Report("acct/m", 1, [RunResult("pair-b", 1, False)]))
    report = switch_check.evaluate_on("acct/m", cfg, ws, {})
    assert report.cases() == ["case-a", "pair-b"] and report.pass_rate() == 0.5
    first = pairs.load_pairs(switch_check._template())[0]
    assert switch_check.titles(ws)[first["id"]] == first["title"]
    monkeypatch.setattr(ev, "estimate_cases", lambda *a, **k: (1.0, 10))
    price, count = REAL_ESTIMATE(cfg, ws, "acct/m")
    every = len(pairs.load_pairs(switch_check._template())) + len(pairs.load_scenarios(switch_check._template()))
    assert count == 10 + every and price == pytest.approx(1.0 + 0.1 * switch_check.PAIR_CALLS * every)
