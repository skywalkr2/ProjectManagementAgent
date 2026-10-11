"""Plugin API 0.3.38: an optional single reference (`Annotated[str, RefTo(...)] | None`) is a reference, references
inside unions of models are found, op models run their nested models' validators, recursive op schemas work, and a
part carries a plugin's label back on text.accepted."""

import json
from typing import Annotated, ClassVar, Literal, Optional

import pytest
from pydantic import BaseModel, Field, field_validator

from engine.ops import CHANGESET, schema_for
from engine.plugin_api import OpModel, RefTo
from engine.records import ref_fields, values_at
from engine.tasks import TaskKind
from engine.texts import check_part


class OnDate(BaseModel):
    kind: Literal["date"] = "date"
    day: str


class AfterAnchor(BaseModel):
    kind: Literal["after"] = "after"
    anchor: Annotated[str, RefTo("p/event")]


class Shaped(BaseModel):
    when: Annotated[OnDate | AfterAnchor, Field(discriminator="kind")]
    many: list[Annotated[OnDate | AfterAnchor, Field(discriminator="kind")]] = []
    single_opt: Annotated[str, RefTo("p/x")] | None = None
    opt_inside: Annotated[str | None, RefTo("p/y")] = None


def test_references_in_unions_and_optional_singles_are_found():
    found = ref_fields(Shaped)
    assert ("when.anchor", "p/event") in found and ("many[].anchor", "p/event") in found
    assert ("single_opt", "p/x") in found and ("opt_inside", "p/y") in found
    assert not any(path == "single_opt[]" for path, _ in found)
    data = {"when": {"kind": "after", "anchor": "EV-1"}, "single_opt": "X-1", "many": [{"kind": "date", "day": "d"}]}
    assert values_at(data, "when.anchor") == ["EV-1"] and values_at(data, "single_opt") == ["X-1"]
    assert [v for v in values_at(data, "many[].anchor") if v] == []  # a member without the field holds none


class Time(BaseModel):
    day: int
    anchor: Optional["Time"] = None

    @field_validator("day")
    @classmethod
    def not_negative(cls, value):
        if value < 0:
            raise ValueError("day must not be negative")
        return value


class SetTime(OpModel):
    op: Literal["p/set-time"] = "p/set-time"
    writes: ClassVar[dict] = {}
    when: Time


def test_op_models_validate_nested_models_and_may_be_recursive():
    models = {"p/set-time": SetTime}
    for bad in ({"day": -1}, {"day": 1, "anchor": {"day": -2}}):
        with pytest.raises(ValueError, match="day must not be negative"):
            CHANGESET.validate_python({"ops": [{"op": "p/set-time", "when": bad}]}, context={"op_models": models})
    ok = CHANGESET.validate_python(
        {"ops": [{"op": "p/set-time", "when": {"day": 1, "anchor": {"day": 2}}}]}, context={"op_models": models}
    )
    assert ok.ops[0].when.anchor.day == 2
    schema = json.dumps(schema_for(["p/set-time"], models))
    assert "$defs" in schema and "$ref" in schema


def test_a_part_carries_a_label():
    draft = TaskKind("p/draft", (), "notes", "notes", output="draft", field="body")
    assert check_part(draft, {"after": "end", "label": " 3 of 5 "}) == {"after": "end", "base": None, "label": "3 of 5"}
    review = TaskKind("p/review", ("note",), "notes", "notes")
    assert check_part(review, {"first": 1, "last": 2, "label": "Scene 1"})["label"] == "Scene 1"
    with pytest.raises(ValueError, match="short line"):
        check_part(draft, {"after": "end", "label": "x" * 81})
