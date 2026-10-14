"""AI task kinds: what each kind of work may return, which prompt and guidance it uses, what its runs see, and its
default settings (the workspace's `ai.tasks.<kind>` overrides any of them)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from dataclasses import field as _field
from pathlib import Path
from typing import Any

from engine.ops import KNOWLEDGE_OPS, OP_MODELS, PERSON_ONLY_OPS

#: The knowledge op reading notes offers: a term or name the note uses that isn't in the glossary can be recorded, or
#: marked unknown. It still applies as a proposal unless the words are the person's own (design 6.22).
OFFERED_TO_NOTES = frozenset({"glossary.add"})

#: Core ops reading notes never offers: deleting is the person's call, file.add is made only by person actions,
#: starting projects is for actions and plugin work, the ops only the person makes are theirs alone, and the ops that
#: keep what the assistant learned belong to the work that learns (design 6.22), except the one in `OFFERED_TO_NOTES`.
NOT_FROM_NOTES = (
    (KNOWLEDGE_OPS - OFFERED_TO_NOTES)
    | PERSON_ONLY_OPS
    | {
        "record.delete",
        "file.add",
        "project.add",
        "text.propose",
        "text.draft",
        "answer",
        "setting.propose",
        "report.draft",
    }
)
#: What an ask may do besides what reading notes does: answer, suggest a setting, draft a report to the maintainers.
ASK_OPS = ("answer", "setting.propose", "report.draft")
#: What learning from a correction may propose (design 6.22): one entry to keep, or a change to a lesson that should
#: have caught the mistake. None of these depends on the account that runs it.
LEARN_OPS = ("lesson.add", "lesson.update", "glossary.add", "routing.add", "style.add", "rule.add")


@dataclass(frozen=True)
class TaskKind:
    name: str
    ops: tuple[str, ...]
    prompt: str
    playbook: str
    label: str = ""
    on: str | None = None  # the record kind a run is about, if any
    packet: Callable[..., Any] | None = None  # (target, view, settings, note) -> PacketParts, from a plugin
    defaults: dict[str, Any] = field(default_factory=dict)  # TaskSettings fields the plugin sets
    prompt_file: Path | None = None  # a plugin's own prompt template
    guidance_file: Path | None = None  # a plugin's own guidance
    output: str = "ops"  # "draft": the answer is prose for the long text field `field` of the record it is about
    field: str | None = None
    anchored: bool = False  # a draft that revises the current text, paragraph by paragraph, with ids
    questions: int = 0  # how many questions for the person a draft may end with
    role: str = "write"  # write, check (an independent second opinion) or research
    where: dict[str, tuple[Any, ...]] = _field(default_factory=dict)  # field values a record of kind `on` must have
    start_where: dict[str, tuple[Any, ...]] = _field(default_factory=dict)  # and, for runs the person starts, these
    all_or_nothing: bool = False  # the answer's ops apply together or not at all
    requires_ops: tuple[str, ...] = ()  # an answer must include at least one of these ops
    learning: str = "core"  # "own": the core's own learning steps don't run on this work (engine/learning.py)
    max_ops: int | None = None  # an answer may hold at most this many ops; more is refused as a whole

    def offered_on(self, record: Any, texts: Callable[[str], bool | None] | None = None) -> bool:
        """Whether this work applies to a record (of kind `on`): every `where` field holds one of its values."""
        return where_matches(self.where, record, texts)

    def startable_on(self, record: Any, texts: Callable[[str], bool | None] | None = None) -> bool:
        """Whether the person may start this work on a record: `where` and `start_where` both match."""
        return self.offered_on(record, texts) and where_matches(self.start_where, record, texts)


def where_matches(
    where: dict[str, tuple[Any, ...]], record: Any, texts: Callable[[str], bool | None] | None = None
) -> bool:
    """Whether a record passes a `where` filter: each field holds one of its values, where ANY means "has a value"
    and None "has none". For a long text field, `texts(field)` says whether the record has text in it (None for a
    field that isn't long text)."""
    from engine.plugin_api import ANY

    for key, values in where.items():
        has_text = texts(key) if texts is not None else None
        value = record.data.get(key)
        present = has_text if has_text is not None else value not in (None, "", [], {})
        if not any(
            (v is ANY and present) or (v is None and not present) or (has_text is None and v is not ANY and v == value)
            for v in values
        ):
            return False
    return True


TASKS: dict[str, TaskKind] = {
    # Reading notes never deletes anything; deletion is the person's own act (or a plugin task that declares it).
    "notes": TaskKind(
        name="notes", ops=tuple(n for n in OP_MODELS if n not in NOT_FROM_NOTES), prompt="notes", playbook="notes"
    ),
    # A question from the PM about the app or the workspace (design 6.25), answered from the material it is given.
    "ask": TaskKind(
        name="ask",
        ops=(*ASK_OPS, *(n for n in OP_MODELS if n not in NOT_FROM_NOTES | OFFERED_TO_NOTES)),
        prompt="ask",
        playbook="notes",
        label="Ask",
    ),
    # Sorting the mail the rules can't place (design 6.5): one run over a batch of headers, with no request and no
    # ops. It sees only sender, subject and category, so it is the low-cost tier's work (engine/mail_sorting.py).
    "sort-mail": TaskKind(
        name="sort-mail",
        ops=(),
        prompt="sort-mail",
        playbook="sort-mail",
        label="Sort mail",
        defaults={"max_output": 2000, "expected_output": 400},
    ),
    # Learning from one correction (design 6.22): at most one proposal, or none. A bad lesson is in every later packet,
    # so this is the stronger tier's work (engine/learn.py).
    "learn.correction": TaskKind(
        name="learn.correction",
        ops=LEARN_OPS,
        prompt="learn-correction",
        playbook="learn-correction",
        label="Learning from a correction",
        defaults={"tier": "deep", "max_output": 2000, "expected_output": 400},
        max_ops=1,
    ),
}


def task_kind(name: str) -> TaskKind:
    try:
        return TASKS[name]
    except KeyError:
        raise KeyError(f"unknown task kind {name!r}") from None


def settings(cfg: Any, kind: TaskKind | None, name: str | None = None) -> Any:
    """A task kind's settings: its own defaults, then the tier its role maps to (ai.roles), then whatever the
    workspace's ai.tasks.<kind> sets."""
    from engine.config.schema import TaskSettings

    key = kind.name if kind is not None else name
    configured = cfg.ai.tasks.get(key) if key else None
    values = dict(kind.defaults) if kind is not None else {}
    role_tier = getattr(cfg.ai.roles, kind.role).tier if kind is not None else None
    if role_tier is not None:
        values["tier"] = role_tier
    if configured is not None:
        values.update({f: getattr(configured, f) for f in configured.model_fields_set})
    return TaskSettings.model_validate(values)
