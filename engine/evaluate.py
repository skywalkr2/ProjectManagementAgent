"""Evaluation (design 6.16): run fictional cases through the whole pipeline and score the result deterministically.

Each case hands in a note or pasted text to a fresh copy of a workspace, lets the assistant process it, then checks
what was applied or held against the case's expectations and forbidden outcomes. Each case runs several times because
models answer differently from run to run; the report gives a pass rate per case. A model may judge nothing here.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.dispatcher import process
from engine.intake import hand_in
from engine.storage import Store
from engine.workspace import init_workspace

RECEIVED_HOUR = 14  # a case that gives only a day is received at this hour, UTC


@dataclass
class RunResult:
    case: str
    run: int
    passed: bool
    missing: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    refused: int = 0
    held: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    error: str | None = None
    got: list[str] = field(default_factory=list)  # what the model produced, shown when the case fails
    not_run: bool = False  # the account wouldn't take the call (rate limit, quota); says nothing about the model


@dataclass
class Report:
    account: str
    runs: int
    results: list[RunResult]

    def pass_rate(self, case: str | None = None) -> float:
        rows = [r for r in self.results if (case is None or r.case == case) and not r.not_run]
        return sum(r.passed for r in rows) / len(rows) if rows else 0.0

    def not_run(self) -> int:
        return sum(r.not_run for r in self.results)

    def cases(self) -> list[str]:
        return list(dict.fromkeys(r.case for r in self.results))

    def text(self) -> str:
        lines = [f"Account: {self.account}   runs per case: {self.runs}", ""]
        for case in self.cases():
            rows = [r for r in self.results if r.case == case]
            notes = sorted({m for r in rows for m in r.missing + r.forbidden + ([r.error] if r.error else [])})
            score = "  n/a" if all(r.not_run for r in rows) else f"{self.pass_rate(case):>5.0%}"
            lines.append(f"{score}  {case}" + (f"   ({'; '.join(notes)})" if notes else ""))
            got = next((r.got for r in rows if not r.passed and r.got), None)
            if got:
                lines.append("        got: " + "; ".join(got))
        cost = sum(r.cost_usd for r in self.results)
        skipped = self.not_run()
        tail = f"   not run: {skipped} (the account refused the calls; run again later)" if skipped else ""
        lines += ["", f"Overall pass rate: {self.pass_rate():.0%}   cost: ${cost:.4f}{tail}"]
        return "\n".join(lines)

    def as_json(self) -> str:
        return json.dumps(
            {
                "account": self.account,
                "runs": self.runs,
                "pass_rate": self.pass_rate(),
                "results": [asdict(r) for r in self.results],
            },
            indent=2,
        )


def received_of(case: dict[str, Any]) -> datetime:
    """When a case's input arrived: its `received` day (at a fixed hour) or date-time (with an offset)."""
    value = case.get("received")
    if isinstance(value, datetime):
        when = value
    elif isinstance(value, date):
        when = datetime(value.year, value.month, value.day, RECEIVED_HOUR, tzinfo=UTC)
    elif isinstance(value, str) and value.strip():
        try:
            when = datetime.fromisoformat(value.strip())
        except ValueError:
            raise ValueError(f"case {case['id']}: received {value!r} is not a day or a date-time") from None
        if len(value.strip()) == 10:
            when = when.replace(hour=RECEIVED_HOUR)
    else:
        raise ValueError(
            f"case {case['id']} has no received date: say when its input arrived, for example received: '2026-10-09'"
        )
    return when if when.tzinfo is not None else when.replace(tzinfo=UTC)


def load_cases(template: Path) -> list[dict[str, Any]]:
    cases = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((template / "evals").glob("*.yaml"))]
    for case in cases:
        received_of(case)
    return cases


def evaluate(
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
) -> Report:
    """Run every case (or `only` these) `runs` times. With `stub`, the stand-in AI gives each case's ideal answer, which
    checks the cases and the pipeline rather than a model. `ai_config` replaces the fixture's AI setup with another
    workspace's `ai.yaml`, so the PM's own accounts run against the fictional cases."""
    env = os.environ if env is None else env
    results: list[RunResult] = []
    cases = [c for c in load_cases(template) if not only or c["id"] in only]
    total = len(cases) * runs
    for case in cases:
        for n in range(1, runs + 1):
            step = f"[{len(results) + 1}/{total}] {case['id']}"
            if notice is not None:
                notice(f"{step}: started")
            waited = (
                (lambda s, step=step: notice(f"{step}: the account asked to slow down; trying again in {s:.0f}s"))
                if notice
                else None
            )
            results.append(
                _run_case(template, case, n, account=account, stub=stub, env=env, ai_config=ai_config, on_wait=waited)
            )
            if progress is not None:
                progress(results[-1], len(results), total)
    return Report(account or ("stub" if stub else "configured"), runs, results)


def _run_case(
    template: Path,
    case: dict[str, Any],
    n: int,
    *,
    account: str | None,
    stub: bool,
    env: Mapping[str, str],
    ai_config: Path | None = None,
    on_wait: Callable[[float], None] | None = None,
) -> RunResult:
    with tempfile.TemporaryDirectory() as tmp:
        ws = init_workspace(Path(tmp) / "ws", template=template, git=False)
        if ai_config is not None:
            shutil.copyfile(ai_config, ws.config_dir / "ai.yaml")
        flags: dict[str, Any] = {}
        if stub:
            flags = {
                "ai.providers.stub": {
                    "adapter": "stub",
                    "models": {"default": "scripted"},
                    "allowed_data": ["open", "internal", "restricted"],
                },
                "ai.tiers.routine.use": "stub/default",
                "ai.tiers.routine.fallback": [],
            }
            set_responder(lambda task, answer=case["stub_answer"]: json.dumps(answer))
        elif account:
            flags = {"ai.tiers.routine.use": account, "ai.tiers.routine.fallback": []}
        cfg = ws.config(env={}, flags=flags)
        store = Store(ws.db_path)
        try:
            people_before = len(store.read().list("person"))
            now = received_of(case)
            handed = hand_in(ws, store, note=case.get("note", ""), pasted=case.get("pasted", ""), now=now)
            cs_id = process(ws, store, cfg, Router(cfg, store, env=env, on_wait=on_wait), handed.request, now=now)
            runs = [r.data for r in store.read().list("run")]
            cost = sum(r.get("cost_usd") or 0.0 for r in runs)
            seconds = sum(r.get("seconds") or 0.0 for r in runs)
            if cs_id is None:
                why = store.read().get("request", handed.request).data.get("waiting")
                last = runs[-1] if runs else {}
                refused = last.get("error_kind") in ("rate_limited", "quota")
                return RunResult(case["id"], n, False, error=why, cost_usd=cost, seconds=seconds, not_run=refused)
            outcomes = store.read().get("changeset", cs_id).data["ops"]
            missing = [_describe(e) for e in case.get("expect", []) if not _matches(e, outcomes, store)]
            forbidden = [_describe(f) for f in case.get("forbid", []) if _forbidden(f, outcomes, store, people_before)]
            passed = not missing and not forbidden
            return RunResult(
                case["id"],
                n,
                passed,
                missing,
                forbidden,
                got=[] if passed else [_summarize(o) for o in outcomes],
                refused=sum(o["status"] == "refused" for o in outcomes),
                held=sum(o["status"] == "held" for o in outcomes),
                cost_usd=cost,
                seconds=seconds,
            )
        finally:
            store.close()
            set_responder(None)


# ---- matching --------------------------------------------------------------------------------------------------------


def _applied(outcomes: list[dict[str, Any]], op: str) -> list[dict[str, Any]]:
    return [o for o in outcomes if o["status"] == "applied" and o["op"]["op"] == op]


def _record(store: Store, outcome: dict[str, Any], kind: str) -> dict[str, Any] | None:
    for ref in outcome.get("records", []):
        if ref["kind"] == kind:
            rec = store.read().get(kind, ref["id"])
            if rec is not None:
                return rec.data
    return None


def _has_words(text: str, words: list[str]) -> bool:
    return all(w.lower() in text.lower() for w in words)


def _matches(e: dict[str, Any], outcomes: list[dict[str, Any]], store: Store) -> bool:
    if e.get("held") == "who-is":
        found = 0
        for o in outcomes:
            if o["status"] == "held" and o.get("question"):
                q = store.read().get("question", o["question"])
                if q and len(q.data.get("options", [])) == e.get("options", len(q.data.get("options", []))):
                    found += 1
        return found == e["count"] if "count" in e else found > 0
    op = e["op"]
    for o in _applied(outcomes, op):
        if op == "action.add":
            a = _record(store, o, "action")
            if a is None:
                continue
            owners = sorted(x["person"] for x in a["owners"])
            if "owners" in e and owners != sorted(e["owners"]):
                continue
            if "text_has" in e and not _has_words(a["text"], e["text_has"]):
                continue
            if "due" in e and a.get("due") != e["due"]:
                continue
            if "status" in e and a["status"] != e["status"]:
                continue
            return True
        if op in ("action.close", "question.done") and o["op"]["id"] == e["id"]:
            return True
        same_field = op == "record.set" and o["op"]["id"] == e["id"] and o["op"]["field"] == e["field"]
        if same_field and ("value" not in e or str(o["op"]["value"]) == str(e["value"])):
            return True
        if op == "question.add":
            q = _record(store, o, "question")
            if q and q["to"] == e.get("to", q["to"]) and q["kind"] == e.get("kind", q["kind"]):
                return True
        if op == "fact":
            f = _record(store, o, "fact")
            if f and _has_words(f["text"], e.get("text_has", [])):
                return True
        if op == "note":
            return True
    return False


def _forbidden(f: dict[str, Any], outcomes: list[dict[str, Any]], store: Store, people_before: int) -> bool:
    if f.get("new_person"):
        return len(store.read().list("person")) > people_before
    for o in _applied(outcomes, f["op"]):
        if f["op"] == "question.add" and "to" in f:
            q = _record(store, o, "question")
            if q and q["to"] != f["to"]:
                continue
        if "text_has" in f:
            text = json.dumps(o["op"])
            if not _has_words(text, f["text_has"]):
                continue
        return True
    return False


def _summarize(outcome: dict[str, Any]) -> str:
    """One produced op in a few words: its name, the fields that decide a match, and what happened to it."""
    op = outcome["op"]
    keys = ("to", "kind", "owners", "id", "due", "field")
    fields = ", ".join(f"{k}={op[k]}" for k in keys if op.get(k) not in (None, [], ""))
    return f"{op['op']}({fields}) {outcome['status']}"


def _describe(item: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in item.items())
