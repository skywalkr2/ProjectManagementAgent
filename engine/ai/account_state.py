"""What each AI account is doing now, for its row in Settings: when it last answered and what it cost today, which kinds
of work it passed the connection check for (or failed), when it was checked, and until when a usage limit holds it.

Read from the recorded runs, the check results the workspace keeps and the pauses; nothing here calls an account. A call
that found no network says nothing about an account and is left out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from engine.ai.task import NO_WORK_KINDS
from engine.config import Config
from engine.today import zone

# How many of the newest runs are looked through for each account's last answer.
LATEST_WINDOW = 300


@dataclass(frozen=True)
class AccountState:
    answered_at: datetime | None = None
    spent_today_usd: float = 0.0
    checked_for: list[str] = field(default_factory=list)
    check_failed_for: list[str] = field(default_factory=list)
    checked_at: datetime | None = None
    paused_until: datetime | None = None


def _at(text: str) -> datetime:
    when = datetime.fromisoformat(text)
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def account_states(ws: Any, store: Any, cfg: Config, now: datetime | None = None) -> dict[str, AccountState]:
    """The state of every account in the settings, by its name there. Times are on the person's own clock."""
    from engine.ai.checked import check_failed, checked_at, is_checked
    from engine.ai.pauses import Pauses, pauses_path

    now = now or datetime.now(UTC)
    here = zone(cfg)
    day_start = datetime.combine(now.astimezone(here).date(), datetime.min.time(), tzinfo=here)
    view = store.read()

    answered: dict[str, datetime] = {}
    for stored in view.latest("run", "started_at", LATEST_WINDOW):
        run = stored.data
        if run.get("error_kind") in NO_WORK_KINDS or run.get("outcome") != "ok":
            continue
        answered.setdefault(run["provider"], _at(run["started_at"]))
    spent: dict[str, float] = {}
    for stored in view.since("run", "started_at", (day_start.astimezone(UTC) - timedelta(days=1)).date().isoformat()):
        run = stored.data
        if run.get("error_kind") in NO_WORK_KINDS or _at(run["started_at"]) < day_start:
            continue
        spent[run["provider"]] = spent.get(run["provider"], 0.0) + (run.get("cost_usd") or 0.0)

    paused = Pauses(pauses_path(store), lambda: now).active()
    found: dict[str, AccountState] = {}
    for name, provider in cfg.ai.providers.items():
        refs = [f"{name}/{short}" for short in provider.models]
        passed = [t for t in cfg.ai.tiers if any(is_checked(ws, cfg, ref, t) for ref in refs)]
        failed = [t for t in cfg.ai.tiers if any(check_failed(ws, cfg, ref, t) for ref in refs)]
        stamps = [s for s in (checked_at(ws, cfg, ref) for ref in refs) if s is not None]
        last = answered.get(name)
        until = paused.get(name)
        found[name] = AccountState(
            answered_at=last.astimezone(here) if last else None,
            spent_today_usd=spent.get(name, 0.0),
            checked_for=[t for t in passed if t not in failed],
            check_failed_for=failed,
            checked_at=max(stamps).astimezone(here) if stamps else None,
            paused_until=until.astimezone(here) if until else None,
        )
    return found
