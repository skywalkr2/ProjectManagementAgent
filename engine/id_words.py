"""A record named the way a person reads it: by its title in quotes, never by its id (design 6.7, 7.14).

`named` is the one place a label that is read on a screen gets a record's name: the op labels, and the reword of a
label or title written before this rule. An id is how the product refers to a record, never a word for a person; a
record with no title is named by its kind in words ("the to-do"). `id_problem` is the check behind the invariant: an op
that writes a title holding the id of a record that exists is refused. Reads only; nothing here writes.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

#: An id as the store writes it: capital letters, a hyphen and a number, standing alone (not inside a longer word).
ID = re.compile(r"(?<![\w-])([A-Z][A-Z0-9]*-[1-9][0-9]*)(?![\w-])")
#: The fields a record's title can be in, the first one it has being the one shown.
TITLE_KEYS = ("title", "name", "full_name", "term", "topic", "audience", "text")
#: How long a title may be inside a label before it is cut.
TITLE_LENGTH = 60
#: What one record of a kind is called in words when it has no title to name it by.
KIND_WORDS = {
    "action": "the to-do",
    "question": "the question",
    "event": "the calendar entry",
    "series": "the series",
    "note": "the note",
    "person": "the person",
    "project": "the project",
    "fact": "the fact",
    "rule": "the rule",
    "lesson": "the lesson",
    "glossary_entry": "the glossary entry",
    "routing_entry": "the routing entry",
    "style_note": "the style note",
    "source": "the message",
    "snapshot": "the mail item",
    "text_version": "the text",
}
#: The kinds an op that retires "an entry" may mean.
KNOWLEDGE_KINDS = ("lesson", "glossary_entry", "routing_entry", "style_note")

#: The fields an op writes that a screen shows as a title, by op: an id of a record in one is refused.
TITLE_OPS: dict[str, tuple[str, ...]] = {
    "action.add": ("text",),
    "question.add": ("title",),
    "question.update": ("title",),
    "event.add": ("title",),
    "series.add": ("title",),
    "project.add": ("name",),
    "report.draft": ("title",),
}
#: The field of each kind of record a screen shows as its title, for `record.set` and `record.edit`.
TITLE_FIELDS: dict[str, str] = {
    "action": "text",
    "question": "title",
    "event": "title",
    "series": "title",
    "project": "name",
}


def kind_words(kind: str) -> str:
    """What one record of a kind is called in words: "the to-do"."""
    return KIND_WORDS.get(kind) or "the " + kind.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")


def title_of(data: Mapping[str, Any]) -> str | None:
    """A record's title in one line, cut when long: the first of its title fields that holds words."""
    for key in TITLE_KEYS:
        value = data.get(key)
        words = " ".join(str(value).split()) if isinstance(value, str) else ""
        if words:
            if len(words) > TITLE_LENGTH:
                words = words[: TITLE_LENGTH - 1].rstrip() + "…"
            return words
    return None


def named(view: Any, kind: str, record_id: str | None) -> str:
    """The record as a label names it: its title in quotes (a person by name, without quotes), else its kind in words.
    Never its id, whether the record is found or not."""
    record = view.get(kind, record_id) if view is not None and record_id else None
    title = title_of(record.data) if record is not None else None
    if title is None:
        return kind_words(kind)
    return title if kind == "person" else f"'{title}'"


def named_one_of(view: Any, kinds: tuple[str, ...], record_id: str | None) -> str:
    """`named` for an id that is one of several kinds of record: the kind that has it."""
    for kind in kinds:
        if view is not None and record_id and view.get(kind, record_id) is not None:
            return named(view, kind, record_id)
    return kind_words(kinds[0]) if len(kinds) == 1 else "the entry"


def named_text_of(view: Any, version: str | None) -> str:
    """A pending version of a long text, named by the record whose text it is."""
    found = view.get("text_version", version) if view is not None and version else None
    if found is None:
        return kind_words("text_version")
    return named(view, found.data["owner_kind"], found.data["owner_id"])


def prefixes(models: Mapping[str, Any]) -> dict[str, str]:
    """The kind each id prefix belongs to, from the record types in use."""
    return {m.prefix: kind for kind, m in models.items() if getattr(m, "prefix", None)}


def ids_in(text: Any, view: Any, by_prefix: Mapping[str, str]) -> list[tuple[str, str]]:
    """The ids in `text` that belong to a record that exists, as (kind, id), in the order they are written."""
    found: list[tuple[str, str]] = []
    if not isinstance(text, str):
        return found
    for match in ID.finditer(text):
        record_id = match.group(1)
        kind = by_prefix.get(record_id.rsplit("-", 1)[0])
        if kind is not None and view.get(kind, record_id) is not None and (kind, record_id) not in found:
            found.append((kind, record_id))
    return found


def reword(text: str, view: Any, by_prefix: Mapping[str, str], skip: Iterable[str] = ()) -> str:
    """`text` with the id of each record that exists replaced by the record's name as a label gives it; the ids in
    `skip` (the record's own) are left as they are."""
    left = set(skip)

    def swap(match: re.Match[str]) -> str:
        record_id = match.group(1)
        kind = by_prefix.get(record_id.rsplit("-", 1)[0])
        if record_id in left or kind is None or view.get(kind, record_id) is None:
            return record_id
        return named(view, kind, record_id)

    return ID.sub(swap, text)


def title_texts(op: Any) -> list[tuple[str, Any]]:
    """The (field, value) pairs an op writes that a screen shows as a title."""
    data = op.model_dump(mode="json")
    name = data["op"]
    found = [(key, data.get(key)) for key in TITLE_OPS.get(name, ())]
    if name == "record.set":
        field = TITLE_FIELDS.get(data.get("kind"))
        if field is not None and data.get("field") == field:
            found.append((field, data.get("value")))
    if name == "record.edit":
        field = TITLE_FIELDS.get(data["record"]["kind"])
        if field is not None and field in (data.get("fields") or {}):
            found.append((field, data["fields"][field]))
    return found


def id_problem(op: Any, view: Any, by_prefix: Mapping[str, str]) -> str | None:
    """Why an op may not be applied: it writes a title that holds the id of a record that exists. The reason says which
    id and where it sits, in plain words. None when it is clean."""
    for field, value in title_texts(op):
        found = ids_in(value, view, by_prefix)
        if found:
            what = named(view, *found[0])
            return (
                f"the {field} written by {op.op} holds the id of {what}, and an id is never a word for a person: "
                f"write {what} by its title, or leave it out"
            )
    return None
