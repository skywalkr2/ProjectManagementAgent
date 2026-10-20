"""Conditions and "before" (design 6.33; the functional designer's answer F21, B-7).

A promise whose due words wait for something to happen ("once the keys arrive") is on hold from the start, waiting for
those words, not merely dateless. "Before <a meeting>" is due at that calendar entry when the words name a known one,
and dateless with the words kept when they don't. Which condition words mean on hold, which mean the entry they name
and which only leave the date open are language settings, beside `due_condition_words`. Names and ids come from the
fixtures."""

from __future__ import annotations

import pytest

from engine.ai.adapters.stub import set_responder
from engine.due_phrases import DEFAULT_BEFORE_WORDS, DEFAULT_CONDITION_WORDS, DEFAULT_HOLD_WORDS, is_condition
from engine.storage import Store
from engine.workspace import init_workspace
from tests.conftest import DEMO_B
from tests.test_promises import (  # noqa: F401
    _SETUP,
    NOW,
    action,
    answer,
    event,
    made_action,
    run,
    someone,
)

TODAY = NOW.date()


@pytest.fixture
def env(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    cfg = ws.config(env={})
    store = Store(ws.db_path)
    yield ws, cfg, store
    store.close()
    set_responder(None)


def promise(words: str, *, due: str | None = None, hold: str | None = None) -> str:
    said = "They will get back to us."
    op = {
        "op": "action.add",
        "text": "Get back to us",
        "owners": [someone()["id"]],
        "due_words": words,
        "evidence": {"quote": said},
    }
    if due is not None:
        op["due"] = due
    if hold is not None:
        op["waiting_for"] = hold
    answer(op)
    return said


def made_from(env, words: str, **more) -> dict:
    _, _, store = env
    (outcome,), _ = run(env, pasted=promise(words, **more))
    assert outcome["status"] == "applied", outcome
    return made_action(store, outcome)


@pytest.mark.parametrize(
    "words",
    [
        "once the keys arrive",
        "Once I receive the keys",
        "after the workshop",
        "when the measurements arrive",
        "whenever the proofs are back",
        "until you publish it",
        "as soon as I've spoken to the surveyor",
        "within two working days of receiving the files",
    ],
)
def test_a_condition_that_waits_for_something_is_on_hold_from_the_start_waiting_for_its_words(env, words):
    made = made_from(env, words, due="2026-10-20")
    assert made["status"] == "open" and made["due"] is None and made["due_words"] == words
    assert made["on_hold"] == {"waiting_for": words, "since": TODAY.isoformat()}


@pytest.mark.parametrize("words", ["sometime soon", "eventually", "soon"])
def test_words_that_only_leave_the_date_open_are_dateless_and_not_on_hold(env, words):
    made = made_from(env, words, due="2026-10-20")
    assert (made["due"], made["due_words"], made["on_hold"]) == (None, words, None)


def test_before_words_that_name_nothing_known_are_dateless_with_the_words_kept(env):
    made = made_from(env, "before his leave starts", due="2026-10-20")
    assert (made["due"], made["due_words"], made["due_event"], made["on_hold"]) == (
        None,
        "before his leave starts",
        None,
        None,
    )


def test_before_a_known_meeting_is_due_at_that_entry_and_moves_with_it(env):
    from engine.applier import follow_event

    _, cfg, store = env
    meeting = event(store, "2026-10-15T15:00", "Print sync")
    event(store, "2026-10-02T15:00", "Print sync")  # an earlier one, already past
    made = made_from(env, "before the print sync", due="2026-12-01")
    assert (made["due"], made["due_event"], made["due_check"], made["on_hold"]) == ("2026-10-15", meeting, False, None)
    assert made["due_words"] == "before the print sync"
    with store.transaction() as tx:
        tx.update(
            "event", meeting, {"start": "2026-10-20T15:00"}, _SETUP, read_version=tx.get("event", meeting).version
        )
        follow_event(tx, meeting, _SETUP)
    (moved,) = [a for a in store.read().list("action") if a.data["due_event"] == meeting]
    assert moved.data["due"] == "2026-10-20"


def test_before_a_meeting_that_is_not_known_or_already_past_stays_dateless(env):
    _, _, store = env
    event(store, "2026-10-02T15:00", "Print sync")
    made = made_from(env, "before the print sync", due="2026-12-01")
    assert (made["due"], made["due_event"]) == (None, None)
    event(store, "2026-10-15T15:00", "Budget review")
    again = made_from(env, "before the harvest festival")
    assert (again["due"], again["due_event"]) == (None, None)


def test_two_different_meetings_the_words_could_name_leave_it_dateless_and_a_longer_title_is_the_same_meeting(env):
    _, _, store = env
    event(store, "2026-10-15T15:00", "Print sync")
    event(store, "2026-10-16T15:00", "Budget review")
    assert made_from(env, "before the print sync and the budget review")["due_event"] is None
    longer = event(store, "2026-10-17T15:00", "Print sync review")
    assert made_from(env, "before the print sync review")["due_event"] == longer


def test_words_the_rules_read_as_a_date_are_never_a_condition(env):
    made = made_from(env, "by Tuesday")
    assert made["due"] == "2026-10-13" and made["on_hold"] is None


def test_the_hold_the_assistant_names_in_its_op_wins_over_the_words(env):
    made = made_from(env, "once the keys arrive", hold="the keys  arrive")
    assert made["on_hold"]["waiting_for"] == "the keys arrive"


def test_which_words_hold_and_which_name_an_entry_is_the_language_settings(env):
    _, cfg, store = env
    cfg.language.due_hold_words = ["pending"]
    cfg.language.due_condition_words = [*cfg.language.due_condition_words, "pending"]
    held = made_from(env, "pending the survey")
    assert held["on_hold"]["waiting_for"] == "pending the survey"
    unheld = made_from(env, "once the keys arrive")  # no longer a hold word: only dateless
    assert (unheld["due"], unheld["on_hold"]) == (None, None)


def test_the_settings_have_descriptions_defaults_and_demo_values():
    import yaml

    from engine.config.schema import LanguageFile
    from tests.conftest import DEMO_A, DEMO_B

    for key in ("due_hold_words", "due_before_words"):
        assert LanguageFile.model_fields[key].description
    assert LanguageFile().due_hold_words == list(DEFAULT_HOLD_WORDS)
    assert LanguageFile().due_before_words == list(DEFAULT_BEFORE_WORDS)
    for template in (DEMO_A, DEMO_B):
        language = yaml.safe_load((template / "config" / "language.yaml").read_text())
        assert language["due_hold_words"] == list(DEFAULT_HOLD_WORDS)
        assert language["due_before_words"] == list(DEFAULT_BEFORE_WORDS)
        assert language["due_condition_words"] == list(DEFAULT_CONDITION_WORDS)
    for word in DEFAULT_HOLD_WORDS + DEFAULT_BEFORE_WORDS:
        assert is_condition(f"{word} something", DEFAULT_CONDITION_WORDS)


# ---- the evaluation cases that carry conditions ------------------------------------------------


def _condition_case_ids():
    from engine.evaluate import load_cases
    from tests.conftest import DEMO_B

    return [
        c["id"]
        for c in load_cases(DEMO_B)
        if any(
            o["op"] == "action.add" and o.get("due_words") and is_condition(o["due_words"], DEFAULT_CONDITION_WORDS)
            for o in c.get("stub_answer", {}).get("ops", [])
        )
    ]


@pytest.mark.parametrize("case_id", _condition_case_ids())
def test_a_condition_case_expects_a_hold_exactly_when_its_words_wait_for_something(monkeypatch, case_id):
    from tests.conftest import DEMO_B
    from tests.test_evaluate_harness import case_of, run_edited

    case = case_of(DEMO_B, case_id)
    (expected,) = [e for e in case["expect"] if e.get("due_words")]
    assert expected["on_hold"] is is_condition(expected["due_words"], DEFAULT_HOLD_WORDS)
    assert run_edited(monkeypatch, DEMO_B, case_id).passed
