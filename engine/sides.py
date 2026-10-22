"""Two sides in the data (design 6.32): the person's own life (Personal) and, when they have one, their business.

`project.personal` and `project.business` name the top project of each side. A project is on a side by the top of its
parent chain; a person is on a side, both or neither by their own record; an item is on the side of the project it is
filed under. Filing by people (`file_by_people`) gives an item that names no project the side's top project when every
person it names, and the one it came from, are on one side; people on both sides, and people not known, don't decide.
When the people don't place an item and there is a business, the signals after them may, each a rank read in order, the
first that decides deciding and a rank pointing to both sides deciding nothing: the sender's mail domain when the sender
is nobody known, a project's aliases, the names of projects that count by themselves (two or more words, or one that is
no everyday word), then the configured `project.side_words`; the item's text and quote are matched as whole words
whatever their case. Whatever files an item is kept on it (`filed_by`) so the item can say why.
Reads only, except `make_personal` and `set_business`, which write the one project each side needs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from engine.ops import ActionAddOp, FactOp, NoteOp, ProjectAddOp, QuestionAddOp
from engine.records import FiledBy
from engine.storage import StoreError, WriteContext
from engine.yaml_load import load_yaml

Side = Literal["personal", "business"]

WORDS_FILE = Path(__file__).parent / "defaults" / "words.yaml"
PERSONAL_NAME_KEY = "project.personal_name"
SETTING_PERSONAL = "workspace.project.personal"
SETTING_BUSINESS = "workspace.project.business"


def word(cfg: Any | None, key: str) -> str:
    """A word the engine writes into a record: the workspace's wording override, else the shipped default."""
    override = (cfg.ui.wording.get(key) or "").strip() if cfg is not None else ""
    if override:
        return override
    shipped = load_yaml(WORDS_FILE.read_text(encoding="utf-8")) or {}
    return str(shipped[key])


def _live(view: Any, project_id: str | None) -> str | None:
    """The configured project's id when a project by that id still exists (an undone or removed one counts as unset)."""
    return project_id if project_id and view.get("project", project_id) is not None else None


def _only_top(view: Any, project_id: str) -> bool:
    """Whether the project is the only top-level project in the workspace."""
    return all(p.id == project_id or p.data.get("parent") for p in view.list("project"))


def personal_project(view: Any, cfg: Any) -> str | None:
    """The project of the personal side, when one is set and still there."""
    return _live(view, cfg.workspace.project.personal)


def business_project(view: Any, cfg: Any) -> str | None:
    """The top project of the business side, when one is set and still there."""
    return _live(view, cfg.workspace.project.business)


def top_of(view: Any, project_id: str) -> str | None:
    """The project at the top of a project's parent chain (itself when it has no parent); none for a project that isn't
    there. A chain that loops, or leads to a parent that isn't there, stops at the last project it reached, so a bad
    parent never hangs a read."""
    seen: list[str] = []
    current: str | None = project_id
    while current and current not in seen:
        record = view.get("project", current)
        if record is None:
            break
        seen.append(current)
        current = record.data.get("parent")
    return seen[-1] if seen else None


def side_of_project(view: Any, cfg: Any, project_id: str | None) -> Side | None:
    """Which side a project is on: the side whose top project the project's parent chain ends in; none when it ends
    in neither (or the project isn't there)."""
    if not project_id:
        return None
    top = top_of(view, project_id)
    if top is None:
        return None
    if top == personal_project(view, cfg):
        return "personal"
    if top == business_project(view, cfg):
        return "business"
    return None


def projects_of(data: dict[str, Any]) -> list[str]:
    """The project ids a record names, from its `project` or `projects` field."""
    found: list[str] = []
    for field in ("project", "projects"):
        value = data.get(field)
        if isinstance(value, str) and value:
            found.append(value)
        elif isinstance(value, list):
            found += [v for v in value if isinstance(v, str) and v]
    return found


def side_of_item(view: Any, cfg: Any, record: Any) -> Side | None:
    """Which side an item (a record with a project) is on: that of the first project it names that has one."""
    for project_id in projects_of(record.data):
        if side := side_of_project(view, cfg, project_id):
            return side
    return None


def side_of_line(view: Any, cfg: Any, line: Any) -> Side | None:
    """Which side a line of Today's queue is on: that of its project, else the one side every record it names (the
    question, the actions and the questions it covers) is on. A line about records on both sides, or about none, is on
    no side, so a side filter shows it under every choice."""
    if side := side_of_project(view, cfg, getattr(line, "project", None)):
        return side
    found: set[Side] = set()
    refs = [("question", getattr(line, "question", None))]
    refs += [("action", i) for i in getattr(line, "actions", None) or []]
    refs += [("question", i) for i in getattr(line, "questions", None) or []]
    for kind, record_id in refs:
        record = view.get(kind, record_id) if record_id else None
        if record is not None and (side := side_of_item(view, cfg, record)):
            found.add(side)
    return next(iter(found)) if len(found) == 1 else None


def side_of_person(people: Any, person_id: str | None) -> Literal["personal", "business", "both"] | None:
    """The side a person's record gives them, none when unset or when no such person is known."""
    data = people.records.get(person_id or "") if person_id else None
    return (data or {}).get("side") or None


def _named(op: Any) -> list[str]:
    """The names (or ids) of the people an op that makes an item names: owners and who a promise is to, or who a
    question is to."""
    if isinstance(op, ActionAddOp):
        return [*op.owners, *op.promised_to]
    if isinstance(op, QuestionAddOp):
        return [op.to]
    return []


def _phrase(words: str) -> re.Pattern[str] | None:
    """A pattern that finds the words as a whole word or phrase, whatever the case and the spacing between them."""
    parts = words.split()
    if not parts:
        return None
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(p) for p in parts) + r"(?!\w)", re.IGNORECASE)


def _words_of(op: Any) -> str:
    """What an item says that its words are read from: its text (or title and detail) and the quote it rests on."""
    if isinstance(op, QuestionAddOp):
        parts = [op.title, op.text]
    else:
        parts = [op.text, getattr(getattr(op, "evidence", None), "quote", "")]
    return "\n".join(p for p in parts if p)


#: The ranks of words, in the order they are read after the people and the sender's domain.
WORD_RANKS: tuple[Literal["alias", "name", "word"], ...] = ("alias", "name", "word")

#: What a rank holds for each side: the pattern, the project it names (none for a configured word) and the word itself.
Patterns = dict[Side, list[tuple[re.Pattern[str], str | None, str]]]


def _everyday(cfg: Any) -> frozenset[str]:
    """The words a project name made of one of them alone never files by (`language.everyday_words`), case ignored."""
    return frozenset(" ".join(w.split()).casefold() for w in cfg.language.everyday_words if w.strip())


def _name_counts(name: str, everyday: frozenset[str]) -> bool:
    """Whether a project's name files an item by itself: two or more words, or one that isn't an everyday word."""
    parts = name.split()
    return len(parts) >= 2 or (len(parts) == 1 and parts[0].casefold() not in everyday)


def _side_words(view: Any, cfg: Any) -> dict[str, Patterns]:
    """For each rank of words, the patterns that place an item on each side, each with the project it names: a
    project's aliases (any alias counts, even one word, since the person gave it), then the names of the projects on
    that side that count by themselves, then the configured side words. Only projects on a side have any."""
    configured = cfg.workspace.project.side_words
    everyday = _everyday(cfg)
    found: dict[str, Patterns] = {rank: {"personal": [], "business": []} for rank in WORD_RANKS}
    for project in view.list("project"):
        side = side_of_project(view, cfg, project.id)
        if side is None:
            continue
        for alias in project.data.get("aliases") or []:
            if pattern := _phrase(str(alias)):
                found["alias"][side].append((pattern, project.id, " ".join(str(alias).split())))
        name = " ".join(str(project.data.get("name") or "").split())
        if name and _name_counts(name, everyday) and (pattern := _phrase(name)):
            found["name"][side].append((pattern, project.id, name))
    for side, words in (("personal", configured.personal), ("business", configured.business)):
        found["word"][side] += [(pattern, None, " ".join(w.split())) for w in words if (pattern := _phrase(w))]
    return found


@dataclass(frozen=True)
class Filing:
    """The project an item is filed under and why: the signal (`FiledBy.by`), the word or domain that matched (none for
    people) and the project."""

    project: str
    by: Literal["people", "domain", "alias", "name", "word"]
    word: str | None = None

    def stamp(self) -> FiledBy:
        return FiledBy(by=self.by, word=self.word, project=self.project)


def _top_of_side(view: Any, cfg: Any, side: Side) -> str | None:
    return personal_project(view, cfg) if side == "personal" else business_project(view, cfg)


def file_by_words(op: Any, view: Any, cfg: Any, words: dict[str, Patterns] | None = None) -> Filing | None:
    """How an item's words place it, none when they don't. The ranks are read in order (identifiers, project names,
    configured words) and the first that decides, decides: a rank whose words are all of one side gives that side's top
    project, or the one project of that side the words name; a rank with words of both sides decides nothing, so the
    next is read."""
    text = _words_of(op)
    ranks = words or _side_words(view, cfg)
    for rank in WORD_RANKS:
        matched: dict[Side, list[tuple[str | None, str]]] = {}
        for side, patterns in ranks[rank].items():
            hits = [(project, word) for pattern, project, word in patterns if pattern.search(text)]
            if hits:
                matched[side] = hits
        if len(matched) != 1:
            continue
        side, hits = next(iter(matched.items()))
        named = {project for project, _ in hits if project}
        project = next(iter(named)) if len(named) == 1 else _top_of_side(view, cfg, side)
        if project is None:
            continue
        word = next((w for p, w in hits if p == project), hits[0][1])
        return Filing(project, rank, word)
    return None


def _domain_of(address: str) -> str:
    return address.rpartition("@")[2].strip().lower().rstrip(".") if "@" in address else ""


def sender_domain(people: Any, raw_input: str | None) -> str | None:
    """The domain of the From address of a message that opens the input, when that sender is nobody known; none for
    anything else."""
    from email.utils import parseaddr

    from engine.reply_lines import leading_headers

    head = leading_headers(raw_input or "")
    sender = (head[0].get("from") or "") if head else ""
    if not sender or people.match_entries([sender]):
        return None
    return _domain_of(parseaddr(sender)[1]) or None


def domain_side(people: Any, cfg: Any, domain: str) -> Side | None:
    """The side a mail domain votes for: when every known person with an address there works for one organization and
    that organization's people are all on one side. A public mail service shared by many unrelated people, an address
    nobody known has, and a person with no organization never vote."""
    from engine.set_aside import is_public_domain

    if is_public_domain(domain, cfg):
        return None
    orgs = {
        data.get("org")
        for data in people.records.values()
        if any(_domain_of(v) == domain for v in data.get("how_to_reach", {}).values())
    }
    if len(orgs) != 1 or None in orgs:
        return None
    org = next(iter(orgs))
    on = {data.get("side") for data in people.records.values() if data.get("org") == org and data.get("side")}
    if len(on) != 1:
        return None
    side = next(iter(on))
    return side if side in ("personal", "business") else None


def without_filed_by(ops: list[Any]) -> list[Any]:
    """The ops with any reason for filing they carry cleared: only `file_by_people` sets one."""
    return [
        op.model_copy(update={"filed_by": None})
        if isinstance(op, (ActionAddOp, QuestionAddOp, FactOp, NoteOp)) and op.filed_by is not None
        else op
        for op in ops
    ]


def file_by_people(
    ops: list[Any], view: Any, cfg: Any, people: Any, sender: str | None, raw_input: str | None = None
) -> list[Any]:
    """The ops with every new action, question, fact or note that names no project filed under a project, each keeping
    why it was (`filed_by`). The signals are read in order and the first that decides, decides; one that points to both
    sides decides nothing and the next is read:
    1. the people the op names and the input's sender, when known: the side every deciding person is on (those on
       both sides and those not known don't decide), filed under that side's top project;
    2. the sender's mail domain, when the sender is nobody known (`domain_side`);
    3. a project's aliases, 4. the names of projects that count by themselves, 5. the configured side words
       (`file_by_words`): under the one project they name, else the side's top project.
    With no business set an unplaced item goes to the personal project when that is the only top-level project (a
    workspace tracking other work without naming a business keeps its unfiled items for the person to place); with one,
    an item no signal places stays unfiled for the person to place. A changeset that also proposes a new project is left
    as it is: adding that project files what the same input made with no project under it. Whatever the assistant
    wrote in `filed_by` is cleared: only this function sets it. The same ops always give the same result."""
    ops = without_filed_by(ops)
    personal, business = personal_project(view, cfg), business_project(view, cfg)
    if personal is None and business is None:
        return ops
    if any(isinstance(op, ProjectAddOp) for op in ops):
        return ops
    words = _side_words(view, cfg) if business is not None else None
    domain = sender_domain(people, raw_input) if business is not None else None
    by_domain = domain_side(people, cfg, domain) if domain else None
    only_personal = business is None and personal is not None and _only_top(view, personal)
    out: list[Any] = []
    for op in ops:
        if not isinstance(op, (ActionAddOp, QuestionAddOp, FactOp, NoteOp)) or op.project:
            out.append(op)
            continue
        if business is None:
            out.append(op.model_copy(update={"project": personal}) if only_personal else op)
            continue
        who = [people.resolve(name) for name in _named(op)]
        persons = [r.person for r in who if r.status == "ok" and r.person] + ([sender] if sender else [])
        decided = {s for p in persons if (s := side_of_person(people, p)) in ("personal", "business")}
        filing: Filing | None = None
        if len(decided) == 1:
            target = business if decided == {"business"} else personal
            filing = Filing(target, "people") if target else None
        if filing is None and len(decided) != 1:
            if by_domain is not None and (target := _top_of_side(view, cfg, by_domain)) and domain:
                filing = Filing(target, "domain", domain)
            else:
                filing = file_by_words(op, view, cfg, words)
        out.append(op.model_copy(update={"project": filing.project, "filed_by": filing.stamp()}) if filing else op)
    return out


def filed_view(view: Any, cfg: Any, kind: str, record: Any) -> dict[str, Any] | None:
    """What an item says about why it was filed, for its line and its page: the signal and the word or domain, the
    project it was filed under and its name, and the top project of the other side it can move to in one step (with
    the field that holds its project and the version to read). None when people placed it or nobody did, when the
    project it was filed under is gone, and once the item is anywhere else: the line goes when the person moves it, and
    comes back with Undo."""
    found = record.data.get("filed_by")
    if not isinstance(found, dict) or found.get("by") == "people":
        return None
    project = view.get("project", found.get("project", ""))
    if project is None or found["project"] not in projects_of(record.data):
        return None
    side = side_of_project(view, cfg, project.id)
    other = _top_of_side(view, cfg, "personal" if side == "business" else "business") if side else None
    target = view.get("project", other) if other and other != project.id else None
    return {
        "by": found["by"],
        "word": found.get("word"),
        "project": project.id,
        "project_name": str(project.data.get("name") or ""),
        "move_to": target.id if target is not None else None,
        "move_to_name": str(target.data.get("name") or "") if target is not None else None,
        "field": "projects" if kind == "question" else "project",
        "version": record.version,
    }


# ---- making the two top projects ----------------------------------------------------------------------------


def make_personal(store: Any, cfg: Any | None = None) -> str:
    """Make the personal project, named from the wording sheet, as the first thing a workspace with no template holds.
    Returns its id; the caller records it in `project.personal`."""
    with store.transaction() as tx:
        return tx.create(
            "project",
            {"name": word(cfg, PERSONAL_NAME_KEY)},
            WriteContext(actor="pm", trust="trusted", op="init"),
        ).id


@dataclass(frozen=True)
class Business:
    """The business project after `set_business`: its `project` id, whether this call made it (`created`), and the
    `changeset` to undo (none when nothing changed)."""

    project: str
    created: bool
    changeset: str | None


def set_business(ws: Any, store: Any, cfg: Any, name: str, *, env: dict[str, str] | None = None) -> Business:
    """Say what the person's business is called: the first call makes a top-level project with that name and sets
    `project.business` to it; a later call renames that project, never making another. Both are the person's own edit,
    with Undo. A business whose project was since undone or removed is made again. Raises `StoreError` in plain words
    for a name another live project has, or no name."""
    from engine import settings as config_screens
    from engine.applier import apply_as_person

    name = " ".join(name.split())
    if not name:
        raise StoreError("Give the business a name.")
    view = store.read()
    current = business_project(view, cfg)
    if current is not None:
        record = view.get("project", current)
        if record.data["name"] == name:
            return Business(current, False, None)
        op = {"op": "record.edit", "record": {"kind": "project", "id": current}, "fields": {"name": name}}
        changeset = apply_as_person(store, cfg, [{**op, "read_version": record.version}], "Renamed the business")
        return Business(current, False, changeset)
    changeset = apply_as_person(store, cfg, [{"op": "project.add", "name": name}], "Added the business")
    made = next(p for p in store.read().list("project") if p.data["name"] == name)
    config_screens.save(
        ws,
        cfg,
        store,
        changes={SETTING_BUSINESS: made.id},
        reset=[],
        read_fingerprint=config_screens.fingerprint(ws.config_dir),
        env=env,
    )
    return Business(made.id, True, changeset)
