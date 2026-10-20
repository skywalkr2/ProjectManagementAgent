"""What the rules do with a calendar entry before the assistant reads anything (design 6.2, 6.32).

An entry of a calendar source with nobody else invited, no description and no change to a date a promise is due at is
plain: it is kept in the calendar by rule, with no run of the assistant and no Review line. The assistant still reads an
invitation from someone else, an entry with a description (or one whose connector doesn't say), and one that changed a
date a promise is due at. A plain entry whose title starts with one of the language's task verbs is offered as a to-do
with one click; one whose title names a known person is linked to them, and one that names a promise's words on that
promise's day is linked to the promise, so the promise moves with it. Nothing here calls AI, and the words come from
the language settings. Reads only, except `link`, which writes the links it finds."""

from __future__ import annotations

import re
from typing import Any

from engine.connectors import EventDetails, EventPerson, SourceItem
from engine.due_phrases import names_title


def identity(view: Any, cfg: Any) -> tuple[set[str], set[str]]:
    """The addresses and the names the person's own calendar entries and invitations use for them."""
    from engine.reply_lines import my_addresses

    mine = {a.email.casefold() for a in my_addresses(view, cfg)}
    me = view.get("person", cfg.workspace.user.person) if cfg.workspace.user.person else None
    names = {n.casefold() for n in [*cfg.workspace.user.accounts, me.data["full_name"] if me else ""] if n}
    return mine, names


def is_mine(person: EventPerson | dict[str, Any] | None, mine: set[str], names: set[str]) -> bool:
    """Whether someone on an event is the person themselves, by address or by name."""
    if person is None:
        return False
    address, name = (
        (person.get("address"), person.get("name")) if isinstance(person, dict) else (person.address, person.name)
    )
    return bool((address and address.casefold() in mine) or (name and name.casefold() in names))


def is_invitation(details: EventDetails, mine: set[str], names: set[str]) -> bool:
    """Whether the event came as an invitation: sent as one, or organized by someone who isn't the person."""
    organizer = details.organizer
    return details.method == "REQUEST" or (
        organizer is not None and not is_mine(organizer, mine, names) and bool(organizer.address or organizer.name)
    )


def is_plain(details: EventDetails | None, mine: set[str], names: set[str]) -> bool:
    """Whether an event is plain by what it is: a connector that keeps entries says it has no description, it isn't
    an invitation, and nobody but the person is on its attendee list."""
    if details is None or not details.entries or details.described is not False:
        return False
    if is_invitation(details, mine, names):
        return False
    return all(is_mine(a, mine, names) for a in details.attendees)


class Plain:
    """Which items of one source are plain right now, read once: the person's identity, the source's entries and the
    calendar entries open promises are due at. A change to an item that a promise is due at is never plain."""

    def __init__(self, view: Any, cfg: Any, source_id: str):
        self.mine, self.names = identity(view, cfg)
        due_at = {
            a.data["due_event"]
            for a in view.list("action")
            if a.data.get("due_event") and a.data.get("status") in ("open", "held")
        }
        self.promised: set[str] = set()
        for entry in view.find("event", {"source": source_id}):
            if entry.id in due_at and entry.data.get("key"):
                self.promised.add(str(entry.data["key"]).split("#", 1)[0])

    def of(self, item: SourceItem) -> bool:
        """Whether the rules file this item by themselves, with no read by the assistant."""
        return is_plain(item.event, self.mine, self.names) and item.key not in self.promised


# ---- a task-like title -----------------------------------------------------------------------------------------------


def first_word(title: str) -> str:
    found = re.findall(r"[\w']+", title.casefold())
    return found[0] if found else ""


def task_offer(entry: dict[str, Any], cfg: Any) -> str | None:
    """The to-do a plain calendar entry is offered as, in its own words, when its title starts with one of the
    language's task verbs; None when it isn't plain, is called off, is an invitation, or reads as no task."""
    if not entry.get("plain") or entry.get("cancelled") or entry.get("invitation"):
        return None
    verbs = {v.casefold() for v in cfg.language.task_verbs}
    return str(entry["title"]) if first_word(str(entry["title"])) in verbs else None


# ---- links -----------------------------------------------------------------------------------------------------------


def people_named(title: str, people: list[Any], pm: str | None) -> list[str]:
    """The known people a title names: those whose full name it holds; when it holds none, the one person a first name
    or alias in it can only mean (a name two people share links nobody). The person themselves never counts."""
    known = [p for p in people if p.id != pm]
    strong = [p.id for p in known if names_title(title, str(p.data["full_name"]))]
    if strong:
        return strong
    weak: set[str] = set()
    for p in known:
        words = [p.data.get("first_name") or str(p.data["full_name"]).split()[0], *(p.data.get("aliases") or [])]
        if any(w and names_title(title, str(w)) for w in words):
            weak.add(p.id)
    return sorted(weak) if len(weak) == 1 else []


def link(tx: Any, entry_id: str, writer: Any, pm: str | None) -> None:
    """Link a plain, kept calendar entry by its title: to the known people it names (`people`), and each open promise
    due on its day whose words the title names, or that names the title's words, to the entry (`due_event`), so the
    promise moves with it. A promise on another day or with none is left as it is."""
    entry = tx.get("event", entry_id)
    if entry is None or not entry.data.get("plain") or entry.data.get("cancelled"):
        return
    title, day = str(entry.data["title"]), str(entry.data["start"])[:10]
    named = people_named(title, tx.list("person"), pm)
    if named != entry.data.get("people", []):
        tx.update("event", entry_id, {"people": named}, writer, read_version=entry.version)
    for action in tx.list("action"):
        d = action.data
        if d.get("status") != "open" or d.get("due_event") or str(d.get("due") or "") != day:
            continue
        if names_title(title, str(d["text"])) or names_title(str(d["text"]), title):
            tx.update("action", action.id, {"due_event": entry_id}, writer, read_version=action.version)
