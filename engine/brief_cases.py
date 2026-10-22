"""The brief's evaluation cases (design 6.32): one day, as records, and the brief it must make.

The brief is built by rules, so a case is scored exactly: it names the form and the moment, the records the day starts
from, what happened since (so what changed overnight has a history), and the lines each section must hold. A
workspace's cases are the files in its `briefs/` folder, one case each:

    id: <name>                  # the case's name
    sample: 1                   # which of the ten sample mornings it stands for, 1 to 10
    title: ...
    received: '2026-10-19'      # the day it is, and the day the starting records were made
    now: '2026-10-19T09:00'     # the moment the brief is made, on the workspace's clock
    form: morning               # morning, evening or monday
    given: [{kind, id, fields}] # the records the day starts from, on top of the workspace's people and projects (its
                                # own actions, questions and calendar entries are left out so each case is alone)
    then:                       # what happened after, oldest first; each has `at` (a moment on the workspace's clock)
    - news: {action, text, by}  # a message from a person said something about an action (it applies on its own)
    - update: {kind, id, fields, rule}   # a record changed: `rule: calendar` is a calendar read, none is the person
    - create: {kind, id, fields, rule}   # a record made, the same way
    expect:                     # the sections in order, each the lines it holds, each line the values it must have
      changed: [{kind, change, text, person, day, at, ...}]
    quiet: true                 # instead of `expect`: nothing to say, so one line and no section
    left: [booking]             # what the sample has that no rule makes yet, so the case leaves it out

A line's values are those of `engine.brief.Line`; `link` is `[kind, id]`. Scoring is exact: the sections and their lines
must be these, in this order, with these values; a value a line is not given to check is not compared, but every line
the brief makes must be one the case names. Ids and names come from the workspace's own people.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from engine import brief
from engine.records import REGISTRY
from engine.storage import Store, StoreError, WriteContext
from engine.today import zone
from engine.workspace import init_workspace
from engine.yaml_load import load_yaml

FOLDER = "briefs"
#: What a sample has that no rule makes yet, by the name a case gives it.
LEFT = ("deadline", "booking", "document_dates", "meeting_dependency")
#: The records of the workspace that a case starts without, so what the case gives is all there is.
LEFT_OUT = ("action", "question", "event", "series", "note")

_STARTING = WriteContext(actor="import", trust="trusted", op="import")
_CALENDAR = WriteContext(actor="engine", trust="untrusted", op="calendar.keep")
_PERSON = WriteContext(actor="pm", trust="trusted", op="test.brief-case")


class Clock:
    """The store's clock, set to the moment each step happens."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> str:
        return self.now.astimezone(UTC).isoformat(timespec="seconds")


@dataclass
class Outcome:
    """A case's result: what is wrong with the brief it made (none when it is right), and the brief."""

    case: str
    problems: list[str]
    made: brief.Brief


def load_cases(template: Path) -> list[dict[str, Any]]:
    """The cases in a workspace's `briefs/` folder, checked for the shape this module documents."""
    cases = []
    seen: set[str] = set()
    for path in sorted((template / FOLDER).glob("*.yaml")):
        case = load_yaml(path.read_text(encoding="utf-8"))
        _check(path.name, case)
        if case["id"] in seen:
            raise ValueError(f"{path.name}: the case {case['id']} is in this workspace twice")
        seen.add(case["id"])
        cases.append(case)
    return cases


def _check(name: str, case: Any) -> None:
    if not isinstance(case, dict):
        raise ValueError(f"{name}: a case is a mapping")
    for key in ("id", "sample", "received", "now", "form"):
        if case.get(key) in (None, ""):
            raise ValueError(f"{name}: a case says its {key}")
    if case["form"] not in brief.FORMS:
        raise ValueError(f"{name}: the form is morning, evening or monday")
    if not isinstance(case["sample"], int) or not 1 <= case["sample"] <= 10:
        raise ValueError(f"{name}: sample is one of the ten sample mornings, 1 to 10")
    if bool(case.get("quiet")) == bool(case.get("expect")):
        raise ValueError(f"{name}: a case is quiet or says what it expects, not both and not neither")
    for kind in case.get("left") or []:
        if kind not in LEFT:
            raise ValueError(f"{name}: left names {', '.join(LEFT)}")
    for record in case.get("given") or []:
        if not isinstance(record, dict) or record.get("kind") not in REGISTRY or not record.get("id"):
            raise ValueError(f"{name}: every starting record needs a kind, an id and its fields")
    for step in case.get("then") or []:
        if not isinstance(step, dict) or not step.get("at") or len({"news", "update", "create"} & set(step)) != 1:
            raise ValueError(f"{name}: every later step says `at` and one of news, update or create")


def _moment(text: str, cfg: Any) -> datetime:
    when = datetime.fromisoformat(str(text))
    return when if when.tzinfo else when.replace(tzinfo=zone(cfg))


def _clear(store: Store) -> None:
    with store.transaction() as tx:
        for kind in LEFT_OUT:
            for found in tx.list(kind):
                tx.delete(kind, found.id, _STARTING, read_version=found.version)


def _news(store: Store, cfg: Any, step: dict[str, Any], at: datetime) -> None:
    """A message from a person said something about an action: `action.news`, which applies by itself."""
    from engine.applier import Context, Inputs, apply_changeset
    from engine.names import People
    from engine.ops import CHANGESET

    said = step["news"]
    people = People(store, cfg)
    words = str(said["text"]).strip()
    with store.transaction() as tx:
        source = tx.create(
            "source",
            {
                "received_at": at.astimezone(UTC).isoformat(),
                "kind": "watched:mailbox",
                "title": "A message",
                "content_hash": "0" * 64,
                "trust": "untrusted",
                "watched": {
                    "source": "inbox",
                    "key": f"<{said['action']}@example.com>",
                    "change": "new",
                    "author": people.name(said["by"]),
                    "by_you": False,
                    "by_us": False,
                },
            },
            _STARTING,
        ).id
        request = tx.create(
            "request",
            {
                "task": "notes",
                "origin": "input",
                "state": "done",
                "created_at": at.astimezone(UTC).isoformat(),
                "source": source,
            },
            _STARTING,
        ).id
    ctx = Context(
        store,
        cfg,
        people,
        tuple(store.plugins.ops),
        Inputs(request, source, f"{words}.", "", "untrusted"),
        actor="assistant",
        confirmed_by_pm=False,
    )
    op = {"op": "action.news", "id": said["action"], "text": words, "evidence": {"quote": words}}
    changeset = CHANGESET.validate_python({"ops": [op]}, context={"op_models": store.plugins.ops})
    apply_changeset(changeset, [], ctx, run=None, now=at.astimezone(UTC))


def _step(store: Store, cfg: Any, clock: Clock, step: dict[str, Any]) -> None:
    at = _moment(step["at"], cfg)
    clock.now = at
    if "news" in step:
        _news(store, cfg, step, at)
        return
    kind = "update" if "update" in step else "create"
    what = step[kind]
    ctx = _CALENDAR if what.get("rule") == "calendar" else _PERSON
    with store.transaction() as tx:
        if kind == "create":
            tx.create(what["kind"], dict(what.get("fields") or {}), ctx, record_id=what["id"])
            return
        found = tx.get(what["kind"], what["id"])
        if found is None:
            raise ValueError(f"the step on {what['kind']} {what['id']} names a record the case never made")
        tx.update(what["kind"], found.id, dict(what.get("fields") or {}), ctx, read_version=found.version)


def run(template: Path, case: dict[str, Any], work: Path | None = None) -> Outcome:
    """Make a case's day in a copy of the workspace and the brief it asks for, and say what is wrong with it."""
    folder = Path(work) if work is not None else Path(tempfile.mkdtemp(prefix="brief-case-"))
    try:
        ws = init_workspace(folder / "ws", template=template, git=False)
        cfg = ws.config(env={})
        received = _moment(f"{case['received']}T00:00", cfg)
        clock = Clock(received - timedelta(days=7))
        store = Store(ws.db_path, cfg=cfg, clock=clock)
        try:
            _clear(store)
            order = list(REGISTRY)
            with store.transaction(notify=False) as tx:
                for record in sorted(case.get("given") or [], key=lambda r: order.index(r["kind"])):
                    tx.create(record["kind"], dict(record.get("fields") or {}), _STARTING, record_id=record["id"])
            for step in sorted(case.get("then") or [], key=lambda s: str(s["at"])):
                _step(store, cfg, clock, step)
            now = _moment(case["now"], cfg)
            clock.now = now
            made = brief.build(ws, store, cfg, now, case["form"])
        finally:
            store.close()
    except (StoreError, ValueError) as err:
        raise ValueError(f"case {case['id']}: it can't be made: {err}") from None
    finally:
        if work is None:
            shutil.rmtree(folder, ignore_errors=True)
    return Outcome(case["id"], score(made, case), made)


def _value(line: brief.Line, field: str) -> Any:
    found = getattr(line, field)
    return list(found) if isinstance(found, tuple) else found


def score(made: brief.Brief, case: dict[str, Any]) -> list[str]:
    """What is wrong with a brief against its case: the sections, their order, and every line against what the case
    names. Exact: a line or a section the case doesn't name is wrong, and so is one it names that is missing."""
    problems: list[str] = []
    if case.get("quiet"):
        if not made.quiet or made.sections:
            problems.append("expected a quiet day with no section, got " + ", ".join(s.key for s in made.sections))
        return problems
    if made.quiet:
        problems.append("expected lines, got a quiet day")
    expect = case["expect"]
    got = [s.key for s in made.sections]
    if got != list(expect):
        problems.append(f"sections {got} where {list(expect)} were expected")
    by_key = {s.key: s for s in made.sections}
    for key, wanted in expect.items():
        lines = by_key[key].lines if key in by_key else []
        if len(lines) != len(wanted):
            problems.append(f"{key}: {len(lines)} lines where {len(wanted)} were expected")
        for index, (line, values) in enumerate(zip(lines, wanted, strict=False), start=1):
            for field, wants in values.items():
                if not hasattr(line, field):
                    problems.append(f"{key} line {index}: a line has no {field}")
                elif _value(line, field) != wants:
                    problems.append(f"{key} line {index}: {field} is {_value(line, field)!r}, expected {wants!r}")
    return problems
