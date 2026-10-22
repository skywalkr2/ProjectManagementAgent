"""What the meeting journey's server is seeded with (`tests/e2e_server.py --meetings`), apart from the server so a
test can read it without starting one."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from engine.storage import WriteContext
from tests.conftest import DEMO_B, fixture_records


def seed_meetings(store, cfg):
    """What the meeting journey acts on: a calendar entry with another person on it that starts in a few hours (its
    prep is a line on Today), one with them that ended a while ago and has nothing written down (its capture is a
    line), and a promise that person made, quiet for eight days (a line to follow up). Returns what the browser test
    reads."""
    pm = cfg.workspace.user.person
    guest = next(p for p in fixture_records(DEMO_B, "person") if p["id"] != pm)
    ctx = WriteContext(actor="engine", trust="trusted", op="e2e.meetings")
    now = datetime.now(UTC)
    attendees = [{"person": guest["id"], "response": "accepted"}]
    with store.transaction() as tx:
        coming = tx.create(
            "event",
            {
                "title": "Design review",
                "start": (now + timedelta(hours=3)).isoformat(),
                "end": (now + timedelta(hours=4)).isoformat(),
                "attendees": attendees,
                "trust": "trusted",
            },
            ctx,
        ).id
        ended = tx.create(
            "event",
            {
                "title": "Kickoff call",
                "start": (now - timedelta(hours=3)).isoformat(),
                "end": (now - timedelta(hours=2)).isoformat(),
                "attendees": attendees,
                "trust": "trusted",
            },
            ctx,
        ).id
    # The promise was made eight days ago: long enough to have gone quiet, short of its own follow-up line.
    before = store.clock
    store.clock = lambda: (now - timedelta(days=8)).isoformat(timespec="seconds")
    try:
        with store.transaction() as tx:
            promise = tx.create(
                "action",
                {
                    "text": "Return the contract",
                    "owners": [{"person": guest["id"]}],
                    "promised_to": [pm],
                    "basis": "said",
                    "evidence": {"source": "note", "quote": "I will return the contract"},
                },
                ctx,
            ).id
    finally:
        store.clock = before
    return {
        "guest": {"id": guest["id"], "name": guest["full_name"]},
        "coming": {"id": coming, "title": "Design review"},
        "ended": {"id": ended, "title": "Kickoff call"},
        "promise": {"id": promise, "text": "Return the contract"},
    }
