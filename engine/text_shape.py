"""Text stays text (design 6.7): a field that holds text is never filled with a mapping or a list, and one that arrives
that way is refused with plain words, never turned into a string.

The usual cause is text with a colon and a space in it: read as structured data, "Team wireless: release on top"
becomes a mapping of one name to one value. Every refusal says so and says what to do.
"""

from __future__ import annotations

from typing import Any

#: The instruction every refusal carries.
PUT_IN_QUOTES = "put text with ': ' in quotes"


def shape_of(value: Any) -> str | None:
    """What a value that isn't text is called in words, when it is a mapping or a list; None for anything else."""
    if isinstance(value, dict):
        return "mapping of names to values"
    if isinstance(value, (list, tuple)):
        return "list"
    return None


def text_problem(label: str, value: Any) -> str | None:
    """The refusal for a value that is a mapping or a list where `label` needs text, or None when it is not."""
    shape = shape_of(value)
    if shape is None:
        return None
    return (
        f"{label} has to be text, but it arrived as a {shape}. A ': ' inside text makes it read as a mapping, "
        f"so {PUT_IN_QUOTES}."
    )


def error_problem(error: dict[str, Any], label: str | None = None) -> str | None:
    """The same refusal for one validation error of a field that holds text, when the input was a mapping or a list;
    None for any other error. `label` names the field; by default the error's own location."""
    if error.get("type") != "string_type":
        return None
    where = label or ".".join(str(part) for part in error.get("loc", ()))
    return text_problem(where or "a field", error.get("input"))


def items_problem(label: str, values: Any) -> str | None:
    """The refusal for the first mapping or list among the items of a list of text, or None."""
    for item in values if isinstance(values, (list, tuple)) else ():
        if (why := text_problem(label, item)) is not None:
            return why
    return None
