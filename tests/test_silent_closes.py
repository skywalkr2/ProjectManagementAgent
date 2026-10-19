"""No close goes unseen (design 6.32): every close the person didn't make or see is counted, listed with what, when, by
which rule or run and why, reviewable from the Set aside by rules screen, and measured out of all closes. Names and ids
come from the fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from engine import closes
from engine.applier import apply_as_person, undo
from engine.dispatcher import looks_good
from engine.set_aside import confirm_items, set_aside_item
from engine.storage import Store, WriteContext
from engine.watch import refresh
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_hold_drop_fold import DROPPING, RAW, WAITING, an_action, drop_op
from tests.test_knowledge_records import apply, source
from tests.test_set_aside import LISTS, mail
from tests.test_set_aside import make as make_mail
from tests.test_watch import NOW, RULES, fake, make, reread

_TEST = WriteContext(actor="pm", trust="trusted", op="test.silent-closes")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def from_input(store, cfg, ops):
    """Apply ops as the assistant does for an input that holds RAW."""
    return apply(store, cfg, ops, origin="input", trust="untrusted", source_id=source(store), raw=RAW)


def closed_by_a_rule(tmp_path):
    """A workspace where a triage rule closed a change nobody read: (ws, cfg, store, the closed request's id)."""
    items = [{"key": "a", "title": "Plan", "text": "One budget."}]
    ws, cfg, store = make(tmp_path, [fake(items)], triage=RULES)
    refresh(ws, store, cfg, "s", NOW)
    cfg, store, spaced = reread(tmp_path, ws, store, [{**items[0], "text": "One  budget"}])
    return ws, cfg, store, spaced.changed[0]


# ---- the assistant's own drops and closes ---------------------------------------------------------------------------


def test_an_assistant_drop_applied_as_data_is_a_silent_close_and_is_listed_with_what_when_by_and_why(env):
    _, cfg, store = env
    target = an_action(cfg, mine=False)
    text = store.read().get("action", target).data["text"]
    cs_id, statuses = from_input(store, cfg, [drop_op(target)])
    assert statuses == ["applied"]
    (found,) = closes.silent(store.read())
    assert (found.kind, found.how, found.record) == ("assistant", "dropped", ("action", target))
    assert found.title == text
    assert found.why == "No longer needed"
    assert found.changeset == cs_id and found.request == store.read().get("changeset", cs_id).data["request"]
    assert found.when == store.read().get("changeset", cs_id).data["created_at"]
    assert not found.by_person and not found.approved


def test_an_assistant_close_of_an_action_and_an_answered_question_are_silent_closes_too(env):
    _, cfg, store = env
    target = an_action(cfg, mine=False)
    from_input(store, cfg, [{"op": "action.close", "id": target, "evidence": {"quote": WAITING}}])
    question = store.read().list("question")[0].id
    from_input(
        store,
        cfg,
        [{"op": "question.done", "id": question, "answer": "Yes", "evidence": {"quote": DROPPING}}],
    )
    rows = {c.record: c for c in closes.silent(store.read())}
    assert set(rows) == {("action", target), ("question", question)}
    assert rows[("action", target)].how == "closed" and rows[("question", question)].how == "answered"
    assert "waiting on the proof" in rows[("action", target)].why


def test_the_persons_own_close_is_not_silent_but_is_counted_in_all_closes(env):
    _, cfg, store = env
    target = an_action(cfg, mine=True)
    apply_as_person(store, cfg, [{"op": "action.drop", "id": target, "reason": "Not needed"}], "Dropped")
    assert closes.silent(store.read()) == []
    (found,) = closes.collect(store.read())
    assert found.by_person and not found.silent


def test_a_close_from_the_persons_own_note_is_theirs(env):
    _, cfg, store = env
    target = an_action(cfg, mine=True)
    _, statuses = apply(store, cfg, [drop_op(target)], origin="pm", source_id=source(store), raw=RAW)
    assert statuses == ["applied"]
    assert closes.silent(store.read()) == []
    assert [c.by_person for c in closes.collect(store.read())] == [True]


def test_a_close_the_person_looked_over_and_approved_is_not_silent(env):
    _, cfg, store = env
    cs_id, _ = from_input(store, cfg, [drop_op(an_action(cfg, mine=False))])
    assert len(closes.silent(store.read())) == 1
    looks_good(store, cs_id)
    assert closes.silent(store.read()) == []
    (found,) = closes.collect(store.read())
    assert found.approved and not found.by_person


def test_a_close_released_from_held_by_the_person_is_approved(env):
    _, cfg, store = env
    cs_id, _ = from_input(store, cfg, [drop_op(an_action(cfg, mine=False))])
    with store.transaction() as tx:
        current = tx.get("changeset", cs_id)
        ops = current.data["ops"]
        ops[0]["problems"] = [{"check": "waits", "severity": "hold", "op": 0, "message": "needs a look"}]
        tx.update("changeset", cs_id, {"ops": ops}, _TEST, read_version=current.version)
    assert closes.silent(store.read()) == []


def test_a_close_that_was_undone_is_no_longer_a_close(env):
    _, cfg, store = env
    cs_id, _ = from_input(store, cfg, [drop_op(an_action(cfg, mine=False))])
    undo(store, cs_id)
    assert closes.collect(store.read()) == []


# ---- rules that close or set mail aside -----------------------------------------------------------------------------


def test_a_rule_close_is_silent_and_says_which_rule_and_why(tmp_path):
    ws, cfg, store, request = closed_by_a_rule(tmp_path)
    try:
        (found,) = closes.silent(store.read())
        assert (found.kind, found.how, found.rule, found.request) == ("rule", "closed", "Spacing", request)
        assert found.title == "Plan" and "spacing" in found.why and found.when
        assert found.ref == f"request:{request}"
    finally:
        store.close()


def test_a_rule_close_the_person_marked_as_seen_stops_being_silent_and_stays_in_all_closes(tmp_path):
    ws, cfg, store, request = closed_by_a_rule(tmp_path)
    try:
        closes.mark_seen(store, f"request:{request}")
        assert closes.silent(store.read()) == []
        (found,) = closes.collect(store.read())
        assert found.approved
    finally:
        store.close()


def test_mail_a_rule_sets_aside_is_silent_until_confirmed_and_what_the_person_sets_aside_never_is(tmp_path):
    ws, cfg, store = make_mail(tmp_path, [mail("by-rule", f"a@{LISTS}", bulk=True), mail("by-hand", f"b@{LISTS}")])
    try:
        refresh(ws, store, cfg, "m", datetime.now(UTC))
        by_hand = next(s for s in store.read().list("snapshot") if s.data["key"] == "by-hand")
        by_rule = next(s for s in store.read().list("snapshot") if s.data["key"] == "by-rule")
        set_aside_item(store, by_hand.id, "personal")
        rows = {c.snapshot: c for c in closes.collect(store.read())}
        assert rows[by_rule.id].kind == "set_aside" and rows[by_rule.id].silent
        assert rows[by_rule.id].rule and rows[by_rule.id].why
        assert rows[by_hand.id].by_person and not rows[by_hand.id].silent
        assert [c.snapshot for c in closes.silent(store.read())] == [by_rule.id]
        confirm_items(store, [by_rule.id])
        assert closes.silent(store.read()) == []
    finally:
        store.close()


# ---- the measure ----------------------------------------------------------------------------------------------------


def test_the_measure_gives_silent_closes_out_of_all_closes_with_the_denominators_by_kind_and_period(env):
    _, cfg, store = env
    mine, theirs, other = an_action(cfg, mine=True), an_action(cfg, mine=False), None
    other = next(a.id for a in store.read().list("action") if a.id not in (mine, theirs) and a.data["status"] == "open")
    apply_as_person(store, cfg, [{"op": "action.drop", "id": mine, "reason": "Not needed"}], "Dropped")
    approved, _ = from_input(store, cfg, [drop_op(theirs)])
    looks_good(store, approved)
    from_input(store, cfg, [drop_op(other)])
    now = datetime.now(UTC)
    whole = closes.measure(store.read(), now - timedelta(days=1), now + timedelta(days=1))
    assert (whole.total, whole.silent, whole.by_person, whole.approved) == (3, 1, 1, 1)
    assert whole.rate == pytest.approx(1 / 3)
    assert whole.by_kind["assistant"] == closes.KindCount(total=3, silent=1)
    before = closes.measure(store.read(), now - timedelta(days=9), now - timedelta(days=8))
    assert (before.total, before.silent, before.rate) == (0, 0, None)


# ---- the screen's API -----------------------------------------------------------------------------------------------


def client_for(ws, cfg):
    app = create_app(ws, cfg, "closes-token", ui_dist=ws.root / "no-ui", start_worker=False)
    return TestClient(app, headers={"Authorization": "Bearer closes-token"}), cfg.server.base_path.rstrip("/") + "/api"


def test_the_api_serves_the_count_the_list_and_the_measure_and_marking_one_seen_lowers_the_count(tmp_path):
    ws, cfg, store, request = closed_by_a_rule(tmp_path)
    cs_id, _ = from_input(store, cfg, [drop_op(an_action(cfg, mine=False))])
    store.close()
    client, api = client_for(ws, cfg)
    body = client.get(f"{api}/silent-closes").json()
    assert body["count"] == 2 and len(body["closes"]) == 2
    kinds = {c["kind"]: c for c in body["closes"]}
    assert kinds["rule"]["rule"] == "Spacing" and kinds["rule"]["request"] == request
    assert kinds["assistant"]["changeset"] == cs_id and kinds["assistant"]["why"] == "No longer needed"
    assert body["measure"]["total"] == 2 and body["measure"]["silent"] == 2
    assert body["measure"]["days"] == cfg.dispatch.knowledge.quality_window_days
    for close in body["closes"]:
        done = client.post(f"{api}/silent-closes/seen", json={"ref": close["ref"]})
        assert done.status_code == 200, done.text
    after = client.get(f"{api}/silent-closes").json()
    assert after["count"] == 0 and after["measure"]["total"] == 2 and after["measure"]["silent"] == 0


def test_marking_something_that_is_not_a_close_as_seen_is_refused(env):
    ws, cfg, store = env
    store.close()
    client, api = client_for(ws, cfg)
    assert client.post(f"{api}/silent-closes/seen", json={"ref": "request:REQ-999"}).status_code == 404
    assert client.post(f"{api}/silent-closes/seen", json={"ref": "nonsense"}).status_code == 404
