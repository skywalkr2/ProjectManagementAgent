"""The define-your-own kit (design 3.10): item types a person defines in settings, built on the plugin API.

For each item type in the kit's settings it registers a record type, ops to add an item, change its fields, tick its
checklist lines and (for the fields the person lets the assistant fill) an op offered to reading notes with evidence,
its stages and their entry checks, a panel listing the items, and its Today lines.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from engine.plugin_api import (
    EvidenceIn,
    LongText,
    OpModel,
    OpWriter,
    ReadView,
    Record,
    RefTo,
    Registrar,
    Settings,
    StageCheckResult,
    StoreError,
    TodayLine,
)

KINDS = ("text", "long_text", "date", "number", "yes_no", "choice", "person", "link")
_SLUG = r"[a-z][a-z0-9_]{0,39}"


class FieldDef(BaseModel):
    """One field of an item type."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_SLUG, description="The field's id: lowercase letters, digits and _.")
    label: str = Field(min_length=1, description="What the field is called on screen.")
    kind: Literal["text", "long_text", "date", "number", "yes_no", "choice", "person", "link"] = Field(
        description="text, long_text, date, number, yes_no, choice (one of its options), person or link."
    )
    options: list[str] = Field(default_factory=list, description="For a choice: the values to pick from.")
    help: str = Field("", description="A line of help shown beside the field.")
    assistant: bool = Field(False, description="The assistant may fill it from what you hand in, with evidence.")
    hidden: bool = Field(False, description="Hidden from screens; its values stay in the items.")


class CheckDef(BaseModel):
    """A check an item must pass to enter a stage."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["filled", "checklist", "date_passed"] = Field(
        description="filled: the field has a value. checklist: every line of the previous stage is ticked. "
        "date_passed: the date in the field has come."
    )
    field: str | None = Field(None, description="The field it looks at, for filled and date_passed.")


class StageDef(BaseModel):
    """One stage of an item type."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_SLUG, description="The stage's id.")
    label: str = Field(min_length=1, description="What the stage is called on screen.")
    description: str = Field("", description="What being in this stage means, in plain words.")
    checks: list[CheckDef] = Field(default_factory=list, description="What an item needs before it enters.")
    checklist: list[str] = Field(default_factory=list, description="Lines to tick while an item is in this stage.")


class TodayDef(BaseModel):
    """What Today shows for an item type."""

    model_config = ConfigDict(extra="forbid")

    due_field: str | None = Field(None, description="A date field; items due soon are shown.")
    due_within_days: int = Field(7, ge=0, le=365, description="How many days ahead counts as soon.")
    waiting_at: list[str] = Field(default_factory=list, description="Stages whose items are shown as waiting.")
    missing: list[str] = Field(default_factory=list, description="Fields whose items are shown while they're empty.")


class TypeDef(BaseModel):
    """An item type."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_SLUG, description="The type's id, used in its identifiers.")
    name: str = Field(min_length=1, description="One item, as it is called on screen.")
    plural: str = Field(min_length=1, description="Several items, as they are called on screen and in folders.")
    prefix: str = Field(pattern=r"[A-Z]{2,8}", description="Capital letters that start the items' ids.")
    title_field: str = Field(description="The text field that names an item.")
    fields: list[FieldDef] = Field(min_length=1, description="The item's fields.")
    in_projects: bool = Field(True, description="Items can belong to a project.")
    stages: list[StageDef] = Field(default_factory=list, description="The steps items move through, in order.")
    columns: list[str] = Field(default_factory=list, description="Fields shown as columns on the list screen.")
    board_by: str | None = Field(None, description="A choice field to group the list screen by, as a board.")
    today: TodayDef = Field(default_factory=TodayDef, description="What Today shows for this type.")
    hidden: bool = Field(False, description="Hidden from screens; its items stay.")

    @model_validator(mode="after")
    def _consistent(self) -> TypeDef:
        names = [f.name for f in self.fields]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.id}: two fields share a name")
        by_name = {f.name: f for f in self.fields}
        reserved = {"id", "stage", "ext", "project", "ticked"}
        if reserved & set(names):
            raise ValueError(f"{self.id}: {sorted(reserved & set(names))[0]} is kept for the core")
        title = by_name.get(self.title_field)
        if title is None or title.kind != "text":
            raise ValueError(f"{self.id}: the title field must be one of its text fields")
        for f in self.fields:
            if f.kind == "choice" and not f.options:
                raise ValueError(f"{self.id}.{f.name}: a choice needs options")
            if f.kind != "choice" and f.options:
                raise ValueError(f"{self.id}.{f.name}: only a choice has options")
            if f.assistant and f.kind == "long_text":
                raise ValueError(f"{self.id}.{f.name}: the assistant drafts long text; it doesn't fill it")
        stage_ids = [s.id for s in self.stages]
        if len(set(stage_ids)) != len(stage_ids):
            raise ValueError(f"{self.id}: two stages share an id")
        for stage in self.stages:
            for check in stage.checks:
                field = by_name.get(check.field or "")
                if check.kind in ("filled", "date_passed") and field is None:
                    raise ValueError(f"{self.id}.{stage.id}: the check names a field the type doesn't have")
                if check.kind == "date_passed" and field.kind != "date":
                    raise ValueError(f"{self.id}.{stage.id}: date_passed needs a date field")
        for name in self.columns:
            if name not in by_name:
                raise ValueError(f"{self.id}: column {name} isn't a field")
        if self.board_by is not None and (self.board_by not in by_name or by_name[self.board_by].kind != "choice"):
            raise ValueError(f"{self.id}: board_by must be a choice field")
        t = self.today
        if t.due_field is not None and (t.due_field not in by_name or by_name[t.due_field].kind != "date"):
            raise ValueError(f"{self.id}: today.due_field must be a date field")
        if set(t.waiting_at) - set(stage_ids):
            raise ValueError(f"{self.id}: today.waiting_at names a stage the type doesn't have")
        if set(t.missing) - set(names):
            raise ValueError(f"{self.id}: today.missing names a field the type doesn't have")
        return self


class Config(Settings):
    types: list[TypeDef] = Field(default_factory=list, description="The item types this workspace uses.")
    due_text: str = Field("{title} is due {date}", description="A Today line for an item due soon.")
    waiting_text: str = Field("{title} is at {stage}", description="A Today line for an item waiting at a stage.")
    missing_text: str = Field("{title} has no {field}", description="A Today line for an item missing a field.")
    filled_pass: str = Field("{field} is filled in.", description="A stage check that passed: a field has a value.")
    filled_fail: str = Field("Fill in {field} first.", description="A stage check that failed: a field is empty.")
    checklist_pass: str = Field("The checklist is done.", description="A stage check that passed: all lines ticked.")
    checklist_fail: str = Field(
        "Tick every line of the checklist first.", description="A stage check that failed: lines are unticked."
    )
    date_pass: str = Field("{field} has come.", description="A stage check that passed: the date has come.")
    date_fail: str = Field("Wait until {field}.", description="A stage check that failed: the date hasn't come.")

    @model_validator(mode="after")
    def _distinct(self) -> Config:
        ids = [t.id for t in self.types]
        prefixes = [t.prefix for t in self.types]
        if len(set(ids)) != len(ids):
            raise ValueError("two item types share an id")
        if len(set(prefixes)) != len(prefixes):
            raise ValueError("two item types share an id prefix")
        return self


# ---- record types ----------------------------------------------------------------------------------------------------


def _python_type(field: FieldDef) -> tuple[Any, Any]:
    """The annotation and default a field kind stores as."""
    if field.kind == "long_text":
        return Annotated[str | None, LongText("markdown")], None
    if field.kind == "date":
        return date | None, None
    if field.kind == "number":
        return float | None, None
    if field.kind == "yes_no":
        return bool, False
    if field.kind == "choice":
        return Literal[tuple(field.options)] | None, None  # type: ignore[valid-type]
    if field.kind == "person":
        return Annotated[str | None, RefTo("person")], None
    if field.kind == "link":
        return Annotated[str | None, Field(pattern=r"^https?://\S+$")], None
    return str | None, None


def record_model(kind: TypeDef) -> type[Record]:
    """The record type for an item type."""
    fields: dict[str, Any] = {}
    for f in kind.fields:
        annotation, default = _python_type(f)
        if f.name == kind.title_field:
            annotation, default = str, ...
        fields[f.name] = (annotation, Field(default, description=f.help or f.label))
    if kind.in_projects:
        fields["project"] = (Annotated[str | None, RefTo("project")], Field(None, description="The project it is in."))
    fields["ticked"] = (list[str], Field(default_factory=list, description="Checklist lines ticked, as <stage>/<n>."))
    model = create_model(f"Kit_{kind.id}", __base__=Record, **fields)
    model.record_kind = f"kit/{kind.id}"
    model.prefix = kind.prefix
    model.layout = f"{_folder(kind.plural)}/{{{kind.title_field}}}"
    return model


def _folder(plural: str) -> str:
    """A folder name from a plural (lowercase, words joined by -)."""
    return re.sub(r"[^a-z0-9]+", "-", plural.lower()).strip("-") or "items"


# ---- ops -------------------------------------------------------------------------------------------------------------


def _ops(kind: TypeDef) -> list[tuple[type[OpModel], Any, bool]]:
    record_kind = f"kit/{kind.id}"
    long_texts = {f.name for f in kind.fields if f.kind == "long_text"}

    class Add(OpModel):
        writes: ClassVar[dict] = {record_kind: ("*",)}
        title: str = Field(min_length=1, description=f"What the {kind.name} is called.")
        project: str | None = Field(None, description="The project it belongs to, if any.")
        values: dict[str, Any] = Field(default_factory=dict, description="Other fields, by name.")

        def describe(self) -> str | None:
            return f"Add the {kind.name} {self.title}"

    class Set(OpModel):
        writes: ClassVar[dict] = {record_kind: tuple(f.name for f in kind.fields) + ("project",)}
        item: str = Field(description=f"The id of the {kind.name}.")
        values: dict[str, Any] = Field(description="The fields to change, by name.")
        read_version: int = Field(ge=1, description="The item's version the change was made from.")

        def describe(self) -> str | None:
            return f"Change {', '.join(sorted(self.values))} of a {kind.name}"

    class Tick(OpModel):
        writes: ClassVar[dict] = {record_kind: ("ticked",)}
        item: str = Field(description=f"The id of the {kind.name}.")
        line: str = Field(pattern=r"^[a-z][a-z0-9_]*/[0-9]+$", description="The checklist line, as <stage>/<n>.")
        done: bool = Field(True, description="Ticked (true) or unticked (false).")
        read_version: int = Field(ge=1, description="The item's version the tick was made from.")

    Add = create_model(f"KitAdd_{kind.id}", __base__=Add, op=(Literal[f"{record_kind}.add"], ...))  # noqa: N806
    Set = create_model(f"KitSet_{kind.id}", __base__=Set, op=(Literal[f"{record_kind}.set"], ...))  # noqa: N806
    Tick = create_model(f"KitTick_{kind.id}", __base__=Tick, op=(Literal[f"{record_kind}.tick"], ...))  # noqa: N806

    def values_of(writer: OpWriter, values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        unknown = set(values) - {f.name for f in kind.fields} - {"project"}
        if unknown:
            raise StoreError(f"a {kind.name} has no field {sorted(unknown)[0]}")
        plain = {k: _stored(v) for k, v in values.items() if k not in long_texts}
        texts = {k: str(v) for k, v in values.items() if k in long_texts and v is not None}
        return plain, texts

    def add(op: Any, writer: OpWriter, config: Config) -> None:
        plain, texts = values_of(writer, op.values)
        data = {**plain, kind.title_field: op.title}
        if kind.in_projects and op.project:
            data["project"] = op.project
        item = writer.create(record_kind, data)
        for field, text in texts.items():
            writer.set_text(record_kind, item.id, field, text)

    def set_(op: Any, writer: OpWriter, config: Config) -> None:
        plain, texts = values_of(writer, op.values)
        if plain:
            writer.update(record_kind, op.item, plain, read_version=op.read_version)
        for field, text in texts.items():
            writer.set_text(record_kind, op.item, field, text)

    def tick(op: Any, writer: OpWriter, config: Config) -> None:
        item = writer.get(record_kind, op.item)
        if item is None:
            raise StoreError(f"there is no {kind.name} {op.item}")
        stage, _, number = op.line.partition("/")
        stage_def = next((s for s in kind.stages if s.id == stage), None)
        if stage_def is None or not 0 <= int(number) < len(stage_def.checklist):
            raise StoreError(f"{op.line} isn't a checklist line of a {kind.name}")
        ticked = [t for t in item.data.get("ticked", []) if t != op.line] + ([op.line] if op.done else [])
        writer.update(record_kind, op.item, {"ticked": sorted(ticked)}, read_version=op.read_version)

    ops: list[tuple[type[OpModel], Any, bool]] = [(Add, add, False), (Set, set_, False), (Tick, tick, False)]
    fillable = [f for f in kind.fields if f.assistant and not f.hidden]
    if fillable:
        extra: dict[str, Any] = {}
        for f in fillable:
            annotation, _ = _python_type(f)
            stored = annotation if f.kind != "yes_no" else bool | None
            extra[f.name] = (stored, Field(None, description=f.help or f.label))
        Fill = create_model(  # noqa: N806
            f"KitFill_{kind.id}",
            __base__=OpModel,
            op=(Literal[f"{record_kind}.fill"], ...),
            item=(str | None, Field(None, description=f"The id of an existing {kind.name}; leave out to add one.")),
            title=(str | None, Field(None, description=f"For a new {kind.name}: what it is called.")),
            project=(str | None, Field(None, description="For a new one: the project it belongs to, if any.")),
            evidence=(EvidenceIn, Field(description="The exact words from the input that say this.")),
            **extra,
        )
        Fill.writes = {record_kind: ("*",)}
        Fill.__doc__ = (
            f"Record what the input says about a {kind.name}: set {', '.join(f.label for f in fillable)} on an "
            f"existing one (item) or add a new one (title). Only fields the input states, with the exact words."
        )

        def fill(op: Any, writer: OpWriter, config: Config) -> None:
            values = {f.name: _stored(getattr(op, f.name)) for f in fillable if getattr(op, f.name) is not None}
            if op.item:
                item = writer.get(record_kind, op.item)
                if item is None:
                    raise StoreError(f"there is no {kind.name} {op.item}")
                if values:
                    writer.update(record_kind, op.item, values, read_version=item.version)
            elif op.title:
                data = {**values, kind.title_field: op.title}
                if kind.in_projects and op.project:
                    data["project"] = op.project
                writer.create(record_kind, data)
            else:
                raise StoreError(f"name the {kind.name} to change (item) or the new one's title")

        ops.append((Fill, fill, True))
    return ops


def _stored(value: Any) -> Any:
    """A value as the record stores it: dates as ISO text."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


# ---- stages, Today and the panel -------------------------------------------------------------------------------------


def _stage_check(kind: TypeDef, stage: StageDef) -> Any:
    labels = {f.name: f.label for f in kind.fields}
    previous = kind.stages[kind.stages.index(stage) - 1] if kind.stages.index(stage) > 0 else None

    def check(record: Any, view: ReadView, config: Config) -> StageCheckResult:
        for c in stage.checks:
            if c.kind == "filled" and record.data.get(c.field) in (None, "", []):
                return StageCheckResult(False, config.filled_fail.format(field=labels[c.field]))
            if c.kind == "date_passed":
                value = record.data.get(c.field)
                if not value or date.fromisoformat(str(value)[:10]) > date.today():
                    return StageCheckResult(False, config.date_fail.format(field=labels[c.field]))
            if c.kind == "checklist" and previous is not None:
                wanted = {f"{previous.id}/{n}" for n in range(len(previous.checklist))}
                if not wanted <= set(record.data.get("ticked", [])):
                    return StageCheckResult(False, config.checklist_fail)
        return StageCheckResult(True, "; ".join(_pass(c, labels, config) for c in stage.checks) or "")

    return check


def _pass(check: CheckDef, labels: dict[str, str], config: Config) -> str:
    if check.kind == "filled":
        return config.filled_pass.format(field=labels[check.field])
    if check.kind == "date_passed":
        return config.date_pass.format(field=labels[check.field])
    return config.checklist_pass


def _today(kind: TypeDef) -> Any:
    record_kind = f"kit/{kind.id}"
    labels = {f.name: f.label for f in kind.fields}
    stage_labels = {s.id: s.label for s in kind.stages}

    def lines(view: ReadView, config: Config) -> list[TodayLine]:
        found: list[TodayLine] = []
        t = kind.today
        today = date.today()
        for item in view.list(record_kind):
            title = str(item.data.get(kind.title_field, item.id))
            about = (record_kind, item.id)
            if t.due_field and item.data.get(t.due_field):
                due = date.fromisoformat(str(item.data[t.due_field])[:10])
                if (due - today).days <= t.due_within_days:
                    text = config.due_text.format(title=title, date=due.isoformat())
                    found.append(TodayLine(f"{item.id}:due", text, about=about, until=due.isoformat()))
            if item.data.get("stage") in t.waiting_at:
                text = config.waiting_text.format(title=title, stage=stage_labels[item.data["stage"]])
                found.append(TodayLine(f"{item.id}:stage", text, about=about))
            for field in t.missing:
                if item.data.get(field) in (None, "", []):
                    text = config.missing_text.format(title=title, field=labels[field].lower())
                    found.append(TodayLine(f"{item.id}:missing:{field}", text, about=about))
        return found

    return lines


# ---- registration ----------------------------------------------------------------------------------------------------


def register(registrar: Registrar) -> None:
    config: Config = registrar.config
    for kind in config.types:
        record_kind = f"kit/{kind.id}"
        registrar.record_type(record_model(kind))
        for model, apply, notes in _ops(kind):
            registrar.op(model, "data", apply, notes=notes)
        if kind.stages:
            stages = []
            for stage in kind.stages:
                entry = []
                if stage.checks:
                    name = f"kit/{kind.id}.{stage.id}"
                    registrar.stage_check(name, _stage_check(kind, stage))
                    entry.append(name)
                stages.append({"id": stage.id, "label": stage.label, "description": stage.description, "entry": entry})
            registrar.stages(record_kind, stages)
        if not kind.hidden:
            others = [f.name for f in kind.fields if f.name != kind.title_field]
            columns = kind.columns or [kind.title_field, *others[:3]]
            if kind.board_by:
                columns = [kind.board_by, *[c for c in columns if c != kind.board_by]]
            visible = [c for c in columns if not next(f for f in kind.fields if f.name == c).hidden]
            registrar.panel(
                f"kit/{kind.id}",
                title=kind.plural,
                kind=record_kind,
                columns=tuple(visible),
                view="board" if kind.board_by else "table",
            )
            if kind.today.due_field or kind.today.waiting_at or kind.today.missing:
                registrar.today(f"kit/{kind.id}", lines=_today(kind))
