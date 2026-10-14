"""A plugin's record field declared with an alias is stored, and named in reference paths, by its field name, as it
was before knowledge records; only a core model that asks for it (the scope's `except`) is stored by its alias."""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import BaseModel, Field

from engine.records import Record, RefTo, Scope, ref_fields
from engine.storage.store import _validate


class Tie(BaseModel):
    other: Annotated[str, RefTo("person")] = Field(alias="with")


class Thing(Record):
    record_kind: ClassVar[str] = "example/thing"
    prefix: ClassVar[str] = "THG"

    id: str
    ties: list[Tie] = Field(default_factory=list)
    label: str = Field("", alias="name")


def test_a_plugins_aliased_fields_are_stored_and_referenced_by_their_field_names():
    stored = _validate(Thing, {"id": "THG-1", "ties": [{"with": "P-1"}], "name": "first"})
    assert stored["ties"] == [{"other": "P-1"}] and stored["label"] == "first"
    assert "with" not in str(stored) and "name" not in stored
    assert ("ties[].other", "person") in ref_fields(Thing)


def test_the_core_scope_is_stored_and_referenced_by_its_alias():
    assert Scope.model_validate({"except": ["PRJ-1"]}).model_dump(mode="json")["except"] == ["PRJ-1"]
    assert ("except[]", "project") in ref_fields(Scope)
