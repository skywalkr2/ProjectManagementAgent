"""Machine timestamps in the assistant's words: an input's text carries them (an add-on writes a date-time with its
zone), the assistant copies them into what it files, and before that text is kept each is written in the person's time
zone and format. Quoted evidence stays exactly as the input has it."""

import pytest

from engine.moments import localize
from tests.test_pipeline import answers, env, outcomes, run  # noqa: F401

STAMP = "2026-10-12T18:19:04Z"
INPUT = f"Subject: Proof call\nWhen: {STAMP}\n\nThe printer will call about the proofs."


def zoned(cfg, name="Asia/Kolkata", shape="%a, %b %d, %Y, %H:%M"):
    cfg.workspace.user.timezone = name
    cfg.language.messages.date_time_format = shape
    return cfg


def test_a_date_time_with_its_zone_is_written_in_the_persons_zone_and_format(env):  # noqa: F811
    cfg = zoned(env[1])
    assert localize(f"When: {STAMP}", cfg) == "When: Mon, Oct 12, 2026, 23:49"
    twelve = zoned(cfg, "UTC", "%b %d, %I:%M %p")
    assert localize("From 2026-10-12 09:30:00+02:00 to 2026-10-12T10:00+02:00.", twelve) == (
        "From Oct 12, 07:30 AM to Oct 12, 08:00 AM."
    )


@pytest.mark.parametrize(
    "text",
    ["Due 2026-10-12.", "At 2026-10-12T18:19:04 sharp.", "Order 2026-10-12T18:19:04Z9", "No dates here."],
)
def test_text_without_a_complete_timestamp_is_left_as_it_is(env, text):  # noqa: F811
    assert localize(text, zoned(env[1])) == text


def test_a_filed_note_shows_the_time_in_the_persons_format_and_the_evidence_keeps_the_inputs_words(env):  # noqa: F811
    ws, cfg, store = env
    zoned(cfg)
    answers(
        {
            "summary": "A call.",
            "ops": [
                {"op": "note", "text": f"Printer call. When: {STAMP}"},
                {
                    "op": "fact",
                    "text": f"The printer calls about the proofs ({STAMP}).",
                    "evidence": {"quote": f"When: {STAMP}"},
                },
            ],
        }
    )
    _, cs_id = run((ws, cfg, store), INPUT)
    ops = outcomes(store, cs_id)
    assert [o["op"]["text"] for o in ops] == [
        "Printer call. When: Mon, Oct 12, 2026, 23:49",
        "The printer calls about the proofs (Mon, Oct 12, 2026, 23:49).",
    ]
    assert ops[1]["op"]["evidence"]["quote"] == f"When: {STAMP}"
    note = store.read().list("note")[-1]
    assert note.data["text"] == "Printer call. When: Mon, Oct 12, 2026, 23:49"
