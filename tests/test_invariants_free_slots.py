"""Check availability against an independent elapsed-minute occupancy model."""

import random
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine.free_slots import Busy, free_slots

CASES = 40


@pytest.mark.parametrize("seed", [4101, 4102, 4103])
def test_partition_of_working_time(seed):
    rng = random.Random(seed)
    for case in range(CASES):
        zone = ZoneInfo(rng.choice(["UTC", "America/New_York", "Europe/Paris"]))
        day = rng.choice([datetime(2026, 3, 6, tzinfo=UTC), datetime(2026, 10, 30, tzinfo=UTC)])
        day += timedelta(days=rng.randrange(10))
        day = day.astimezone(zone).date()
        lower = datetime.combine(day, time(), zone).astimezone(UTC) + timedelta(minutes=rng.randrange(180))
        upper = lower + timedelta(days=rng.randrange(1, 5), minutes=rng.randrange(180))
        start_hour, end_hour = rng.choice([(0, 4), (1, 5), (8, 17)])
        workdays = tuple(sorted(rng.sample(range(7), rng.randrange(1, 8))))
        buffer = rng.randrange(61)
        tentative_free = rng.choice([True, False])
        minimum = rng.choice([1, 30, 90])
        busy = []
        blocks = []
        for _ in range(rng.randrange(16)):
            status = rng.choice(["busy", "tentative", "free", "out of office"])
            all_day = rng.randrange(5) == 0
            if all_day:
                left = day + timedelta(days=rng.randrange(-1, 6))
                right = left + timedelta(days=rng.randrange(1, 3))
                a = datetime.combine(left, time(), zone).astimezone(UTC)
                b = datetime.combine(right, time(), zone).astimezone(UTC)
            else:
                left = lower + timedelta(minutes=rng.randrange(-240, 7500))
                right = left + timedelta(minutes=rng.randrange(1, 600))
                a, b = left - timedelta(minutes=buffer), right + timedelta(minutes=buffer)
            busy.append(Busy(left, right, status, all_day))
            if status in {"busy", "out of office"} or (status == "tentative" and not tentative_free):
                blocks.append((a, b))
        context = repr((seed, case, busy, lower, upper, workdays, buffer, tentative_free, minimum, zone.key))
        result = free_slots(
            busy,
            time(start_hour),
            time(end_hour),
            workdays,
            zone,
            window_start=lower,
            window_end=upper,
            min_minutes=minimum,
            buffer_minutes=buffer,
            tentative_as_free=tentative_free,
        )
        working, occupied = {}, {}
        tick = lower
        while tick < upper:
            local = tick.astimezone(zone)
            # UTC round-trips preserve both copies of a repeated local hour.
            d = local.date()
            a = datetime.combine(d, time(start_hour), zone).astimezone(UTC)
            b = datetime.combine(d, time(end_hour), zone).astimezone(UTC)
            if d.weekday() in workdays and a <= tick < b:
                working[d] = working.get(d, 0) + 1
                occupied[d] = occupied.get(d, 0) + int(any(x <= tick < y for x, y in blocks))
            tick += timedelta(minutes=1)
        assert set(result.free_minutes) == set(working), context
        for d, minutes in working.items():
            assert result.free_minutes[d] + occupied[d] == minutes, context
        for interval in result.intervals:
            a, b = interval.start.astimezone(UTC), interval.end.astimezone(UTC)
            assert lower <= a < b <= upper, context
            assert (b - a).total_seconds() >= minimum * 60, context
            assert not any(a < y and b > x for x, y in blocks), context
        unfiltered = free_slots(
            busy,
            time(start_hour),
            time(end_hour),
            workdays,
            zone,
            window_start=lower,
            window_end=upper,
            min_minutes=1,
            buffer_minutes=buffer,
            tentative_as_free=tentative_free,
        )
        assert unfiltered.free_minutes == result.free_minutes, context
        elapsed = sum(
            (item.end.astimezone(UTC) - item.start.astimezone(UTC)).total_seconds() / 60
            for item in unfiltered.intervals
        )
        assert elapsed == sum(result.free_minutes.values()), context
        utc_intervals = [(item.start.astimezone(UTC), item.end.astimezone(UTC)) for item in unfiltered.intervals]
        assert all(a[1] <= b[0] for a, b in zip(utc_intervals, utc_intervals[1:], strict=False)), context
        shuffled = busy.copy()
        rng.shuffle(shuffled)
        assert (
            free_slots(
                shuffled,
                time(start_hour),
                time(end_hour),
                workdays,
                zone,
                window_start=lower,
                window_end=upper,
                min_minutes=minimum,
                buffer_minutes=buffer,
                tentative_as_free=tentative_free,
            )
            == result
        ), context
