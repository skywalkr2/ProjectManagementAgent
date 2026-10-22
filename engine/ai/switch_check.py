"""The check that comes with a switch of a tier's account or model (design 6.16, 6.22).

Changing which account or model does a tier's work is exactly when learning and extraction can get worse without anyone
noticing, so the person is offered a check with the switch: the golden cases and the plugins' own cases run on the new
choice, with the estimate shown first. A pass keeps the switch. A failure is a line on Today with Switch back, which
restores what the tier had before, and Keep it.

What is kept lives on this computer, in the workspace's private folder: for each switched tier, the choice before and
after, what Switch back writes, and how the check went. Nothing here is a setting.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.config import Config, load_config
from engine.state_file import changing, write_whole

STATE_FILE = "ai-switches.json"
CHECKING, PASSED, FAILED = "checking", "passed", "failed"
#: A switch made on its own after a passed check (a newer model of the tier's family), waiting for the person's Keep or
#: Switch back.
MOVED = "moved"
#: The most failed cases a Today line names.
NAMED = 5


@dataclass(frozen=True)
class Switch:
    """A tier moving from one choice ("account/model") to another."""

    tier: str
    before: str
    after: str


def path_of(store: Any) -> Path:
    """Where this workspace keeps the state of its switch checks."""
    return store.path.parent / ".cockpit" / STATE_FILE


def _model_id(cfg: Config, ref: str) -> str | None:
    name, _, short = ref.partition("/")
    provider = cfg.ai.providers.get(name)
    return provider.models.get(short, short) if provider is not None else None


def switches(before: Config, after: Config) -> list[Switch]:
    """The tiers that had an account and now do their work on another account or another model. A tier that had none
    isn't switching, it is being set up."""
    found = []
    for tier, now in after.ai.tiers.items():
        old = before.ai.tiers.get(tier)
        if old is None or not old.use or not now.use:
            continue
        if old.use != now.use or _model_id(before, old.use) != _model_id(after, now.use):
            found.append(Switch(tier, old.use, now.use))
    return found


# ---- what is kept ----------------------------------------------------------------------------------------------------


def read(store: Any) -> dict[str, dict[str, Any]]:
    """Every tier's kept entry: `state` (checking, passed or failed), `before` and `after`, `restore` (the settings
    Switch back writes: `changes` and `reset`), `failed` (what didn't pass, by name), `unfinished` and `at`."""
    import json

    try:
        data = json.loads(path_of(store).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return (
        {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(data, dict) else {}
    )


def _write(store: Any, data: dict[str, dict[str, Any]]) -> None:
    import json

    write_whole(path_of(store), json.dumps(data, sort_keys=True, indent=2) + "\n")


def restore_of(tier: str, saved_changes: list[dict[str, Any]]) -> dict[str, Any]:
    """What puts a tier back as it was: the saved settings of the switch that belong to it (its own choice, and the
    models of the accounts), each with the value it had before, or reset when it had none of its own."""
    changes: dict[str, Any] = {}
    reset: list[str] = []
    for change in saved_changes:
        key = change["key"]
        if not (key.startswith(f"ai.tiers.{tier}.") or (key.startswith("ai.providers.") and key.endswith(".models"))):
            continue
        if change.get("was_default"):
            reset.append(key)
        else:
            changes[key] = change["before"]
    return {"changes": changes, "reset": reset}


def begin(store: Any, found: list[Switch], saved_changes: list[dict[str, Any]], *, check: bool) -> None:
    """Keep each switch: to be checked now, or (without a check) just forgetting any earlier entry for its tier, which
    this switch supersedes."""
    with changing(path_of(store)):
        data = read(store)
        for switch in found:
            data.pop(switch.tier, None)
            if check:
                data[switch.tier] = {
                    "state": CHECKING,
                    "before": switch.before,
                    "after": switch.after,
                    "restore": restore_of(switch.tier, saved_changes),
                    "failed": [],
                    "unfinished": None,
                    "at": datetime.now(UTC).isoformat(),
                }
        _write(store, data)


def clear(store: Any, tier: str) -> dict[str, Any] | None:
    """Forget a tier's entry (Keep it, or Switch back); returns what was there."""
    with changing(path_of(store)):
        data = read(store)
        gone = data.pop(tier, None)
        if gone is not None:
            _write(store, data)
        return gone


def failed(store: Any) -> dict[str, dict[str, Any]]:
    """The tiers whose check didn't pass and that the person hasn't decided about."""
    return {tier: entry for tier, entry in read(store).items() if entry.get("state") == FAILED}


def keep_moved(
    store: Any, switch: Switch, saved_changes: list[dict[str, Any]], usd_per_day: float | None = None
) -> None:
    """Keep a switch made on its own after its check passed: Switch back restores what the tier had, Keep clears it.
    Any earlier entry of the tier is superseded."""
    with changing(path_of(store)):
        data = read(store)
        data[switch.tier] = {
            "state": MOVED,
            "before": switch.before,
            "after": switch.after,
            "restore": restore_of(switch.tier, saved_changes),
            "failed": [],
            "unfinished": False,
            "usd_per_day": usd_per_day,
            "at": datetime.now(UTC).isoformat(),
        }
        _write(store, data)


def moved(store: Any) -> dict[str, dict[str, Any]]:
    """The tiers moved on their own that the person hasn't decided about."""
    return {tier: entry for tier, entry in read(store).items() if entry.get("state") == MOVED}


def waiting(store: Any) -> list[str]:
    """The tiers whose check is still to run."""
    return [tier for tier, entry in read(store).items() if entry.get("state") == CHECKING]


# ---- the check -------------------------------------------------------------------------------------------------------


def _template() -> Path:
    from engine.shipped import demo

    return demo()


#: About how many calls one learning pair makes, for its estimate.
PAIR_CALLS = 3


def evaluate_on(
    account: str,
    cfg: Config,
    ws: Any,
    env: Mapping[str, str],
    most_private: str | None = None,
    ai_config: Path | None = None,
) -> Any:
    """The report of the golden cases, the plugins' own cases and the learning pairs on one choice, with the person's
    accounts: what `cockpit evaluate` and `cockpit evaluate --pairs` run, as one report. With `most_private`, only the
    ones whose material is no more private than that run (measuring an account that may not see the rest). `ai_config`
    is the accounts file to run with (the saved one unless a change isn't saved yet)."""
    from engine.ai.matrix import record_report
    from engine.evaluate import Report, evaluate
    from engine.pairs import evaluate_pairs

    runs = cfg.ai.evaluation.runs
    cases = evaluate(
        _template(),
        account=account,
        runs=runs,
        ai_config=ai_config or ws.config_dir / "ai.yaml",
        packs_of=ws.root,
        env=env,
        most_private=most_private,
    )
    pairs = evaluate_pairs(
        _template(),
        account=account,
        runs=runs,
        ai_config=ai_config or ws.config_dir / "ai.yaml",
        env=env,
        most_private=most_private,
    )
    for done in (cases, pairs):
        record_report(ws, done, stale_days=cfg.ai.skills.stale_days)
    return Report(
        cases.account,
        runs,
        [*cases.results, *pairs.results],
        {**cases.program_versions, **pairs.program_versions},
    )


def titles(ws: Any) -> dict[str, str]:
    """What each case and pair is called, by id, for the Today line."""
    from engine.evaluate import case_titles
    from engine.pairs import load_pairs, load_scenarios

    found = case_titles(_template(), ws.root)
    for item in (*load_pairs(_template()), *load_scenarios(_template())):
        found[item["id"]] = item.get("title") or item["id"]
    return found


def estimate(
    cfg: Config,
    ws: Any,
    ref: str,
    env: Mapping[str, str] | None = None,
    ai_config: Path | None = None,
    most_private: str | None = None,
) -> tuple[float | None, int]:
    """About what the check of one choice would cost in USD (None when its price isn't known), and its case count.
    `ai_config` is the accounts file to price it with (the saved one unless the change isn't saved yet). With
    `most_private`, cases and pairs whose material is more private than that aren't counted."""
    from engine.evaluate import estimate_cases
    from engine.pairs import load_pairs, load_scenarios
    from engine.skills import within_level

    runs = cfg.ai.evaluation.runs
    price, count = estimate_cases(
        _template(),
        account=ref,
        runs=runs,
        ai_config=ai_config or ws.config_dir / "ai.yaml",
        packs_of=ws.root,
        env=env,
        most_private=most_private,
    )
    # A pair or scenario makes about PAIR_CALLS calls (the learning run, the later input and what it proposes), each
    # priced at the cases' average.
    pairs = sum(within_level(p, most_private) for p in (*load_pairs(_template()), *load_scenarios(_template())))
    if price is None or not count:
        return None, count + pairs
    return price + price / count * PAIR_CALLS * pairs, count + pairs


def judge(ws: Any, cfg: Config, report: Any) -> dict[str, Any]:
    """The verdict on a report of a check: passed when the score reaches the configured one, failed with the names of
    the cases that didn't come out right, or failed as unfinished when nothing could run."""
    called = titles(ws)
    ran = [r for r in report.results if not r.not_run]
    names = [called.get(c, c) for c in report.cases() if any(not r.passed for r in ran if r.case == c)]
    if not ran:
        return {"state": FAILED, "failed": [], "unfinished": True}
    if report.pass_rate() >= cfg.ai.evaluation.min_score:
        return {"state": PASSED, "failed": [], "unfinished": False}
    return {"state": FAILED, "failed": names, "unfinished": False}


def run_waiting(
    ws: Any,
    store: Any,
    env: Mapping[str, str] | None = None,
    evaluator: Callable[[str, Config, Any, Mapping[str, str]], Any] | None = None,
) -> list[str]:
    """Run every check still waiting and keep its verdict. A check that passes the configured score keeps the switch
    and leaves nothing for the person; one that doesn't, or that can't finish, is kept as failed for Today. Returns the
    tiers that were checked."""

    env = os.environ if env is None else env
    run = evaluator or evaluate_on
    done = []
    for tier in waiting(store):
        entry = read(store).get(tier)
        if entry is None or entry.get("state") != CHECKING:
            continue
        try:
            cfg = load_config(ws.config_dir, env=dict(env))
            verdict = judge(ws, cfg, run(entry["after"], cfg, ws, env))
        except Exception:  # a check that can't run is shown as one that didn't finish, never as a pass
            verdict = {"state": FAILED, "failed": [], "unfinished": True}
        with changing(path_of(store)):
            data = read(store)
            current = data.get(tier)
            # The person may have switched again, or decided, while the check ran: only its own entry takes the verdict.
            if current is not None and current.get("after") == entry["after"] and current.get("state") == CHECKING:
                data[tier] = {**current, **verdict, "at": datetime.now(UTC).isoformat()}
                _write(store, data)
        done.append(tier)
    return done
