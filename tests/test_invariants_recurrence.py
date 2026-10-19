"""Check sorted overlap results with generated rules, exclusions, and moves."""

import random
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine.recurrence import Override, occurrences

CASES = 50


@pytest.mark.parametrize("seed", [6301, 6302, 6303])
def test_recurrences_are_sorted_and_overlap_window(seed):
    rng = random.Random(seed)
    for case in range(CASES):
        zone = ZoneInfo(rng.choice(["UTC", "America/New_York", "Europe/Paris"]))
        all_day = rng.choice([True, False])
        start = date(2024, 1, 1) + timedelta(days=rng.randrange(1000))
        if not all_day:
            start = datetime(start.year, start.month, start.day, rng.choice([1, 2, 9, 23]), 30, tzinfo=zone)
        end = start + (timedelta(days=rng.randrange(1, 4)) if all_day else timedelta(minutes=rng.randrange(181)))
        freq = rng.choice(["DAILY", "WEEKLY", "MONTHLY", "YEARLY"])
        count = rng.randrange(1, 35)
        rule = f"FREQ={freq};INTERVAL={rng.randrange(1, 4)}"
        rule += f";COUNT={count}" if case % 2 else ";UNTIL=20281231"
        if freq == "WEEKLY":
            rule += ";BYDAY=" + rng.choice(["MO,FR", "TU,TH", "SU"])
        elif freq == "MONTHLY":
            rule += rng.choice([";BYDAY=2MO", ";BYDAY=-1FR", ";BYMONTHDAY=31", ";BYDAY=MO,TU;BYSETPOS=-1"])
        elif freq == "YEARLY":
            rule += rng.choice([";BYMONTH=2;BYMONTHDAY=29", ";BYMONTH=3,11;BYDAY=1SU"])
        lower = start + timedelta(days=rng.randrange(-3, 150))
        upper = lower + timedelta(days=rng.randrange(1, 500))
        context = repr((seed, case, start, end, rule, lower, upper, zone.key))

        def instant(value):
            if isinstance(value, datetime):
                return value.astimezone(UTC)
            return value

        base = occurrences(start, end, rule, (), (), {}, lower, upper, zone)
        exclusions = [item.start for item in base[::3]]
        additions = [lower, lower + timedelta(days=1)]
        changes = {}
        for n, item in enumerate(base[1::4]):
            changes[item.start] = Override(
                start=item.start + timedelta(days=rng.randrange(-5, 6)), cancelled=n % 2 == 0
            )
        result = occurrences(start, end, rule, exclusions, additions, changes, lower, upper, zone)
        context += repr((exclusions, additions, changes))
        keys = [(instant(item.start), instant(item.override_id or item.start)) for item in result]
        assert keys == sorted(keys), context
        assert len(keys) == len(set(keys)), context
        for item in result:
            a, b = instant(item.start), instant(item.end)
            assert (a < instant(upper) and b > instant(lower)) or (a == b and instant(lower) <= a < instant(upper)), (
                context
            )
            assert item.all_day == all_day, context
            assert instant(item.override_id or item.start) not in {instant(value) for value in exclusions}, context
        if case % 2:
            assert len(base) <= count, context
        reordered = occurrences(
            start,
            end,
            rule,
            reversed(exclusions),
            reversed(additions),
            dict(reversed(list(changes.items()))),
            lower,
            upper,
            zone,
        )
        assert result == reordered, context
