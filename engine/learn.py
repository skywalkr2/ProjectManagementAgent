"""Learning from corrections (design 6.22): one request per correction, a packet that shows what was corrected, and
the closing steps.

A correction is a `signal` record. Each one the person made while writing something (a send back with a note, an
answer to the assistant's question) queues a learning request at once; each silent one (an undo, an edited message, a
change pulled back) queues one that waits for the next batch, with a time that says so. A request names its signal in
`about`, goes through the normal request path (estimate, go, budgets), and asks for at most one proposal. What it
proposes is a proposal like any other: it changes nothing until the person keeps it.

Netting: a correction the person undid within its undo time doesn't teach. Signals stay as they are; the learning for
one is cancelled before it runs, or its result is undone after.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from engine.ops import ChangesetIn
from engine.records import REGISTRY, RunKnowledge
from engine.storage import WriteContext

TASK = "learn-correction"
LEARNING_TASKS = (TASK,)
#: Corrections the person wrote something for: looked at when they happen, while the person is still looking.
AT_ONCE = ("sent_back", "routed", "answered_assistant", "change_requested", "missed")
#: Corrections made without writing anything: looked at in the next batch. `edited` is the person's own direct edit of
#: something the assistant set.
SILENT = (
    "undone",
    "pulled_back",
    "draft_edited",
    "dropped",
    "reworded",
    "held_declined",
    "edited",
    "no_reply_needed",
)
TEACHES = AT_ONCE + SILENT

_ENGINE = WriteContext(actor="engine", trust="trusted", op="learn.queue")
_NETTED = WriteContext(actor="engine", trust="trusted", op="learn.net")
_DONE = WriteContext(actor="engine", trust="trusted", op="learn.finish")

NETTED_WAITING = "Not learned from: the correction was undone."
CUT = "(cut: the rest isn't shown)"

#: What each kind of correction means, in words for the packet.
KIND_WORDS = {
    "sent_back": "The person sent the assistant's work back with a note.",
    "undone": "The person undid some or all of the assistant's work (the ops marked undone).",
    "pulled_back": "The person pulled back a change that the assistant had closed by itself.",
    "draft_edited": "The person edited the assistant's draft before using it; the note is the text as they used it.",
    "routed": "The person answered the assistant's question about who someone is or who owns something.",
    "answered_assistant": "The person answered a question the assistant asked them; the note is their answer.",
    "dropped": "The person dropped a question or an action the assistant filed.",
    "reworded": "The person reworded a question the assistant filed; the note is the new wording.",
    "held_declined": "The person declined something the assistant had held for them.",
    "edited": "The person changed a field the assistant had set.",
    "no_reply_needed": "The person said no reply was owed for a message the assistant added a reply for.",
    "missed": "The person said the assistant missed something; the note is their sentence, and no run is named.",
}


def is_learning(task: str | None) -> bool:
    """Whether a task kind is one of the kinds of learning from a correction."""
    return task in LEARNING_TASKS


def signal_of(request: Mapping[str, Any]) -> str | None:
    """The signal a learning request learns from, as it names it in `about`."""
    about = request.get("about") or {}
    return about.get("id") if is_learning(request.get("task")) and about.get("kind") == "signal" else None


def _when(value: Any) -> datetime:
    when = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def kind_of_id(records: Mapping[str, Any], record_id: str) -> str | None:
    """The record kind an id belongs to, from its prefix; None when no kind has it."""
    prefix, _, number = record_id.rpartition("-")
    if not number.isdigit():
        return None
    return next((kind for kind, model in records.items() if getattr(model, "prefix", None) == prefix), None)


def _number(record_id: str) -> int:
    tail = record_id.rpartition("-")[2]
    return int(tail) if tail.isdigit() else 0


def learn_request(reader: Any, signal_id: str) -> Any | None:
    """The learning request for a signal, in any state; each correction has at most one."""
    return next((r for r in reader.list("request") if signal_of(r.data) == signal_id), None)


def next_batch(now: datetime, every_minutes: int) -> datetime:
    """The next moment a batch of silent corrections is looked at: the next multiple of `every_minutes` since the
    start of the day. Corrections made in the same window wait for the same moment, and so run together."""
    now = _when(now)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    done = int((now - start).total_seconds() // 60) // every_minutes
    return start + timedelta(minutes=(done + 1) * every_minutes)


def _names_set_aside(reader: Any, signal: Mapping[str, Any]) -> bool:
    """Whether the correction is about mail that is set aside as not work, which learning never reads."""
    from engine.set_aside import is_set_aside

    for ref in signal.get("refs") or []:
        kind = kind_of_id(REGISTRY, ref)
        found = reader.get(kind, ref) if kind in ("request", "snapshot") else None
        if found is not None and is_set_aside(found):
            return True
    return False


def record(tx: Any, cfg: Any, data: dict[str, Any], write: Any, now: datetime | str) -> str:
    """Write a correction's signal and queue what the assistant learns from it, in the same transaction. Every signal is
    written through here, so no correction is recorded without its learning."""
    signal_id = tx.create("signal", data, write).id
    on_signal(tx, cfg, signal_id, _when(now))
    return signal_id


#: The fields whose edit by the person corrects the assistant, by record kind; others (a status, a note) are their own.
EDITED_FIELDS = {
    "action": ("text", "due", "owners", "project", "promised_to", "basis"),
    "question": ("title", "text", "to", "matters_for", "projects"),
    "fact": ("key", "value", "as_of", "project"),
    "event": ("title", "start", "end", "project"),
    "note": ("project",),
}


def record_edits(tx: Any, cfg: Any, now: datetime | str) -> list[str]:
    """Record one `edited` signal per record the person edited in this transaction, for the fields the assistant had
    set, naming the change and run that set them; a record a signal already names here is left alone. Returns the
    signals' ids."""
    by_record: dict[tuple[str, str], list[tuple[str, Any, Any, str | None]]] = {}
    for kind, record_id, field, before, after, changeset in tx.person_edits:
        if field in EDITED_FIELDS.get(kind, ()) and record_id not in tx.signalled:
            by_record.setdefault((kind, record_id), []).append((field, before, after, changeset))
    tx.person_edits = []
    made = []
    for (_kind, record_id), fields in by_record.items():
        changeset = next((c for *_, c in reversed(fields) if c), None)
        cs = tx.get("changeset", changeset) if changeset else None
        note = "; ".join(f"{field}: was {before!r}, now {after!r}" for field, before, after, _ in fields)
        data = {
            "kind": "edited",
            "refs": [record_id],
            "changeset": changeset,
            "run": cs.data.get("run") if cs is not None else None,
            "note": note,
            "at": _when(now).isoformat(),
        }
        made.append(record(tx, cfg, data, WriteContext(actor="pm", trust="trusted", op="edited"), now))
    return made


def on_signal(tx: Any, cfg: Any, signal_id: str, now: datetime) -> str | None:
    """Queue the learning for a correction that was just recorded, inside the transaction that recorded it. One that
    needs no wait is queued to run now. A silent one is queued with the time of the next batch as the reason it
    waits. Nothing is queued when learning is off, for a kind of signal that doesn't teach, for one already queued,
    for one whose own answer already recorded what it teaches (one correction, one piece of learning), or for mail set
    aside as not work. Returns the request id."""
    knowledge = cfg.dispatch.knowledge
    found = tx.get("signal", signal_id)
    if not knowledge.learn or found is None or found.data["kind"] not in TEACHES or found.data.get("learned"):
        return None
    if learn_request(tx, signal_id) is not None or _names_set_aside(tx, found.data):
        return None
    data: dict[str, Any] = {
        "task": TASK,
        "about": {"kind": "signal", "id": signal_id},
        "origin": "schedule",
        "state": "queued",
        "waiting": "With the assistant, starting now",
        "created_at": _when(now).isoformat(),
    }
    if found.data["kind"] not in AT_ONCE:
        from engine.ai.pauses import when_text

        until = next_batch(now, knowledge.learn_every_minutes)
        data["waiting"] = f"Learning from this correction with the next batch, at {when_text(cfg, until, now)}."
        data["cause"] = {"kind": "retry", "until": until.isoformat()}
    return tx.create("request", data, _ENGINE).id


def corrected_task(reader: Any, signal: Mapping[str, Any]) -> str | None:
    """The kind of work a correction is about (the task of the request whose work was corrected), when it is known."""
    _, original = _original(reader, signal)
    return original.data.get("task") if original is not None else None


def reach_misses_correction(reader: Any, request_data: Mapping[str, Any], op: Any) -> str | None:
    """Why a learning answer's entry can't stand as it reaches, or None: an entry that names kinds of work must include
    the one corrected, or it would never reach the work it is meant to change."""
    reach = getattr(op, "applies_to", None)
    signal = reader.get("signal", signal_of(request_data) or "")
    if reach is None or not reach.task_kinds or signal is None:
        return None
    corrected = corrected_task(reader, signal.data)
    if corrected is None or corrected in reach.task_kinds:
        return None
    return (
        f'this comes from a correction of "{corrected}" work, so applies_to.task_kinds must include "{corrected}" '
        "(or be left empty); as written it would never reach the work it is meant to change"
    )


def _original(reader: Any, signal: Mapping[str, Any]) -> tuple[Any | None, Any | None]:
    """The changeset a correction is about and the request that asked for it, when there are any: from the signal's
    changeset, else from a request it names."""
    changeset = reader.get("changeset", signal["changeset"]) if signal.get("changeset") else None
    if changeset is not None:
        return changeset, reader.get("request", changeset.data["request"])
    for ref in signal.get("refs") or []:
        if kind_of_id(REGISTRY, ref) == "request":
            request = reader.get("request", ref)
            if request is not None:
                done = reader.get("changeset", request.data["changeset"]) if request.data.get("changeset") else None
                return done, request
    return None, None


def skip_reason(store: Any, cfg: Any, request: Mapping[str, Any]) -> str | None:
    """Why a learning request has nothing to do any more, in plain words, or None: learning is off, the correction is
    gone, the work it was about keeps its own lessons, or it was about mail set aside as not work."""
    from engine.learning import request_learns

    if not cfg.dispatch.knowledge.learn:
        return "Learning from corrections is switched off."
    view = store.read()
    signal = view.get("signal", signal_of(request) or "")
    if signal is None:
        return "The correction this was for is gone."
    _, original = _original(view, signal.data)
    if original is not None and not request_learns(store, original.data):
        return "That work keeps its own lessons, so nothing is learned from it here."
    if _names_set_aside(view, signal.data):
        return "Mail set aside as not work is never learned from."
    if signal.data.get("learned"):
        return "The person's own answer already recorded what this teaches."
    return None


def close(store: Any, request_id: str, why: str) -> None:
    """Finish a learning request that has nothing to do, saying why."""
    changes = {"state": "done", "waiting": why, "cause": None}
    with store.transaction() as tx:
        current = tx.get("request", request_id)
        if current is not None and (current.data["state"], current.data.get("waiting")) != ("done", why):
            tx.update("request", request_id, changes, _NETTED, read_version=current.version)


def net_out(store: Any, kind: str, refs: list[str], *, at: Collection[Any] | None = None) -> list[str]:
    """The person undid the act that made the newest correction of this kind naming any of `refs` (and, when `at` is
    given, recorded at one of those times): it doesn't teach. Learning that hasn't run is cancelled. Learning that ran
    has its changeset undone, which takes back a proposal nobody has kept yet; a held change is refused. The signal
    itself is untouched. Returns the requests netted."""
    from engine.applier import undo

    view = store.read()
    times = {_when(a) for a in at} if at is not None else None
    named = [
        s
        for s in view.list("signal")
        if s.data["kind"] == kind
        and set(s.data.get("refs") or []) & set(refs)
        and (times is None or _when(s.data["at"]) in times)
    ]
    if not named:
        return []
    request = learn_request(view, max(named, key=lambda s: _number(s.id)).id)
    if request is None or request.data.get("dismissed"):
        return []
    changeset = request.data.get("changeset")
    if changeset is None:
        if request.data["state"] == "done":
            return []
        close(store, request.id, NETTED_WAITING)
        return [request.id]
    found = view.get("changeset", changeset)
    if any(o["status"] == "applied" for o in found.data["ops"]):
        undo(store, changeset)
    with store.transaction() as tx:
        found = tx.get("changeset", changeset)
        held = [o for o in found.data["ops"] if o["status"] == "held"]
        for outcome in held:
            outcome["status"], outcome["reason"] = "refused", NETTED_WAITING
        if held:
            status = "applied" if any(o["status"] == "applied" for o in found.data["ops"]) else "rejected"
            tx.update(
                "changeset",
                changeset,
                {"ops": found.data["ops"], "status": status},
                _NETTED,
                read_version=found.version,
            )
    close(store, request.id, NETTED_WAITING)
    return [request.id]


def link_signal(changeset: ChangesetIn, signal_id: str | None) -> ChangesetIn:
    """The answer with each lesson it adds tied to the correction it came from (or to none, without one), whatever the
    answer gave there: which correction a lesson comes from is the app's to say, never the answer's."""
    ops = [
        op.model_copy(update={"signal": signal_id}) if getattr(op, "op", None) == "lesson.add" else op
        for op in changeset.ops
    ]
    return changeset.model_copy(update={"ops": ops})


def finish(store: Any, request_id: str, changeset_id: str) -> None:
    """A learning run was applied. Its proposal is on the knowledge screens, so the run itself needs no review: it is
    done, unless it holds a change that waits for the person (a lesson changed, a rule proposed), which stays in review
    so the decision shows on Today."""
    with store.transaction() as tx:
        found = tx.get("changeset", changeset_id)
        current = tx.get("request", request_id)
        if found is None or current is None or any(o["status"] == "held" for o in found.data["ops"]):
            return
        tx.update("request", request_id, {"state": "done", "waiting": None}, _DONE, read_version=current.version)


def rule_in_report(cfg: Any, title: str, text: str) -> str | None:
    """The configured phrase that makes a draft report to the maintainers read as a standing rule for the assistant,
    or None."""
    words = f"{title} {text}".lower()
    for phrase in cfg.language.rule_report_phrases:
        if phrase.strip() and re.search(r"(?<![a-z])" + re.escape(phrase.lower()) + r"(?![a-z])", words):
            return phrase
    return None


# ---- the packet ------------------------------------------------------------------------------------------------------


def _marked(text: str) -> str:
    """Text that can't close the marking it sits in."""
    return text.replace("</untrusted", "</ untrusted")


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + f" {CUT}"


def _short(value: Any, limit: int = 300) -> Any:
    if isinstance(value, str):
        return _cut(value, limit)
    if isinstance(value, (list, dict)):
        return _cut(json.dumps(value, ensure_ascii=False), limit)
    return value


def _shown(store: Any, kind: str, record_id: str) -> dict[str, Any]:
    """A record as it is now, for the packet: its filled-in fields, long ones cut."""
    found = store.read().get(kind, record_id)
    if found is None:
        return {"kind": kind, "id": record_id, "gone": True}
    shown: dict[str, Any] = {"kind": kind, "id": record_id}
    shown.update({k: _short(v) for k, v in found.data.items() if v not in (None, "", [], {})})
    return shown


def _entry_text(store: Any, record_id: str) -> str:
    """One piece of knowledge a run was given, as its line says it now: the wording and whether it still guides."""
    kind = kind_of_id(store.plugins.records, record_id)
    found = store.read().get(kind, record_id) if kind else None
    if found is None:
        return f"- {record_id}: (no longer there)"
    data = found.data
    text = data.get("text") or " ".join(str(data.get(k, "")) for k in ("term", "meaning")).strip()
    status = data.get("status")
    return f"- {record_id}: {text}" + (f" (now {status})" if status not in (None, "active") else "")


def _record_ids(store: Any, signal: Mapping[str, Any], changeset: Any | None) -> list[tuple[str, str]]:
    """The records the corrected work touched, and those the correction names, once each."""
    found: list[tuple[str, str]] = []
    if changeset is not None:
        for outcome in changeset.data["ops"]:
            found += [(r["kind"], r["id"]) for r in outcome.get("records") or []]
    for ref in signal.get("refs") or []:
        kind = kind_of_id(store.plugins.records, ref)
        if kind is not None and kind not in ("changeset", "signal", "request", "run"):
            found.append((kind, ref))
    return list(dict.fromkeys(found))


def _input_block(store: Any, ws: Any, request: Any, limit: int) -> str:
    """What an input said, as outside content with when it arrived, cut at `limit` characters; a note the person typed
    with it is theirs."""
    from engine.intake import source_text

    parts: list[str] = []
    source = store.read().get("source", request.data["source"]) if request.data.get("source") else None
    if source is not None:
        label = " ".join(str(source.data["title"]).split()).replace('"', "'")
        received = _when(source.data["received_at"]).date().isoformat()
        text = _cut(source_text(ws, store, source.id), limit)
        tag = "note" if source.data["trust"] == "trusted" else "untrusted"
        parts.append(f'<{tag} source="{label}" received="{received}">\n{_marked(text)}\n</{tag}>')
    if request.data.get("note"):
        parts.append(f"<note>\n{request.data['note']}\n</note>")
    return "\n".join(parts)


def _later(
    store: Any, cfg: Any, since: datetime, touched: set[tuple[str, str]], original: Any | None
) -> list[tuple[datetime, Any]]:
    """The requests, oldest first, that were handed in after `since` and changed some of the same records: at most the
    configured number of the most recent. The input the work was made from (and its redo) isn't one, mail set aside as
    not work is left out, and so is learning itself."""
    from engine.set_aside import learnable

    view = store.read()
    allowed = {r.id for r in learnable(view, "request")}
    found: list[tuple[datetime, Any]] = []
    for changeset in view.list("changeset"):
        request = view.get("request", changeset.data["request"])
        created = _when(changeset.data["created_at"])
        if request is None or request.id not in allowed or created <= since or not request.data.get("source"):
            continue
        if is_learning(request.data["task"]) or (
            original is not None and request.data["source"] == original.data.get("source")
        ):
            continue
        records = {(r["kind"], r["id"]) for o in changeset.data["ops"] for r in o.get("records") or []}
        if records & touched:
            found.append((created, request))
    found.sort(key=lambda pair: pair[0])
    most = cfg.dispatch.knowledge.learn_later_inputs
    return found[-most:] if most else []


def build(ws: Any, store: Any, cfg: Any, req: Any, kind: Any, today: date) -> Any:
    """The packet for learning from one correction. Stable first: the instructions, the op reference, the practice for
    good lessons, the active rules and lessons, the people and the projects. Then the request: the item as it is now,
    what the assistant did, the correction, the knowledge the run was given, the input it read and the inputs that came
    after it. Everything that came from outside is marked, and a note the person wrote is theirs."""
    from engine.ai.router import LEVELS
    from engine.cleaning import Cleaned
    from engine.dispatcher import _data_level
    from engine.knowledge_section import all_guidance
    from engine.names import People
    from engine.ops import reach_choices, reference_for
    from engine.packet import Packet, PacketRefused, _guidance, _people, _projects, _task
    from engine.prompts import render
    from engine.set_aside import learnable

    view = store.read()
    signal = view.get("signal", signal_of(req.data) or "")
    if signal is None:
        raise PacketRefused("the correction this was for is gone")
    data = signal.data
    changeset, original = _original(view, data)
    limit = cfg.dispatch.knowledge.learn_input_chars

    guidance_text, guidance_ids, rule_ids = all_guidance(view)
    instructions = render(kind.prompt, {"assistant_name": cfg.workspace.assistant_name}, ws.root, kind.prompt_file)
    stable = "\n\n".join(
        part
        for part in (
            "# Op reference\n" + reference_for(list(kind.ops), store.plugins.ops, reach=reach_choices(store.plugins)),
            "# Practice\n" + _guidance(kind),
            guidance_text,
            "# People\n" + _people(store, cfg),
            "# Projects\n" + _projects(store),
        )
        if part.strip()
    )

    made = _when(data["at"]).date().isoformat()
    parts = [
        f"Today is {today.isoformat()} ({today.strftime('%A')}).",
        f"This is correction {signal.id}, made on {made}.",
    ]
    if (corrected := corrected_task(view, data)) is not None:
        parts.append(
            f'The work corrected is the kind of work "{corrected}": a lesson that names kinds of work in '
            "applies_to.task_kinds includes it."
        )

    records = _record_ids(store, data, changeset)
    items = [_shown(store, k, i) for k, i in records[:12]]
    now = json.dumps(items, ensure_ascii=False, indent=1) if items else "(no record)"
    parts.append(f'# The item as it is now\n<untrusted source="records">\n{_marked(now)}\n</untrusted>')

    did = "(not recorded)"
    if changeset is not None:
        ops = [
            {k: o[k] for k in ("index", "op", "status", "reason") if o.get(k) is not None}
            for o in changeset.data["ops"]
        ]
        did = json.dumps({"summary": changeset.data["summary"], "ops": ops}, ensure_ascii=False, indent=1)
    parts.append(
        '# What the assistant did\n<untrusted source="the assistant\'s earlier answer">\n'
        f"{_marked(_cut(did, limit * 2))}\n</untrusted>"
    )

    note = data.get("note") or ""
    correction = [KIND_WORDS.get(data["kind"], "The person corrected the assistant's work.")]
    if note and data["kind"] in ("sent_back", "draft_edited", "answered_assistant", "missed"):
        correction.append(f"<note>\n{note}\n</note>")
    elif note:
        correction.append(f'<untrusted source="the note">\n{_marked(_cut(note, limit))}\n</untrusted>')
    people = People(store, cfg)
    named = [i for i in data.get("refs") or [] if kind_of_id(store.plugins.records, i) == "person"]
    if named:
        correction.append("The people it names: " + ", ".join(f"{people.name(p)} ({p})" for p in named) + ".")
    parts.append("# The correction\n" + "\n".join(correction))

    given_heading = "# What the assistant had been given from what it had learned\n"
    run = view.get("run", data["run"]) if data.get("run") else None
    if run is None:
        parts.append(given_heading + "Not recorded: no run made that work.")
    else:
        given = (run.data.get("knowledge") or {}).get("given", [])
        lines = [_entry_text(store, i) for i in given]
        parts.append(given_heading + ("\n".join(lines) if lines else "Nothing: that run was given no lesson or rule."))

    level = "internal"
    if original is not None:
        level = _data_level(store, original.data)
        readable = {r.id for r in learnable(view, "request")}
        block = _input_block(store, ws, original, limit) if original.id in readable else ""
        if block:
            parts.append("# The input the assistant read\n" + block)
    baseline = changeset if changeset is not None else original
    if baseline is not None:
        later = _later(store, cfg, _when(baseline.data["created_at"]), set(records), original)
        blocks = [_input_block(store, ws, r, limit) for _, r in later]
        parts.append(
            "# Inputs that arrived after that work and are about the same items\n" + ("\n".join(blocks) or "None.")
        )
        for _, r in later:
            raised = _data_level(store, r.data)
            level = raised if LEVELS.index(raised) > LEVELS.index(level) else level

    request = "\n\n".join(parts)
    log = RunKnowledge(given=guidance_ids, stable_chars=len(guidance_text), rules_present=rule_ids)
    task = replace(_task(cfg, store, kind, instructions, stable, request), knowledge=log.model_dump())
    return Packet(
        task,
        request,
        Cleaned("", 0, 0, False, 0),
        note,
        too_long=False,
        untrusted_material=True,
        cites=f"signal:{signal.id}",
        data_level=level,
        knowledge=log,
    )
