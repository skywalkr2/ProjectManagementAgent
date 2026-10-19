"""Class-local annotations and the guide's type spelling are the same on every supported interpreter."""

from __future__ import annotations

import typing
from datetime import date

from engine.annotations import local_annotations
from engine.plugin_guide import _type


class _Base:
    inherited: int


class _Child(_Base):
    own: str


def test_local_annotations_are_the_class_own_only():
    assert set(local_annotations(_Child)) == {"own"}
    assert set(local_annotations(_Base)) == {"inherited"}


def test_guide_types_have_one_spelling():
    assert _type(typing.Optional[str]) == "str | None"  # noqa: UP045
    assert _type(str | None) == "str | None"
    assert _type(typing.Optional[typing.Literal["a", "b"]]) == "Literal['a', 'b'] | None"  # noqa: UP045
    assert _type(list[date | None]) == "list[date | None]"
    assert _type(dict[str, typing.Any]) == "dict[str, Any]"
    assert _type(int) == "int"
