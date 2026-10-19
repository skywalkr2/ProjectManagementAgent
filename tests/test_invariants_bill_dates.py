"""Check that half-open queries partition adjusted due dates consistently."""

import random
from datetime import date, timedelta

import pytest

from engine.bill_dates import BillRule, bill_due_dates


@pytest.mark.parametrize("seed", [5201, 5202, 5203])
def test_splitting_windows_preserves_bills(seed):
    rng = random.Random(seed)
    for case in range(150):
        lower = date(2024, 1, 1) + timedelta(days=rng.randrange(1400))
        upper = lower + timedelta(days=rng.randrange(2, 500))
        split = lower + timedelta(days=rng.randrange(1, (upper - lower).days))
        kind = rng.choice(["monthly", "last_day", "nth_weekday", "weeks", "yearly"])
        fields = {}
        if kind in {"monthly", "yearly"}:
            fields["day"] = rng.randrange(1, 32)
        if kind == "yearly":
            fields["month"] = rng.randrange(1, 13)
        if kind == "nth_weekday":
            fields.update(weekday=rng.randrange(7), nth=rng.choice([-5, -2, -1, 1, 2, 5]))
        if kind == "weeks":
            fields.update(anchor=lower + timedelta(days=rng.randrange(-100, 100)), interval=rng.randrange(1, 7))
        elif rng.choice([True, False]):
            fields["anchor"] = lower + timedelta(days=rng.randrange(-100, 100))
        rule = BillRule(
            kind,
            **fields,
            business_day=rng.choice(["none", "previous", "next"]),
            workdays=tuple(sorted(rng.sample(range(7), rng.randrange(1, 8)))),
            reminder_days=tuple(rng.randrange(31) for _ in range(rng.randrange(5))),
        )
        holidays = {lower + timedelta(days=rng.randrange(-60, (upper - lower).days + 60)) for _ in range(50)}
        # Long closures test adjustments across query and month boundaries.
        holidays.update(split + timedelta(days=n) for n in range(-15, 16))
        context = repr((seed, case, rule, lower, split, upper, sorted(holidays)))
        whole = bill_due_dates(rule, lower, upper, holidays)
        pieces = bill_due_dates(rule, lower, split, holidays) + bill_due_dates(rule, split, upper, holidays)
        assert whole == pieces, context
        assert len({item.scheduled for item in whole}) == len(whole), context
        assert list(whole) == sorted(whole, key=lambda item: (item.due, item.scheduled)), context
        for item in whole:
            assert lower <= item.due < upper, context
            assert item.reminders == tuple(sorted({item.due - timedelta(days=n) for n in rule.reminder_days})), context
            if rule.business_day != "none":
                assert item.due.weekday() in rule.workdays and item.due not in holidays, context
