"""The owner's learning run, fixed (design 6.7, 6.33): a condition is a promise's due words with no date, a reply that
doesn't answer is news on the open action, a moved promise from a quoted thread waits for the person's Keep, and the
words the date reader uses are the language's settings. Cases, ids and quotes come from the fixtures."""

from __future__ import annotations

from importlib import resources

import pytest
import yaml

from engine.due_phrases import DEFAULT_CONDITION_WORDS, DEFAULT_LEAD_WORDS, DEFAULT_ORDINAL_SUFFIXES, is_condition
from engine.evaluate import load_cases
from engine.names import People
from engine.packet import _open_actions
from engine.storage import Store, WriteContext
from engine.workspace import init_workspace
from tests.conftest import DEMO_A, DEMO_B
from tests.test_evaluate_harness import case_of, run_edited, with_ops

_SETUP = WriteContext(actor="pm", trust="trusted", op="test.learning-run")


def _ideal(case):
    return case["stub_answer"]["ops"]


def _case_ids(template, test):
    return [c["id"] for c in load_cases(template) if test(c)]


def _promise_ops(case):
    return [o for o in _ideal(case) if o["op"] == "action.add" and o.get("due_words")]


CONDITION_CASES = _case_ids(
    DEMO_B, lambda c: any(is_condition(o["due_words"], DEFAULT_CONDITION_WORDS) for o in _promise_ops(c))
)
NON_ANSWER_CASES = _case_ids(
    DEMO_B, lambda c: any(e.get("op") == "action.news" for e in c.get("expect", [])) and "no-answer" in c["id"]
)
RELAXED_CASES = [
    "promise-025-send-minutes-pella",
    "promise-026-send-varo-missing",
    "promise-035-send-ansel-spreadsheet",
    "promise-068-resend-avery-link",
]


# ---- a condition is the due: its words, no date ------------------------------------------------------------------


def test_the_cases_that_expect_a_condition_are_found():
    assert len(CONDITION_CASES) >= 8, CONDITION_CASES
    for case_id in CONDITION_CASES:
        expected = [e for e in case_of(DEMO_B, case_id)["expect"] if e.get("due_words")]
        assert expected and all(e["due"] is None for e in expected), case_id


@pytest.mark.parametrize("case_id", CONDITION_CASES)
def test_a_condition_keeps_its_words_and_never_gets_a_date(monkeypatch, case_id):
    case = case_of(DEMO_B, case_id)
    assert run_edited(monkeypatch, DEMO_B, case_id).passed
    # The model puts a date on the condition anyway: the rules drop it, so the case still passes.
    dated = {**case["stub_answer"], "ops": [{**o, "due": "2026-12-01"} for o in _ideal(case)]}
    assert run_edited(monkeypatch, DEMO_B, case_id, stub_answer=dated).passed
    # The words left out (only a hold given) is a miss.
    held = {
        **case["stub_answer"],
        "ops": [{k: v for k, v in o.items() if k != "due_words"} | {"waiting_for": "something"} for o in _ideal(case)],
    }
    assert not run_edited(monkeypatch, DEMO_B, case_id, stub_answer=held).passed


@pytest.mark.parametrize("case_id", RELAXED_CASES)
def test_words_that_are_neither_a_date_nor_a_condition_may_keep_the_models_date_marked_to_check(monkeypatch, case_id):
    case = case_of(DEMO_B, case_id)
    assert all("due" not in e for e in case["expect"]), "the date is the model's own, kept and checked, or none"
    assert not is_condition(_promise_ops(case)[0]["due_words"], DEFAULT_CONDITION_WORDS)
    assert run_edited(monkeypatch, DEMO_B, case_id).passed
    dated = {**case["stub_answer"], "ops": [{**o, "due": "2026-11-02"} for o in _ideal(case)]}
    assert run_edited(monkeypatch, DEMO_B, case_id, stub_answer=dated).passed


# ---- a reply that doesn't answer is news -------------------------------------------------------------------------


def test_the_non_answer_cases_are_found():
    assert len(NON_ANSWER_CASES) >= 7, NON_ANSWER_CASES


@pytest.mark.parametrize("case_id", NON_ANSWER_CASES)
def test_a_reply_that_does_not_answer_is_news_never_an_ending_and_never_nothing(monkeypatch, case_id):
    case = case_of(DEMO_B, case_id)
    (news,) = _ideal(case)
    assert news["op"] == "action.news" and run_edited(monkeypatch, DEMO_B, case_id).passed
    closed = {**case["stub_answer"], "ops": [{"op": "action.close", "id": news["id"], "evidence": news["evidence"]}]}
    result = run_edited(monkeypatch, DEMO_B, case_id, stub_answer=closed)
    assert not result.passed and result.forbidden == [f"op=action.close, id={news['id']}"]
    nothing = {"summary": "Nothing to record.", "ops": []}
    assert not run_edited(monkeypatch, DEMO_B, case_id, stub_answer=nothing).passed
    fact = {"op": "fact", "text": "The reply was friendly.", "evidence": news["evidence"]}
    assert run_edited(monkeypatch, DEMO_B, case_id, stub_answer=with_ops(case, fact)).passed, "a fact weighs nothing"


def test_the_prompt_and_the_playbook_say_a_reply_that_does_not_answer_is_news():
    prompt = resources.files("engine.prompts").joinpath("notes.md").read_text(encoding="utf-8")
    playbook = resources.files("engine.playbook.guidance").joinpath("notes.md").read_text(encoding="utf-8")
    for word in ("acknowledge", "defer", "action.news", "nothing to record"):
        assert word in prompt, word
    for word in ("acknowledge", "defer", "news on the open action"):
        assert word in playbook, word


def test_the_prompt_and_the_playbook_say_a_condition_is_the_due_words_with_no_date():
    prompt = resources.files("engine.prompts").joinpath("notes.md").read_text(encoding="utf-8")
    playbook = resources.files("engine.playbook.guidance").joinpath("notes.md").read_text(encoding="utf-8")
    assert "A condition with no date is the due" in prompt and '"due_words"' in prompt and 'no "due"' in prompt
    assert "is a condition: with no day named, its words are the due" in playbook


def test_a_condition_with_a_date_keeps_the_date_as_its_due_and_the_condition_in_its_text():
    """A promise with both a day and a condition keeps the day's words as its due words and the condition in its text
    and its "waiting_for", so the date isn't lost (the owner's re-run, B-10: the condition replaced the date)."""
    prompt = resources.files("engine.prompts").joinpath("notes.md").read_text(encoding="utf-8")
    playbook = resources.files("engine.playbook.guidance").joinpath("notes.md").read_text(encoding="utf-8")
    assert "A condition with a date keeps both, apart" in prompt and 'the condition goes in "waiting_for"' in prompt
    assert 'The action\'s "text" says the whole promise, its condition included' in prompt
    assert "keeps the day as its due and the condition beside it" in playbook


@pytest.mark.parametrize("case_id", ["promise-owed-cc-team", "promise-owed-named-third-party", "promise-owed-we-team"])
def test_a_promise_is_owed_to_whoever_it_is_said_to(monkeypatch, case_id):
    """Cc'd, a named third party, a team's "we'll": the instructions say who it is owed to, and each case holds it."""
    prompt = resources.files("engine.prompts").joinpath("notes.md").read_text(encoding="utf-8")
    playbook = resources.files("engine.playbook.guidance").joinpath("notes.md").read_text(encoding="utf-8")
    assert "It is owed to whoever it is said to" in prompt and "It is owed to whoever it is said to" in playbook
    assert run_edited(monkeypatch, DEMO_B, case_id).passed


# ---- a moved promise from a quoted thread waits for the person's Keep --------------------------------------------


def test_the_move_of_a_promise_that_exists_is_held_for_keep_not_applied_as_a_direct_date_change(monkeypatch):
    case = case_of(DEMO_A, "quoted-thread-action-exists")
    given = case["given"][0]["fields"]
    assert given["promised_to"] and case["expect"][0]["op"] == "action.move"
    assert run_edited(monkeypatch, DEMO_A, case["id"]).passed
    (ideal,) = _ideal(case)
    direct = {
        **case["stub_answer"],
        "ops": [
            {
                "op": "record.set",
                "kind": "action",
                "id": ideal["id"],
                "field": "due",
                "value": "2026-10-22",
                "evidence": ideal["evidence"],
            }
        ],
    }
    result = run_edited(monkeypatch, DEMO_A, case["id"], stub_answer=direct)
    assert not result.passed and result.forbidden == [f"op=record.set, id={ideal['id']}"]


def test_the_promise_said_again_with_its_new_date_is_the_same_held_move(monkeypatch):
    case = case_of(DEMO_A, "quoted-thread-action-exists")
    (ideal,) = _ideal(case)
    given = case["given"][0]["fields"]
    names = {p["id"]: p["full_name"] for p in _people(DEMO_A)}
    again = {
        **case["stub_answer"],
        "ops": [
            {
                "op": "action.add",
                "text": given["text"],
                "owners": [names[given["owners"][0]["person"]]],
                "promised_to": [names[given["promised_to"][0]]],
                "basis": "said",
                "due_words": ideal["due_words"],
                "evidence": ideal["evidence"],
            }
        ],
    }
    restated = run_edited(monkeypatch, DEMO_A, case["id"], stub_answer=again)
    assert restated.passed, (restated.missing, restated.forbidden, restated.extra)


def _people(template):
    from tests.conftest import fixture_records

    return fixture_records(template, "person")


# ---- the open actions say which ones are promises ----------------------------------------------------------------


def test_an_open_promise_says_who_it_is_promised_to_and_a_plain_to_do_says_nothing_of_it(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    try:
        people = [p for p in _people(DEMO_B)]
        owner, owed = people[1], people[2]
        with store.transaction() as tx:
            promise = tx.create(
                "action",
                {
                    "text": "Send the floor plan to the printer",
                    "owners": [{"person": owner["id"]}],
                    "promised_to": [owed["id"]],
                },
                _SETUP,
            )
            plain = tx.create("action", {"text": "Order the bookmarks", "owners": [{"person": owner["id"]}]}, _SETUP)
        listing = _open_actions(store, People(store, cfg))
        lines = {line.split()[1]: line for line in listing.splitlines()}
        assert f"promised to {owed['full_name']}" in lines[promise.id]
        assert "promised" not in lines[plain.id]
    finally:
        store.close()


# ---- the language settings carry the date reader's words ---------------------------------------------------------


@pytest.mark.parametrize("template", [DEMO_A, DEMO_B], ids=lambda p: p.name)
def test_both_fictional_workspaces_carry_the_date_readers_words(template):
    language = yaml.safe_load((template / "config" / "language.yaml").read_text())
    assert language["due_lead_words"] == list(DEFAULT_LEAD_WORDS)
    assert language["due_ordinal_suffixes"] == list(DEFAULT_ORDINAL_SUFFIXES)
    assert language["due_condition_words"] == list(DEFAULT_CONDITION_WORDS)


def test_the_settings_have_descriptions_and_the_defaults_the_reader_starts_from(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    language = ws.config(env={}).language
    from engine.config.schema import LanguageFile

    for key in ("due_lead_words", "due_ordinal_suffixes", "due_condition_words"):
        assert LanguageFile.model_fields[key].description
    assert language.due_lead_words == list(DEFAULT_LEAD_WORDS)
    assert LanguageFile().due_condition_words == list(DEFAULT_CONDITION_WORDS)


def test_a_lessons_breadth_is_read_from_the_persons_words_and_a_mistake_always_teaches_the_narrow_one():
    """A named person or project, a role or plural group, or "always", "every" or "never" set how far a lesson reaches,
    and a correction too small to generalize still proposes the narrow lesson (design 6.22)."""
    prompt = resources.files("engine.prompts").joinpath("learn-correction.md").read_text(encoding="utf-8")
    playbook = resources.files("engine.playbook.guidance").joinpath("learn-correction.md").read_text(encoding="utf-8")
    assert "Read the breadth from the PM's words" in prompt and 'only "always", "every" or "never"' in prompt
    assert "propose the narrow lesson" in prompt and "only about this one item" not in prompt
    assert "The person's words set the breadth" in playbook and "still teaches the narrow lesson" in playbook


def test_the_prompt_says_who_owns_shared_work_and_where_a_direct_choice_and_a_disputed_claim_go():
    """The owner's re-run (B-10): a task two people do together is one action with both owners
    (production-checkin), a choice asked of the person directly is a reply they owe (decision-for-pm), two accounts that
    disagree go to the one quoted (follow-up-goes-to-who-made-the-claim), and a colon inside an item is its text
    (colon-in-title)."""
    prompt = " ".join(resources.files("engine.prompts").joinpath("notes.md").read_text(encoding="utf-8").split())
    playbook = " ".join(
        resources.files("engine.playbook.guidance").joinpath("notes.md").read_text(encoding="utf-8").split()
    )
    assert "Work two people do together" in prompt and 'one action with both as owners and no "promised_to"' in prompt
    assert "Work two people do together is one action with both as owners" in playbook
    assert "is a reply the PM owes (below), not a decision question" in prompt
    assert "a choice someone asks the PM directly, which is a reply the PM owes" in playbook
    assert "are a follow-up to the person quoted as saying it, not a question to the PM" in prompt
    assert "a colon inside an item" in prompt


def test_a_reply_owed_with_no_recorded_answer_also_asks_whoever_the_routing_names():
    """The routing pair (B-10): a question asked of the person that no fact answers is a reply owed, and a question to
    the person a "Who answers what" entry names, so the reply can be drafted once they answer."""
    prompt = " ".join(resources.files("engine.prompts").joinpath("notes.md").read_text(encoding="utf-8").split())
    assert 'a "Who answers what" entry names who answers that kind of question, also ask that person' in prompt
    assert "the reply owed and that question are the whole answer" in prompt
