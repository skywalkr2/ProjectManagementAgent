"""What `cockpit ai test` concludes per kind of work: a tier whose main account fails still runs on a backup that passed
every part of its check, and only a tier with no account that answered can't run."""

from __future__ import annotations

from engine.ai.smoke import SmokeResult, tier_summary


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
