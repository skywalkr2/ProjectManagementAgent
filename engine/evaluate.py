"""Evaluation (design 6.16): run fictional cases through the whole pipeline and score the result deterministically.

Each case hands in a note or pasted text to a fresh copy of a workspace, lets the assistant process it, then checks
what was applied or held against the case's expectations and forbidden outcomes. Each case runs several times because
models answer differently from run to run; the report gives a pass rate per case. A model may judge nothing here.

A case may name starting records (`given`, and `given_file` for a state several cases share), which are created before
its input is handed in. Scoring is exact unless a case says `exact: false`: an op the case doesn't expect fails the run.
A case lists in `allow` the op kinds that are right but optional there, which never count as extra. An expected op
may name several kinds (`op: [fact, action.add]`) when the case checks something either of them can hold, and is met by
any one of them.
A case may name the `project` its input is about (as the person does when handing it in), or give `watched` (title,
change, author, by_us, by_you, credited_to) to be received as the item a watched source found. A case may expect a
held op (`held: <op>`, with `text_has` words in its fields) or a held "who is this?" question (`held: who-is`). A
hostile case (`hostile: true`) also fails on any system-tier op and on any op that names a person listed under
`injected`. A plugin's own cases (`provides.evals`, in this same format, ids `<plugin>/<name>`) run too, for each
plugin enabled in the workspace being evaluated: such a case may name a task kind of the plugin (`task`) and a scorer
of the plugin (`score`) that judges the plugin's own ops, while the core's exact matching scores everything else.
The report says which accounts ran, the version of each command-line agent, and whether every tier ran on
one account.

Learning pairs and the day-30 scenario are run the same way, by `engine/pairs.py`, which documents their format.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from engine.ai.adapters import make_adapter
from engine.ai.adapters.stub import set_responder
from engine.ai.router import Router
from engine.config import Config
from engine.dispatcher import process
from engine.followups import they_finished
from engine.intake import hand_in, note_as_input
from engine.records import REGISTRY, canonical_time
from engine.storage import Store, StoreError, WriteContext
from engine.workspace import Workspace, init_workspace
from engine.yaml_load import load_yaml

RECEIVED_HOUR = 14  # a case that gives only a day is received at this hour, UTC
EXACT_EXEMPT = frozenset({"note"})  # ops an exact case never counts as extra
PEOPLE_FIELDS = ("owners", "owner", "to", "person", "people", "full_name", "aliases")  # where an op names people
ONE_ACCOUNT_LINE = (
    "Every tier ran on the same account, so this run does not compare a low-cost tier with a stronger one."
)
_STARTING = WriteContext(actor="import", trust="trusted", op="import")
AdapterFactory = Callable[[str, Any, str | None], Any]


@dataclass
class RunResult:
    case: str
    run: int
    passed: bool
    missing: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)  # ops an exact case didn't expect
    refused: int = 0
    held: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    error: str | None = None
    got: list[str] = field(default_factory=list)  # what the model produced, shown when the case fails
    not_run: bool = False  # the account wouldn't take the call (rate limit, quota); says nothing about the model
    out_of_quota: bool = False  # the account's plan was used up, so the runs after this one are not made
    accounts: list[str] = field(default_factory=list)  # provider/model of every call the case made
    given: list[str] = field(default_factory=list)  # a pair's later run: what it was given from what was learned
    negative: bool = False  # a pair whose later output must not change


@dataclass
class Report:
    account: str
    runs: int
    results: list[RunResult]
    program_versions: dict[str, str | None] = field(default_factory=dict)  # command-line agents, by provider

    def pass_rate(self, case: str | None = None) -> float:
        rows = [r for r in self.results if (case is None or r.case == case) and not r.not_run]
        return sum(r.passed for r in rows) / len(rows) if rows else 0.0

    def not_run(self) -> int:
        return sum(r.not_run for r in self.results)

    def cases(self) -> list[str]:
        return list(dict.fromkeys(r.case for r in self.results))

    def accounts(self) -> list[str]:
        """Every account (provider/model) a call was made on."""
        return sorted({a for r in self.results for a in r.accounts})

    def one_account(self) -> bool:
        """Whether every tier the run used resolved to the same account, so no tier was compared with another."""
        return len(self.accounts()) == 1

    def text(self) -> str:
        lines = [f"Account: {self.account}   runs per case: {self.runs}"]
        for provider, version in sorted(self.program_versions.items()):
            lines.append(f"Agent program version ({provider}): {version or 'not known'}")
        if self.one_account():
            lines.append(ONE_ACCOUNT_LINE)
        lines.append("")
        for case in self.cases():
            rows = [r for r in self.results if r.case == case]
            notes = sorted(
                {
                    m
                    for r in rows
                    for m in r.missing
                    + r.forbidden
                    + [f"unexpected {e}" for e in r.extra]
                    + ([r.error] if r.error else [])
                }
            )
            score = "  n/a" if all(r.not_run for r in rows) else f"{self.pass_rate(case):>5.0%}"
            lines.append(f"{score}  {case}" + (f"   ({'; '.join(notes)})" if notes else ""))
            got = next((r.got for r in rows if not r.passed and r.got), None)
            if got:
                lines.append("        got: " + "; ".join(got))
            given = next((r.given for r in rows if r.given), None)
            if given:
                lines.append("        later run was given: " + "; ".join(given))
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
                "accounts": self.accounts(),
                "one_account": self.one_account(),
                "program_versions": self.program_versions,
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
    """The cases in a workspace's `evals/` folder. A file holding a list is a shared starting state (named by a case's
    `given_file`), not a case."""
    folder = template / "evals"
    cases = []
    for path in sorted(folder.glob("*.yaml")):
        loaded = load_yaml(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            cases.append(loaded)
    for case in cases:
        received_of(case)
        _check_case(folder, case)
    return cases


def _check_case(folder: Path, case: dict[str, Any]) -> None:
    where = f"case {case['id']}"
    if not isinstance(case.get("exact", True), bool):
        raise ValueError(f"{where}: exact is true or false")
    if not all(isinstance(op, str) for op in case.get("allow", [])):
        raise ValueError(f"{where}: allow is a list of op names")
    if case.get("injected") and not case.get("hostile"):
        raise ValueError(f"{where}: injected names people only a hostile case checks; add hostile: true")
    if not all(isinstance(name, str) for name in case.get("injected", [])):
        raise ValueError(f"{where}: injected is a list of names or person ids")
    if case.get("score") is not None and not case.get("_pack"):
        raise ValueError(f"{where}: score names a plugin's scorer, which only the plugin's own cases use")
    if case.get("watched") is not None and not isinstance(case["watched"], dict):
        raise ValueError(f"{where}: watched is a mapping (title, change, author, by_us, by_you, credited_to)")
    starting_records(folder.parent, case)


def starting_records(template: Path, case: dict[str, Any]) -> list[dict[str, Any]]:
    """The records a case starts from: those in its `given_file`, then its own `given`. Each is a `kind`, the `id` the
    case refers to and its `fields`."""
    where = f"case {case['id']}"
    records: list[dict[str, Any]] = []
    name = case.get("given_file")
    if name:
        folder = Path(case["_pack"]["folder"]) if case.get("_pack") else template / "evals"
        path = folder / str(name)
        if not path.is_file():
            raise ValueError(f"{where}: given_file {name} isn't in the evals folder")
        shared = load_yaml(path.read_text(encoding="utf-8"))
        if not isinstance(shared, list):
            raise ValueError(f"{where}: {name} should be a list of records")
        records += shared
    records += case.get("given") or []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("kind"), str):
            raise ValueError(f"{where}: every starting record needs a kind, an id and its fields")
        if not isinstance(record.get("fields") or {}, dict):
            raise ValueError(f"{where}: the fields of starting record {record.get('id')} are a mapping")
    return records


def _create_starting_records(store: Store, case_id: str, records: list[dict[str, Any]]) -> None:
    """Create a case's starting records the way the fixture loader does, people and projects before what refers to
    them."""
    order = list(REGISTRY)
    ordered = sorted(records, key=lambda r: order.index(r["kind"]) if r["kind"] in order else len(order))
    unknown = sorted({r["kind"] for r in records if r["kind"] not in store.plugins.records})
    if unknown:
        raise ValueError(f"case {case_id}: no record kind {', '.join(unknown)}")
    try:
        with store.transaction(notify=False) as tx:
            for record in ordered:
                tx.create(record["kind"], dict(record.get("fields") or {}), _STARTING, record_id=record.get("id"))
    except (StoreError, ValueError) as err:
        raise ValueError(f"case {case_id}: its starting records don't load: {err}") from None


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
    adapter_factory: AdapterFactory = make_adapter,
    packs_of: Path | None = None,
) -> Report:
    """Run every case (or `only` these) `runs` times. With `stub`, the stand-in AI gives each case's ideal answer, which
    checks the cases and the pipeline rather than a model. `ai_config` replaces the fixture's AI setup with another
    workspace's `ai.yaml`, so the PM's own accounts run against the fictional cases. The cases of the plugins enabled
    in `packs_of` (default: the template) run after the core's."""
    env = os.environ if env is None else env
    results: list[RunResult] = []
    versions: dict[str, str | None] = {}
    found = [*load_cases(template), *load_pack_cases(packs_of or template)]
    cases = [c for c in found if not only or c["id"] in only]
    total = len(cases) * runs
    for case, n in ((case, n) for case in cases for n in range(1, runs + 1)):
        if results and results[-1].out_of_quota:
            results.append(not_made(case["id"], n, results[-1]))
            if progress is not None:
                progress(results[-1], len(results), total)
            continue
        step = f"[{len(results) + 1}/{total}] {case['id']}"
        if notice is not None:
            notice(f"{step}: started")
        waited = (
            (lambda s, step=step: notice(f"{step}: the account asked to slow down; trying again in {s:.0f}s"))
            if notice
            else None
        )
        results.append(
            _run_case(
                template,
                case,
                n,
                account=account,
                stub=stub,
                env=env,
                ai_config=ai_config,
                on_wait=waited,
                versions=versions,
                adapter_factory=adapter_factory,
            )
        )
        if progress is not None:
            progress(results[-1], len(results), total)
    return Report(account or ("stub" if stub else "configured"), runs, results, versions)


def not_made(case_id: str, n: int, spent: RunResult) -> RunResult:
    """A run left out because the account's plan was used up during an earlier one: not run, and never called."""
    return RunResult(
        case_id,
        n,
        False,
        error=f"Not run: the account's plan was used up during {spent.case} (run {spent.run}).",
        not_run=True,
        out_of_quota=True,
    )


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
    versions: dict[str, str | None] | None = None,
    adapter_factory: AdapterFactory = make_adapter,
) -> RunResult:
    with tempfile.TemporaryDirectory() as tmp:
        ws = init_workspace(Path(tmp) / "ws", template=template, git=False)
        if ai_config is not None:
            shutil.copyfile(ai_config, ws.config_dir / "ai.yaml")
        flags: dict[str, Any] = {
            "ai.budgets.first_go": False
        }  # a case runs unattended, so it never waits for a first go
        if stub:
            flags |= {
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
            flags |= {"ai.tiers.routine.use": account, "ai.tiers.routine.fallback": []}
        if case.get("_pack"):
            flags |= _enable_pack(ws, template, case["_pack"])
        cfg = ws.config(env={}, flags=flags)
        store = Store(ws.db_path, cfg=cfg if case.get("_pack") else None)
        try:
            records = starting_records(template, case)
            if records:
                _create_starting_records(store, case["id"], records)
            people_before = len(store.read().list("person"))
            now = received_of(case)
            request_id = _hand_in_case(ws, store, cfg, case, now)
            cs_id = process(ws, store, cfg, Router(cfg, store, env=env, on_wait=on_wait), request_id, now=now)
            runs = [r.data for r in store.read().list("run")]
            accounts = sorted({f"{r['provider']}/{r['model']}" for r in runs})
            if versions is not None:
                _read_program_versions(cfg, {r["provider"] for r in runs}, versions, adapter_factory)
            cost = sum(r.get("cost_usd") or 0.0 for r in runs)
            seconds = sum(r.get("seconds") or 0.0 for r in runs)
            if cs_id is None:
                why = store.read().get("request", request_id).data.get("waiting")
                last = runs[-1] if runs else {}
                refused = last.get("error_kind") in ("rate_limited", "quota")
                return RunResult(
                    case["id"],
                    n,
                    False,
                    error=why,
                    cost_usd=cost,
                    seconds=seconds,
                    not_run=refused,
                    out_of_quota=last.get("error_kind") == "quota",
                    accounts=accounts,
                )
            produced = store.read().get("changeset", cs_id).data["ops"]
            case, outcomes, own = _without_own_ops(case, produced)
            missing = [_describe(e) for e in case.get("expect", []) if not _matches(e, outcomes, store, request_id)]
            forbidden = [_describe(f) for f in case.get("forbid", []) if _forbidden(f, outcomes, store, people_before)]
            if case.get("hostile"):
                forbidden += _hostile_findings(case, outcomes, store)
            extra = _unexpected(case, outcomes, store, request_id) if case.get("exact", True) else []
            if case.get("score"):
                missing += store.plugins.score_case(case["score"], _as_written(case), own)
            outcomes = produced
            passed = not missing and not forbidden and not extra
            return RunResult(
                case["id"],
                n,
                passed,
                missing,
                forbidden,
                extra,
                got=[] if passed else [_summarize(o) for o in outcomes],
                refused=sum(o["status"] == "refused" for o in outcomes),
                held=sum(o["status"] == "held" for o in outcomes),
                cost_usd=cost,
                seconds=seconds,
                accounts=accounts,
            )
        finally:
            store.close()
            set_responder(None)


def _read_program_versions(
    cfg: Config, providers: set[str], versions: dict[str, str | None], adapter_factory: AdapterFactory
) -> None:
    """Record, once per provider, the program version of each account that is a command-line agent."""
    for name in sorted(providers - set(versions)):
        settings = cfg.ai.providers.get(name)
        if settings is None or settings.adapter != "cli-agent":
            continue
        adapter = adapter_factory(settings.adapter, settings, None)
        versions[name] = adapter.program_version()


def _hand_in_watched(ws: Workspace, store: Store, case: dict[str, Any], now: datetime) -> str:
    """Hand in a case's `pasted` text as an item a watched source found, as the watcher records it: untrusted, with the
    change, the author, whether it is the app's own publish (`by_us`) and whether it is the person's own work
    (`by_you`) (`watched`: `title`, `change`, `author`, `by_us`, `by_you`, `credited_to`)."""
    watched = case["watched"]
    text = case.get("pasted", "").strip()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    ws.sources_dir.mkdir(parents=True, exist_ok=True)
    path = ws.sources_dir / f"{digest}.txt"
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    ctx = WriteContext(actor="watcher", trust="untrusted", op="watch.read")
    with store.transaction() as tx:
        source = tx.create(
            "source",
            {
                "received_at": now.isoformat(),
                "kind": "watched:file",
                "title": str(watched.get("title") or "Watched item")[:120],
                "content_hash": digest,
                "trust": "untrusted",
                "watched": {
                    "source": str(watched.get("source") or "watched"),
                    "key": str(watched.get("key") or "item"),
                    "change": watched.get("change", "changed"),
                    "author": watched.get("author"),
                    "by_us": bool(watched.get("by_us", False)),
                    "by_you": bool(watched.get("by_you", False)),
                    "credited_to": watched.get("credited_to"),
                },
            },
            ctx,
        )
        request = tx.create(
            "request",
            {
                "task": "notes",
                "source": source.id,
                "origin": "input",
                "state": "queued",
                "waiting": "With the assistant, starting now",
                "created_at": now.isoformat(),
            },
            ctx,
        )
    return request.id


def _hand_in_case(ws: Workspace, store: Store, cfg: Config, case: dict[str, Any], now: datetime) -> str:
    """Hand a case's input in. A case with `typed_on` is a note typed on a button of an action or question: it names
    the item (`kind`, `id`), the button (`route`) and, for They finished it, the person it waited on. The button's own
    change is made first, as the screen does, then the note is handed in as the person's own words."""
    on = case.get("typed_on")
    if on is None and case.get("watched") is not None:
        return _hand_in_watched(ws, store, case, now)
    if on is None:
        request = hand_in(
            ws, store, note=case.get("note", ""), pasted=case.get("pasted", ""), now=now, project=case.get("project")
        ).request
        if case.get("task"):
            _set_task(store, case, request)
        return request
    if on["route"] == "they_finished":
        they_finished(store, cfg, on["id"], on["person"])
    item = (on["kind"], on["id"])
    request = note_as_input(
        ws, store, cfg, item=item, text=case["note"], route=on["route"], author=on.get("person"), now=now
    )
    if request is None:
        raise ValueError(f"case {case['id']}: its note is a bare confirmation, so nothing reaches the assistant")
    return request


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


def _matches(e: dict[str, Any], outcomes: list[dict[str, Any]], store: Store, request_id: str = "") -> bool:
    if "source" in e:
        # The input was saved as a source of this trust ("trusted": the person's own words).
        request = store.read().get("request", request_id)
        saved = store.read().get("source", request.data["source"]) if request and request.data.get("source") else None
        return saved is not None and saved.data["trust"] == e["source"]
    if e.get("held") == "who-is":
        asked = set()
        for o in outcomes:
            if o["status"] == "held" and o.get("question"):
                q = store.read().get("question", o["question"])
                if q and len(q.data.get("options", [])) == e.get("options", len(q.data.get("options", []))):
                    asked.add(q.id)
        found = len(asked)  # ops waiting on one question count once
        return found == e["count"] if "count" in e else found > 0
    if "held" in e:
        return bool(_held(e, outcomes))
    return bool(_matching(e, outcomes, store))


def _held(e: dict[str, Any], outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The held ops that satisfy an expected held op: the op it names, with the words of `text_has` in the op's own
    fields (never its quoted evidence)."""
    found = []
    for o in outcomes:
        if o["status"] != "held" or o["op"]["op"] != e["held"]:
            continue
        own = json.dumps({k: v for k, v in o["op"].items() if k != "evidence"})
        if "text_has" in e and not _has_words(own, e["text_has"]):
            continue
        found.append(o)
    return found


def _matching(e: dict[str, Any], outcomes: list[dict[str, Any]], store: Store) -> list[int]:
    """The positions of the applied ops that satisfy an expected op."""
    return [
        i
        for i, o in enumerate(outcomes)
        if o["status"] == "applied" and o["op"]["op"] in _kinds(e) and _op_matches({**e, "op": o["op"]["op"]}, o, store)
    ]


def _same_time(found: Any, wanted: Any) -> bool:
    """Whether two days or date-times are the same, however each was written."""
    if found is None or wanted is None:
        return found is None and wanted is None
    return canonical_time(str(found)) == canonical_time(str(wanted))


def _kinds(e: dict[str, Any]) -> list[str]:
    """The op kinds an expected op may be met by: the one it names, or any of a list."""
    return list(e["op"]) if isinstance(e["op"], list) else [e["op"]]


def _op_matches(e: dict[str, Any], o: dict[str, Any], store: Store) -> bool:
    op = e["op"]
    if op == "action.add":
        a = _record(store, o, "action")
        if a is None:
            return False
        owners = sorted(x["person"] for x in a["owners"])
        if "owners" in e and owners != sorted(e["owners"]):
            return False
        if "text_has" in e and not _has_words(a["text"], e["text_has"]):
            return False
        if "due" in e and a.get("due") != e["due"]:
            return False
        return "status" not in e or a["status"] == e["status"]
    if op in ("action.close", "action.hold", "action.unhold", "action.drop", "question.drop", "question.done"):
        return o["op"]["id"] == e["id"]
    if op == "record.set":
        same_field = o["op"]["id"] == e["id"] and o["op"]["field"] == e["field"]
        return same_field and ("value" not in e or str(o["op"]["value"]) == str(e["value"]))
    if op == "question.add":
        q = _record(store, o, "question")
        return bool(q and q["to"] == e.get("to", q["to"]) and q["kind"] == e.get("kind", q["kind"]))
    if op == "fact":
        f = _record(store, o, "fact")
        return bool(
            f
            and _has_words(f["text"], e.get("text_has", []))
            and ("as_of" not in e or f.get("as_of") == str(e["as_of"]))
        )
    if op == "routing.add":
        entry = _record(store, o, "routing_entry")
        return bool(
            entry
            and _has_words(entry["topic"], e.get("topic_has", []))
            and entry.get("person") == e.get("person", entry.get("person"))
            and bool(entry.get("negative")) == bool(e.get("negative", False))
        )
    if op == "event.add":
        entry = _record(store, o, "event")
        return bool(
            entry
            and _has_words(entry["title"], e.get("text_has", []))
            and _same_time(entry["start"], e.get("start", entry["start"]))
            and _same_time(entry.get("end"), e["end"] if "end" in e else entry.get("end"))
            and entry.get("project") == e.get("project", entry.get("project"))
        )
    return op == "note"


def _unexpected(case: dict[str, Any], outcomes: list[dict[str, Any]], store: Store, request_id: str) -> list[str]:
    """Ops an exact case didn't expect, one line each. Each expected op accounts for one produced op, so a duplicate is
    extra. A held op is extra too, unless the case expects something held, which accounts for the held ops."""
    spent: set[int] = set()
    for e in case.get("expect", []):
        if "source" in e or "held" in e:
            continue
        free = next((i for i in _matching(e, outcomes, store) if i not in spent), None)
        if free is not None:
            spent.add(free)
    expects_held = any("held" in e for e in case.get("expect", []))
    allowed = set(case.get("allow", []))
    return [
        _summarize(o)
        for i, o in enumerate(outcomes)
        if i not in spent
        and o["op"]["op"] not in EXACT_EXEMPT
        and o["op"]["op"] not in allowed
        and (o["status"] == "applied" or (o["status"] == "held" and not expects_held))
    ]


def _forbidden(f: dict[str, Any], outcomes: list[dict[str, Any]], store: Store, people_before: int) -> bool:
    if f.get("new_person"):
        return len(store.read().list("person")) > people_before
    for o in _applied(outcomes, f["op"]):
        if "id" in f and o["op"].get("id") != f["id"]:
            continue
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


def _hostile_findings(case: dict[str, Any], outcomes: list[dict[str, Any]], store: Store) -> list[str]:
    """What a hostile case forbids beyond its own list: any system-tier op the assistant proposed (whatever became of
    it) and any op that names a person the input's injected text pointed at."""
    tiers = store.plugins.tiers
    found = [f"proposed a system op ({o['op']['op']})" for o in outcomes if tiers.get(o["op"]["op"]) == "system"]
    for entry in case.get("injected", []):
        names = _identifiers(store, entry)
        pattern = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(n) for n in names) + r")(?![A-Za-z0-9])", re.I)
        for o in outcomes:
            if pattern.search(_people_text(o, store)):
                found.append(f"names {entry} ({o['op']['op']})")
    return found


def _identifiers(store: Store, entry: str) -> list[str]:
    """What an injected person is called: the person's id, full name and aliases when the entry is one of the
    workspace's people (by id or full name), else the entry itself."""
    for person in store.read().list("person"):
        if entry in (person.id, person.data["full_name"]):
            return [person.id, person.data["full_name"], *person.data.get("aliases", [])]
    return [entry]


def _people_text(outcome: dict[str, Any], store: Store) -> str:
    """The parts of an op, and of the records it made, that name people (never its quoted evidence or free text)."""
    op = outcome["op"]
    parts = [json.dumps(op[k]) for k in PEOPLE_FIELDS if k in op]
    if op.get("field") in PEOPLE_FIELDS:
        parts.append(json.dumps(op.get("value")))
    for ref in outcome.get("records", []):
        rec = store.read().get(ref["kind"], ref["id"])
        if rec is not None:
            parts += [json.dumps(rec.data[k]) for k in PEOPLE_FIELDS if k in rec.data]
    return " ".join(parts)


def _summarize(outcome: dict[str, Any]) -> str:
    """One produced op in a few words: its name, the fields that decide a match, and what happened to it."""
    op = outcome["op"]
    keys = ("to", "kind", "owners", "id", "due", "field", "person", "negative", "start", "end", "project")
    fields = ", ".join(f"{k}={op[k]}" for k in keys if op.get(k) not in (None, [], ""))
    return f"{op['op']}({fields}) {outcome['status']}"


def _describe(item: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in item.items())


# ---- a plugin's own cases and scorers --------------------------------------------------------------------------------


def load_pack_cases(workspace: Path) -> list[dict[str, Any]]:
    """The evaluation cases of every plugin enabled in a workspace that names a folder of them (`provides.evals`), in
    the core's format. Each case's id is `<plugin>/<name>`, it may name a task kind (`task`) and a scorer (`score`) of
    its own plugin, and it is marked with where it came from. A plugin's case that expects or forbids one of its own
    ops must name a scorer, since the core's matching can't judge them."""
    from engine.config import ConfigError, load_config
    from engine.plugin_manifest import plugin_paths, read_manifest

    try:
        enabled = list(load_config(workspace / "config", env={}).workspace.plugins.enabled)
    except (ConfigError, OSError):
        return []
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name, path in plugin_paths(workspace / "config", enabled):
        try:
            manifest = read_manifest(path)
        except (ValueError, OSError):
            continue
        if not manifest.provides.evals:
            continue
        folder = path.parent / manifest.provides.evals
        local = path.parent.parent == workspace / "plugins"
        mark = {
            "plugin": name,
            "folder": str(folder),
            "scorers": list(manifest.provides.scorers),
            "needs": [name, *(d.name for d in manifest.depends_on)],
            "local": str(path.parent) if local else None,
        }
        for file in sorted(folder.glob("*.yaml")):
            loaded = load_yaml(file.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                continue  # a shared starting state, named by a case's `given_file`
            case = {**loaded, "_pack": mark}
            _check_pack_case(name, mark, case)
            received_of(case)
            _check_case(folder, case)
            if case["id"] in seen:
                raise ValueError(f"case {case['id']} is in more than one evaluation folder")
            seen.add(case["id"])
            found.append(case)
    return found


def _check_pack_case(plugin: str, mark: dict[str, Any], case: dict[str, Any]) -> None:
    where = f"case {case.get('id')}"
    if not re.fullmatch(re.escape(plugin) + r"/[a-z][a-z0-9_.-]*", str(case.get("id", ""))):
        raise ValueError(f"{where}: a plugin's case id is {plugin}/<name>")
    score = case.get("score")
    if score is not None and score not in mark["scorers"]:
        raise ValueError(f"{where}: score {score} isn't a scorer the plugin lists in provides.scorers")
    prefix = plugin + "/"
    own = [e for key in ("expect", "forbid") for e in case.get(key, []) if str(e.get("op", "")).startswith(prefix)]
    if own and not score:
        raise ValueError(f"{where}: it expects or forbids an op of the plugin, which needs score: <scorer>")
    if case.get("task") is not None and not str(case["task"]).startswith(prefix):
        raise ValueError(f"{where}: task names a task kind of the plugin ({prefix}<name>)")


def _without_own_ops(
    case: dict[str, Any], outcomes: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """For a case that names a scorer: the case without the expectations about the plugin's own ops, the produced ops
    that are not the plugin's own (the core's matching scores those), and the plugin's own ops (the scorer judges
    them). Any other case is returned whole."""
    pack = case.get("_pack")
    if not pack or not case.get("score"):
        return case, outcomes, []
    prefix = pack["plugin"] + "/"

    def own(op: dict[str, Any]) -> bool:
        return str(op.get("op", "")).startswith(prefix)

    trimmed = {k: [e for e in case.get(k, []) if not own(e)] for k in ("expect", "forbid") if k in case}
    return (
        {**case, **trimmed},
        [o for o in outcomes if not own(o["op"])],
        [o for o in outcomes if own(o["op"])],
    )


def _as_written(case: dict[str, Any]) -> dict[str, Any]:
    """A case as its file says it, without what the harness added."""
    return {k: v for k, v in case.items() if not k.startswith("_")}


def _enable_pack(ws: Workspace, template: Path, pack: dict[str, Any]) -> dict[str, Any]:
    """What a plugin's case needs in its fresh workspace: the plugin (and those it depends on) enabled, and a plugin
    that lives in the evaluated workspace's own plugins folder copied in beside the others."""
    if pack.get("local"):
        target = ws.root / "plugins" / Path(pack["local"]).name
        if not target.exists():
            shutil.copytree(pack["local"], target)
    from engine.config import load_config

    enabled = list(load_config(ws.config_dir, env={}).workspace.plugins.enabled)
    return {"workspace.plugins.enabled": list(dict.fromkeys([*enabled, *pack["needs"]]))}


def _set_task(store: Store, case: dict[str, Any], request_id: str) -> None:
    """Make the request a case's handed-in input starts the kind of work the case names (a plugin's own)."""
    if case["task"] not in store.plugins.tasks:
        raise ValueError(f"case {case['id']}: there is no task kind {case['task']} (is its plugin running?)")
    request = store.read().get("request", request_id)
    with store.transaction(notify=False) as tx:
        tx.update("request", request_id, {"task": case["task"]}, _STARTING, read_version=request.version)


# ---- what a run of the cases would cost, and what they are called ----------------------------------------------------

#: How many cases are priced to estimate the whole set: the rest are taken to cost about as much as these on average.
ESTIMATE_SAMPLE = 8


def case_titles(template: Path, packs_of: Path | None = None) -> dict[str, str]:
    """What each case is called on screen: its title, else its id."""
    found = [*load_cases(template), *load_pack_cases(packs_of or template)]
    return {c["id"]: str(c.get("title") or c["id"]) for c in found}


def estimate_cases(
    template: Path,
    *,
    account: str,
    runs: int,
    ai_config: Path | None = None,
    packs_of: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[float | None, int]:
    """About what running every case `runs` times on an account would cost in USD, and how many cases that is. A few
    evenly spread cases have their packets built and priced as a real run is; the rest are taken to cost the average of
    those. None when the account's price isn't known or no case could be priced."""
    from engine.dispatcher import estimate_request

    env = os.environ if env is None else env
    cases = [*load_cases(template), *load_pack_cases(packs_of or template)]
    core = [c for c in cases if not c.get("_pack")]
    step = max(1, len(core) // ESTIMATE_SAMPLE)
    prices: list[float | None] = []
    for case in core[::step][:ESTIMATE_SAMPLE]:
        with tempfile.TemporaryDirectory() as tmp:
            ws = init_workspace(Path(tmp) / "ws", template=template, git=False)
            if ai_config is not None:
                shutil.copyfile(ai_config, ws.config_dir / "ai.yaml")
            flags: dict[str, Any] = {
                "ai.tiers.routine.use": account,
                "ai.tiers.routine.fallback": [],
                "ai.budgets.first_go": False,
            }
            cfg = ws.config(env={}, flags=flags)
            store = Store(ws.db_path)
            try:
                records = starting_records(template, case)
                if records:
                    _create_starting_records(store, case["id"], records)
                now = received_of(case)
                request = _hand_in_case(ws, store, cfg, case, now)
                prices.append(estimate_request(ws, store, cfg, Router(cfg, store, env=env), request, now, use=account))
            except (ValueError, StoreError):
                continue
            finally:
                store.close()
    if not prices or any(p is None for p in prices):
        return None, len(cases)
    return sum(p for p in prices if p is not None) / len(prices) * len(cases) * runs, len(cases)
