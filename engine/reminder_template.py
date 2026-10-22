"""The core's reminder template (design 6.12): the subject, body and event title of a reminder that goes out to the
person themselves, from a data file whose version is the hash of its text.

The shipped file is `defaults/reminder_template.yaml`; a workspace's own `templates/reminder.yaml` replaces it, which
changes the version. A reminder act is rendered only from this template, and the person's standing yes names the
version it saw. Everything here reads."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any

from engine.yaml_load import load_yaml

#: The template's name, as a reminder act and a standing yes carry it.
NAME = "reminder"
SHIPPED = Path(__file__).parent / "defaults" / "reminder_template.yaml"
FORMS = ("item", "plain")
PARTS = ("subject", "body", "event_title")


class TemplateError(ValueError):
    """The template file is missing a form or a part, or can't be read."""


def source(root: Path | None) -> Path:
    """The file the template is read from: the workspace's own when it has one, else the shipped one."""
    own = root / "templates" / "reminder.yaml" if root is not None else None
    return own if own is not None and own.is_file() else SHIPPED


def version(root: Path | None) -> str:
    """The version of the template as it stands: a hash of the text of the file in use."""
    return hashlib.sha256(source(root).read_text(encoding="utf-8").encode()).hexdigest()[:16]


def load(root: Path | None) -> dict[str, Any]:
    """The template as data, checked to hold both forms with every part."""
    found = load_yaml(source(root).read_text(encoding="utf-8")) or {}
    forms = found.get("forms") or {}
    for form in FORMS:
        for part in PARTS:
            if not str((forms.get(form) or {}).get(part, "")).strip():
                raise TemplateError(f"the reminder template has no {part} in its {form} form")
    if not str(found.get("time_format", "")).strip():
        raise TemplateError("the reminder template has no time_format")
    minutes = found.get("event_minutes")
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= 1440:
        raise TemplateError("the reminder template's event_minutes is a whole number of minutes, 1 to 1440")
    return found


class _Placeholders(dict):
    """The values a template's placeholders take; a placeholder it doesn't know stays as written."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@dataclass(frozen=True)
class Rendered:
    """A reminder as it goes out: the mail's subject and body, and an event's title. `plain` is True for the form that
    holds none of the to-do's words."""

    subject: str
    body: str
    event_title: str
    plain: bool


def render(root: Path | None, *, text: str, at: datetime, tz: tzinfo, app: str, plain: bool) -> Rendered:
    """The reminder for a to-do worded `text`, due at `at` (shown on the clock of `tz`), in the item's own form or the
    plain one. The plain form never sees `text`."""
    found = load(root)
    form = found["forms"]["plain" if plain else "item"]
    values = _Placeholders(
        text="" if plain else " ".join(text.split()),
        time=at.astimezone(tz).strftime(found["time_format"]),
        app=app,
    )
    return Rendered(
        **{part: str(form[part]).format_map(values) for part in PARTS},
        plain=plain,
    )


def example(root: Path | None, *, at: datetime, tz: tzinfo, app: str) -> dict[str, Rendered]:
    """Both forms rendered with the template's own example, for the screen that shows what a reminder will say."""
    text = str((load(root).get("example") or {}).get("text", ""))
    return {
        "item": render(root, text=text, at=at, tz=tz, app=app, plain=False),
        "plain": render(root, text=text, at=at, tz=tz, app=app, plain=True),
    }
