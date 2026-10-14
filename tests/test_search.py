"""The search round and the checks that keep a run local first (design 6.22): the search ranks and is bounded, a run
that asks to search gets the results and then answers, a run that keeps asking must answer after the configured rounds,
`already-known` sends back a question the workspace already answers, and `near-duplicate-question` flags a repeat."""

import json
from datetime import UTC, datetime

import pytest

from engine import search as workspace_search
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.applier import Context, Inputs, check
from engine.dispatcher import process, search_request
from engine.intake import hand_in
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_B, fixture_records

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
_PM = WriteContext("pm", "trusted", "test")
SEARCH = {"search": {"words": "interior file deadline", "kinds": ["facts"]}}


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def project() -> dict:
    return fixture_records(DEMO_B, "project")[0]


def pm_id(cfg) -> str:
    return cfg.workspace.user.person


def other_person(cfg) -> dict:
    return next(p for p in fixture_records(DEMO_B, "person") if p["id"] != pm_id(cfg))


def add_fact(store, text, **more) -> str:
    with store.transaction() as tx:
        return tx.create("fact", {"text": text, "project": project()["id"], **more}, _PM).id


def fact_text() -> str:
    return f"The interior file deadline for {project()['name']} is the sixteenth of October"


def question_title() -> str:
    return f"What is the interior file deadline for {project()['name']}?"


def scripted(*bodies):
    """Make the stub answer with these bodies in turn (the last one repeats), and record each task it is asked."""
    asked, queue = [], [json.dumps(b) for b in bodies]

    def responder(task):
        asked.append(task)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    set_responder(responder)
    return asked


def run(env, pasted="Note for the file.", note=""):
    ws, cfg, store = env
    handed = hand_in(ws, store, note=note, pasted=pasted, now=NOW)
    cs_id = process(ws, store, cfg, Router(cfg, store, env={}), handed.request, now=NOW)
    return handed, cs_id


def an_answer(text="Nothing new."):
    return {"summary": text, "ops": []}


# ---- the search itself -----------------------------------------------------------------------------------------------


def test_search_ranks_by_shared_words_and_is_bounded_by_the_limit(env):
    ws, _, store = env
    best = add_fact(store, fact_text())
    partial = add_fact(store, "The interior pages are proofread twice")
    add_fact(store, "The cover is matte")
    query = workspace_search.Query(words="interior file deadline", kinds=("facts",))
    hits = workspace_search.search(ws, store, query, limit=10)
    assert [h.id for h in hits] == [best, partial]  # a fact with nothing in common isn't a result
    assert [h.id for h in workspace_search.search(ws, store, query, limit=1)] == [best]


def test_search_finds_a_record_by_its_id_first(env):
    ws, _, store = env
    add_fact(store, fact_text())
    other = add_fact(store, "Something else entirely")
    query = workspace_search.Query(words="interior file deadline", ids=(other,), kinds=("facts",))
    assert workspace_search.search(ws, store, query, limit=5)[0].id == other


def test_search_returns_only_active_knowledge(env):
    ws, cfg, store = env
    kept = {"origin": "person", "learned_at": NOW.isoformat(), "kept_by": pm_id(cfg), "kept_at": NOW.isoformat()}
    with store.transaction() as tx:
        active = tx.create("lesson", {"text": "Ask about the interior file early", "status": "active", **kept}, _PM).id
        tx.create(
            "lesson",
            {
                "text": "Ask about the interior file late",
                "status": "proposed",
                "origin": "assistant",
                "learned_at": NOW.isoformat(),
            },
            _PM,
        )
    query = workspace_search.Query(words="interior file", kinds=("knowledge",))
    assert [h.id for h in workspace_search.search(ws, store, query, limit=5)] == [active]


def test_a_replaced_fact_is_found_and_marked_with_what_replaced_it(env):
    ws, _, store = env
    old = add_fact(store, fact_text())
    new = add_fact(store, "The interior file deadline moved to the twenty-third of October", supersedes=old)
    query = workspace_search.Query(words="interior file deadline", kinds=("facts",))
    hits = {h.id: h for h in workspace_search.search(ws, store, query, limit=5)}
    assert hits[old].replaced_by == new and hits[new].replaced_by is None
    assert f"Replaced by {new}" in workspace_search.render([hits[old]], query, 1, 1)


def test_search_over_past_inputs_marks_outside_ones_and_skips_the_one_being_read(env):
    ws, _, store = env
    earlier = hand_in(ws, store, pasted="The interior file deadline is Friday.\n\nUnrelated closing line.", now=NOW)
    current = hand_in(ws, store, pasted="The interior file deadline is Monday.", now=NOW)
    query = workspace_search.Query(words="interior file deadline", kinds=("inputs",))
    hits = workspace_search.search(ws, store, query, limit=5, exclude_sources=[current.source])
    assert [h.id for h in hits] == [earlier.source]
    assert hits[0].untrusted and "Friday" in hits[0].text and "Unrelated" not in hits[0].text
    assert "<untrusted" in workspace_search.render(hits, query, 1, 0)


def test_search_leaves_out_material_above_the_runs_data_level(env):
    ws, _, store = env
    hand_in(ws, store, pasted="The interior file deadline is Friday.", now=NOW, data_level="restricted")
    query = workspace_search.Query(words="interior file deadline", kinds=("inputs",))
    assert workspace_search.search(ws, store, query, limit=5, level="internal") == []
    assert workspace_search.search(ws, store, query, limit=5, level="restricted")


def test_an_answer_asks_for_a_search_only_without_ops():
    assert search_request(json.dumps(SEARCH)).words == "interior file deadline"
    assert search_request("```json\n" + json.dumps(SEARCH) + "\n```").kinds == ("facts",)
    assert search_request(json.dumps({**SEARCH, "ops": [{"op": "note", "text": "x"}]})) is None
    assert search_request(json.dumps(an_answer())) is None
    assert search_request("not json") is None


# ---- the search round ------------------------------------------------------------------------------------------------


def test_a_run_that_asks_to_search_gets_the_results_and_then_answers(env):
    _, _, store = env
    fact = add_fact(store, fact_text())
    asked = scripted(SEARCH, an_answer("Answered from the results."))
    _, cs_id = run(env)
    assert len(asked) == 2
    assert fact not in asked[0].request and fact in asked[1].request and fact_text() in asked[1].request
    assert store.read().get("changeset", cs_id).data["summary"] == "Answered from the results."
    first, second = sorted(store.read().list("run"), key=lambda r: r.id)
    assert first.data["knowledge"]["searches"] == [
        {"words": "interior file deadline", "kinds": ["facts"], "results": 1}
    ]
    assert not second.data.get("knowledge")


def test_a_search_uses_up_no_fix_round_and_no_try(env):
    _, cfg, store = env
    assert cfg.dispatch.fix_rounds == 1
    asked = scripted(SEARCH, "this is not an answer", an_answer("Fixed after one return."))
    handed, cs_id = run(env)
    assert len(asked) == 3  # the search, the unreadable answer, the fix: the one fix round was still there
    assert store.read().get("changeset", cs_id).data["summary"] == "Fixed after one return."
    assert store.read().get("request", handed.request).data["attempts"] == 1


def test_a_run_that_keeps_asking_must_answer_after_the_configured_rounds(env):
    _, cfg, store = env
    rounds = cfg.dispatch.knowledge.search_rounds
    asked = []

    def responder(task):
        asked.append(task)
        return json.dumps(an_answer("Answered at last.") if "Answer now" in task.request else SEARCH)

    set_responder(responder)
    _, cs_id = run(env)
    assert len(asked) == rounds + 1
    assert "search 1" in asked[1].request and f"search {rounds}" in asked[-1].request
    assert "Answer now" not in asked[rounds - 1].request and "Answer now" in asked[-1].request
    assert store.read().get("changeset", cs_id).data["summary"] == "Answered at last."


def test_a_run_that_ignores_the_order_to_answer_is_stopped_not_looped(env):
    _, cfg, store = env
    asked = scripted(SEARCH)
    handed, cs_id = run(env)
    assert cs_id is None
    # Each pass is the asked search rounds, then the fix rounds; the stronger tier gets one more pass (as it does for
    # any answer that can't be read), and nothing beyond that.
    one_pass = 1 + cfg.dispatch.knowledge.search_rounds + cfg.dispatch.fix_rounds
    assert one_pass <= len(asked) <= 2 * one_pass
    assert store.read().get("request", handed.request).data["state"] != "review"


def test_results_from_an_outside_input_make_the_work_untrusted(env):
    ws, _, store = env
    hand_in(ws, store, pasted="The interior file deadline is Friday.", now=NOW)
    scripted({"search": {"words": "interior file deadline", "kinds": ["inputs"]}}, an_answer())
    _, cs_id = run(env, pasted="", note="Look into the interior file deadline.")
    assert store.read().get("changeset", cs_id).data["trust"] == "untrusted"


def test_results_from_the_workspaces_own_records_leave_the_work_trusted(env):
    _, _, store = env
    add_fact(store, fact_text())
    scripted(SEARCH, an_answer())
    _, cs_id = run(env, pasted="", note="Look into the interior file deadline.")
    assert store.read().get("changeset", cs_id).data["trust"] == "trusted"


# ---- already-known ---------------------------------------------------------------------------------------------------


def question_op(cfg, title, to=None, **more):
    return {
        "op": "question.add",
        "to": to or pm_id(cfg),
        "title": title,
        "links": [project()["links"][0]],
        **more,
    }


def problems_for(env, op, name, *, searched=False, actor="assistant"):
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        ("question.add", "report.draft"),
        Inputs("REQ-1", None, "", "", "trusted"),
        actor=actor,
        searched=searched,
    )
    return [p for p in check(cs, ctx) if p.check == name]


def test_already_known_returns_a_question_a_fact_answers(env):
    _, cfg, store = env
    fact = add_fact(store, fact_text())
    (problem,) = problems_for(env, question_op(cfg, question_title()), "already-known")
    assert problem.severity == "return" and f"answered by {fact}" in problem.message and "sixteenth" in problem.message


def test_already_known_leaves_a_question_with_no_match_and_one_after_a_search(env):
    _, cfg, store = env
    add_fact(store, fact_text())
    assert not problems_for(
        env, question_op(cfg, f"Which caterer handles the party for {project()['name']}?"), "already-known"
    )
    assert not problems_for(env, question_op(cfg, question_title()), "already-known", searched=True)
    assert not problems_for(env, question_op(cfg, question_title()), "already-known", actor="pm")


def test_already_known_checks_a_question_to_someone_else_and_a_report_too(env):
    _, cfg, store = env
    fact = add_fact(store, fact_text())
    to_other = question_op(cfg, question_title(), to=other_person(cfg)["id"])
    assert [p.severity for p in problems_for(env, to_other, "already-known")] == ["return"]
    report = {"op": "report.draft", "title": question_title(), "text": "It would help to know."}
    (problem,) = problems_for(env, report, "already-known")
    assert fact in problem.message


def test_already_known_ignores_a_replaced_fact_in_favor_of_its_replacement(env):
    _, cfg, store = env
    old = add_fact(store, fact_text())
    new = add_fact(
        store, f"The interior file deadline for {project()['name']} moved to the twenty-third", supersedes=old
    )
    (problem,) = problems_for(env, question_op(cfg, question_title()), "already-known")
    assert new in problem.message and old not in problem.message


def test_already_known_is_off_when_the_workspace_switches_it_off(env):
    _, cfg, store = env
    add_fact(store, fact_text())
    cfg.checks.lints["already-known"] = "off"
    assert not problems_for(env, question_op(cfg, question_title()), "already-known")


def test_a_question_the_workspace_answers_is_sent_back_once_with_the_match(env):
    _, cfg, store = env
    fact = add_fact(store, fact_text())
    asked = scripted({"summary": "Asked.", "ops": [question_op(cfg, question_title())]}, an_answer("Dropped it."))
    _, cs_id = run(env)
    assert len(asked) == 2 and f"answered by {fact}" in asked[1].request
    assert store.read().get("changeset", cs_id).data["ops"] == []


def test_a_question_from_a_run_that_searched_is_not_sent_back(env):
    _, cfg, store = env
    add_fact(store, fact_text())
    asked = scripted(SEARCH, {"summary": "Asked.", "ops": [question_op(cfg, question_title())]})
    _, cs_id = run(env)
    assert len(asked) == 2
    (outcome,) = store.read().get("changeset", cs_id).data["ops"]
    assert outcome["status"] == "applied"


def test_the_subject_must_share_enough_words_with_the_fact():
    assert workspace_search.ASKING_OPS["question.add"](type("Op", (), {"title": "A title"})()) == "A title"
    from engine.config.schema import AlreadyKnownTuning

    assert AlreadyKnownTuning().similarity == 0.7
    for value in (-0.1, 1.1):
        with pytest.raises(ValueError):
            AlreadyKnownTuning(similarity=value)


# ---- near-duplicate-question -----------------------------------------------------------------------------------------

OPEN_QUESTION = "Which printer takes the hardcover run"
SHARES_FOUR_OF_FIVE = "Which printer takes the hardcover run today"  # words of four letters or more: 4 of 5
SHARES_THREE_OF_FIVE = "Which printer takes the paperback run"  # 3 of 5


def add_question(store, title, status="open", **more):
    cfg_person = fixture_records(DEMO_B, "person")[0]["id"]
    with store.transaction() as tx:
        return tx.create("question", {"to": cfg_person, "title": title, "status": status, **more}, _PM).id


def near_duplicates(env, title):
    _, cfg, _ = env
    return problems_for(env, question_op(cfg, title), "near-duplicate-question")


def test_near_duplicate_question_fires_at_and_above_the_similarity_and_not_below(env):
    _, cfg, store = env
    add_question(store, OPEN_QUESTION)
    cfg.checks.tuning.near_duplicate_question.similarity = 0.8
    (problem,) = near_duplicates(env, SHARES_FOUR_OF_FIVE)  # exactly at the setting
    assert problem.severity == "warn" and "open question" in problem.message and OPEN_QUESTION in problem.message
    assert not near_duplicates(env, SHARES_THREE_OF_FIVE)  # below it
    cfg.checks.tuning.near_duplicate_question.similarity = 0.6
    assert near_duplicates(env, SHARES_THREE_OF_FIVE)  # at the lower setting


def test_near_duplicate_question_compares_with_questions_answered_within_the_days(env):
    _, cfg, store = env
    store.clock = lambda: "2026-09-20T09:00:00+00:00"
    qid = add_question(store, OPEN_QUESTION)
    with store.transaction() as tx:
        tx.update("question", qid, {"status": "answered", "answer": "The usual one."}, _PM, read_version=1)
    store.clock = lambda: "2026-10-14T09:00:00+00:00"  # 24 days later
    cfg.checks.tuning.near_duplicate_question.days = 30
    (problem,) = near_duplicates(env, OPEN_QUESTION)
    assert "answered question" in problem.message
    cfg.checks.tuning.near_duplicate_question.days = 10
    assert not near_duplicates(env, OPEN_QUESTION)


def test_near_duplicate_question_ignores_dropped_questions(env):
    _, _, store = env
    add_question(store, OPEN_QUESTION, status="dropped")
    assert not near_duplicates(env, OPEN_QUESTION)


def test_the_lint_defaults_and_ranges():
    from engine.config.schema import ChecksFile, NearDuplicateQuestionTuning

    checks = ChecksFile()
    assert checks.lints["already-known"] == "return" and checks.lints["near-duplicate-question"] == "warn"
    tuning = NearDuplicateQuestionTuning()
    assert (tuning.similarity, tuning.days) == (0.8, 30)
    for value in (-0.1, 1.1):
        with pytest.raises(ValueError):
            NearDuplicateQuestionTuning(similarity=value)
