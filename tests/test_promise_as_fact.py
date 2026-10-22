"""promise-as-fact: someone's promise with a date, recorded as a fact, goes back once to be recorded as their action."""

from __future__ import annotations

import pytest

from engine.applier import Context, Inputs, check
from engine.names import People
from engine.ops import CHANGESET
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from engine.yaml_load import load_yaml
from tests.conftest import DEMO_A, DEMO_B, fixture_records

LINT = "promise-as-fact"
_PM = WriteContext(actor="pm", trust="trusted", op="test")
PEOPLE = fixture_records(DEMO_B, "person")
ME = next(p for p in PEOPLE if p["id"] == "PER-1")
TEAMMATE = next(
    p
    for p in PEOPLE
    if p["id"] != ME["id"]
    and p.get("team") == ME["team"]
    and sum(q["full_name"].split()[0] == p["full_name"].split()[0] for q in PEOPLE) == 1
)
OUTSIDER = next(p for p in PEOPLE if p.get("team") not in (None, ME["team"]))
PROJECT = fixture_records(DEMO_B, "project")[0]["id"]
CASE = load_yaml((DEMO_A / "evals" / "new-person-with-organization.yaml").read_text(encoding="utf-8"))
NEW = next(op for op in CASE["stub_answer"]["ops"] if op["op"] == "person.add")


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path, cfg=cfg)
    yield ws, cfg, store
    store.close()


def first(person: dict) -> str:
    return person["full_name"].split()[0]


def fact(quote: str, **more) -> dict:
    return {"op": "fact", "text": quote, "evidence": {"quote": quote}, **more}


def found(env, ops: list[dict], *, actor: str = "assistant") -> list:
    _, cfg, store = env
    raw = "\n".join(op["evidence"]["quote"] for op in ops if "evidence" in op)
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", "SRC-1", raw, "", "untrusted"),
        actor=actor,
    )
    return [p for p in check(cs, ctx) if p.check == LINT]


def test_a_new_persons_dated_promise_recorded_as_a_fact_is_sent_back_to_be_their_action(env):
    quote = f"{NEW['full_name']} from {NEW['org']} will drive the pallet audit by the 20th"
    person = {"op": "person.add", "full_name": NEW["full_name"], "org": NEW["org"]}
    (problem,) = found(env, [person, fact(quote)])
    assert (problem.severity, problem.op) == ("return", 1)
    assert NEW["full_name"] in problem.message and "action.add" in problem.message


def test_a_teammates_promise_by_first_name_is_sent_back_too(env):
    (problem,) = found(env, [fact(f"{first(TEAMMATE)} will draft the pilot plan by the 30th.")])
    assert problem.op == 0


def test_a_state_no_date_nobody_named_or_words_another_op_quotes_are_left_alone(env):
    assert found(env, [fact(f"{first(TEAMMATE)} will be away on the 20th.")]) == []
    assert found(env, [fact(f"{first(TEAMMATE)} will draft the pilot plan.")]) == []
    assert found(env, [fact("The depot will close by the 20th.")]) == []
    quote = f"{first(TEAMMATE)} will draft the pilot plan by the 30th."
    action = {
        "op": "action.add",
        "text": "Draft the pilot plan",
        "owners": [TEAMMATE["id"]],
        "evidence": {"quote": quote},
    }
    assert found(env, [action, fact(quote)]) == []


def test_another_teams_promise_a_watched_project_and_the_persons_own_note_are_left_alone(env):
    assert found(env, [fact(f"{OUTSIDER['full_name']} will send the figures by the 30th.")]) == []
    quote = f"{first(TEAMMATE)} will draft the pilot plan by the 30th."
    assert found(env, [fact(quote)], actor="pm") == []
    _, _, store = env
    with store.transaction() as tx:
        project = tx.get("project", PROJECT)
        roles = [{"person": ME["id"], "role": "watch"}]
        tx.update("project", PROJECT, {"roles": roles}, _PM, read_version=project.version)
    assert found(env, [fact(quote, project=PROJECT)]) == []


def test_severity_off_turns_it_off(env):
    _, cfg, _ = env
    cfg.checks.lints[LINT] = "off"
    assert found(env, [fact(f"{first(TEAMMATE)} will draft the pilot plan by the 30th.")]) == []


# ---- due-move-missed: a new day for an open action, answered only with a fact or a note ------------------------------


def moved(env, ops: list[dict], note: str, *, actor: str = "assistant") -> list:
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs("REQ-1", None, note, "", "trusted"),
        actor=actor,
    )
    return [p for p in check(cs, ctx) if p.check == "due-move-missed"]


MOVE = "Done, and my review can wait until Oct 20."


def open_action(env) -> str:
    _, _, store = env
    return next(a.id for a in store.read().list("action") if a.data["status"] == "open")


def test_a_new_day_for_an_open_action_answered_only_with_a_fact_is_sent_back(env):
    note = {"op": "fact", "text": "Review can wait", "evidence": {"quote": "my review can wait until Oct 20"}}
    (problem,) = moved(env, [note], MOVE)
    assert problem.severity == "return" and "record.set" in problem.message


def test_a_moved_due_quoting_the_words_a_day_no_rule_reads_or_the_persons_own_change_is_left_alone(env):
    quote = "my review can wait until Oct 20"
    move = {"op": "record.set", "kind": "action", "id": open_action(env), "field": "due", "value": "2026-10-20"}
    assert moved(env, [move | {"evidence": {"quote": quote}}], MOVE) == []
    assert moved(env, [], "My review can wait until later.") == []
    assert moved(env, [], MOVE, actor="pm") == []


# ---- record.set due on an action that is no longer open -----------------------------------------------------------


def test_a_new_day_on_a_finished_action_is_refused(env):
    _, _, store = env
    action = open_action(env)
    with store.transaction() as tx:
        found_action = tx.get("action", action)
        tx.update("action", action, {"status": "done"}, _PM, read_version=found_action.version)
    move = {"op": "record.set", "kind": "action", "id": action, "field": "due", "value": "2026-10-20"}
    _, cfg, _ = env
    cs = CHANGESET.validate_python({"ops": [move | {"evidence": {"quote": "can wait until Oct 20"}}]})
    ctx = Context(store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-1", None, MOVE, "", "trusted"))
    (problem,) = [p for p in check(cs, ctx) if p.check == "targets"]
    assert problem.severity == "refuse" and "done" in problem.message


# ---- owed-to-missing: the person's own action for something another person has ---------------------------------------


def owed(env, op: dict) -> list:
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-1", None, op["text"], "", "trusted")
    )
    return [p for p in check(cs, ctx) if p.check == "owed-to-missing"]


def test_the_persons_own_action_for_someones_thing_owed_to_nobody_is_sent_back_naming_them(env):
    text = f"Return {TEAMMATE['full_name']}'s library book"
    (problem,) = owed(env, {"op": "action.add", "text": text, "owners": [ME["id"]], "evidence": {"quote": text}})
    assert problem.severity == "return" and TEAMMATE["id"] in problem.message


def test_an_action_owed_to_someone_already_or_owned_by_someone_else_is_left_alone(env):
    text = f"Return {TEAMMATE['full_name']}'s library book"
    base = {"op": "action.add", "text": text, "evidence": {"quote": text}}
    assert owed(env, base | {"owners": [ME["id"]], "promised_to": [TEAMMATE["id"]]}) == []
    assert owed(env, base | {"owners": [TEAMMATE["id"]]}) == []
    plain = "Return the library book"
    assert owed(env, {"op": "action.add", "text": plain, "owners": [ME["id"]], "evidence": {"quote": plain}}) == []


# ---- project-start-as-fact: a named start that no project has, kept only as a fact ---------------------------------


def started(env, ops: list[dict]) -> list:
    _, cfg, store = env
    raw = "\n".join(op["evidence"]["quote"] for op in ops if "evidence" in op)
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-1", "SRC-1", raw, "", "untrusted")
    )
    return [p for p in check(cs, ctx) if p.check == "project-start-as-fact"]


NEW_WORK = load_yaml((DEMO_A / "evals" / "project-no-record.yaml").read_text(encoding="utf-8"))
START = next(op for op in NEW_WORK["stub_answer"]["ops"] if op["op"] == "project.add")


def test_a_named_start_no_project_has_kept_only_as_a_fact_is_sent_back(env):
    (problem,) = started(env, [fact(f"We are {START['evidence']['quote']}.")])
    assert problem.severity == "return" and START["name"] in problem.message


def test_a_known_project_a_proposed_one_or_a_start_with_no_name_is_left_alone(env):
    known = fixture_records(DEMO_B, "project")[0]["name"]
    assert started(env, [fact(f"We are starting {known} next month.")]) == []
    proposed = {"op": "project.add", "name": START["name"], "evidence": START["evidence"]}
    assert started(env, [proposed, fact(f"We are {START['evidence']['quote']}.")]) == []
    assert started(env, [fact("We are starting the pilot next month.")]) == []


# ---- claim-asked-of-the-person: a question about someone's claim goes to them ---------------------------------------


def claimed(env, ops: list[dict], raw: str) -> list:
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-1", "SRC-1", raw, "", "untrusted")
    )
    return [p for p in check(cs, ctx) if p.check == "claim-asked-of-the-person"]


CLAIM = f"{TEAMMATE['full_name']} told me the stock arrives on November 10, but the quote says October 30."


def question(to: str) -> dict:
    title = "Does the stock arrive on November 10 or October 30?"
    return {"op": "question.add", "to": to, "kind": "question", "title": title, "text": "The quote disagrees."}


def test_a_question_to_the_person_about_someones_claim_is_sent_back_to_ask_them(env):
    (problem,) = claimed(env, [question(ME["id"])], CLAIM)
    assert problem.severity == "return" and TEAMMATE["id"] in problem.message


def test_a_question_to_the_claimant_or_one_with_no_claim_in_the_words_is_left_alone(env):
    assert claimed(env, [question(TEAMMATE["id"])], CLAIM) == []
    assert claimed(env, [question(ME["id"])], "The stock arrives on November 10, but the quote says October 30.") == []


# ---- owner-mail-unanswered: mail from whoever owes a promise, about it, answered with nothing on it -----------------


OWER = next(p for p in PEOPLE if p.get("how_to_reach", {}).get("email") and p["id"] != ME["id"])


def promise_of(env, text: str) -> str:
    _, _, store = env
    fields = {"text": text, "owners": [{"person": OWER["id"]}], "promised_to": [ME["id"]], "status": "open"}
    with store.transaction() as tx:
        return tx.create("action", fields, _PM).id


def answered(env, ops: list[dict], body: str) -> list:
    _, cfg, store = env
    raw = f"From: {OWER['full_name']} <{OWER['how_to_reach']['email']}>\nTo: {ME['full_name']}\n\n{body}\n"
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-1", "SRC-1", raw, "", "untrusted")
    )
    return [p for p in check(cs, ctx) if p.check == "owner-mail-unanswered"]


def test_mail_from_whoever_owes_a_promise_about_it_answered_with_nothing_on_it_is_sent_back(env):
    action = promise_of(env, "Confirm the interview time")
    (problem,) = answered(env, [], "The interview sounds interesting.")
    assert problem.severity == "return" and action in problem.message


def test_news_on_the_promise_or_mail_about_something_else_is_left_alone(env):
    action = promise_of(env, "Confirm the interview time")
    quote = "The interview sounds interesting."
    news = {"op": "action.news", "id": action, "text": "No time yet.", "evidence": {"quote": quote}}
    assert answered(env, [news], quote) == []
    assert answered(env, [], "Lovely weather today.") == []


# ---- promise-owed-to-reader: the sender's own promise in mail is owed to whoever it went to ------------------------


def owed_mail(env, op: dict, body: str) -> list:
    _, cfg, store = env
    to = f"{ME['full_name']} <{ME['full_name'].lower().replace(' ', '.')}@example.com>"
    raw = f"From: {OWER['full_name']} <{OWER['how_to_reach']['email']}>\nTo: {to}\n\n{body}\n"
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(
        store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-1", "SRC-1", raw, "", "untrusted")
    )
    return [p for p in check(cs, ctx) if p.check == "promise-owed-to-reader"]


def test_the_senders_own_promise_in_mail_owed_to_nobody_is_sent_back_naming_who_it_went_to(env):
    quote = "I'll send the figures toward the end of the month."
    op = {"op": "action.add", "text": "Send the figures", "owners": [OWER["id"]], "evidence": {"quote": quote}}
    (problem,) = owed_mail(env, op, quote)
    assert problem.severity == "return" and ME["id"] in problem.message


def test_a_promise_already_owed_someone_else_owning_it_or_no_own_promise_words_is_left_alone(env):
    quote = "I'll send the figures toward the end of the month."
    op = {"op": "action.add", "text": "Send the figures", "owners": [OWER["id"]], "evidence": {"quote": quote}}
    assert owed_mail(env, op | {"promised_to": [ME["id"]]}, quote) == []
    assert owed_mail(env, op | {"owners": [ME["id"]]}, quote) == []
    plain = "The figures go out toward the end of the month."
    assert owed_mail(env, op | {"evidence": {"quote": plain}}, plain) == []
