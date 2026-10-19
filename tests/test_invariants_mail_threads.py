"""Check candidate and participant order independence for thread selection."""

import random
from datetime import UTC, datetime, timedelta

import pytest

from engine.mail_threads import ThreadCandidate, normalize_subject, thread_key


@pytest.mark.parametrize("seed", [7401, 7402, 7403])
def test_candidate_order_does_not_change_thread_key(seed):
    rng = random.Random(seed)
    for case in range(150):
        received = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=rng.randrange(8000))
        people = ["rowan@example.com", "mira@example.com"]
        subject = rng.choice(["[EXT] Re[2]: Garden plan", "AW: Garden plan", "返信：Garden plan"])
        candidates = [
            ThreadCandidate(
                key=f"thread-{rng.randrange(4)}",
                subject=rng.choice(["Garden plan", "Other notes"]),
                participants=(rng.choice(people + ["oren@example.com"]),),
                received=received + timedelta(days=rng.randrange(-30, 31)),
                message_id=f"<earlier-{n}@example.com>",
            )
            for n in range(rng.randrange(1, 15))
        ]
        mode = case % 4
        references = "<earlier-0@example.com> <earlier-1@example.com>" if mode == 0 else None
        reply = "<earlier-0@example.com>" if mode == 1 else None
        message_id = None if mode == 3 else "<current@example.com>"
        max_days = rng.randrange(22)
        context = repr((seed, case, message_id, reply, references, subject, people, received, candidates, max_days))
        expected = thread_key(
            message_id, reply, references, subject, people, received=received, candidates=candidates, max_days=max_days
        )
        for _ in range(6):
            rng.shuffle(candidates)
            rng.shuffle(people)
            actual = thread_key(
                message_id,
                reply,
                references,
                subject,
                people,
                received=received,
                candidates=candidates,
                max_days=max_days,
            )
            assert actual == expected, context + repr(candidates)


@pytest.mark.parametrize(
    "subject", ["[EXT] Re[2]: Garden plan", "AW: Garden plan", "返信：Garden plan", "Re: Fwd: RE: x"]
)
def test_normalize_subject_is_idempotent(subject):
    normalized = normalize_subject(subject)
    assert normalize_subject(normalized) == normalized
