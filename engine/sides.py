"""Two sides in the data (design 6.32): the person's own life (Personal) and, when they have one, their business.

`project.personal` and `project.business` name the top project of each side. A project is on a side by the top of its
parent chain; a person is on a side, both or neither by their own record; an item is on the side of the project it is
filed under. Filing by people (`file_by_people`) gives an item that names no project the side's top project when every
person it names, and the one it came from, are on one side; people on both sides, and people not known, don't decide.
Reads only, except `make_personal` and `set_business`, which write the one project each side needs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from engine.ops import ActionAddOp, FactOp, NoteOp, QuestionAddOp
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


def file_by_people(ops: list[Any], view: Any, cfg: Any, people: Any, sender: str | None) -> list[Any]:
    """The ops with every new action, question, fact or note that names no project filed under a side's top project.
    The side is the one every deciding person is on (the people the op names and the input's sender, when a known
    person; those on both sides and those not known don't decide). With no business set an unplaced item goes to the
    personal project; with one, an item whose people don't agree, or don't say, stays unfiled for the person to place.
    The same ops always give the same result."""
    personal, business = personal_project(view, cfg), business_project(view, cfg)
    if personal is None and business is None:
        return ops
    out: list[Any] = []
    for op in ops:
        if not isinstance(op, (ActionAddOp, QuestionAddOp, FactOp, NoteOp)) or op.project:
            out.append(op)
            continue
        who = [people.resolve(name) for name in _named(op)]
        persons = [r.person for r in who if r.status == "ok" and r.person] + ([sender] if sender else [])
        decided = {s for p in persons if (s := side_of_person(people, p)) in ("personal", "business")}
        if business is None:
            target = personal
        elif len(decided) == 1:
            target = business if decided == {"business"} else personal
        else:
            target = None
        out.append(op.model_copy(update={"project": target}) if target else op)
    return out


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
