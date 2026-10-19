"""The catch-up list (design 6.22): corrections recorded before the assistant could learn from them are learned from
once, into one list kept short enough for one sitting.

The selection and ranking are plain functions over the signals. The app runs `start` once at startup: it fixes the
moment the list was made, picks at most `knowledge.catch_up_max` kinds of correction that no entry was learned from,
the most repeated first, counts the rest as left out, and moves the rule decisions that were held for the person
into proposals. Running it again changes nothing.

`queue_learning` then queues the learning runs for the chosen kinds: one request for each kind still waiting, about its
newest correction that can be learned from. They are held together for the person's go, with one total estimate, and
`grant_go` starts them all. Their proposals are in the list as they come in.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine import knowledge, learn
from engine.records import REGISTRY
from engine.state_file import changing, write_whole
from engine.storage import StoreError, WriteContext

#: The corrections a lesson can be learned from: the kinds learning reads (`learn.TEACHES`), so the list and the runs
#: never disagree. Set aside mail, putting an action on or off hold, and what the person does to what was learned (keep,
#: discard, retire, narrow, "just this time") are not.
LEARNED_FROM = learn.TEACHES

_PREFIXES = {model.prefix: kind for kind, model in REGISTRY.items()}

#: What the learning runs for the catch-up list wait on until the person's go; Today gathers them into one line.
WAITING = "Learning from your earlier corrections waits for you to start it."

_ENGINE = WriteContext(actor="engine", trust="trusted", op="catch_up.queue")
_GO = WriteContext(actor="pm", trust="trusted", op="catch_up.go")


@dataclass(frozen=True)
class Group:
    """One kind of correction and the corrections of it, newest first. `key` is the signal's kind and what it was a
    correction of (the task kind and the records its change touched)."""

    key: tuple[str, str]
    signals: list[str]
    count: int
    latest: str = ""


@dataclass
class CatchUp:
    """The list as it was made: when, the kinds of correction chosen, how many were left out, and the rules moved from
    the held decisions."""

    made_at: str
    groups: list[Group] = field(default_factory=list)
    left_out: int = 0
    rules: list[str] = field(default_factory=list)


def state_path(store: Any) -> Path:
    return store.path.parent / ".cockpit" / "catch-up.json"


def _read(path: Path) -> CatchUp | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return CatchUp(
        raw["made_at"],
        [Group((g["key"][0], g["key"][1]), list(g["signals"]), g["count"], g.get("latest", "")) for g in raw["groups"]],
        raw.get("left_out", 0),
        list(raw.get("rules", [])),
    )


def _write(path: Path, state: CatchUp) -> None:
    raw = {
        "made_at": state.made_at,
        "groups": [
            {"key": list(g.key), "signals": g.signals, "count": g.count, "latest": g.latest} for g in state.groups
        ],
        "left_out": state.left_out,
        "rules": state.rules,
    }
    write_whole(path, json.dumps(raw, indent=2))


def load(store: Any) -> CatchUp | None:
    """The catch-up list, or None when `start` hasn't made it yet."""
    return _read(state_path(store))


# ---- what has been learned from ------------------------------------------------------------------------------------


def learned_signals(view: Any) -> set[str]:
    """The corrections some entry was learned from: those a lesson, or any entry's evidence, names."""
    found: set[str] = set()
    for kind in (*knowledge.KINDS, "rule"):
        for stored in view.list(kind):
            data = stored.data
            for evidence in (data.get("evidence"), *(data.get("more_evidence") or [])):
                if isinstance(evidence, dict) and evidence.get("signal"):
                    found.add(evidence["signal"])
            if data.get("signal"):
                found.add(data["signal"])
    return found


def correction_key(view: Any, signal: Any) -> tuple[str, str]:
    """The kind of correction a signal is: its kind, and what it corrected, as the task kind that made the change and
    the kinds of record the change touched (or the kinds of the records it names)."""
    data = signal.data
    changeset = view.get("changeset", data["changeset"]) if data.get("changeset") else None
    task = None
    touched: set[str] = set()
    if changeset is not None:
        request = view.get("request", changeset.data["request"])
        task = request.data.get("task") if request is not None else None
        touched = {r["kind"] for o in changeset.data.get("ops", []) for r in o.get("records", [])}
    if not touched:
        touched = {kind for ref in data.get("refs", []) if (kind := _PREFIXES.get(ref.rpartition("-")[0]))}
    return data["kind"], f"{task or '-'}: {', '.join(sorted(touched)) or '-'}"


def groups_of(view: Any, before: datetime | None = None) -> list[Group]:
    """The corrections no entry was learned from, grouped by kind of correction and ranked: the most repeated first,
    then the most recent. With `before`, only those recorded then or earlier."""
    learned = learned_signals(view)
    found: dict[tuple[str, str], list[Any]] = {}
    for s in view.list("signal"):
        if s.data["kind"] not in LEARNED_FROM or s.id in learned:
            continue
        if before is not None and _at(s.data["at"]) > before:
            continue
        found.setdefault(correction_key(view, s), []).append(s)
    groups = []
    for key, signals in found.items():
        signals.sort(key=lambda s: (str(s.data["at"]), s.id), reverse=True)
        groups.append(Group(key, [s.id for s in signals], len(signals), str(signals[0].data["at"])))
    groups.sort(key=lambda g: g.key)
    groups.sort(key=lambda g: g.latest, reverse=True)
    groups.sort(key=lambda g: -g.count)
    return groups


def _at(stamp: Any) -> datetime:
    moment = stamp if isinstance(stamp, datetime) else datetime.fromisoformat(str(stamp))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def select(groups: list[Group], most: int) -> tuple[list[Group], int]:
    """At most `most` of the ranked groups, and how many were left out."""
    chosen = groups[: max(most, 0)]
    return chosen, len(groups) - len(chosen)


def waiting(view: Any, state: CatchUp | None) -> list[Group]:
    """The chosen kinds of correction no entry has been learned from yet, in rank order: what the learning step reads
    next. A kind is learned from once, so each is dropped as soon as an entry cites one of its corrections."""
    if state is None:
        return []
    learned = learned_signals(view)
    return [g for g in state.groups if not learned & set(g.signals)]


def proposal_ids(view: Any, state: CatchUp | None) -> set[str]:
    """The proposals that belong to the catch-up list: those learned from a chosen correction, and the rules moved
    from the held decisions."""
    if state is None:
        return set()
    chosen = {s for g in state.groups for s in g.signals}
    found = set(state.rules)
    for kind in (*knowledge.KINDS, "rule"):
        for stored in view.list(kind):
            data = stored.data
            cited = {e.get("signal") for e in (data.get("evidence"), *(data.get("more_evidence") or [])) if e}
            if chosen & (cited | {data.get("signal")}):
                found.add(stored.id)
    return found


# ---- making the list, once -------------------------------------------------------------------------------------------


def start(store: Any, cfg: Any, now: datetime | None = None) -> CatchUp:
    """Make the catch-up list if it has not been made, and move the held rule decisions into proposals. Safe to run at
    every startup: the list is made once, and a decision already moved is no longer held."""
    now = now or datetime.now(UTC)
    path = state_path(store)
    with changing(path):
        state = _read(path)
        if state is None:
            chosen, left_out = select(groups_of(store.read(), before=now), cfg.dispatch.knowledge.catch_up_max)
            state = CatchUp(now.isoformat(), chosen, left_out)
        moved = move_held_rules(store, cfg, now)
        state.rules = [*state.rules, *[r for r in moved if r not in state.rules]]
        _write(path, state)
        return state


def move_held_rules(store: Any, cfg: Any, now: datetime) -> list[str]:
    """Turn each rule decision held for the person into a proposal, as if the rule had been added now by what it
    came from, and mark the held item as done. Returns the ids of the proposals made, one for each decision moved
    (a decision that merged into a rule already there makes none)."""
    from engine.ops import CHANGESET
    from engine.rules import add_rule

    view = store.read()
    pm = _pm(store, cfg)
    settings = cfg.dispatch.knowledge
    made: list[str] = []
    for changeset in view.list("changeset"):
        request = view.get("request", changeset.data["request"])
        if request is None or request.data.get("dismissed"):
            continue
        for outcome in changeset.data.get("ops", []):
            if outcome.get("status") != "held" or (outcome.get("op") or {}).get("op") != "rule.add":
                continue
            if outcome.get("question"):
                continue
            try:
                op = CHANGESET.validate_python({"ops": [outcome["op"]]}, context={"op_models": store.plugins.ops}).ops[
                    0
                ]
            except Exception:
                continue
            source = request.data.get("source")
            untrusted = changeset.data.get("trust") == "untrusted"
            standing = knowledge.Standing(
                person=False,
                pm=pm,
                origin="input" if untrusted or source else "assistant",
                trust=changeset.data.get("trust", "trusted"),
                source=source,
                request=request.id,
                now=now.isoformat(),
                hold_days=settings.discards_hold_days,
                alike=settings.discard_similarity,
            )
            quote = ((outcome["op"].get("evidence") or {}).get("quote")) or None
            evidence = {"source": source or "note", "quote": quote} if quote else None
            w = WriteContext(
                actor="assistant",
                trust=standing.trust,
                op=f"rule.add#{outcome['index']}",
                changeset=changeset.id,
                request=request.id,
                evidence=evidence,
            )
            try:
                with store.transaction() as tx:
                    records = add_rule(tx, store, op, w, standing, evidence=evidence)
                    current = tx.get("changeset", changeset.id)
                    ops = current.data["ops"]
                    done = next(o for o in ops if o["index"] == outcome["index"])
                    done.update(status="applied", records=records, reason=None)
                    status = "held" if any(o["status"] == "held" for o in ops) else "applied"
                    tx.update(
                        "changeset",
                        changeset.id,
                        {"ops": ops, "status": status},
                        WriteContext(actor="engine", trust="trusted", op="rules.move"),
                        read_version=current.version,
                    )
                    for record in records:
                        stored = tx.get(record["kind"], record["id"])
                        if stored is not None and stored.data.get("status") == "proposed":
                            made.append(stored.id)
            except StoreError:
                continue  # it could not be added as it stands, so it stays for the person
    return made


def _pm(store: Any, cfg: Any) -> str | None:
    from engine.names import People

    return People(store, cfg).pm


# ---- the learning runs, held for one go ------------------------------------------------------------------------------


def waits_on_go(request: Any) -> bool:
    """Whether a request's data says it is a catch-up learning run waiting for the person's go."""
    return (
        request.get("state") == "needs_you"
        and request.get("approval") == "required"
        and request.get("waiting") == WAITING
        and not request.get("dismissed")
    )


#: The kinds of correction whose note is what the person wrote: a send-back's note, what they asked to change, their
#: answer, the new wording of a question, the text of a message as they used it.
THEIR_WORDS = ("sent_back", "change_requested", "answered_assistant", "reworded", "draft_edited", "missed")


def holds_their_words(signal: dict[str, Any]) -> bool:
    """Whether a correction carries something the person wrote (a note on a kind whose note is theirs)."""
    return signal["kind"] in THEIR_WORDS and bool((signal.get("note") or "").strip())


def _to_learn_from(view: Any, group: Group, requests: dict[str, Any]) -> str | None:
    """The correction to learn a kind from: the newest that holds the person's own words, else the newest, among those
    with no learning request of its own that can be learned from. None when the kind already has a learning request
    that wasn't netted out (it is queued, running or done), or nothing in it can be learned from."""
    for signal_id in group.signals:
        found = requests.get(signal_id)
        if found is not None and not (
            found.data["state"] == "done" and found.data.get("waiting") == learn.NETTED_WAITING
        ):
            return None
    eligible = []
    for signal_id in group.signals:
        stored = view.get("signal", signal_id)
        if (
            signal_id not in requests
            and stored is not None
            and stored.data["kind"] in learn.TEACHES
            and not learn._names_set_aside(view, stored.data)
        ):
            eligible.append(stored)
    # One that holds the person's own words says most about what they wanted; otherwise the newest.
    return next((s.id for s in eligible if holds_their_words(s.data)), eligible[0].id if eligible else None)


def queue_learning(ws: Any, store: Any, cfg: Any, router: Any = None, now: datetime | None = None) -> list[str]:
    """Queue the learning runs for the kinds of correction on the list that no entry was learned from yet, held for
    the person's go with each run's estimate. A correction that was learned from, was netted out, or already has a
    learning request is skipped, so running this again queues nothing new. Nothing is queued while learning is off.
    `router` is a router, or a function that makes one when there is something to price. Returns the ids of the
    requests made."""
    state = load(store)
    if state is None or not cfg.dispatch.knowledge.learn:
        return []
    now = now or datetime.now(UTC)
    with changing(state_path(store)):
        view = store.read()
        requests = {sid: r for r in view.list("request") if (sid := learn.signal_of(r.data)) is not None}
        picked = [s for g in waiting(view, state) if (s := _to_learn_from(view, g, requests)) is not None]
        if not picked:
            return []
        with store.transaction() as tx:
            made = [
                tx.create(
                    "request",
                    {
                        "task": learn.TASK,
                        "about": {"kind": "signal", "id": signal_id},
                        "origin": "schedule",
                        "state": "needs_you",
                        "approval": "required",
                        "waiting": WAITING,
                        "created_at": now.isoformat(),
                    },
                    _ENGINE,
                ).id
                for signal_id in picked
            ]
    _price(ws, store, cfg, router, made, now)
    return made


def _price(
    ws: Any, store: Any, cfg: Any, router: Any, request_ids: list[str], now: datetime, ctx: WriteContext | None = None
) -> None:
    """Put each queued run's estimate on its request, so the line can show one total. A run with no price is left
    without one. `ctx`: who writes the estimate (the engine's own, by default)."""
    import os

    from engine.ai.router import Router
    from engine.dispatcher import estimate_request

    router = router() if callable(router) else router or Router(cfg, store, env=os.environ)
    for request_id in request_ids:
        try:
            estimate = estimate_request(ws, store, cfg, router, request_id, now)
        except Exception:  # a run that can't be priced is shown as unpriced, never blocks the others
            estimate = None
        if estimate is None:
            continue
        with store.transaction() as tx:
            current = tx.get("request", request_id)
            tx.update(
                "request",
                request_id,
                {"estimate_usd": round(estimate, 4)},
                ctx or _ENGINE,
                read_version=current.version,
            )


def total_waiting(view: Any) -> tuple[int, float | None, int]:
    """The runs waiting for the go, what the ones with a price cost together (None when none has one) and how many
    have no price."""
    held = [r for r in view.list("request") if waits_on_go(r.data)]
    priced = [r.data["estimate_usd"] for r in held if r.data.get("estimate_usd") is not None]
    return len(held), (round(sum(priced), 4) if priced else None), len(held) - len(priced)


def grant_go(store: Any) -> int:
    """The person's go: every learning run held for it is approved and queued. Returns how many were."""
    started = 0
    with store.transaction() as tx:
        for req in tx.list("request"):
            if waits_on_go(req.data):
                tx.update(
                    "request",
                    req.id,
                    {"approval": "granted", "state": "queued", "waiting": None},
                    _GO,
                    read_version=req.version,
                )
                started += 1
    return started
