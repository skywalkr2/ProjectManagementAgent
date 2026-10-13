"""A retry that applies retires the attempts before it: attempts are linked by the request they answer (a request sent
back is followed by one whose `previous` names it), and when one applies, the earlier attempts' held items, open
questions and proposals close, a queued automatic try or fix round for them does not run, and nothing they write later
brings their line back. A fake provider stands in for the assistant; nothing sleeps."""

import json

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.dispatcher import SUPERSEDED, needs_you, process, retire_earlier_attempts, retry, send_back
from engine.intake import hand_in
from engine.storage import WriteContext
from engine.today_queue import queue
from tests.test_pipeline import NOW, answers, env, outcomes, run  # noqa: F401  (the fixture and helpers)

_TEST = WriteContext(actor="engine", trust="trusted", op="test.setup")
APPLYING = {"ops": [{"op": "note", "text": "Something to keep."}]}
# A different kind of op, since an answer made of the same ops as the one sent back is refused as a repeat.
APPLYING_OTHER = {"ops": [{"op": "question.add", "to": "me", "title": "Which finish?"}]}


def lines_of(world, request_ids):
    """The Today lines that stand for any of these requests or their changesets."""
    ws, cfg, store = world
    changesets = {c.id for c in store.read().list("changeset") if c.data["request"] in request_ids}
    return [
        line
        for line in queue(ws, store, cfg, NOW)
        if line.request in request_ids or (line.changeset and line.changeset in changesets)
    ]


def process_again(world, request_id):
    ws, cfg, store = world
    return process(ws, store, cfg, Router(cfg, store, env={}), request_id, now=NOW)


def an_unknown_owner(name):
    return {
        "ops": [
            {
                "op": "action.add",
                "text": "Book the venue",
                "owners": [name],
                "evidence": {"quote": "will book the venue"},
            }
        ]
    }


def a_request_redoing(world, previous):
    """A request that redoes `previous`, as one made by sending work back is."""
    ws, _, store = world
    handed = hand_in(ws, store, note="Do it again.", pasted="", now=NOW)
    with store.transaction() as tx:
        cur = tx.get("request", handed.request)
        tx.update("request", cur.id, {"previous": previous}, _TEST, read_version=cur.version)
    return handed.request


# ---- a try again on the same request ----------------------------------------------------------------------------


def test_a_try_again_on_the_same_request_that_applies_leaves_no_line_or_cause_for_the_failed_try(env):  # noqa: F811
    _, cfg, store = env
    cfg.dispatch.retries = 0
    set_responder(lambda task: "I can't help with that.")
    handed, cs_id = run(env, "Anything.")
    assert cs_id is None
    assert [line.kind for line in lines_of(env, {handed.request})] == ["refused"]
    set_responder(lambda task: json.dumps(APPLYING))
    retry(store, handed.request)
    assert process_again(env, handed.request) is not None
    request = store.read().get("request", handed.request).data
    assert request["cause"] is None and request["waiting"] is None
    assert [line.kind for line in lines_of(env, {handed.request})] == ["review"]


# ---- the attempts before one that applies --------------------------------------------------------------------------


def test_a_sent_back_attempt_with_a_held_item_is_retired_when_the_next_one_applies(env):  # noqa: F811
    _, _, store = env
    stranger = "Jordan " + "Pike"
    answers(an_unknown_owner(stranger))
    first, first_cs = run(env, f"{stranger} will book the venue.")
    (held,) = outcomes(store, first_cs)
    assert held["status"] == "held"
    assert {line.kind for line in lines_of(env, {first.request})} == {"who_is", "review"}
    second = send_back(store, first_cs, "Make it a note instead.")
    answers(APPLYING)
    assert process_again(env, second) is not None

    request = store.read().get("request", first.request).data
    assert request["state"] == "done" and request["superseded_by"] == second
    (retired,) = outcomes(store, first_cs)
    assert retired["status"] == "refused" and retired["reason"] == SUPERSEDED
    assert store.read().get("changeset", first_cs).data["status"] == "rejected"
    assert store.read().get("question", held["question"]).data["status"] == "dropped"
    assert lines_of(env, {first.request}) == []
    assert [line.request for line in lines_of(env, {second})] == [second]
    assert store.read().get("request", second).data.get("superseded_by") is None


def test_a_stopped_attempt_and_its_cause_close_when_a_later_attempt_applies(env):  # noqa: F811
    ws, _, store = env
    first = hand_in(ws, store, note="Do it.", pasted="", now=NOW)
    needs_you(store, first.request, "Something stopped it.", cause={"kind": "no_person"})
    assert [line.kind for line in lines_of(env, {first.request})] == ["refused"]
    second = a_request_redoing(env, first.request)
    answers(APPLYING)
    assert process_again(env, second) is not None
    request = store.read().get("request", first.request).data
    assert request["state"] == "done" and request["cause"] is None and request["waiting"] is None
    assert lines_of(env, {first.request}) == []


def test_an_attempt_that_kept_its_applied_work_keeps_it_when_the_next_one_applies(env):  # noqa: F811
    _, _, store = env
    answers(APPLYING)
    first, first_cs = run(env, "Keep something.")
    second = send_back(store, first_cs, "Also this.", undo_first=False)
    answers({"ops": [{"op": "note", "text": "Something else."}]})
    assert process_again(env, second) is not None
    assert [o["status"] for o in outcomes(store, first_cs)] == ["applied"]
    assert len(store.read().list("note")) == 2


def test_the_attempts_open_proposals_are_discarded(env):  # noqa: F811
    _, _, store = env
    answers(APPLYING)
    first, first_cs = run(env, "Keep something.")
    with store.transaction() as tx:
        report = tx.create(
            "report", {"request": first.request, "title": "Missing", "text": "Nothing here.", "status": "draft"}, _TEST
        ).id
        proposal = tx.create(
            "setting_proposal",
            {"request": first.request, "key": "dispatch.retries", "value": 2, "why": "x", "status": "open"},
            _TEST,
        ).id
    second = send_back(store, first_cs, "Again.")
    answers(APPLYING_OTHER)
    assert process_again(env, second) is not None
    assert store.read().get("report", report).data["status"] == "dismissed"
    assert store.read().get("setting_proposal", proposal).data["status"] == "dismissed"


def test_an_attempt_that_applied_nothing_retires_nothing(env):  # noqa: F811
    _, _, store = env
    stranger = "Jordan " + "Pike"
    answers(an_unknown_owner(stranger))
    first, first_cs = run(env, f"{stranger} will book the venue.")
    second = send_back(store, first_cs, "Again.")
    editor = next(p for p in store.read().list("person") if p.data.get("role") == "Editor")
    answers({"ops": [{"op": "question.add", "to": editor.data["full_name"], "title": "Is the date final?"}]})
    second_cs = process_again(env, second)
    assert [o["status"] for o in outcomes(store, second_cs)] == ["refused"]
    assert store.read().get("request", first.request).data.get("superseded_by") is None
    assert [o["status"] for o in outcomes(store, first_cs)] == ["held"]


# ---- a follow-up checks that its cause still stands -------------------------------------------------------------


def test_a_queued_automatic_try_for_a_request_that_has_since_applied_does_not_run(env):  # noqa: F811
    _, _, store = env
    set_responder(lambda task: "not an answer")
    first, cs_id = run(env, "Something.")
    assert cs_id is None
    queued = store.read().get("request", first.request).data
    assert queued["state"] == "queued" and queued["cause"]["kind"] == "retry"
    second = a_request_redoing(env, first.request)
    answers(APPLYING)
    assert process_again(env, second) is not None
    assert store.read().get("request", first.request).data["state"] == "done"
    asked = answers(APPLYING)
    assert process_again(env, first.request) is None
    assert asked == []
    assert store.read().get("request", first.request).data["state"] == "done"


def test_a_request_that_is_not_waiting_in_line_is_not_run(env):  # noqa: F811
    asked = answers(APPLYING)
    first, cs_id = run(env, "Keep something.")
    assert len(asked) == 1 and cs_id is not None
    assert process_again(env, first.request) is None  # it is in review: nothing runs again
    assert len(asked) == 1


def test_a_fix_round_for_a_request_retired_meanwhile_does_not_run(env):  # noqa: F811
    ws, _, store = env
    editor = next(p for p in store.read().list("person") if p.data.get("role") == "Editor")
    # A question to someone else with no link is refused, so the answer would go back for a fix round.
    failing = {"ops": [{"op": "question.add", "to": editor.data["full_name"], "title": "Is the date final?"}]}
    handed = hand_in(ws, store, note="", pasted="We need to settle the date.", now=NOW)
    asked = []
    later = []

    def responder(task):
        asked.append(task)
        if not later:  # while the first call is out, a later attempt at the same request applies
            later.append(a_request_redoing(env, handed.request))
            retire_earlier_attempts(store, later[0])
        return json.dumps(failing)

    set_responder(responder)
    assert process_again(env, handed.request) is None
    assert len(asked) == 1  # neither the fix round nor the stronger tier ran
    request = store.read().get("request", handed.request).data
    assert request["state"] == "done" and request["superseded_by"] == later[0]
    assert store.read().list("changeset") == []
    assert lines_of(env, {handed.request}) == []


def test_a_retired_request_is_not_stopped_again_by_a_late_failure(env):  # noqa: F811
    ws, _, store = env
    handed = hand_in(ws, store, note="Do it.", pasted="", now=NOW)
    retire_earlier_attempts(store, a_request_redoing(env, handed.request))
    needs_you(store, handed.request, "Something went wrong.")
    assert store.read().get("request", handed.request).data["state"] == "done"
    assert lines_of(env, {handed.request}) == []
