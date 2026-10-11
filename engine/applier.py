"""The applier (design 6.7): check a proposed changeset, resolve names, hold what needs the PM, apply the rest in one
transaction with a ledger entry per field, and undo by op group.

Checks are invariants (always refuse the op) or lints (severity from config/checks.yaml). Refusals and lints that
would refuse or return are fed back to the AI by the dispatcher first; what still fails is decided here: refused ops are
dropped and shown, returned lints hold an op that would reach another person and only warn otherwise.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import ValidationError

from engine.cleaning import normalize
from engine.config import Config
from engine.names import People
from engine.ops import (
    EVIDENCE_FIELDS,
    NEEDS_EVIDENCE,
    PERSON_ONLY_OPS,
    SETTABLE,
    ActionAddOp,
    ActionCloseOp,
    ChangesetIn,
    EvidenceIn,
    FactOp,
    FileAddOp,
    NoteOp,
    OpModel,
    PersonAddOp,
    ProjectAddOp,
    QuestionAddOp,
    QuestionDoneOp,
    RecordDeleteOp,
    RecordLogOp,
    RecordSetOp,
    StageMoveOp,
    TextAcceptOp,
    TextDiscardOp,
    TextDraftOp,
    TextEditOp,
    TextProposeOp,
)
from engine.plugin_api import NeedsPerson
from engine.records import model_for
from engine.storage import Store, StoreError, WriteContext
from engine.storage.store import Tx

Severity = Literal["refuse", "return", "hold", "warn"]


@dataclass(frozen=True)
class Problem:
    check: str
    severity: Severity
    op: int | None
    message: str
    passage: str | None = None  # the exact words it is about, when a lint names them
    guidance: str | None = None  # how to fix it


@dataclass
class Inputs:
    """What a changeset may cite as evidence, and who it came from."""

    request: str
    source: str | None
    raw_input: str
    note: str
    trust: Literal["trusted", "untrusted"]
    cites: str | None = None  # what the input is cited as when it isn't a saved source, e.g. "<kind>:<id>"

    def evidence_source(self, quote: str) -> str | None:
        """The source id (or what the input is cited as, or "note") that contains the quote, if any does."""
        q = normalize(quote)
        cited = self.source or self.cites
        if cited and q and q in normalize(self.raw_input):
            return cited
        if q and q in normalize(self.note):
            return "note"
        return None


@dataclass
class Context:
    store: Store
    cfg: Config
    people: People
    allowed_ops: tuple[str, ...]
    inputs: Inputs
    hidden_words: list[str] = field(default_factory=list)
    confirmed_by_pm: bool = False
    actor: Literal["assistant", "pm"] = "assistant"  # "pm" for a person action, whose exact proposal the person saw


# ---- checks ----------------------------------------------------------------------------------------------------------


def check(cs: ChangesetIn, ctx: Context) -> list[Problem]:
    problems: list[Problem] = [
        Problem("plugin-validator", "refuse", i, message) for i, message in _validate_in_order(cs, ctx)
    ]
    view = ctx.store.read()
    lints = ctx.cfg.checks.lints
    open_actions = [a for a in view.list("action") if a.data["status"] != "done"]

    def refuse(i: int, check_name: str, message: str) -> None:
        problems.append(Problem(check_name, "refuse", i, message))

    def lint(i: int, name: str, message: str) -> None:
        severity = lints.get(name, "off")
        if severity != "off":
            problems.append(Problem(name, severity, i, message))

    for i, op in enumerate(cs.ops):
        name = op.op
        if name not in ctx.allowed_ops:
            refuse(i, "allowed-ops", f"{name} isn't an op this task may use")
            continue
        if name in PERSON_ONLY_OPS and ctx.actor != "pm":
            refuse(i, "person-only", f"only the person can {name.split('.', 1)[1]} text")
            continue
        if isinstance(op, (TextEditOp, TextProposeOp, TextDraftOp)):
            why = _text_target(ctx.store, view, op.record.kind, op.record.id, op.field)
            if why:
                refuse(i, "targets", why)
                continue
        if isinstance(op, (TextAcceptOp, TextDiscardOp)):
            pending = view.get("text_version", op.version)
            if pending is None or pending.data["status"] != "pending":
                refuse(i, "targets", f"{op.version} isn't a version waiting for review")
                continue
            if pending.version != op.read_version:
                refuse(i, "record-changed", f"{op.version} changed since it was reviewed")
                continue
        if isinstance(op, RecordDeleteOp):
            target = view.get(op.record.kind, op.record.id)
            if target is None or target.version != op.read_version:
                refuse(i, "record-changed", f"{op.record.kind} {op.record.id} is gone or changed since it was read")
                continue
            users = ctx.store.plugins._referrers(view)(op.record.kind, op.record.id)
            if users:
                refuse(
                    i,
                    "still-referred-to",
                    f"{op.record.kind} {op.record.id} is still referred to by {users[0][0]} {users[0][1]}",
                )
                continue
        if isinstance(op, StageMoveOp):
            from engine.stages import validate_move, wording

            # Even a trusted PM note interpreted by AI is a proposal, never consent.
            messages = [wording(ctx.cfg, "confirm")]
            try:
                validate_move(ctx.store, op, view)
            except StoreError as err:
                messages.append(str(err))
            problems.append(Problem("stage-confirm", "hold", i, "; ".join(messages)))
        # evidence
        evidence = _evidence(op)
        needs = name in NEEDS_EVIDENCE or (isinstance(op, RecordSetOp) and op.field in EVIDENCE_FIELDS)
        if needs and evidence is None:
            refuse(i, "evidence", f"{name} needs evidence: the exact words from the input that justify it")
        if evidence is not None and ctx.inputs.evidence_source(evidence.quote) is None:
            refuse(i, "evidence", f"the quote {evidence.quote!r} isn't in the input; copy the words exactly")
        # targets
        for project in _projects_of(op):
            if view.get("project", project) is None:
                refuse(i, "targets", f"there is no project {project}")
        if isinstance(op, ActionCloseOp):
            target = view.get("action", op.id)
            if target is None:
                refuse(i, "targets", f"there is no action {op.id}")
            elif target.data["status"] == "done":
                refuse(i, "targets", f"action {op.id} is already done")
            elif evidence is not None and not _shares_words(evidence.quote, target.data["text"]):
                lint(i, "evidence-fit", f"the quote doesn't seem to be about action {op.id}")
        if isinstance(op, QuestionDoneOp):
            target = view.get("question", op.id)
            if target is None:
                refuse(i, "targets", f"there is no question {op.id}")
            elif target.data["status"] in ("answered", "dropped"):
                refuse(i, "targets", f"question {op.id} is already closed")
            elif evidence is not None and not _shares_words(evidence.quote, target.data["title"] + " " + op.answer):
                lint(i, "evidence-fit", f"the quote doesn't seem to answer question {op.id}")
        if isinstance(op, RecordSetOp):
            target = view.get(op.kind, op.id)
            if target is None:
                refuse(i, "targets", f"there is no {op.kind} {op.id}")
            elif op.field not in SETTABLE[op.kind]:
                refuse(i, "targets", f"{op.kind}.{op.field} can't be changed this way")
            else:
                try:
                    model_for(op.kind).model_validate({**target.data, op.field: op.value})
                except ValidationError as err:
                    refuse(i, "targets", f"{op.kind}.{op.field}: {err.errors()[0]['msg']}")
                else:
                    if op.kind == "project" and op.field == "parent" and op.value is not None:
                        why = parent_problem(view, op.id, op.value)
                        if why:
                            refuse(i, "targets", why)
        if isinstance(op, ProjectAddOp):
            taken = {p.data["name"].strip().lower() for p in view.list("project")}
            if op.name.strip().lower() in taken:
                refuse(i, "targets", f"there is already a project called {op.name}")
            if op.parent is not None and view.get("project", op.parent) is None:
                refuse(i, "targets", f"there is no project {op.parent}")
            if op.language is not None and not re.fullmatch(LANGUAGE_TAG, op.language):
                refuse(i, "targets", f"{op.language} isn't a language tag such as en-US")
        # questions to other people
        if isinstance(op, QuestionAddOp):
            resolved = ctx.people.resolve(op.to)
            to_pm = resolved.person == ctx.people.pm
            if not to_pm:
                if not op.links:
                    refuse(i, "question-links", "a question to someone else needs a link to what it is about")
                for link in op.links:
                    if not _openable(link.url):
                        refuse(i, "question-links", f"{link.url} isn't a link the recipient can open")
            _wording(i, op.title + " " + op.text, ctx, lint)
        if isinstance(op, ActionAddOp):
            _wording(i, op.text, ctx, lint)
            if any(sep in op.text for sep in ctx.cfg.language.run_on_separators):
                lint(i, "run-on-list", "the action crams several items into one line; make one action per task")
            for existing in open_actions:
                if _similar(op.text, existing.data["text"]) >= 0.8:
                    lint(i, "near-duplicate-action", f"looks like open action {existing.id}: {existing.data['text']}")
                    break
        # plugins' lints: soft checks, with the severity the workspace sets (never a refusal by default)
        for name, default, found in ctx.store.plugins.lint_findings(op, view):
            severity = lints.get(name, default)
            if severity != "off":
                problems.append(Problem(name, severity, i, found.message, found.passage, found.guidance))
        # never shown
        text = " ".join(_texts(op)).lower()
        for word in ctx.hidden_words:
            if word and re.search(r"(?<![a-z0-9])" + re.escape(word.lower()) + r"(?![a-z0-9])", text):
                refuse(i, "never-shown", "text people will see mentions the AI model or service")
                break
        # tiers
        request = view.get("request", ctx.inputs.request)
        from_pm = request is not None and request.data["origin"] == "pm" and ctx.inputs.trust == "trusted"
        if ctx.store.plugins.tiers.get(name) == "system" and not from_pm and not ctx.confirmed_by_pm:
            problems.append(Problem("tier", "hold", i, "changes how the product behaves; needs your confirmation"))
    return problems


def _wording(i: int, text: str, ctx: Context, lint: Any) -> None:
    lowered = text.lower()
    for phrase in ctx.cfg.language.blocked_phrases:
        if re.search(r"(?<![a-z])" + re.escape(phrase.lower()) + r"(?![a-z])", lowered):
            lint(i, "blocked-wording", f"avoid {phrase!r}: say what to do, or ask the real question")
            return


def _openable(url: str) -> bool:
    if not re.match(r"^https?://", url):
        return False
    host = re.sub(r"^https?://", "", url).split("/", 1)[0].split(":", 1)[0].lower()
    return host not in ("localhost", "127.0.0.1", "::1", "0.0.0.0") and "." in host


LANGUAGE_TAG = r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*"


def parent_problem(view: Any, project: str | None, parent: str) -> str | None:
    """Why `parent` can't hold `project`, or None: it must exist, and never be the project or inside it."""
    seen = set()
    current = view.get("project", parent)
    if current is None:
        return f"there is no project {parent}"
    while current is not None and current.id not in seen:
        if current.id == project:
            return "a project can't be inside itself or one of its own parts"
        seen.add(current.id)
        up = current.data.get("parent")
        current = view.get("project", up) if up else None
    return None


def _text_target(store: Store, view: Any, kind: str, record_id: str, field: str) -> str | None:
    """Why a record's field can't take text, or None."""
    from engine.texts import long_text_fields

    model = store.plugins.records.get(kind)
    if model is None or view.get(kind, record_id) is None:
        return f"there is no {kind} {record_id}"
    if field not in long_text_fields(model):
        return f"{kind}.{field} isn't a long text field"
    return None


def _evidence(op: OpModel) -> EvidenceIn | None:
    """An op's evidence, when it carries the core's kind; a plugin op's own field of that name is its business."""
    value = getattr(op, "evidence", None)
    return value if isinstance(value, EvidenceIn) else None


def _projects_of(op: OpModel) -> list[str]:
    if isinstance(op, (NoteOp, FactOp, ActionAddOp, QuestionAddOp)) and op.project:
        return [op.project]
    if isinstance(op, RecordLogOp):
        return [op.project]
    return []


def _texts(op: OpModel) -> list[str]:
    out = []
    for key in ("text", "title", "answer", "summary"):
        value = getattr(op, key, None)
        if isinstance(value, str):
            out.append(value)
    return out


_WORD = re.compile(r"[a-z0-9]{4,}")


def _shares_words(a: str, b: str) -> bool:
    return bool(set(_WORD.findall(normalize(a))) & set(_WORD.findall(normalize(b))))


def _similar(a: str, b: str) -> float:
    wa, wb = set(_WORD.findall(normalize(a))), set(_WORD.findall(normalize(b)))
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def needs_another_round(problems: list[Problem]) -> bool:
    return any(p.severity in ("refuse", "return") for p in problems)


def feedback(problems: list[Problem]) -> str:
    lines = [
        (f"- op {p.op}: {p.message}" if p.op is not None else f"- {p.message}")
        + (f' (the passage: "{p.passage}")' if p.passage else "")
        + (f" {p.guidance}" if p.guidance else "")
        for p in problems
        if p.severity in ("refuse", "return")
    ]
    return (
        "Your previous answer had these problems:\n"
        + "\n".join(lines)
        + ("\nAnswer again with the complete corrected JSON object.")
    )


# ---- apply -----------------------------------------------------------------------------------------------------------


@dataclass
class OpOutcome:
    index: int
    op: dict[str, Any]
    status: Literal["applied", "held", "refused", "undone"]
    group: str
    records: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None
    question: str | None = None
    problems: list[dict[str, Any]] = field(default_factory=list)
    label: str | None = None


def _label(op: OpModel, view: Any = None, store: Store | None = None) -> str | None:
    """An op's own one-line label. A plugin op's `describe` may take a read view, to name the records it changes."""
    import inspect

    try:
        takes_view = len(inspect.signature(op.describe).parameters) >= 1
        if takes_view and view is not None and store is not None and "/" in op.op:
            from engine.plugin_api import ReadView

            text = op.describe(store.plugins._with_files(ReadView(view, op.op.split("/", 1)[0])))
        else:
            text = op.describe() if not takes_view else None
    except Exception:
        return None
    return " ".join(text.split())[:200] if isinstance(text, str) and text.strip() else None


def apply_changeset(
    cs: ChangesetIn,
    problems: list[Problem],
    ctx: Context,
    *,
    run: str | None,
    now: datetime | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Apply what passed, hold what needs the PM, record refusals. Returns the changeset id."""
    now = now or datetime.now(UTC)
    # Recheck at the write boundary: callers cannot bypass plugin validators or tiers.
    problems = list(dict.fromkeys([*problems, *check(cs, ctx)]))
    today = now.date()
    by_op: dict[int, list[Problem]] = {}
    for p in problems:
        if p.op is not None:
            by_op.setdefault(p.op, []).append(p)

    with ctx.store.transaction() as tx:
        cs_id = tx.new_id("changeset")
        outcomes: list[OpOutcome] = []
        for i, op in enumerate(cs.ops):
            mine = list(by_op.get(i, []))
            known = {p.message for p in mine if p.check == "plugin-validator"}
            mine += [
                Problem("plugin-validator", "refuse", i, message)
                for message in ctx.store.plugins.validators(op, view=tx, origin=origin_of(ctx))
                if message not in known
            ]
            outcome = OpOutcome(
                i,
                op.model_dump(mode="json", exclude_none=True),
                "applied",
                op.group or f"op{i}",
                problems=[asdict(p) for p in mine],
                label=_label(op, tx, ctx.store),
            )
            if any(p.severity == "refuse" for p in mine):
                outcome.status = "refused"
                outcome.reason = "; ".join(p.message for p in mine if p.severity == "refuse")
            elif any(p.severity == "hold" for p in mine) or _returned_to_someone_else(op, mine, ctx):
                outcome.status = "held"
                outcome.reason = "; ".join(p.message for p in mine if p.severity in ("hold", "return"))
            else:
                hold = _needs_person_choice(op, ctx)
                if hold is not None:
                    outcome.status = "held"
                    outcome.reason = hold
            if outcome.status == "applied":
                wctx = _wctx(ctx, cs_id, i, op)
                # Each op in its own savepoint: one that fails is refused alone and leaves nothing behind.
                tx.sql("SAVEPOINT plugin_op")
                pending = len(tx.pending)
                try:
                    outcome.records, question = _apply_op(tx, op, ctx, wctx, today)
                    outcome.question = question
                except NeedsPerson as err:
                    tx.sql("ROLLBACK TO plugin_op")
                    del tx.pending[pending:]
                    outcome.status, outcome.reason = "held", str(err)
                except StoreError as err:
                    tx.sql("ROLLBACK TO plugin_op")
                    del tx.pending[pending:]
                    outcome.status, outcome.reason = "refused", str(err)
                finally:
                    tx.sql("RELEASE plugin_op")
            elif outcome.status == "held" and outcome.reason and outcome.reason.startswith("who-is"):
                outcome.question = _routing_question(tx, op, i, cs_id, ctx, outcome.reason)
                outcome.reason = "Waiting for you to say who this is"
            outcomes.append(outcome)
        status = "held" if any(o.status == "held" for o in outcomes) else "applied"
        tx.create(
            "changeset",
            {
                "request": ctx.inputs.request,
                "summary": cs.summary,
                "ops": [asdict(o) for o in outcomes],
                "status": status,
                "problems": [asdict(p) for p in problems if p.op is None],
                "trust": ctx.inputs.trust,
                "run": run,
                "created_at": now.isoformat(),
                **(extra or {}),
            },
            WriteContext(actor="engine", trust="trusted", op="changeset.record"),
            record_id=cs_id,
        )
    ctx.store.plugins.publish("changeset.applied", {"id": cs_id})
    return cs_id


def _returned_to_someone_else(op: OpModel, mine: list[Problem], ctx: Context) -> bool:
    if not any(p.severity == "return" for p in mine):
        return False
    if isinstance(op, QuestionAddOp):
        return ctx.people.resolve(op.to).person != ctx.people.pm
    return False


def _needs_person_choice(op: OpModel, ctx: Context) -> str | None:
    names: list[str] = []
    if isinstance(op, ActionAddOp):
        names = op.owners
    elif isinstance(op, QuestionAddOp):
        names = [op.to]
    for name in names:
        r = ctx.people.resolve(name)
        if r.status != "ok":
            return f"who-is:{name}:{','.join(r.candidates)}"
    if isinstance(op, PersonAddOp) and ctx.inputs.trust == "untrusted" and not ctx.confirmed_by_pm:
        return "A new person named only in outside content: add them?"
    return None


def origin_of(ctx: Context) -> dict[str, str]:
    """Who asked for a change, as plugin validators see it."""
    if ctx.actor == "pm":
        return {"actor": "pm", "trust": "trusted", "via": "action"}
    if ctx.confirmed_by_pm:
        return {"actor": "pm", "trust": "trusted", "via": "screen"}
    via = "input" if ctx.inputs.source else "task" if ctx.inputs.trust == "untrusted" else "note"
    return {"actor": "assistant", "trust": ctx.inputs.trust, "via": via}


class _DryRun(Exception):
    pass


def _validate_in_order(cs: ChangesetIn, ctx: Context) -> list[tuple[int, str]]:
    """Run plugin validators op by op against a transaction where the earlier ops are applied, then roll it all back,
    so a validator sees what earlier ops in the same changeset created. Nothing is kept and no event is published."""
    found: list[tuple[int, str]] = []
    try:
        with ctx.store.transaction(notify=False) as tx:
            for i, op in enumerate(cs.ops):
                messages = ctx.store.plugins.validators(op, view=tx, origin=origin_of(ctx))
                found += [(i, m) for m in messages]
                if messages or op.op not in ctx.allowed_ops:
                    continue
                tx.sql("SAVEPOINT dry_op")
                try:
                    _apply_op(tx, op, ctx, _wctx(ctx, "dry-run", i, op), datetime.now(UTC).date())
                except Exception:
                    tx.sql("ROLLBACK TO dry_op")
                finally:
                    tx.sql("RELEASE dry_op")
            raise _DryRun
    except _DryRun:
        pass
    return found


def _wctx(ctx: Context, cs_id: str, index: int, op: OpModel) -> WriteContext:
    evidence = _evidence(op)
    ev = None
    if evidence is not None:
        ev = {"source": ctx.inputs.evidence_source(evidence.quote), "quote": evidence.quote}
    return WriteContext(
        actor=ctx.actor,
        trust=ctx.inputs.trust,
        op=f"{op.op}#{index}",
        changeset=cs_id,
        request=ctx.inputs.request,
        evidence=ev,
    )


def _apply_op(
    tx: Tx, op: OpModel, ctx: Context, w: WriteContext, today: date
) -> tuple[list[dict[str, Any]], str | None]:
    if isinstance(op, StageMoveOp):
        from engine.stages import apply_move

        return apply_move(ctx.store, tx, op, w), None
    if "/" in op.op:
        return ctx.store.plugins.apply(tx, op, w), None
    if isinstance(op, RecordDeleteOp):
        kind, rid = op.record.kind, op.record.id
        users = ctx.store.plugins._referrers(tx)(kind, rid)
        if users:
            raise StoreError(f"{kind} {rid} is still referred to by {users[0][0]} {users[0][1]}")
        tx.delete(kind, rid, w, read_version=op.read_version)
        return [{"kind": kind, "id": rid}], None
    if isinstance(op, (TextEditOp, TextProposeOp)):
        from engine.texts import new_version

        proposal = isinstance(op, TextProposeOp)
        version = new_version(
            ctx.store,
            tx,
            w,
            op.record.kind,
            op.record.id,
            op.field,
            op.text,
            source="proposal" if proposal else "edit",
            by="person",
            base=op.base if proposal else None,
            note=op.note if proposal else None,
            accept=not proposal,
            unmapped=op.unmapped if proposal else None,
        )
        return [{"kind": op.record.kind, "id": op.record.id}, {"kind": "text_version", "id": version.id}], None
    if isinstance(op, TextDraftOp):
        from engine.texts import new_version

        version = new_version(
            ctx.store,
            tx,
            w,
            op.record.kind,
            op.record.id,
            op.field,
            op.text,
            source="draft",
            by="assistant",
            run=op.run,
            base=op.base,
            paragraph_map=op.paragraph_map,
            questions=op.questions,
        )
        return [{"kind": "text_version", "id": version.id}], None
    if isinstance(op, TextAcceptOp):
        from engine.texts import accept

        version = accept(ctx.store, tx, w, op.version, op.read_version, dict(op.choices))
        return [{"kind": "text_version", "id": op.version}, {"kind": "text_version", "id": version.id}], None
    if isinstance(op, TextDiscardOp):
        from engine.texts import discard

        discard(tx, w, op.version, op.read_version)
        return [{"kind": "text_version", "id": op.version}], None
    if isinstance(op, ProjectAddOp):
        data = {"name": op.name.strip(), "summary": op.summary, "parent": op.parent, "language": op.language}
        return [{"kind": "project", "id": tx.create("project", data, w).id}], None
    if isinstance(op, FileAddOp):
        from engine.files import blob_matches, check_file

        if not blob_matches(ctx.store, op.sha256, op.size):
            raise StoreError(f"the bytes for {op.name} aren't stored")
        name, details = check_file(
            ctx.store,
            ctx.cfg,
            tx,
            name=op.name,
            media_type=op.media_type,
            size=op.size,
            file_kind=op.file_kind,
            meta=op.meta,
            project=op.project,
            replaces=op.replaces,
        )
        data = {
            "name": name,
            "media_type": op.media_type,
            "size": op.size,
            "sha256": op.sha256,
            "file_kind": op.file_kind,
            "project": op.project,
            "meta": details,
            "origin": "tool",
            "trust": "untrusted",
            "replaces": op.replaces,
            "added_at": ctx.store.clock(),
        }
        return [{"kind": "file", "id": tx.create("file", data, w, record_id=op.id).id}], None
    trust = ctx.inputs.trust
    source = ctx.inputs.source
    touched: list[dict[str, Any]] = []

    def made(kind: str, rid: str) -> None:
        touched.append({"kind": kind, "id": rid})

    if isinstance(op, NoteOp):
        made(
            "note", tx.create("note", {"text": op.text, "project": op.project, "source": source, "trust": trust}, w).id
        )
    elif isinstance(op, FactOp):
        ev = {"source": w.evidence["source"] or source or "note", "quote": op.evidence.quote}
        made(
            "fact",
            tx.create(
                "fact", {"text": op.text, "project": op.project, "source": source, "evidence": ev, "trust": trust}, w
            ).id,
        )
    elif isinstance(op, RecordSetOp):
        cur = tx.get(op.kind, op.id)
        tx.update(op.kind, op.id, {op.field: op.value}, w, read_version=cur.version)
        made(op.kind, op.id)
    elif isinstance(op, RecordLogOp):
        cur = tx.get("project", op.project)
        log = [*cur.data.get("log", []), {"on": today.isoformat(), "text": op.text}]
        tx.update("project", op.project, {"log": log}, w, read_version=cur.version)
        made("project", op.project)
    elif isinstance(op, ActionAddOp):
        owners = [{"person": ctx.people.resolve(n).person} for n in op.owners]
        ev = {"source": w.evidence["source"] or source or "note", "quote": op.evidence.quote}
        data = {
            "text": op.text,
            "owners": owners,
            "due": op.due.isoformat() if op.due else None,
            "project": op.project,
            "source": source,
            "evidence": ev,
            "status": "open" if owners else "held",
        }
        action = tx.create("action", data, w)
        made("action", action.id)
        if not owners:
            q = _pm_question(
                tx,
                w,
                ctx,
                f"Pick an owner: {op.text}",
                "routing",
                options=[],
                resolves={"kind": "owner", "action": action.id},
            )
            made("question", q)
            return touched, q
    elif isinstance(op, ActionCloseOp):
        cur = tx.get("action", op.id)
        tx.update("action", op.id, {"status": "done"}, w, read_version=cur.version)
        made("action", op.id)
    elif isinstance(op, QuestionAddOp):
        to = ctx.people.resolve(op.to).person
        data = {
            "to": to,
            "title": op.title,
            "text": op.text,
            "links": [link.model_dump() for link in op.links],
            "projects": [op.project] if op.project else [],
            "kind": op.kind,
            "source": source,
        }
        made("question", tx.create("question", data, w).id)
    elif isinstance(op, QuestionDoneOp):
        cur = tx.get("question", op.id)
        tx.update("question", op.id, {"status": "answered", "answer": op.answer}, w, read_version=cur.version)
        made("question", op.id)
        projects = cur.data.get("projects") or [None]
        ev = {"source": w.evidence["source"] or source or "note", "quote": op.evidence.quote}
        fact = tx.create(
            "fact",
            {
                "text": f"{cur.data['title']} {op.answer}",
                "project": projects[0],
                "source": source,
                "evidence": ev,
                "trust": trust,
            },
            w,
        )
        made("fact", fact.id)
    elif isinstance(op, PersonAddOp):
        made(
            "person",
            tx.create(
                "person", {"full_name": op.full_name, "role": op.role, "org": op.org, "aliases": op.aliases}, w
            ).id,
        )
    return touched, None


def _pm_question(
    tx: Tx, w: WriteContext, ctx: Context, title: str, kind: str, *, options: list[str], resolves: dict[str, Any]
) -> str:
    pm = ctx.people.pm
    if pm is None:
        raise StoreError("workspace.user.person isn't set, so there is no one to ask")
    data = {"to": pm, "title": title, "kind": kind, "options": options, "resolves": resolves}
    return tx.create("question", data, w).id


def _routing_question(tx: Tx, op: OpModel, index: int, cs_id: str, ctx: Context, reason: str) -> str:
    _, name, candidates = reason.split(":", 2)
    options = [c for c in candidates.split(",") if c]
    w = WriteContext(
        actor="engine", trust="trusted", op=f"routing#{index}", changeset=cs_id, request=ctx.inputs.request
    )
    title = f"Who is “{name}”?"
    return _pm_question(
        tx,
        w,
        ctx,
        title,
        "routing",
        options=options,
        resolves={"kind": "held-op", "changeset": cs_id, "op": index, "name": name},
    )


# ---- releasing held ops and answering routing questions --------------------------------------------------------------


def release(
    store: Store, cfg: Config, changeset_id: str, index: int, *, person: str | None = None, now: datetime | None = None
) -> None:
    """Apply a held op, optionally saying who an unresolved name is."""
    now = now or datetime.now(UTC)
    cs = store.read().get("changeset", changeset_id)
    if cs is None:
        raise StoreError(f"there is no changeset {changeset_id}")
    outcomes = cs.data["ops"]
    outcome = outcomes[index]
    if outcome["status"] != "held":
        raise StoreError("that item isn't waiting for you")
    from engine.ops import CHANGESET

    try:
        op = CHANGESET.validate_python({"ops": [outcome["op"]]}, context={"op_models": store.plugins.ops}).ops[0]
    except ValidationError:
        # The op belongs to a plugin that isn't running now; it stays held until the plugin is back.
        raise StoreError("the plugin this belongs to is turned off or failed to start") from None
    name = (outcome.get("question") and _question_name(store, outcome["question"])) or None
    if person is not None and name is not None:
        op = _substitute(op, name, person)
    people = People(store, cfg)
    req = store.read().get("request", cs.data["request"])
    inputs = Inputs(cs.data["request"], req.data.get("source") if req else None, "", "", cs.data["trust"])
    ctx = Context(store, cfg, people, tuple(), inputs, confirmed_by_pm=True)
    refusals = store.plugins.validators(op)
    if refusals:
        raise StoreError("; ".join(refusals))
    with store.transaction() as tx:
        if outcome.get("question"):
            q = tx.get("question", outcome["question"])
            if q and q.data["status"] == "open":
                tx.update(
                    "question",
                    q.id,
                    {"status": "answered", "answer": person or "added"},
                    WriteContext(actor="pm", trust="trusted", op="question.answer"),
                    read_version=q.version,
                )
        still = _needs_person_choice(op, ctx)
        if still is not None and still.startswith("who-is"):
            outcome["op"] = op.model_dump(mode="json", exclude_none=True)
            outcome["question"] = _routing_question(tx, op, index, changeset_id, ctx, still)
            tx.update(
                "changeset",
                changeset_id,
                {"ops": outcomes},
                WriteContext(actor="pm", trust="trusted", op="changeset.release"),
                read_version=cs.version,
            )
            return
        w = WriteContext(
            actor="pm",
            trust="trusted",
            op=f"{op.op}#{index}",
            changeset=changeset_id,
            request=cs.data["request"],
            evidence=outcome["op"].get("evidence")
            and {"source": inputs.source, "quote": outcome["op"]["evidence"]["quote"]},
        )
        records, question = _apply_op(tx, op, ctx, w, now.date())
        outcome.update(status="applied", records=records, reason=None)
        if question:
            outcome["question"] = question
        status = "held" if any(o["status"] == "held" for o in outcomes) else "applied"
        tx.update(
            "changeset",
            changeset_id,
            {"ops": outcomes, "status": status},
            WriteContext(actor="pm", trust="trusted", op="changeset.release"),
            read_version=cs.version,
        )

    store.plugins.publish("changeset.applied", {"id": changeset_id})


def pick_owner(store: Store, question_id: str, person: str) -> None:
    """Answer a "Pick an owner" question: the held action gets its first owner and opens."""
    q = store.read().get("question", question_id)
    if q is None or (q.data.get("resolves") or {}).get("kind") != "owner":
        raise StoreError("that question isn't asking for an owner")
    action_id = q.data["resolves"]["action"]
    w = WriteContext(actor="pm", trust="trusted", op="action.assign")
    with store.transaction() as tx:
        if tx.get("person", person) is None:
            raise StoreError(f"there is no person {person}")
        a = tx.get("action", action_id)
        tx.update("action", action_id, {"owners": [{"person": person}], "status": "open"}, w, read_version=a.version)
        tx.update("question", question_id, {"status": "answered", "answer": person}, w, read_version=q.version)


def _question_name(store: Store, qid: str) -> str | None:
    q = store.read().get("question", qid)
    return (q.data.get("resolves") or {}).get("name") if q else None


def _substitute(op: OpModel, name: str, person: str) -> OpModel:
    if isinstance(op, ActionAddOp):
        return op.model_copy(update={"owners": [person if o == name else o for o in op.owners]})
    if isinstance(op, QuestionAddOp) and op.to == name:
        return op.model_copy(update={"to": person})
    return op


# ---- undo ------------------------------------------------------------------------------------------------------------


@dataclass
class UndoReport:
    restored: list[int] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)


def undo(store: Store, changeset_id: str, indices: list[int] | None = None) -> UndoReport:
    """Undo applied ops of a changeset by group: all or nothing within a group, skipping a group with a conflict."""
    cs = store.read().get("changeset", changeset_id)
    if cs is None:
        raise StoreError(f"there is no changeset {changeset_id}")
    outcomes = cs.data["ops"]
    wanted = [o for o in outcomes if o["status"] == "applied" and (indices is None or o["index"] in indices)]
    groups: dict[str, list[dict[str, Any]]] = {}
    for o in outcomes:
        if o["status"] == "applied":
            groups.setdefault(o["group"], []).append(o)
    # Newest first, so a later op that refers to what an earlier one made is undone before it.
    chosen = sorted({o["group"] for o in wanted}, key=lambda g: -max(o["index"] for o in groups[g]))
    report = UndoReport()
    entries = [e for e in store.read().ledger() if e["changeset"] == changeset_id]
    with store.transaction() as tx:
        for group in chosen:
            members = groups[group]
            idx = {o["index"] for o in members}
            mine = [e for e in entries if _op_index(e["op"]) in idx]
            conflict = _conflict(tx, mine) or _breaks_rules(store, tx, mine)
            if conflict:
                report.skipped.append({"ops": sorted(idx), "reason": conflict})
                continue
            _revert(tx, mine, changeset_id)
            for o in members:
                o["status"] = "undone"
                report.restored.append(o["index"])
        remaining = [o for o in outcomes if o["status"] in ("applied", "held")]
        status = "undone" if not remaining else ("partly_undone" if report.restored else cs.data["status"])
        tx.update(
            "changeset",
            changeset_id,
            {"ops": outcomes, "status": status},
            WriteContext(actor="pm", trust="trusted", op="changeset.undo"),
            read_version=cs.version,
        )
    if report.restored:
        store.plugins.publish("changeset.undone", {"id": changeset_id, "ops": report.restored})
    return report


def _breaks_rules(store: Store, tx: Tx, entries: list[dict[str, Any]]) -> str | None:
    """Why undoing these entries would break a rule the records declare, or None: bringing back a record whose unique
    values another live record now has, or removing a record something else still refers to."""
    touched = {(e["kind"], e["record_id"]) for e in entries}
    for kind, rid in sorted(touched):
        current = tx.get(kind, rid, include_deleted=True)
        model = store.plugins.records.get(kind)
        if current is None or model is None:
            continue
        rows = [e for e in entries if (e["kind"], e["record_id"]) == (kind, rid)]
        if current.deleted and any(r["field"] is None and r["version"] == current.version for r in rows):
            for group in model.unique:
                equals = {f: current.data.get(f) for f in group}
                if [s for s in tx.find(kind, equals) if s.id != rid]:
                    shown = ", ".join(f"{f}={v}" for f, v in equals.items())
                    return f"another {kind} now has {shown}"
        elif not current.deleted and any(r["version"] == 1 for r in rows):
            users = [u for u in store.plugins._referrers(tx)(kind, rid) if u not in touched]
            if users:
                return f"{kind} {rid} is now referred to by {users[0][0]} {users[0][1]}"
    return None


def _op_index(op_name: str) -> int | None:
    _, _, idx = op_name.rpartition("#")
    return int(idx) if idx.isdigit() else None


def _conflict(tx: Tx, entries: list[dict[str, Any]]) -> str | None:
    """Why undoing these entries would overwrite a later change, or None. A field written again since counts only
    while it holds something other than what these entries set: a later change that was itself undone has left it as
    they left it."""
    by_record: dict[tuple[str, str], dict[str, Any]] = {}
    for e in entries:
        key = (e["kind"], e["record_id"])
        cur = by_record.setdefault(key, {"version": 0, "fields": set(), "set_to": {}})
        cur["version"] = max(cur["version"], e["version"])
        if e["field"]:
            cur["fields"].add(e["field"])
            cur["set_to"][e["field"]] = e["after"]
    for (kind, rid), info in by_record.items():
        current = tx.get(kind, rid, include_deleted=True)
        if current is None:
            continue
        if current.version > info["version"]:
            later = tx.sql(
                "SELECT field FROM ledger WHERE kind=? AND record_id=? AND version>? AND field IS NOT NULL",
                (kind, rid, info["version"]),
            ).fetchall()
            clash = {
                f for f in {r["field"] for r in later} & info["fields"] if current.data.get(f) != info["set_to"].get(f)
            }
            if clash or current.deleted:
                return f"{kind} {rid} changed since ({', '.join(sorted(clash)) or 'deleted'})"
    return None


def _revert(tx: Tx, entries: list[dict[str, Any]], changeset_id: str) -> None:
    w = WriteContext(actor="pm", trust="trusted", op="undo", changeset=changeset_id)
    by_record: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for e in entries:
        by_record.setdefault((e["kind"], e["record_id"]), []).append(e)
    for (kind, rid), rows in by_record.items():
        current = tx.get(kind, rid, include_deleted=True)
        if current is None:
            continue
        if current.deleted:
            # This changeset deleted it (its last row is the delete): bring it back under its own id.
            if any(r["field"] is None and r["version"] == current.version for r in rows):
                tx.undelete(kind, rid, w, read_version=current.version)
            continue
        created = any(r["version"] == 1 for r in rows)
        if created:
            tx.delete(kind, rid, w, read_version=current.version)
            continue
        before: dict[str, Any] = {}
        for r in sorted(rows, key=lambda r: r["seq"]):
            if r["field"] and r["field"] not in before:
                before[r["field"]] = r["before"]
        tx.update(kind, rid, before, w, read_version=current.version)


def move_stage(store: Store, op: StageMoveOp, *, actor: Literal["pm", "rule"] = "pm") -> str:
    """A person's explicit move or a deterministic rule's move, through the same op and ledger."""
    from engine.stages import apply_move

    with store.transaction() as tx:
        cs_id = tx.new_id("changeset")
        request = tx.create(
            "request",
            {
                "task": "notes",
                "origin": "pm" if actor == "pm" else "schedule",
                "state": "done",
                "created_at": store.clock(),
                "changeset": cs_id,
            },
            WriteContext(actor, "trusted", "stage.request"),
        )
        source = {"rule": f"stages/{op.record.kind}/{op.to}"} if actor == "rule" else None
        w = WriteContext(actor, "trusted", "stage.move#0", cs_id, request.id, source)
        records = apply_move(store, tx, op, w)
        tx.create(
            "changeset",
            {
                "request": request.id,
                "ops": [asdict(OpOutcome(0, op.model_dump(mode="json"), "applied", "op0", records=records))],
                "status": "applied",
                "trust": "trusted",
                "reviewed": actor == "pm",
                "created_at": store.clock(),
            },
            WriteContext("engine", "trusted", "changeset.record"),
            record_id=cs_id,
        )
    store.plugins.publish("changeset.applied", {"id": cs_id})
    return cs_id


def apply_as_person(store: Store, cfg: Config, ops: list[dict[str, Any]], summary: str, task: str = "notes") -> str:
    """Apply ops the person made on screen (an edit, a review's choices) as theirs. Returns the changeset id."""
    from engine.names import People
    from engine.ops import CHANGESET

    changeset = CHANGESET.validate_python({"summary": summary, "ops": ops}, context={"op_models": store.plugins.ops})
    with store.transaction() as tx:
        request = tx.create(
            "request",
            {"task": task, "origin": "pm", "state": "done", "note": summary, "created_at": store.clock()},
            WriteContext("pm", "trusted", "screen.request"),
        )
    ctx = Context(
        store,
        cfg,
        People(store, cfg),
        tuple(store.plugins.ops),
        Inputs(request.id, None, "", "", "trusted"),
        confirmed_by_pm=True,
        actor="pm",
    )
    cs_id = apply_changeset(changeset, [], ctx, run=None, extra={"reviewed": True})
    refused = [o for o in store.read().get("changeset", cs_id).data["ops"] if o["status"] == "refused"]
    if refused:
        raise StoreError(refused[0].get("reason") or "that couldn't be done")
    with store.transaction() as tx:
        current = tx.get("request", request.id)
        tx.update(
            "request",
            request.id,
            {"changeset": cs_id},
            WriteContext("engine", "trusted", "screen.request"),
            read_version=current.version,
        )
    return cs_id
