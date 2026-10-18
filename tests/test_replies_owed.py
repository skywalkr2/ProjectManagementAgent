from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from engine.replies_owed import Address, Message, reply_owed


def instant():
    return datetime(2027, 1, 5, 12, tzinfo=UTC)


def message(text="Is the draft ready?"):
    return Message(
        text,
        Address("mira@example.com", "Mira"),
        (Address("rowan@example.com", "Rowan"),),
        (),
        instant() - timedelta(hours=48),
        False,
    )


def response(text):
    return replace(
        message(text),
        from_address=Address("rowan@example.com", "Rowan"),
        to=(Address("mira@example.com", "Mira"),),
        received=instant() - timedelta(hours=1),
    )


def check(item, later=(), wait=24, mine=("rowan@example.com",)):
    return reply_owed(item, mine, later, instant(), wait)


def test_owed_exact_evidence():
    result = check(message())
    assert result.owed is True
    assert result.evidence == ("Is the draft ready?",)


def test_automatic():
    assert check(replace(message(), automatic=True)).owed is False


def test_cc_only():
    item = replace(message(), to=(Address("oren@example.com", "Oren"),), cc=message().to)
    assert check(item).owed is False


def test_to_and_cc_still_direct():
    assert check(replace(message(), cc=message().to)).owed is True


@pytest.mark.parametrize("text", ["Who knows?", "Who cares?", "Why bother?", "What could possibly go wrong?"])
def test_rhetorical(text):
    assert check(message(text)).owed is False


def test_someone_else_named():
    item = replace(message("Oren, is the draft ready?"), cc=(Address("oren@example.com", "Oren"),))
    assert check(item).owed is False


def test_me_named_among_recipients():
    item = replace(message("Rowan, is the draft ready?"), to=message().to + (Address("oren@example.com", "Oren"),))
    assert check(item).owed is True


def test_unknown_named_recipient():
    assert check(message("Tess, is the draft ready?")).owed is None


def test_multiple_recipients_unspecified():
    item = replace(message(), to=message().to + (Address("oren@example.com", "Oren"),))
    assert check(item).owed is None


@pytest.mark.parametrize(
    "text",
    [
        "Is the draft ready? No need to reply.",
        "Is the draft ready? No response required.",
        "Is the draft ready? Don't reply.",
    ],
)
def test_no_reply(text):
    assert check(message(text)).owed is False


def test_fyi_no_question():
    assert check(message("FYI, the draft is ready.")).owed is False


def test_fyi_with_question_unknown():
    assert check(message("FYI: is the draft ready?")).owed is None


def test_wait_not_elapsed():
    assert check(message(), wait=49).owed is False


def test_wait_boundary():
    assert check(message(), wait=48).owed is True


@pytest.mark.parametrize("text", ["Yes.", "No.", "yes", "NO!"])
def test_binary_answer(text):
    assert check(message(), (response(text),)).owed is False


def test_nonanswer_unknown_not_resolved():
    result = check(message(), (response("Thanks for checking. I'll look."),))
    assert result.owed is None
    assert result.evidence == ("Is the draft ready?",)


def test_explicit_answer():
    question = "What time should we meet?"
    assert check(message(question), (response(f'Answer to "{question}": 10:00.'),)).owed is False


def test_explicit_nonanswer():
    question = "What time should we meet?"
    assert check(message(question), (response(f'Answer to "{question}": I do not know.'),)).owed is None


def test_yes_does_not_resolve_work_request():
    assert check(message("Can you send the draft?"), (response("Yes."),)).owed is None


def test_other_person_reply_does_not_answer_for_me():
    later = replace(response("Yes."), from_address=Address("oren@example.com", "Oren"))
    assert check(message(), (later,)).owed is True


def test_automatic_reply_from_me_does_not_resolve():
    assert check(message(), (replace(response("Yes."), automatic=True),)).owed is True


def test_future_response_not_used():
    later = replace(response("Yes."), received=instant() + timedelta(hours=1))
    assert check(message(), (later,)).owed is True


def test_earlier_response_not_used():
    later = replace(response("Yes."), received=message().received - timedelta(seconds=1))
    assert check(message(), (later,)).owed is True


def test_partial_answers_unknown():
    item = message("Is the draft ready? What time should we meet?")
    later = response('Answer to "Is the draft ready?": Yes.')
    result = check(item, (later,))
    assert result.owed is None
    assert result.evidence == ("What time should we meet?",)


def test_multiple_questions_no_reply():
    result = check(message("Is the draft ready? What time should we meet?"))
    assert result.owed is True
    assert len(result.evidence) == 2


def test_alias():
    item = replace(message(), to=(Address("consulting@example.com", "Rowan"),))
    assert check(item, mine=("rowan@example.com", "consulting@example.com")).owed is True


def test_self_sent():
    assert check(response("Is the draft ready?")).owed is False


def test_unknown_flag():
    assert check(replace(message(), automatic=None)).owed is None


@pytest.mark.parametrize("wait", [-1, float("nan"), float("inf"), True, "24"])
def test_invalid_wait(wait):
    assert check(message(), wait=wait).owed is None


def test_no_inferred_request_without_question_mark():
    assert check(message("Please send the draft.")).owed is False


def test_plain_newline_questions():
    result = check(message("Hello Rowan.\nIs the draft ready?\nWhat time should we meet?"))
    assert result.evidence == ("Is the draft ready?", "What time should we meet?")


def test_future_original_unknown():
    assert check(replace(message(), received=instant() + timedelta(days=1))).owed is None


def test_naive_now_unknown():
    now = datetime(2027, 1, 5, 12)  # noqa: DTZ001 -- Floating now must be rejected.
    assert reply_owed(message(), ("rowan@example.com",), (), now, 24).owed is None


def test_email_period_does_not_cut_question():
    question = "Can you send the draft to oren@example.com?"
    assert check(message(question)).evidence == (question,)


def test_decimal_does_not_cut_question():
    question = "Is 3.5 hours enough?"
    assert check(message(question)).evidence == (question,)


def test_all_explicit_answers_resolve():
    item = message("Is the draft ready? What time should we meet?")
    later = response('Answer to "Is the draft ready?": Yes.\nAnswer to "What time should we meet?": 10:00.')
    assert check(item, (later,)).owed is False


def test_every_answer_carries_a_code():
    assert check(message()).code == "owed"
    assert check(message(), wait=49).code == "still_waiting"
    assert check(message(), (response("Thanks, I'll look."),)).code == "needs_reading"
    assert check(replace(message(), automatic=None)).code == "unreadable"
