"""Fictional email examples for conservative reply separation."""

from collections import Counter

import pytest

from engine.reply_split import Split, split_message


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", Split("", "", "", False)),
        ("I'll send it Friday.", Split("I'll send it Friday.", "", "", False)),
        ("Mira, I'll call tomorrow.\n", Split("Mira, I'll call tomorrow.\n", "", "", False)),
        ("\n\n", Split("\n\n", "", "", False)),
        ("A\r\nB\r\n", Split("A\r\nB\r\n", "", "", False)),
        ("> Earlier promise.\n", Split("", "> Earlier promise.\n", "", False)),
        ("> Earlier.\n> More.\n", Split("", "> Earlier.\n> More.\n", "", False)),
        ("New note.\n> Earlier.\n", Split("New note.\n", "> Earlier.\n", "", False)),
        ("> Question?\nYes, Friday.\n", Split("Yes, Friday.\n", "> Question?\n", "", False)),
        (
            "> When?\nI'll send it Friday.\n> Which file?\nThe draft.\n",
            Split("I'll send it Friday.\nThe draft.\n", "> When?\n> Which file?\n", "", False),
        ),
        (">> Nested.\n", Split("", ">> Nested.\n", "", False)),
        ("  > Indented quote.\n", Split("", "  > Indented quote.\n", "", False)),
        ("On Friday, Mira wrote:\nOld text.\n", Split("", "On Friday, Mira wrote:\nOld text.\n", "", False)),
        (
            "I'll reply tomorrow.\nOn Fri, 6 Nov 2026, Mira wrote:\nOld text.\n",
            Split("I'll reply tomorrow.\n", "On Fri, 6 Nov 2026, Mira wrote:\nOld text.\n", "", False),
        ),
        (
            "On 2026-11-06 at 09:00, Mira <mira@example.com> wrote:\n> Old.\nNew answer.\n",
            Split("New answer.\n", "On 2026-11-06 at 09:00, Mira <mira@example.com> wrote:\n> Old.\n", "", False),
        ),
        (
            "On November 6, 2026,\nMira <mira@example.com> wrote:\nOld.\n",
            Split("", "On November 6, 2026,\nMira <mira@example.com> wrote:\nOld.\n", "", False),
        ),
        ("On yesterday, Oren wrote:\nOld.\n", Split("", "On yesterday, Oren wrote:\nOld.\n", "", False)),
        ("ON FRIDAY, OREN WROTE:\nOld.\n", Split("", "ON FRIDAY, OREN WROTE:\nOld.\n", "", False)),
        (
            "On this project, Mira wrote:\nI'll send the draft.\n",
            Split("On this project, Mira wrote:\nI'll send the draft.\n", "", "", False),
        ),
        ("On Friday I'll call Mira.\n", Split("On Friday I'll call Mira.\n", "", "", False)),
        (
            "On Friday, Mira wrote:\n> Question?\nI'll call Friday.\n> Thanks.\n",
            Split("I'll call Friday.\n", "On Friday, Mira wrote:\n> Question?\n> Thanks.\n", "", False),
        ),
        ("-----Original Message-----\nOld.\n", Split("", "-----Original Message-----\nOld.\n", "", False)),
        (
            "My note.\n-----Original Message-----\nOld.\n",
            Split("My note.\n", "-----Original Message-----\nOld.\n", "", False),
        ),
        (
            "Please review.\nBegin forwarded message:\nOld promise.\n",
            Split("Please review.\n", "Begin forwarded message:\nOld promise.\n", "", True),
        ),
        (
            "I'll handle this.\n---------- Forwarded message ---------\nOld.\n",
            Split("I'll handle this.\n", "---------- Forwarded message ---------\nOld.\n", "", True),
        ),
        ("begin forwarded message:\nOld.", Split("", "begin forwarded message:\nOld.", "", True)),
        ("> Begin forwarded message:\nNew.\n", Split("New.\n", "> Begin forwarded message:\n", "", False)),
        ("Original Message is the title.\n", Split("Original Message is the title.\n", "", "", False)),
        ("Begin forwarded message is a phrase.\n", Split("Begin forwarded message is a phrase.\n", "", "", False)),
        ("New.\n-- \nRowan\n", Split("New.\n", "", "-- \nRowan\n", False)),
        (
            "New.\n-- \nRowan\nI promise reliable service.\nrowan@example.com\n",
            Split("New.\n", "", "-- \nRowan\nI promise reliable service.\nrowan@example.com\n", False),
        ),
        ("New.\n--\nStill new.\n", Split("New.\n--\nStill new.\n", "", "", False)),
        ("New.\nSent from my phone\n", Split("New.\n", "", "Sent from my phone\n", False)),
        ("New.\nsent from my tablet", Split("New.\n", "", "sent from my tablet", False)),
        (
            "New.\nSent from my mobile device, excuse typos.\n",
            Split("New.\n", "", "Sent from my mobile device, excuse typos.\n", False),
        ),
        (
            "Sent from my office yesterday.\nI'll resend tomorrow.\n",
            Split("Sent from my office yesterday.\nI'll resend tomorrow.\n", "", "", False),
        ),
        ("Sent from my office.\n", Split("Sent from my office.\n", "", "", False)),
        (
            "Sent from my phone\nActually, I'll call Friday.\n",
            Split("Sent from my phone\nActually, I'll call Friday.\n", "", "", False),
        ),
        (
            "New.\nThis email is confidential and intended only for the intended recipient.\n",
            Split("New.\n", "", "This email is confidential and intended only for the intended recipient.\n", False),
        ),
        (
            "New.\nThis email and any attachments are confidential.\nIf received in error, delete it.\n",
            Split(
                "New.\n",
                "",
                "This email and any attachments are confidential.\nIf received in error, delete it.\n",
                False,
            ),
        ),
        (
            "New.\nConfidentiality notice: This message is for the intended recipient only.\n",
            Split("New.\n", "", "Confidentiality notice: This message is for the intended recipient only.\n", False),
        ),
        ("This email is confidential.\n", Split("This email is confidential.\n", "", "", False)),
        (
            "This message is confidential and for the intended recipient.\n\nI'll call Mira tomorrow.\n",
            Split(
                "This message is confidential and for the intended recipient.\n\nI'll call Mira tomorrow.\n",
                "",
                "",
                False,
            ),
        ),
        ("Confidential\nI'll send it Friday.\n", Split("Confidential\nI'll send it Friday.\n", "", "", False)),
        (
            "> -- \n> I'll always help.\nNew.\n",
            Split("New.\n", "> -- \n> I'll always help.\n", "", False),
        ),
        (
            "New.\n-- \nRowan\nOn Friday, Mira wrote:\nOld.\n",
            Split("New.\n", "On Friday, Mira wrote:\nOld.\n", "-- \nRowan\n", False),
        ),
        (
            "On Friday, Mira wrote:\n> When?\nFriday.\n-- \nRowan\n> Thanks.\nI'll send two copies.\n",
            Split(
                "Friday.\nI'll send two copies.\n",
                "On Friday, Mira wrote:\n> When?\n> Thanks.\n",
                "-- \nRowan\n",
                False,
            ),
        ),
        ("On Friday, Mira wrote:\n", Split("", "On Friday, Mira wrote:\n", "", False)),
        ("-- \nI promise to help.\n", Split("", "", "-- \nI promise to help.\n", False)),
        ("New.\r\n-- \r\nRowan\r\n", Split("New.\r\n", "", "-- \r\nRowan\r\n", False)),
        ("New.\nSent from my phone\n\n", Split("New.\n", "", "Sent from my phone\n\n", False)),
        ("Mira wrote: I'll send it Friday.\n", Split("Mira wrote: I'll send it Friday.\n", "", "", False)),
    ],
)
def test_body_examples(text, expected):
    result = split_message(text)
    assert result == expected
    assert Counter(result.new + result.quoted + result.signature) == Counter(text)
    assert len(result.new) + len(result.quoted) + len(result.signature) == len(text)
    assert split_message(text) == result


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_outlook_header_block(ending):
    header = ending.join(
        [
            "From: Mira <mira@example.com>",
            "Sent: Friday, November 6, 2026 09:00",
            "To: Rowan <rowan@example.com>",
            "Subject: Draft",
            "Old promise.",
            "",
        ]
    )
    result = split_message("I'll follow up tomorrow." + ending + header)
    assert result == Split("I'll follow up tomorrow." + ending, header, "", False)


def test_outlook_with_cc_and_blank_lines():
    header = (
        "From: Mira <mira@example.com>\n\nSent: Friday\nTo: Rowan <rowan@example.com>\n"
        "Cc: Oren <oren@example.com>\nSubject: Review\nEarlier promise.\n"
    )
    assert split_message(header) == Split("", header, "", False)


@pytest.mark.parametrize(
    "body",
    [
        "From: a new perspective, I'll review it.\n",
        "From: Mira\nTo: Rowan\nSubject: Draft\nI'll send it Friday.\n",
        "From: Mira\nSent: Friday\nThis is my new note.\nTo: Rowan\nSubject: Review\n",
        "From: Mira\nSent: Friday\nTo: Rowan\nI'll send it tomorrow.\n",
        "On our project,\nMira wrote:\nI'll handle it.\n",
        "My note contains > but is new.\n",
    ],
)
def test_ambiguous_headers_stay_new(body):
    assert split_message(body) == Split(body, "", "", False)


def test_forwarded_outlook_thread_with_top_note():
    quoted = (
        "Begin forwarded message:\nFrom: Mira <mira@example.com>\nSent: Friday\n"
        "To: Rowan <rowan@example.com>\nSubject: Promise\nI'll send it Monday.\n"
    )
    assert split_message("Please keep track of this.\n" + quoted) == Split(
        "Please keep track of this.\n", quoted, "", True
    )


def test_forward_marker_with_explicit_quotes_keeps_inline_note():
    body = "Begin forwarded message:\n> I'll send it Friday.\nI'll ask for Monday instead.\n"
    assert split_message(body) == Split(
        "I'll ask for Monday instead.\n", "Begin forwarded message:\n> I'll send it Friday.\n", "", True
    )


def test_explicit_quote_after_unmarked_history_restores_inline_mode():
    text = "On Friday, Mira wrote:\nOld introduction.\n> Question?\nI'll send it Monday.\n"
    assert split_message(text) == Split(
        "I'll send it Monday.\n", "On Friday, Mira wrote:\nOld introduction.\n> Question?\n", "", False
    )


def test_uncertain_mobile_signature_does_not_hide_promise():
    text = "Sent from my workshop; I'll send the plans tomorrow.\n"
    assert split_message(text) == Split(text, "", "", False)


@pytest.mark.parametrize(
    "header",
    [
        "From: Mira <mira@example.com>\nDate: Friday, November 6, 2026 at 09:00\nTo: Rowan <rowan@example.com>\n"
        "Subject: Draft\n",
        "From: Mira <mira@example.com>\nDate: Fri, Nov 6, 2026\nSubject: Draft\nTo: <rowan@example.com>\n",
    ],
)
def test_header_blocks_with_date_and_any_order_are_history(header):
    text = "Thanks, will do Friday.\n" + header + "I'll send the draft Monday.\n"
    assert split_message(text) == Split(
        "Thanks, will do Friday.\n", header + "I'll send the draft Monday.\n", "", False
    )


def test_a_header_block_with_a_field_twice_stays_new():
    body = "From: Mira\nSent: Friday\nDate: Friday\nTo: Rowan\nSubject: Draft\nI'll send it.\n"
    assert split_message(body) == Split(body, "", "", False)


@pytest.mark.parametrize("attribution", ["Rowan <rowan@example.com> wrote:", "rowan@example.com wrote:"])
def test_name_wrote_attribution_before_quotes_is_history(attribution):
    body = f"Thanks for checking in.\n\nSent from my phone\n\n{attribution}\n> Could you send that address?\n"
    split = split_message(body)
    assert split.new == "Thanks for checking in.\n\n"
    assert split.signature.startswith("Sent from my phone")
    assert attribution not in split.new + split.signature


def test_wrote_line_without_quotes_stays_new():
    body = "Mira wrote:\nthe plan looks fine to me.\n"
    assert split_message(body).new == body
