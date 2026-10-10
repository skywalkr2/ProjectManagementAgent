"""What the assistant has cost so far, from the recorded runs: today's and this month's total (UTC) and whether either
is near its limit. The same arithmetic the router uses for its budgets, kept here so a status view can show it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from engine.config import Config
from engine.storage import Store


@dataclass(frozen=True)
class Spend:
    today_usd: float
    month_usd: float
    per_day_usd: float
    per_month_usd: float
    warn_today: bool
    warn_month: bool

    @property
    def warn(self) -> bool:
        return self.warn_today or self.warn_month


def spend(store: Store, cfg: Config, now: datetime | None = None) -> Spend:
    now = now or datetime.now(UTC)
    day = month = 0.0
    for run in store.read().list("run"):
        cost = run.data.get("cost_usd") or 0.0
        at = datetime.fromisoformat(run.data["started_at"])
        if (at.year, at.month) == (now.year, now.month):
            month += cost
            if at.date() == now.date():
                day += cost
    budgets = cfg.ai.budgets
    return Spend(
        today_usd=day,
        month_usd=month,
        per_day_usd=budgets.per_day_usd,
        per_month_usd=budgets.per_month_usd,
        warn_today=day > 0 and day >= budgets.warn_at * budgets.per_day_usd,
        warn_month=month > 0 and month >= budgets.warn_at * budgets.per_month_usd,
    )
