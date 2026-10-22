"""Text written for someone else carries only what they need (design 6.35): none of the app's own ids or terms, and no
long passage quoted back. Both are lints with a severity; the words and the length are settings.

Names and ids come from the fictional workspace's records."""

from __future__ import annotations

from engine.applier import Context, Inputs, check
from engine.names import People
from engine.ops import CHANGESET
from tests import test_scope_slice
from tests.test_scope_slice import PLAIN, outsider, pm_of, pm_record, problems, question

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


# ---- never single a person out in a draft to several people (design 6.35) ------------------------------------------


def two_outsiders(cfg):
    first = outsider(cfg)
    return first, outsider(cfg, skip=(first["id"],))


def written(person) -> str:
    """A person as a message's header line writes them: their name and an address on example.com."""
    return f"{person['full_name']} <{person['full_name'].lower().replace(' ', '.')}@example.com>"


def group_mail(cfg, sender, *others) -> str:
    """A saved message from `sender` to the person and `others`: the group a reply to all of them reaches."""
    to = ", ".join(written(p) for p in [pm_record(cfg), *others])
    return f"From: {written(sender)}\nTo: {to}\nSubject: The proofs\n\nWhen do the proofs ship?"


def reply_op(cfg, text):
    return {
        "op": "action.add",
        "text": "Reply about the proofs",
        "owners": [pm_of(cfg)],
        "reply": text,
        "evidence": {"quote": "When do the proofs ship?"},
    }


def test_a_reply_to_a_group_that_blames_one_member_is_returned_and_names_who(env):
    _, cfg, _ = env
    asker, other = two_outsiders(cfg)
    raw = group_mail(cfg, asker, other)
    blame = f"The proofs are late because {other['full_name']} missed the file deadline."
    (hit,) = problems(env, reply_op(cfg, blame), raw, "singling-out")
    assert hit.severity == "return" and other["full_name"] in hit.message and "on their own" in hit.message
    first_name = other["full_name"].split()[0]
    (again,) = problems(
        env, reply_op(cfg, f"{first_name} forgot to send the file, so the proofs slipped."), raw, "singling-out"
    )
    assert other["full_name"] in again.message


def test_a_reply_to_a_group_that_names_no_miss_or_names_it_without_a_name_is_not_returned(env):
    _, cfg, _ = env
    asker, other = two_outsiders(cfg)
    raw = group_mail(cfg, asker, other)
    for text in (
        f"{other['full_name']}, could you confirm when the file is final?",
        "The file deadline was missed, so the proofs slipped by a week.",
        "The proofs ship on Monday.",
    ):
        assert problems(env, reply_op(cfg, text), raw, "singling-out") == [], text


def test_a_reply_to_one_other_person_is_not_a_group_draft(env):
    _, cfg, _ = env
    asker, other = two_outsiders(cfg)
    raw = f"From: {written(asker)}\nTo: {written(pm_record(cfg))}\nSubject: The proofs\n\nWhen do the proofs ship?"
    text = f"{asker['full_name']} missed the file deadline."
    assert problems(env, reply_op(cfg, text), raw, "singling-out") == []


def test_the_phrases_are_a_setting_and_the_lint_has_a_severity(env):
    _, cfg, _ = env
    asker, other = two_outsiders(cfg)
    raw = group_mail(cfg, asker, other)
    text = f"{other['full_name']} missed the file deadline."
    cfg.language.singling_out_phrases = []
    assert problems(env, reply_op(cfg, text), raw, "singling-out") == []
    cfg.language.singling_out_phrases = ["missed"]
    cfg.checks.lints["singling-out"] = "off"
    assert problems(env, reply_op(cfg, text), raw, "singling-out") == []


def draft_op(cfg, recipients, text):
    return {
        "op": "act.draft",
        "channel": "copy",
        "target": {"kind": "message", "recipients": [{"person": r["full_name"]} for r in recipients]},
        "parts": {"subject": "The proofs", "body": text},
    }


def drafted(env, op):
    """The singling-out problems of an act drafted by the assistant on the person's own request."""
    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    ctx = Context(store, cfg, People(store, cfg), tuple(store.plugins.ops), Inputs("REQ-1", None, "", "", "trusted"))
    return [p for p in check(cs, ctx) if p.check == "singling-out"]


def test_a_drafted_message_to_several_people_is_checked_and_one_to_a_single_person_is_not(env):
    _, cfg, store = env
    first, second = two_outsiders(cfg)
    blame = f"The proofs slipped because {second['full_name']} was late with the file."
    assert [p.check for p in drafted(env, draft_op(cfg, [first, second], blame))] == ["singling-out"]
    assert drafted(env, draft_op(cfg, [second], blame)) == []
