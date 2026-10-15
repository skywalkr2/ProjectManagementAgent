"""Borrowing another tier's account for a while (design 6.16).

When every account a tier can use is paused until a usage limit resets, and an account that belongs to another tier is
free, the person is asked whether to use it for that work until the reset. The answer is kept in the workspace's
private folder, so it holds across a restart: a yes lets the router use that account for the tier until the time given,
and a no keeps the work waiting without asking again for the same pause. Nothing here calls a provider; nothing is
borrowed without the person's yes.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.state_file import write_whole

_LOCK = threading.Lock()

YES, NO = "yes", "no"


def borrowed_path(store: Any) -> Path:
    """Where the workspace keeps the person's answers about borrowing."""
    return store.path.parent / ".cockpit" / "ai-borrowed.json"


@dataclass(frozen=True)
class Answer:
    """The person's answer for one tier's pause: `yes` or `no`, the account offered ("provider/model"), the account
    whose limit it waits for and when that limit resets, when the answer stops counting."""

    tier: str
    answer: str
    account: str
    paused: str
    until: datetime


class Borrowed:
    def __init__(self, path: Path, now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.path = path
        self.now = now

    def _load(self) -> dict[str, dict[str, str]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)}

    def _save(self, data: dict[str, dict[str, str]]) -> None:
        with contextlib.suppress(OSError):
            write_whole(self.path, json.dumps(data, sort_keys=True))

    def active(self) -> dict[str, Answer]:
        """The answers that still count, by tier. An answer whose time has passed is dropped."""
        now = self.now()
        live: dict[str, Answer] = {}
        for tier, row in self._load().items():
            try:
                until = datetime.fromisoformat(str(row["until"]))
                answer = str(row["answer"])
                account, paused = str(row["account"]), str(row.get("paused", ""))
            except (KeyError, ValueError):
                continue
            if until.tzinfo is None:
                until = until.replace(tzinfo=UTC)
            if until > now and answer in (YES, NO):
                live[tier] = Answer(tier, answer, account, paused, until)
        return live

    def get(self, tier: str) -> Answer | None:
        return self.active().get(tier)

    def lent(self, tier: str) -> str | None:
        """The account ("provider/model") the person said yes to for this tier, while that answer counts."""
        found = self.get(tier)
        return found.account if found is not None and found.answer == YES else None

    def keep(self, answer: Answer) -> None:
        with _LOCK:
            data = {
                t: {"answer": a.answer, "account": a.account, "paused": a.paused, "until": a.until.isoformat()}
                for t, a in self.active().items()
            }
            data[answer.tier] = {
                "answer": answer.answer,
                "account": answer.account,
                "paused": answer.paused,
                "until": answer.until.isoformat(),
            }
            self._save(data)

    def clear(self, tier: str | None = None) -> None:
        with _LOCK:
            data = {} if tier is None else {t: v for t, v in self._load().items() if t != tier}
            self._save(data)


def chain(cfg: Any, tier: str) -> list[str]:
    """The accounts ("provider/model") a tier is set up to use, the main one first."""
    found = cfg.ai.tiers.get(tier)
    return [ref for ref in ([found.use] if found and found.use else []) + (list(found.fallback) if found else [])]


def candidates(
    cfg: Any,
    tier: str,
    paused: Collection[str],
    unchecked: Collection[tuple[str, str]] = (),
) -> list[tuple[str, str]]:
    """The accounts of other tiers that are free to take this tier's work, as (their tier, "provider/model") in tier
    order: not paused, not one of this tier's own accounts, and not a backup that can't stand in yet. An account
    already in this tier's chain is never offered, so a tier whose accounts are all paused doesn't offer one of them
    under another name."""
    own = {ref.partition("/")[0] for ref in chain(cfg, tier)}
    found: list[tuple[str, str]] = []
    for other in cfg.ai.tiers:
        if other == tier:
            continue
        for ref in chain(cfg, other):
            provider = ref.partition("/")[0]
            if provider in own or provider in paused or provider not in cfg.ai.providers:
                continue
            if (other, ref) in unchecked or any(ref == r for _, r in found):
                continue
            found.append((other, ref))
    return found


def lendable(
    cfg: Any,
    tier: str,
    levels: Iterable[str],
    paused: Collection[str],
    unchecked: Collection[tuple[str, str]] = (),
) -> tuple[str, int] | None:
    """The account to offer for this tier's waiting work and how many of the waiting requests (whose data levels are
    `levels`) it may take: the one that takes the most, the first in tier order when they tie. None when no free
    account of another tier may see any of the material."""
    from engine.ai.router import LEVELS

    wanted = [lv for lv in levels if lv in LEVELS]
    best: tuple[str, int] | None = None
    for _, ref in candidates(cfg, tier, paused, unchecked):
        provider = cfg.ai.providers[ref.partition("/")[0]]
        top = max(LEVELS.index(lv) for lv in provider.allowed_data)
        takes = sum(1 for lv in wanted if LEVELS.index(lv) <= top)
        if takes and (best is None or takes > best[1]):
            best = (ref, takes)
    return best


class BorrowError(Exception):
    """An answer can't be taken: the message says why in plain words."""


def answer(ws: Any, store: Any, cfg: Any, tier: str, ref: str, yes: bool, now: datetime) -> int:
    """Keep the person's answer to the question of borrowing `ref` for the work of `tier` while its accounts are
    paused. A yes lasts until the earliest reset of the accounts the work waits on, and lets that work run on `ref` at
    once; a no keeps it waiting and is not asked again for the same pause. Returns how many waiting requests were let
    go. Only the account the question offered can be answered for."""
    from engine.ai.checked import cannot_stand_in
    from engine.ai.pauses import Pauses, pauses_path
    from engine.dispatcher import _data_level
    from engine.worker import release_waiting

    paused = Pauses(pauses_path(store), lambda: now).active()
    waiting = [
        r
        for r in store.read().list("request")
        if r.data.get("state") == "queued"
        and not r.data.get("dismissed")
        and (r.data.get("cause") or {}).get("kind") == "paused"
        and (r.data.get("cause") or {}).get("tier") == tier
        and (r.data.get("cause") or {}).get("account") in paused
    ]
    unchecked = {(s.tier, s.ref) for s in cannot_stand_in(ws, cfg)}
    offered = lendable(cfg, tier, [_data_level(store, r.data) for r in waiting], set(paused), unchecked)
    if cfg.ai.borrow_other_tier != "ask" or not waiting or offered is None or offered[0] != ref:
        raise BorrowError("That account isn't on offer for this work any more.")
    first = min(waiting, key=lambda r: str(r.data["cause"].get("until")))
    until = datetime.fromisoformat(str(first.data["cause"]["until"]))
    until = until if until.tzinfo else until.replace(tzinfo=UTC)
    Borrowed(borrowed_path(store), lambda: now).keep(
        Answer(tier, YES if yes else NO, ref, str(first.data["cause"].get("account") or ""), until)
    )
    return release_waiting(store, tier) if yes else 0
