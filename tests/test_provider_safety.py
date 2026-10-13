"""The AI setup never fails silently: no default account, a check of every tier, settings changed under a running
process, and no repeating an answer the PM sent back."""

import json
from datetime import UTC, datetime

import pytest

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.ai.smoke import record, smoke_test, untested_since_change
from engine.ai.task import AiError
from engine.config import ConfigError
from engine.config.yaml_edit import set_key
from engine.dispatcher import process, send_back
from engine.intake import hand_in
from engine.storage import Store, WriteContext
from engine.worker import RESTART_NEEDED, Events, Worker
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, add_example_account

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    store = Store(ws.db_path)
    yield ws, store
    store.close()
    set_responder(None)


def test_a_fresh_workspace_has_no_ai_account_and_says_so(tmp_path):
    ws = init_workspace(tmp_path / "fresh", git=False)
    cfg = ws.config(env={})
    assert cfg.ai.providers == {} and cfg.ai.tiers["routine"].use == ""
    store = Store(ws.db_path)
    with store.transaction() as tx:
        cfg.workspace.user.person = tx.create(
            "person", {"full_name": "Someone"}, WriteContext("pm", "trusted", "test")
        ).id
    req = hand_in(ws, store, note="file this", now=NOW).request
    assert process(ws, store, cfg, Router(cfg, store, env={}), req, now=NOW) is None
    waiting = store.read().get("request", req).data["waiting"]
    assert "no AI account is set up" in waiting and "routine" in waiting
    store.close()


def test_a_tier_naming_a_missing_account_is_a_config_error(env):
    ws, _ = env
    with pytest.raises(ConfigError, match="no account 'nobody'"):
        ws.config(env={}, flags={"ai.tiers.routine.use": "nobody/model"})
    with pytest.raises(ConfigError, match="isn't a tier"):
        ws.config(env={}, flags={"ai.tasks.notes.tier": "missing"})


def test_the_smoke_test_tries_every_tier_with_each_tasks_parameters(env):
    ws, _ = env
    cfg = ws.config(env={})
    seen = []

    def responder(task):
        seen.append((task.temperature, task.max_output))
        return '{"ok": true}'

    set_responder(responder)
    results = smoke_test(cfg, env={})
    assert {r.tier for r in results} == set(cfg.ai.tiers)
    notes = cfg.ai.tasks["notes"]
    assert (notes.temperature, notes.max_output) in seen
    assert all(r.ok for r in results)


def test_the_smoke_test_reports_a_refused_parameter_and_a_missing_key(env, tmp_path):
    ws, _ = env
    real, model, named = add_example_account(ws.config_dir / "ai.yaml")
    cfg = ws.config(env={}, flags={"ai.tiers.deep.use": f"{real}/{model}"})

    def responder(task):
        raise AiError("other", "this model does not accept that setting")

    set_responder(responder)
    results = smoke_test(cfg, env={})
    deep = [r for r in results if r.tier == "deep"]
    assert deep and not deep[0].ok and "key not found" in deep[0].detail
    routine = [r for r in results if r.tier == "routine"]
    assert routine and not routine[0].ok and "does not accept" in routine[0].detail


def test_the_last_smoke_test_is_remembered_until_ai_settings_change(env):
    ws, _ = env
    set_responder(lambda task: '{"ok": true}')
    assert untested_since_change(ws)
    record(ws, smoke_test(ws.config(env={}), env={}))
    assert not untested_since_change(ws)
    path = ws.config_dir / "ai.yaml"
    path.write_text(path.read_text() + "\n# changed\n")
    assert untested_since_change(ws)


def test_changed_settings_stop_new_work_until_restart(env):
    ws, store = env
    cfg = ws.config(env={})
    worker = Worker(ws, store, cfg, Events(), lambda: Router(cfg, store, env={}))
    path = ws.config_dir / "ai.yaml"
    path.write_text(path.read_text() + "\n# edited while running\n")
    assert worker.restart_needed is None and not worker.needs_restart()  # AI settings are taken in live
    path = ws.config_dir / "storage.yaml"
    path.write_text(set_key(path.read_text(), ["export", "commit"], False))  # this one waits for a restart
    req = hand_in(ws, store, note="file this", now=NOW).request
    assert worker.run_pending() == 0
    assert worker.restart_needed == RESTART_NEEDED
    stored = store.read().get("request", req).data
    assert stored["state"] == "queued" and stored["waiting"] == RESTART_NEEDED


def test_the_same_answer_after_a_send_back_is_refused(env):
    ws, store = env
    cfg = ws.config(env={})
    same = {"summary": "Noted.", "ops": [{"op": "note", "text": "The reading is at the library."}]}
    asked = []

    def responder(task):
        asked.append(task.request)
        return json.dumps(same)

    set_responder(responder)
    req = hand_in(ws, store, note="note where the reading is", now=NOW).request
    cs = process(ws, store, cfg, Router(cfg, store, env={}), req, now=NOW)
    again = send_back(store, cs, "I meant the bookshop, not the library", now=NOW)
    assert process(ws, store, cfg, Router(cfg, store, env={}), again, now=NOW) is None
    assert any("same as the one the PM sent back" in r for r in asked)
    assert "same answer again" in store.read().get("request", again).data["waiting"]


# ---- the provider's own reason, and the assistant's state ----------------------------------------------------


def test_a_failure_adds_the_providers_own_message(env):
    from engine.dispatcher import _ai_failure

    body = 'HTTP 401: {"error": {"message": "User not found.", "code": 401}}'
    assert _ai_failure(AiError("auth", body)).startswith("The AI account refused the key (User not found).")
    assert "(Bad request)" in _ai_failure(AiError("other", 'HTTP 400: {"message": "Bad request"}'))
    plain = _ai_failure(AiError("quota", "no credit left on this account " + "x" * 300))
    assert "(no credit left on this account x" in plain
    inside = plain[plain.index("(") + 1 : plain.index(")")]
    assert len(inside) == 200
    assert "(" not in _ai_failure(AiError("timeout"))


def test_the_assistants_state_follows_the_account_the_test_and_the_last_refusal(env, monkeypatch):
    from engine.ai.smoke import ai_state

    ws, store = env
    cfg = ws.config(env={})
    assert ai_state(ws, cfg, store) == ("stand_in", None)
    # From here the stand-in plays a real account, answering through the test responder.
    monkeypatch.setattr("engine.ai.smoke.stand_in", lambda cfg: False)
    assert ai_state(ws, cfg, store) == ("untested", None)
    set_responder(lambda task: '{"ok": true}')
    record(ws, smoke_test(cfg, env={}))
    assert ai_state(ws, cfg, store) == ("ok", None)

    def refuse(task):
        raise AiError("other", "x" * 500)

    set_responder(refuse)
    record(ws, smoke_test(cfg, env={}))
    state, detail = ai_state(ws, cfg, store)
    assert state == "failing" and detail and len(detail) == 200
    # Settings changed since that failure: it no longer says anything about them.
    path = ws.config_dir / "ai.yaml"
    path.write_text(path.read_text() + "\n# changed\n")
    assert ai_state(ws, cfg, store) == ("untested", None)


def test_no_account_for_any_tier_is_not_set_up(tmp_path):
    from engine.ai.smoke import ai_state

    ws = init_workspace(tmp_path / "fresh", git=False)
    store = Store(ws.db_path)
    assert ai_state(ws, ws.config(env={}), store) == ("not_set_up", None)
    store.close()


def test_the_smoke_test_says_where_a_refused_or_missing_key_was_read_from(env, tmp_path):
    ws, _ = env
    real, model, named = add_example_account(ws.config_dir / "ai.yaml")
    cfg = ws.config(env={}, flags={"ai.tiers.deep.use": f"{real}/{model}"})
    sources = [r.key_source for r in smoke_test(cfg, env={}) if r.tier == "deep"]
    assert sources and sources[0] == f"key from the secret named {named}"

    key_file = tmp_path / "key.txt"
    cfg = ws.config(
        env={}, flags={"ai.tiers.deep.use": f"{real}/{model}", f"ai.providers.{real}.auth": f"file:{key_file}"}
    )
    assert [r.key_source for r in smoke_test(cfg, env={}) if r.tier == "deep"][0] == f"key from the file {key_file}"

    class Refusing:
        def run(self, task, model_id):
            raise AiError("auth", "HTTP 401: provider text")

    key_file.write_text("the-secret-value\n")
    results = smoke_test(cfg, env={}, adapter_factory=lambda *_: Refusing())
    deep = [r for r in results if r.tier == "deep"][0]
    assert deep.key_source == f"key from the file {key_file}"
    assert "the-secret-value" not in deep.detail + (deep.key_source or "")


def test_a_model_name_without_a_space_after_the_colon_is_explained(tmp_path):
    from engine.config import load_config

    (tmp_path / "ai.yaml").write_text(
        "providers:\n  acct:\n    adapter: stub\n    models: {small:vendor/model-id}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="put a space after the colon: write 'small: vendor/model-id'"):
        load_config(tmp_path, env={})
