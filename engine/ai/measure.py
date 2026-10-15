"""Measuring an account on request (design 6.16, "What a model can do, measured").

"Measure" runs the golden cases, the plugins' own cases and the learning pairs on one account's models and adds the
runs to the capability matrix (`engine/ai/matrix.py`), the same work the check on a switch does. Spending is the
person's choice, so an estimate comes first (`estimate`), and only the cases and pairs whose material the account is
allowed to see are priced and run: its most private allowed data level decides (`engine.skills.within_level`).

A measuring that was asked for is kept on this computer, in the workspace's private folder, so a restart finishes what
was asked: for each model, `waiting`, `measuring` or `failed` with why. A finished one leaves nothing here; the matrix
holds what it found. Nothing here is a setting.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.ai.router import LEVELS
from engine.config import Config, load_config
from engine.state_file import changing, write_whole

STATE_FILE = "ai-measures.json"
WAITING, MEASURING, FAILED = "waiting", "measuring", "failed"
#: Why a measuring failed, as kept; the screen words them.
NO_ANSWER, UNFINISHED = "no-answer", "unfinished"


class MeasureError(ValueError):
    """A measuring that can't be planned; the message says why in plain words."""


@dataclass(frozen=True)
class Plan:
    """What measuring an account would run."""

    account: str
    models: list[str]  # the short names of the models measured, each on its own
    level: str | None  # the most private data level the account may see, None when it may see none
    cases: int  # what one model's measuring runs: cases, the plugins' cases, pairs and scenarios
    skipped: int  # left out because their material is more private than the account may see
    runs: int  # how many times each runs
    usd: float | None  # about what all of it costs; None when a model's price isn't known


def most_private(cfg: Config, account: str) -> str | None:
    """The most private data level an account is allowed to see; None when it is allowed none."""
    provider = cfg.ai.providers.get(account)
    levels = [level for level in (provider.allowed_data if provider else []) if level in LEVELS]
    return max(levels, key=LEVELS.index) if levels else None


def _everything(ws: Any) -> int:
    """How many cases, plugin cases, pairs and scenarios there are, whoever may see them."""
    from engine.ai import switch_check
    from engine.evaluate import load_cases, load_pack_cases
    from engine.pairs import load_pairs, load_scenarios

    template = switch_check._template()
    return (
        len(load_cases(template))
        + len(load_pack_cases(ws.root))
        + len(load_pairs(template))
        + len(load_scenarios(template))
    )


def estimate(
    cfg: Config,
    ws: Any,
    account: str,
    model: str | None = None,
    env: Mapping[str, str] | None = None,
    ai_config: Path | None = None,
) -> Plan:
    """What measuring an account's models (or the one named, by its short name) would run and cost, priced as the
    switch check prices its cases. Raises MeasureError for an account or model that isn't there."""
    from engine.ai import switch_check

    provider = cfg.ai.providers.get(account)
    if provider is None:
        raise MeasureError(f"There is no account called {account}.")
    if model is not None and model not in provider.models:
        raise MeasureError(f"{model} isn't one of this account's models.")
    shorts = [model] if model is not None else list(provider.models)
    level = most_private(cfg, account)
    total = _everything(ws)
    runs = cfg.ai.evaluation.runs
    if level is None:
        return Plan(account, shorts, None, 0, total, runs, 0.0)
    usd: float | None = 0.0
    count = 0
    for short in shorts:
        price, count = switch_check.estimate(
            cfg, ws, f"{account}/{short}", env, ai_config=ai_config, most_private=level
        )
        usd = None if price is None or usd is None else usd + price
    # Nothing to run costs nothing, whatever the account's price: an unknown price only matters for work that runs.
    return Plan(account, shorts, level, count, max(0, total - count), runs, 0.0 if not count else usd)


def needs_go(cfg: Config, plan: Plan) -> bool:
    """Whether the person's go is needed first: the estimate is above the amount they asked to be asked about, or
    there is none and they asked to be asked about those too."""
    budgets = cfg.ai.budgets
    if plan.usd is None:
        return budgets.confirm_unpriced
    return plan.usd > budgets.confirm_above_usd


# ---- what is kept ----------------------------------------------------------------------------------------------------


def path_of(ws: Any) -> Path:
    """Where this workspace keeps the measurings that were asked for."""
    return ws.private_dir / STATE_FILE


def read(ws: Any) -> dict[str, dict[str, Any]]:
    """Every asked-for measuring by "account/short model name": `state` (waiting, measuring or failed), `why` for a
    failed one and `at`."""
    try:
        data = json.loads(path_of(ws).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return (
        {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(data, dict) else {}
    )


def _write(ws: Any, data: dict[str, dict[str, Any]]) -> None:
    write_whole(path_of(ws), json.dumps(data, sort_keys=True, indent=2) + "\n")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def begin(ws: Any, refs: list[str]) -> list[str]:
    """Ask for these models ("account/short name") to be measured. One already waiting or measuring is left as it is;
    one that failed is asked again. Returns the refs that were already waiting or measuring."""
    with changing(path_of(ws)):
        data = read(ws)
        already = [ref for ref in refs if data.get(ref, {}).get("state") in (WAITING, MEASURING)]
        for ref in refs:
            if ref not in already:
                data[ref] = {"state": WAITING, "why": None, "at": _now()}
        _write(ws, data)
    return already


def waiting(ws: Any) -> list[str]:
    """The models whose measuring is still to run."""
    return [ref for ref, entry in read(ws).items() if entry.get("state") == WAITING]


def interrupted(ws: Any) -> None:
    """Put the measurings that were running when the app stopped back to waiting, to run again from the start. Called
    when no thread is measuring."""
    with changing(path_of(ws)):
        data = read(ws)
        for entry in data.values():
            if entry.get("state") == MEASURING:
                entry["state"] = WAITING
        _write(ws, data)


def state_of(ws: Any, ref: str) -> dict[str, Any] | None:
    return read(ws).get(ref)


def _set(ws: Any, ref: str, state: str | None, why: str | None = None) -> None:
    with changing(path_of(ws)):
        data = read(ws)
        if state is None:
            data.pop(ref, None)
        elif ref in data:
            data[ref] = {**data[ref], "state": state, "why": why, "at": _now()}
        _write(ws, data)


def run_waiting(
    ws: Any,
    env: Mapping[str, str] | None = None,
    evaluator: Callable[[str, Config, Any, Mapping[str, str], str | None], Any] | None = None,
) -> list[str]:
    """Run every measuring still waiting, one after another. Each adds its runs to the matrix and leaves nothing
    behind; one that wasn't answered at all, or that can't finish, is kept as failed with why, never as a result.
    Returns the models that were run."""
    from engine.ai import switch_check

    env = os.environ if env is None else env
    run = evaluator or switch_check.evaluate_on
    done = []
    for ref in waiting(ws):
        _set(ws, ref, MEASURING)
        try:
            cfg = load_config(ws.config_dir, env=dict(env))
            report = run(ref, cfg, ws, env, most_private(cfg, ref.partition("/")[0]))
            if any(not r.not_run for r in report.results):
                _set(ws, ref, None)
            else:
                _set(ws, ref, FAILED, NO_ANSWER)
        except Exception:  # a measuring that can't run is shown as one that didn't finish, never as a result
            _set(ws, ref, FAILED, UNFINISHED)
        done.append(ref)
    return done
