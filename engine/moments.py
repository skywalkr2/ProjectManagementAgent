"""Dates and times in the assistant's own words, shown the way the person reads them.

An input often carries machine timestamps (ISO 8601 with a zone). The assistant copies them into the text it writes, so
before that text is kept, each one is rewritten in the person's time zone and date-and-time format. Quoted evidence is
never touched: it stays the exact words of the input.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from engine.today import zone

#: A date, a time and a zone offset, joined by "T" or a space and ending in Z or an offset such as +01:00. A time
#: with no zone is left alone, since there is nothing to convert it from.
_MOMENT = re.compile(
    r"(?<![\w:.-])(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)\s?(Z|[+-]\d{2}:?\d{2})(?![\w:])(?!\.\d)"
)

#: The text fields of the ops the assistant writes prose in, by op name.
PROSE_FIELDS: dict[str, tuple[str, ...]] = {
    "note": ("text",),
    "fact": ("text",),
    "event.add": ("title",),
    "action.add": ("text",),
    "question.add": ("title", "text"),
    "record.log": ("text",),
    "answer": ("text",),
}


def localize(text: str, cfg: Any) -> str:
    """The text with every machine timestamp in it written in the person's time zone and format."""
    here, shape = zone(cfg), cfg.language.messages.date_time_format

    def one(found: re.Match[str]) -> str:
        date, clock, offset = found.groups()
        zone_part = "+00:00" if offset == "Z" else offset
        try:
            when = datetime.fromisoformat(f"{date}T{clock}{zone_part}")
            return when.astimezone(here).strftime(shape)
        except ValueError:
            return found.group(0)

    return _MOMENT.sub(one, text)


def localize_ops(ops: list[Any], cfg: Any) -> list[Any]:
    """The ops with the machine timestamps in their prose fields rewritten; every other field is as it was."""
    out = []
    for op in ops:
        changes = {}
        for name in PROSE_FIELDS.get(getattr(op, "op", ""), ()):
            value = getattr(op, name, None)
            if isinstance(value, str) and localize(value, cfg) != value:
                changes[name] = localize(value, cfg)
        out.append(op.model_copy(update=changes) if changes else op)
    return out
