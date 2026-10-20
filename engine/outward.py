"""What others read never names the assistant (design 6.7, 6.12).

The assistant is never a source, a reporter or an author on anything another person reads: a shared page, a history
line, an update, a message. The names it is blocked by are the one the person gave it now, every name they gave it
before (kept in the settings history) and the product's default, matched as whole words and ignoring case. Four
guards use them:

- `op_problem`: the applier refuses an op that writes what others read when it holds one of the names;
- `SourceLabels`: a history row shown to a reader says where the change came from (the input and its day, or the
  person for their own words), never who made it;
- `outgoing_problem` and `check_outgoing`: what goes out (a message to copy, a draft for someone else) is refused
  while it still holds a name, and the reason says where;
- `sweep`: lines written before the guard, or before a rename, are re-sourced from the ledger's evidence with their
  dates kept, as one change of the core's own with Undo.

The person's own screens may still say the assistant did something; nothing here touches the ledger's own rows.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from datetime import date
from typing import Any

from engine.config.schema import LanguageFile, MessageSettings, WorkspaceFile
from engine.names import People
from engine.storage import StoreError, WriteContext
from engine.titles import title_for

#: The setting that holds the assistant's name, and the key its history is kept under.
NAME_KEY = "workspace.assistant_name"
DEFAULT_NAME = WorkspaceFile.model_fields["assistant_name"].default
#: What a changeset made by the sweep is recorded as (`Changeset.by_rule`).
RULE = "history_resourced"

#: The text each op writes that others read, by op.
READ_BY_OTHERS_OPS: dict[str, tuple[str, ...]] = {
    "note": ("text",),
    "fact": ("text",),
    "event.add": ("title",),
    "series.add": ("title",),
    "record.log": ("text",),
    "action.add": ("text", "waiting_for", "reply"),
    "action.reply": ("text",),
    "action.hold": ("waiting_for",),
    "action.drop": ("reason",),
    "action.part": ("delivered", "left"),
    "action.news": ("text",),
    "question.add": ("title", "text"),
    "question.update": ("title", "text"),
    "question.drop": ("reason",),
    "question.done": ("answer",),
    "project.add": ("name", "summary"),
}
#: The fields `record.set` writes that others read, by kind of record.
READ_BY_OTHERS_FIELDS: dict[str, frozenset[str]] = {
    "project": frozenset({"summary"}),
    "action": frozenset({"text", "notes"}),
    "question": frozenset({"title", "text"}),
}
#: Fields of any op that name who a thing came from; they are checked on every op.
SOURCE_FIELDS = ("said_by", "reported_by", "author", "reporter")


def assistant_names(view: Any, current: str) -> list[str]:
    """Every name the assistant has gone by: the current one first, then each earlier or later value the settings
    history holds, then the product's default. Each once, in order."""
    found: list[Any] = [current]
    for stored in view.list("setting_change"):
        if stored.data.get("key") == NAME_KEY:
            found += [stored.data.get("before"), stored.data.get("after")]
    found.append(DEFAULT_NAME)
    names: list[str] = []
    seen: set[str] = set()
    for name in found:
        text = " ".join(name.split()) if isinstance(name, str) else ""
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            names.append(text)
    return names


#: Names that are also ordinary words ("an executive assistant"): in free text they count only where they attribute
#: something, never as a word in a sentence.
GENERIC_NAMES = frozenset({"assistant", "the assistant", "your assistant"})
#: Where a generic name attributes: after "by", "from" or "per", or before a date, "'s" or "judgment".
_BEFORE = r"(?:\b(?:by|from|per|reported by|source:?)\s+)"
_AFTER = r"(?=(?:'s|\u2019s)?\s*(?:,\s*\d|\d{1,2}/\d{1,2}|(?:pm\s+)?judge?ment\b))"


def _pattern(names: Iterable[str]) -> re.Pattern[str] | None:
    words = sorted({n for n in names if n}, key=len, reverse=True)
    if not words:
        return None
    specific = [re.escape(w) for w in words if w.casefold() not in GENERIC_NAMES]
    generic = [re.escape(w) for w in words if w.casefold() in GENERIC_NAMES]
    parts = []
    if specific:
        parts.append(r"(?<!\w)(?P<s>" + "|".join(specific) + r")(?!\w)")
    if generic:
        alternatives = "|".join(generic)
        parts.append(_BEFORE + r"(?P<g1>" + alternatives + r")(?!\w)")
        parts.append(r"(?<!\w)(?P<g2>" + alternatives + r")" + _AFTER)
    return re.compile("|".join(parts), re.IGNORECASE)


def _matched(found: re.Match[str]) -> str:
    return next(found.group(k) for k in ("s", "g1", "g2") if k in found.groupdict() and found.group(k))


def name_in(text: str, names: Iterable[str]) -> str | None:
    """The first of the names that `text` holds, as the name is written in `names`: a name the person gave anywhere as
    a whole word, and an ordinary word ("assistant") only where it attributes something. Case is ignored."""
    names = list(names)
    pattern = _pattern(names)
    found = pattern.search(text) if pattern is not None and isinstance(text, str) else None
    if found is None:
        return None
    word = _matched(found)
    return next((n for n in names if n.casefold() == word.casefold()), word)


def names_in(value: Any, names: Iterable[str]) -> str | None:
    """The first of the names that any text inside `value` (a string, or lists and maps of them) holds."""
    names = list(names)
    if isinstance(value, str):
        return name_in(value, names)
    if isinstance(value, Mapping):
        value = list(value.values())
    if isinstance(value, (list, tuple)):
        return next((found for item in value if (found := names_in(item, names))), None)
    return None


def op_problem(op: Any, names: Iterable[str]) -> str | None:
    """Why an op may not be applied: it writes what others read (the text of a shared item, a history line, a
    reporter or an author) and holds one of the names. None when it is clean."""
    names = list(names)
    data = op.model_dump(mode="json")
    where: list[tuple[str, Any]] = [(key, data.get(key)) for key in SOURCE_FIELDS]
    where += [(key, data.get(key)) for key in READ_BY_OTHERS_OPS.get(data["op"], ())]
    if data["op"] == "record.set" and data.get("field") in READ_BY_OTHERS_FIELDS.get(data.get("kind"), frozenset()):
        where.append((data["field"], data.get("value")))
    for key, value in where:
        found = names_in(value, names)
        if found is not None:
            return (
                f"{data['op']} writes {key}, which others read, and it names the assistant ({found}); the assistant "
                "is never a source, reporter or author there: cite where the change came from instead (the page, "
                "mail or person, and the day), or leave the name out"
            )
    return None


def outgoing_problem(view: Any, cfg: Any, parts: Mapping[str, str]) -> str | None:
    """Why content going to someone else is not offered: `parts` maps where each piece sits (a label a person
    understands) to its text, and the first that holds one of the names is the reason, in the wording sheet's words."""
    names = assistant_names(view, cfg.workspace.assistant_name)
    for where, text in parts.items():
        found = name_in(text or "", names)
        if found is not None:
            return cfg.language.messages.withheld_name.format(where=where, name=found)
    return None


def check_outgoing(view: Any, cfg: Any, parts: Mapping[str, str]) -> None:
    """Refuse content going to someone else that still holds one of the names, saying where."""
    problem = outgoing_problem(view, cfg, parts)
    if problem is not None:
        raise StoreError(problem)


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class SourceLabels:
    """What a history row says its source is, for readers: the evidence behind the change, never the assistant. With
    the settings (`cfg`) the wording and the person's name come from them; without, from the defaults."""

    def __init__(self, view: Any, cfg: Any = None):
        language = cfg.language if cfg is not None else LanguageFile()
        self.view = view
        self.words: MessageSettings = language.messages
        self.skip = list(language.title_skip)
        self.min_words = language.title_min_words
        pm = cfg.workspace.user.person if cfg is not None else getattr(view, "user", None)
        self.people = People.from_records(
            {p.id: p.data for p in view.list("person")}, pm, self_words=language.self_words
        )
        self.names = assistant_names(view, cfg.workspace.assistant_name if cfg is not None else DEFAULT_NAME)

    def _on(self, day: date | None) -> str:
        return day.strftime(self.words.source_date_format) if day else ""

    def recorded(self, day: date | None) -> str:
        return self.words.source_recorded.format(date=self._on(day))

    def _person(self, person: str | None, day: date | None) -> str:
        name = self.people.name(person) if person else ""
        if not name or name_in(name, self.names):
            return self.recorded(day)
        return self.words.source_by_person.format(who=name, date=self._on(day))

    def __call__(self, row: Mapping[str, Any]) -> str:
        """The source of one ledger row: the input its evidence cites (else the one its request is about), cited by
        the one known person it came from, or by its title and day; the person's own words are the person's; a row
        with no evidence at all is "recorded" on its day."""
        view, pm = self.view, self.people.pm
        at = _day(row.get("at"))
        cited = (row.get("evidence") or {}).get("source")
        request = view.get("request", row["request"], include_deleted=True) if row.get("request") else None
        found = view.get("source", cited) if cited and cited != "note" else None
        if found is None and cited != "note" and request is not None and request.data.get("source"):
            found = view.get("source", request.data["source"])
        if found is None:
            own = cited == "note" or (request is not None and request.data.get("origin") == "pm")
            if own or (row.get("actor") == "pm" and request is None):
                return self._person(pm, at)
            return self.recorded(at)
        data = found.data
        day = _day(data.get("received_at")) or at
        if data.get("trust") == "trusted":
            return self._person(data.get("author") or pm, day)
        title = title_for(
            request.data if request is not None else {},
            data,
            None,
            people=self.people,
            skip=self.skip,
            min_words=self.min_words,
        )
        if title.person:
            return self._person(title.person, day)
        what = title.topic or " ".join(str(data.get("title") or "").split())
        if not what or name_in(what, self.names):
            return self.recorded(day)
        return self.words.source_input.format(date=self._on(day), what=what)


def reader_row(row: Mapping[str, Any], label: str) -> dict[str, Any]:
    """A ledger row as a reader is shown it: `actor` is the person (`pm`) or an input (`input`), never the assistant,
    and `source` says where the change came from."""
    return {**row, "actor": "pm" if row.get("actor") == "pm" else "input", "source": label}


def _line_row(view: Any, project: str, line: Mapping[str, Any]) -> dict[str, Any] | None:
    """The ledger row that added a history line to a project: the first whose log held the line afterwards and not
    before."""
    for row in view.ledger(kind="project", record_id=project):
        if row.get("field") != "log":
            continue
        if line in (row.get("after") or []) and line not in (row.get("before") or []):
            return row
    return None


def _resourced(text: str, names: list[str], label: str) -> str:
    """`text` with each attribution to the assistant replaced by `label`: a whole "<name>[ a few words], <date>" or
    "<name>'s judgment" phrase where there is one, else the name alone."""
    alternatives = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    phrase = re.compile(
        r"(?<!\w)(?:" + alternatives + r")(?:'s|\u2019s)?(?:\s+[A-Za-z]+){0,3}?\s*,\s*\d{1,2}/\d{1,2}(?:/\d{2,4})?"
        r"|(?<!\w)(?:" + alternatives + r")(?:'s|\u2019s)?\s+(?:pm\s+)?judge?ment\b",
        re.IGNORECASE,
    )
    text = phrase.sub(lambda _m: label, text)
    pattern = _pattern(names)
    return pattern.sub(lambda _m: label, text) if pattern is not None else text


def sweep(store: Any, cfg: Any) -> str | None:
    """Find history lines (a project's update log) that name the assistant and put the evidence in the name's place,
    from the ledger row that wrote each line, keeping its date. All in one change of the core's own, recorded in the
    ledger, that Undo takes back. Returns the changeset's id, or None when no line names the assistant."""
    from engine.applier import OpOutcome

    view = store.read()
    names = assistant_names(view, cfg.workspace.assistant_name)
    labels = SourceLabels(view, cfg)
    pattern = _pattern(names)
    fixes: list[tuple[Any, list[dict[str, Any]]]] = []
    count = 0
    for project in view.list("project"):
        lines = [dict(entry) for entry in project.data.get("log") or []]
        changed = False
        for entry in lines:
            if pattern is None or not pattern.search(entry["text"]):
                continue
            row = _line_row(view, project.id, entry)
            label = labels(row) if row is not None else labels.recorded(_day(entry["on"]))
            if name_in(label, names):
                label = labels.recorded(_day(entry["on"]))
            entry["text"] = _resourced(entry["text"], names, label)
            changed = True
            count += 1
        if changed:
            fixes.append((project, lines))
    if not fixes:
        return None
    with store.transaction() as tx:
        cs_id = tx.new_id("changeset")
        request = tx.create(
            "request",
            {
                "task": "notes",
                "origin": "schedule",
                "state": "done",
                "created_at": store.clock(),
                "changeset": cs_id,
            },
            WriteContext("engine", "trusted", "outward.request"),
        )
        outcomes = []
        for index, (project, lines) in enumerate(fixes):
            w = WriteContext("engine", "trusted", f"outward.resource#{index}", cs_id, request.id)
            tx.update("project", project.id, {"log": lines}, w, read_version=project.version)
            outcomes.append(
                OpOutcome(
                    index,
                    {"op": "outward.resource", "project": project.id},
                    "applied",
                    f"op{index}",
                    records=[{"kind": "project", "id": project.id}],
                    label=cfg.language.messages.resourced_label,
                )
            )
        tx.create(
            "changeset",
            {
                "request": request.id,
                "summary": cfg.language.messages.resourced_summary.format(count=count),
                "ops": [asdict(o) for o in outcomes],
                "status": "applied",
                "trust": "trusted",
                "by_rule": RULE,
                "created_at": store.clock(),
            },
            WriteContext("engine", "trusted", "changeset.record"),
            record_id=cs_id,
        )
    store.plugins.publish("changeset.applied", {"id": cs_id}, follows=cs_id)
    return cs_id
