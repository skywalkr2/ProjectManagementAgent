"""What `cockpit ai test` concludes per kind of work: a tier whose main account fails still runs on a backup that passed
every part of its check, and only a tier with no account that answered can't run."""

from __future__ import annotations

from engine.ai.smoke import SmokeResult, _problem, tier_summary
from engine.ai.task import AiError


def line(tier: str, ref: str, main: bool, ok: bool, part: str = "call") -> SmokeResult:
    return SmokeResult(tier, f"{ref} ({part})", main, ok, "answered" if ok else "out of credit", ref=ref, part=part)


def test_a_spent_main_account_with_a_checked_backup_still_runs_and_names_the_backup_once_per_tier():
    results = [
        line("routine", "main/default", True, False),
        line("routine", "main/default", True, True, "lockdown"),
        line("routine", "main/default", True, False, "learning"),
        line("routine", "spare/everyday", False, True),
        line("routine", "spare/everyday", False, True, "learning"),
        line("deep", "main/default", True, False),
        line("deep", "spare/everyday", False, True),
    ]
    lines, every = tier_summary(results)
    assert every
    assert lines == [
        "routine: the main account didn't answer; spare/everyday stands in until it does.",
        "deep: the main account didn't answer; spare/everyday stands in until it does.",
    ]


def test_a_backup_that_failed_any_part_does_not_stand_in():
    lines, every = tier_summary(
        [
            line("routine", "main/default", True, False),
            line("routine", "spare/everyday", False, True),
            line("routine", "spare/everyday", False, False, "learning"),
        ]
    )
    assert not every
    assert lines == ["routine can't run: no account for it answered. See the lines above, then test again."]


def test_every_main_account_answering_says_so():
    assert tier_summary([line("routine", "main/default", True, True)]) == (["All tiers answered."], True)


def test_a_service_that_cant_be_reached_says_what_to_do_and_never_shows_this_computers_error_text():
    line = _problem(AiError("provider_down", "[Errno 61] Connection refused"))
    assert line == "It couldn't be reached. Check the address, or start it if it runs on this computer."
    assert "Errno" not in _problem(AiError("offline", "[Errno 8] nodename nor servname provided"))


def test_an_accounts_own_words_for_a_refusal_are_still_shown():
    line = _problem(AiError("auth", '{"error": {"message": "Invalid API key provided."}}'))
    assert line == "It isn't signed in, or the key was refused (Invalid API key provided)."
