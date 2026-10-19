"""Plan reminder delivery without reading or changing external state."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo


@dataclass(frozen=True)
class WorkingHours:
    start: time
    end: time
    days: tuple[int, ...] = (0, 1, 2, 3, 4)
    later_today_delay: timedelta | None = None
    evening: time | None = None


@dataclass(frozen=True)
class QuietHours:
    start: time
    end: time


@dataclass(frozen=True)
class Reminder:
    occurrences: tuple[datetime, ...]
    delivered: tuple[datetime, ...] = ()
    missed_mode: str = "each"


@dataclass(frozen=True)
class Fire:
    at: datetime
    occurrences: tuple[datetime, ...]
    late: bool


@dataclass(frozen=True)
class FirePlan:
    status: str
    fires: tuple[Fire, ...]
    reason: str


@dataclass(frozen=True)
class Snooze:
    status: str
    at: datetime | None
    reason: str


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware datetime is required")
    # Round trips expose nonexistent local times without filesystem access.
    if value.astimezone(UTC).astimezone(value.tzinfo).replace(tzinfo=None) != value.replace(tzinfo=None):
        raise ValueError("A local datetime falls in a daylight-saving gap")
    return value.astimezone(UTC)


def _clock(value: time) -> None:
    if value.tzinfo is not None:
        raise ValueError("Hour boundaries must be plain local times")


def _validate(hours: WorkingHours | None, quiet: QuietHours | None = None) -> None:
    if hours is not None:
        _clock(hours.start)
        _clock(hours.end)
        if hours.start >= hours.end or not hours.days or any(day not in range(7) for day in hours.days):
            raise ValueError("Working hours need a nonempty set of weekdays and a same-day interval")
        if hours.later_today_delay is not None and hours.later_today_delay <= timedelta(0):
            raise ValueError("The later-today delay must be positive")
        if hours.evening is not None:
            _clock(hours.evening)
    if quiet is not None:
        _clock(quiet.start)
        _clock(quiet.end)
        if quiet.start == quiet.end:
            raise ValueError("Equal quiet-hour boundaries are ambiguous")


def _local(day: date, clock: time, zone: tzinfo) -> datetime:
    first = datetime.combine(day, clock, zone)
    second = first.replace(fold=1)
    _aware(first)
    if first.utcoffset() != second.utcoffset():
        raise ValueError("A generated local time is ambiguous at a daylight-saving change")
    return first


def _allowed(value: datetime, hours: WorkingHours | None, quiet: QuietHours | None) -> bool:
    clock = value.time()
    if hours is not None and (value.weekday() not in hours.days or not hours.start <= clock < hours.end):
        return False
    if quiet is None:
        return True
    if quiet.start < quiet.end:
        return not quiet.start <= clock < quiet.end
    return not (clock >= quiet.start or clock < quiet.end)


def in_quiet_hours(value: datetime, quiet: QuietHours | None) -> bool:
    """Whether a moment's own local clock time falls inside quiet hours (which may cross midnight)."""
    return quiet is not None and not _allowed(value, None, quiet)


def _permitted(value: datetime, zone: tzinfo, hours: WorkingHours | None, quiet: QuietHours | None) -> datetime:
    local = value.astimezone(zone)
    if _allowed(local, hours, quiet):
        return local
    # A weekly schedule repeats within seven days; inspect one extra boundary day.
    for offset in range(9):
        candidates = []
        day = local.date() + timedelta(days=offset)
        boundaries = [time(0)]
        if hours is not None:
            boundaries.append(hours.start)
        if quiet is not None:
            boundaries.append(quiet.end)
        for boundary in boundaries:
            # A boundary missing or doubled by a clock change that day (some zones change at midnight) is skipped.
            try:
                candidate = _local(day, boundary, zone)
            except ValueError:
                continue
            if candidate.astimezone(UTC) >= value.astimezone(UTC) and _allowed(candidate, hours, quiet):
                candidates.append(candidate)
        if candidates:
            return min(candidates, key=lambda candidate: candidate.astimezone(UTC))
    raise ValueError("Quiet hours and working hours leave no delivery time")


def next_fire(
    reminder: Reminder,
    now: datetime,
    tz: tzinfo,
    quiet_hours: QuietHours | None,
    working_hours: WorkingHours | None,
) -> FirePlan:
    """Return all missed deliveries, or the next future delivery; never consume them."""
    try:
        if not isinstance(tz, tzinfo):
            raise ValueError("Supply a time-zone object, not a zone name")
        zone = tz
        instant = _aware(now)
        _validate(working_hours, quiet_hours)
        if reminder.missed_mode not in {"each", "summary"}:
            raise ValueError("missed_mode must be each or summary")
        delivered = {_aware(value) for value in reminder.delivered}
        pending = sorted({_aware(value) for value in reminder.occurrences} - delivered)
        if not pending:
            return FirePlan("empty", (), "No undelivered occurrences are supplied.")
        missed = tuple(value.astimezone(zone) for value in pending if value < instant)
        if missed:
            groups = (missed,) if reminder.missed_mode == "summary" else tuple((value,) for value in missed)
            fires = tuple(Fire(now.astimezone(zone), group, True) for group in groups)
            # Also return an occurrence due exactly now so it is not delayed behind the missed batch.
            if instant in pending:
                fires += (Fire(_permitted(now, zone, working_hours, quiet_hours), (now.astimezone(zone),), False),)
            return FirePlan(
                "known", fires, "Missed occurrences fire immediately, even during quiet or nonworking hours."
            )
        due = pending[0].astimezone(zone)
        fire = Fire(_permitted(due, zone, working_hours, quiet_hours), (due,), False)
        return FirePlan("known", (fire,), "The next occurrence respects quiet and working hours.")
    except (ValueError, KeyError, OverflowError) as error:
        return FirePlan("unknown", (), str(error))


def snooze(
    choice: str | datetime,
    now: datetime,
    tz: tzinfo,
    working_hours: WorkingHours | None,
) -> Snooze:
    """Resolve an explicit choice; reject choices that need unstated preferences."""
    try:
        if not isinstance(tz, tzinfo):
            raise ValueError("Supply a time-zone object, not a zone name")
        zone = tz
        instant = _aware(now)
        _validate(working_hours)
        local = now.astimezone(zone)
        if isinstance(choice, datetime):
            target = _aware(choice).astimezone(zone)
        elif choice == "in 1 hour":
            target = (instant + timedelta(hours=1)).astimezone(zone)
        else:
            if working_hours is None:
                raise ValueError("This choice needs working hours and its relevant preferences")
            if choice == "later today":
                if working_hours.later_today_delay is None:
                    raise ValueError("No later-today delay was supplied")
                target = _permitted(instant + working_hours.later_today_delay, zone, working_hours, None)
                if target.date() != local.date():
                    raise ValueError("No working time remains later today")
            elif choice == "this evening":
                if working_hours.evening is None:
                    raise ValueError("No evening time was supplied")
                target = _local(local.date(), working_hours.evening, zone)
            elif choice == "tomorrow morning":
                # Tomorrow literally, at the working-day start, whether or not tomorrow is a working day.
                target = _local(local.date() + timedelta(days=1), working_hours.start, zone)
            elif choice == "next week":
                monday = local.date() + timedelta(days=7 - local.weekday())
                target = _local(monday + timedelta(days=min(working_hours.days)), working_hours.start, zone)
            else:
                raise ValueError("The snooze choice is not recognized")
        if _aware(target) <= instant:
            raise ValueError("The picked or configured time is not in the future")
        return Snooze("known", target, "Resolved from the explicit choice and supplied preferences.")
    except (ValueError, KeyError, OverflowError) as error:
        return Snooze("unknown", None, str(error))
