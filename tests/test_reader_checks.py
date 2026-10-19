"""Text written for someone else carries only what they need (design 6.35): none of the app's own ids or terms, and no
long passage quoted back. Both are lints with a severity; the words and the length are settings.

Names and ids come from the fictional workspace's records."""

from __future__ import annotations

from tests import test_scope_slice
from tests.test_scope_slice import PLAIN, outsider, pm_of, problems, question

env = test_scope_slice.env  # the scope tests' workspace fixture


def found(env, op, name):
    return problems(env, op, "", name)


def test_a_record_id_or_an_internal_term_in_a_question_for_someone_else_is_returned(env):
    _, cfg, _ = env
    them = outsider(cfg)
    (by_id,) = found(env, question(cfg, them, PLAIN, text="This is about ACT-12 from last week."), "bookkeeping")
    assert "ACT-12" in by_id.message and by_id.severity == "return"
    (by_term,) = found(env, question(cfg, them, PLAIN, text="The changeset shows the plan moved."), "bookkeeping")
    assert "changeset" in by_term.message
    assert found(env, question(cfg, them, PLAIN, text="The plan moved to next week."), "bookkeeping") == []


def test_a_question_to_the_person_themselves_is_not_checked(env):
    _, cfg, _ = env
    me = {"full_name": pm_of(cfg)}
    assert found(env, question(cfg, me, PLAIN, text="About ACT-12 in the changeset."), "bookkeeping") == []


def test_a_long_quote_back_is_returned_and_the_length_is_a_setting(env):
    _, cfg, _ = env
    them = outsider(cfg)
    long = " ".join(["word"] * 30)
    (hit,) = found(env, question(cfg, them, PLAIN, text=f'You wrote "{long}".'), "long-quote")
    assert "30 words" in hit.message
    assert found(env, question(cfg, them, PLAIN, text='You wrote "the plan is late".'), "long-quote") == []
    cfg.checks.tuning.long_quote.max_words = 40
    assert found(env, question(cfg, them, PLAIN, text=f'You wrote "{long}".'), "long-quote") == []


def test_a_drafted_reply_is_checked_the_same_way(env):
    _, cfg, _ = env
    me = next(p for p in test_scope_slice.PEOPLE if p["id"] == pm_of(cfg))
    reply = {
        "op": "action.add",
        "text": "Reply about the plan",
        "owners": [me["full_name"]],
        "reply": "Per the ledger, it ships Friday.",
        "evidence": {"quote": "When does it ship?"},
    }
    (hit,) = found(env, reply, "bookkeeping")
    assert "ledger" in hit.message


def test_the_internal_terms_are_a_setting(env):
    _, cfg, _ = env
    them = outsider(cfg)
    cfg.language.internal_terms = []
    assert found(env, question(cfg, them, PLAIN, text="The changeset shows it."), "bookkeeping") == []
