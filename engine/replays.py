"""Replay cases (design 6.16, "Replaying the real event"): a miss that really happened, replayed from the person's own
action and scored on the records as they end up.

A replay is a file in a workspace's `replays/` folder. It runs in a fresh copy of the workspace, never the person's.

    id, title
    received: '2026-10-09'   # the day it starts
    skills: [dates, ...]      # the skills it proves (ids in engine/defaults/skills.yaml)
    given / given_file        # starting records, as a golden case has them
    setup: [{received, <input keys>, answer: {...}, label}]
                              # inputs handed in first, each with a fixed answer (so the change the person acts on
                              # exists); the first one's change is what the action acts on unless it says `of: <label>`
    action:                   # what the person does, through the code the screens use: the same keys as a pair's
      kind: ...               # `correction` (engine/pairs.py)
    expect_learning: true | false   # true: the action must queue a learning run; false: none may be queued
    expect_follow_on: true | false  # true: the action must queue one follow-on run (design 6.7); false: none
    expect_undo: true               # with a follow-on run: undoing its change takes back the expected end state
    expect_records: [{kind, id, where: {field: value}, text_has: [words], count}]
                              # the end state: some record of the kind has each field as given (and the words in its
                              # text, title, term, meaning or note); `count` is how many (default: at least one)
    forbid_records: [{kind, id, where, text_has}]   # no record may match
    expect_signals: [kind]    # each kind of signal the action must have recorded
    ideal:
      learn: {...}            # the learning run's answer, for the stand-in
      follow_on: {...}        # the follow-on run's answer, for the stand-in

`cockpit evaluate --replays` runs each replay N times. The setup inputs are fixed answers; a learning or follow-on run
the action queues is the account's (with the stand-in, it answers from `ideal`). The report is the same as the golden
set's.
"""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from engine.ai.adapters import make_adapter
from engine.evaluate import (
    AdapterFactory,
    Report,
    RunResult,
    _create_starting_records,
    _has_words,
    not_made,
    received_of,
    starting_records,
)
from engine.pairs import (
    CHANGE_CORRECTIONS,
    _check_correction,
    _check_input,
    _load_folder,
    _need,
    _Play,
    _Stop,
    _usage,
    _versions,
)
from engine.skills import check_named

WORDS_FROM = ("text", "title", "term", "meaning", "name", "note", "topic")


def load_replays(template: Path) -> list[dict[str, Any]]:
    """The replays in a workspace's `replays/` folder, each checked."""
    replays = _load_folder(template, "replays")
    for replay in replays:
        _check_replay(template, replay)
    return replays


def _check_records(where: str, key: str, specs: Any) -> None:
    if not isinstance(specs, list) or not all(isinstance(s, dict) and isinstance(s.get("kind"), str) for s in specs):
        raise ValueError(f"{where}: {key} is a list of records, each naming its kind")
    for spec in specs:
        if not isinstance(spec.get("where", {}), dict) or not isinstance(spec.get("text_has", []), list):
            raise ValueError(f"{where}: in {key}, `where` is a mapping and `text_has` a list of words")
        if not isinstance(spec.get("count", 1), int):
            raise ValueError(f"{where}: in {key}, `count` is a number")


def _check_replay(template: Path, replay: dict[str, Any]) -> None:
    where = f"replay {replay['id']}"
    check_named(where, replay.get("skills"), required=True)
    received_of({"id": replay["id"], **replay})
    starting_records(template, replay)
    for n, step in enumerate(replay.get("setup") or []):
        _check_input(f"{where} setup[{n}]", step, answer=True)
    action = _need(where, replay, "action")
    _check_correction(f"{where} action", action)
    if action["kind"] in CHANGE_CORRECTIONS and not replay.get("setup"):
        raise ValueError(f"{where}: the action {action['kind']} acts on an earlier change; give a setup input")
    if not isinstance(replay.get("expect_learning", True), bool):
        raise ValueError(f"{where}: expect_learning is true or false")
    for key in ("expect_records", "forbid_records"):
        if key in replay:
            _check_records(where, key, replay[key])
    if not any(replay.get(k) for k in ("expect_records", "forbid_records", "expect_signals")):
        raise ValueError(f"{where}: say what the end state holds or must not hold")
    if not all(isinstance(kind, str) for kind in replay.get("expect_signals", [])):
        raise ValueError(f"{where}: expect_signals is a list of signal kinds")
    if replay.get("expect_learning") and not isinstance((replay.get("ideal") or {}).get("learn"), dict):
        raise ValueError(f"{where}: a replay that expects learning carries ideal.learn")
    for key in ("expect_follow_on", "expect_undo"):
        if not isinstance(replay.get(key, False), bool):
            raise ValueError(f"{where}: {key} is true or false")
    if replay.get("expect_follow_on") and not isinstance((replay.get("ideal") or {}).get("follow_on"), dict):
        raise ValueError(f"{where}: a replay that expects a follow-on run carries ideal.follow_on")
    if replay.get("expect_undo") and not replay.get("expect_follow_on"):
        raise ValueError(f"{where}: expect_undo needs expect_follow_on")


def _matches(spec: Mapping[str, Any], stored: Any) -> bool:
    if stored.kind != spec["kind"] or ("id" in spec and stored.id != spec["id"]):
        return False
    if any(stored.data.get(key) != want for key, want in (spec.get("where") or {}).items()):
        return False
    return _has_words(" ".join(str(stored.data.get(k) or "") for k in WORDS_FROM), spec.get("text_has", []))


def _label(spec: Mapping[str, Any]) -> str:
    fields = [f"{k}={v}" for k, v in (spec.get("where") or {}).items()] + list(spec.get("text_has") or [])
    return f"{spec['kind']}({', '.join(fields)})"


def end_state_problems(store: Any, replay: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """What the end state lacks and what it holds that it must not: the replay's expected and forbidden records and
    the signals the action must have recorded."""
    view = store.read()
    missing: list[str] = []
    for spec in replay.get("expect_records") or []:
        found = sum(_matches(spec, s) for s in view.list(spec["kind"]))
        wanted = spec.get("count")
        if (wanted is None and not found) or (wanted is not None and found != wanted):
            more = f" ({found} found, {wanted} wanted)" if wanted is not None else ""
            missing.append(f"{_label(spec)}{more}")
    signals = {s.data["kind"] for s in view.list("signal")}
    missing += [f"signal {kind}" for kind in replay.get("expect_signals") or [] if kind not in signals]
    forbidden = [
        _label(spec)
        for spec in replay.get("forbid_records") or []
        if any(_matches(spec, s) for s in view.list(spec["kind"]))
    ]
    return missing, forbidden


def _undo_problems(store: Any, replay: Mapping[str, Any], request_id: str) -> list[str]:
    """What is wrong with undoing a follow-on run: it made no change, or undoing it leaves the end state in place."""
    from engine.applier import undo

    changeset = store.read().get("request", request_id).data.get("changeset")
    if changeset is None:
        return ["the follow-on run made no change to undo"]
    undo(store, changeset)
    still, _ = end_state_problems(store, replay)
    return [] if still else ["undoing the follow-on run's change left the end state in place"]


def _run_replay(
    template: Path, replay: dict[str, Any], n: int, *, versions: dict[str, str | None] | None, **how: Any
) -> RunResult:
    factory: AdapterFactory = how.pop("adapter_factory")
    with tempfile.TemporaryDirectory() as tmp:
        play = _Play(template, Path(tmp), replay["id"], **how)
        try:
            return _play_replay(play, template, replay, n, versions, factory)
        finally:
            play.close()


def _play_replay(
    play: _Play, template: Path, replay: dict[str, Any], n: int, versions: dict[str, str | None] | None, factory: Any
) -> RunResult:
    missing: list[str] = []
    forbidden: list[str] = []
    problems: list[str] = []
    request: str | None = None

    def result(passed: bool, **more: Any) -> RunResult:
        accounts, cost, seconds, models = _usage(play)
        _versions(play, versions, factory)
        return RunResult(
            replay["id"],
            n,
            passed,
            [*missing, *problems],
            forbidden,
            cost_usd=cost,
            seconds=seconds,
            accounts=accounts,
            models=models,
            **more,
        )

    try:
        records = starting_records(template, {"id": replay["id"], **replay})
        if records:
            _create_starting_records(play.store, replay["id"], records)
        for step in replay.get("setup") or []:
            done = play.run_input(step, step["answer"], live=False)
            if done.changeset is None:
                return result(False, error=f"a setup input didn't finish: {play.waiting_reason(done.request)}")
            if play.first_changeset is None:
                play.first_changeset = done.changeset
            if step.get("label"):
                play.labels[step["label"]] = done.changeset
        play.at(replay)  # the day it starts: the person's action comes after it and after every setup input
        followed_before = play.follow_ons()
        signals = play.correct(replay["action"])
        queued = play.learn_from(signals, (replay.get("ideal") or {}).get("learn"))
        request = queued[0] if queued else None
        expected = replay.get("expect_learning")
        if expected is False and queued:
            problems.append("learning was queued for an action that teaches nothing")
        if expected and not queued:
            problems.append("the action queued no learning")
        followed = play.follow_on_from(followed_before, (replay.get("ideal") or {}).get("follow_on"))
        wanted = replay.get("expect_follow_on")
        if wanted is False and followed:
            problems.append("a follow-on run was queued for an action that moves nothing")
        if wanted and len(followed) != 1:
            problems.append(f"the action queued {len(followed)} follow-on runs, not one")
        found, found_forbidden = end_state_problems(play.store, replay)
        missing += found
        forbidden += found_forbidden
        if replay.get("expect_undo") and len(followed) == 1:
            problems += _undo_problems(play.store, replay, followed[0])
    except _Stop as err:
        if request is not None and play.refused(request):
            return result(False, error=str(err), not_run=True, out_of_quota=play.spent(request))
        return result(False, error=str(err))
    return result(not (missing or forbidden or problems))


def evaluate_replays(
    template: Path,
    *,
    account: str | None = None,
    runs: int = 1,
    stub: bool = False,
    env: Mapping[str, str] | None = None,
    only: list[str] | None = None,
    ai_config: Path | None = None,
    progress: Callable[[RunResult, int, int], None] | None = None,
    notice: Callable[[str], None] | None = None,
    adapter_factory: AdapterFactory = make_adapter,
    pause: Callable[[float], None] = time.sleep,
) -> Report:
    """Run every replay (or `only` these) `runs` times. With `stub`, a learning run answers from `ideal`. A stage that
    finds no network waits for it as the app's own work does (`pause` is how)."""
    env = os.environ if env is None else env
    versions: dict[str, str | None] = {}
    everything = load_replays(template)
    items = [r for r in everything if not only or r["id"] in only]
    total, results = len(items) * runs, []
    for item, n in ((item, n) for item in items for n in range(1, runs + 1)):
        if results and results[-1].out_of_quota:
            results.append(not_made(item["id"], n, results[-1]))
        else:
            step = f"[{len(results) + 1}/{total}] {item['id']}"
            if notice is not None:
                notice(f"{step}: started")
            waited = (
                (lambda s, step=step: notice(f"{step}: the account asked to slow down; trying again in {s:.0f}s"))
                if notice
                else None
            )
            results.append(
                _run_replay(
                    template,
                    item,
                    n,
                    versions=versions,
                    account=account,
                    stub=stub,
                    env=env,
                    ai_config=ai_config,
                    on_wait=waited,
                    on_outage=(lambda line, step=step: notice(f"{step}: {line}")) if notice else None,
                    pause=pause,
                    adapter_factory=adapter_factory,
                )
            )
        if progress is not None:
            progress(results[-1], len(results), total)
    return Report(
        account or ("stub" if stub else "configured"),
        runs,
        results,
        versions,
        case_set={item["id"]: list(item.get("skills") or []) for item in everything},
        kind="replays",
        template=template.name,
    )
