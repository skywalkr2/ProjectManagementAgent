"""Whether the assistant is alive, for the header's status line: when it last ran, today's runs by account, what waits
for it, the order of accounts each tier falls back through, and the accounts paused until a limit resets.

Only today's runs and the few newest ones are read, so the answer stays cheap however many runs there are. A call that
found no network says nothing about the assistant and is left out of every count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from engine.config import Config
from engine.storage import Store
from engine.today import zone

# How many of the newest runs are looked through for the last one that reached an account.
LATEST_WINDOW = 20


@dataclass(frozen=True)
class AccountRuns:
    account: str
    count: int
    failed: int


@dataclass(frozen=True)
class Chain:
    tier: str
    accounts: list[str]


@dataclass(frozen=True)
class Paused:
    account: str
    until: datetime


@dataclass(frozen=True)
class AssistantState:
    last_run_at: datetime | None
    last_run_failed: bool
    runs_today: list[AccountRuns]
    queued: int
    oldest_queued_since: datetime | None
    chains: list[Chain]
    paused: list[Paused] = field(default_factory=list)


def _at(text: str) -> datetime:
    when = datetime.fromisoformat(text)
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def _reached(run: dict) -> bool:
    return run.get("error_kind") != "offline"


def chains(cfg: Config) -> list[Chain]:
    """For each tier that has an account, the accounts it tries in order (by their names in the settings), each once."""
    found = []
    for tier, settings in cfg.ai.tiers.items():
        if not settings.use:
            continue
        accounts: list[str] = []
        for ref in [settings.use, *settings.fallback]:
            name = ref.partition("/")[0]
            if name not in accounts:
                accounts.append(name)
        found.append(Chain(tier=tier, accounts=accounts))
    return found


def assistant_state(store: Store, cfg: Config, now: datetime | None = None) -> AssistantState:
    from engine.ai.pauses import Pauses, pauses_path

    now = now or datetime.now(UTC)
    here = zone(cfg)
    day_start = datetime.combine(now.astimezone(here).date(), datetime.min.time(), tzinfo=here)
    view = store.read()

    # A run written as a UTC time can fall on the day before the person's local date, so the lookup starts a day early.
    today: dict[str, list[int]] = {}
    for stored in view.since("run", "started_at", (day_start.astimezone(UTC) - timedelta(days=1)).date().isoformat()):
        run = stored.data
        if not _reached(run) or _at(run["started_at"]) < day_start:
            continue
        count = today.setdefault(run["provider"], [0, 0])
        count[0] += 1
        count[1] += run["outcome"] != "ok"
    runs_today = [AccountRuns(account, c[0], c[1]) for account, c in sorted(today.items())]

    newest = next((s.data for s in view.latest("run", "started_at", LATEST_WINDOW) if _reached(s.data)), None)

    # Waiting for the assistant: queued, not set aside, and not held for the person's go (that wait is theirs).
    queued = [
        r.data
        for r in view.find("request", {"state": "queued"})
        if not r.data.get("dismissed") and not r.data.get("set_aside") and r.data.get("approval") != "required"
    ]
    oldest = min((_at(str(r["created_at"])) for r in queued), default=None)

    paused = sorted(Pauses(pauses_path(store), lambda: now).active().items(), key=lambda x: (x[1], x[0]))
    return AssistantState(
        last_run_at=_at(newest["started_at"]).astimezone(here) if newest else None,
        # A run that ended because its account is paused is not a failure: the pause says why it waits.
        last_run_failed=bool(newest and newest["outcome"] == "error" and newest["provider"] not in dict(paused)),
        runs_today=runs_today,
        queued=len(queued),
        oldest_queued_since=oldest.astimezone(here) if oldest else None,
        chains=chains(cfg),
        paused=[Paused(account, until.astimezone(here)) for account, until in paused],
    )
