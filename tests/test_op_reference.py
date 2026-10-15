"""The op reference the assistant reads (design 6.6): a nested field is shown with its own keys and the values it
allows, since the reference is all a model sees of an op's shape."""

from __future__ import annotations

from pydantic import BaseModel

from engine.ops import OP_MODELS, reference_for


def line_of(op: str) -> str:
    """The op's own entry: its description and fields, which may wrap onto several lines."""
    entry = reference_for([op]).split("\n  Always checked:")[0].split("\nEvery op is checked:")[0]
    return " ".join(entry.splitlines())


def test_a_lessons_reach_is_shown_with_its_keys_and_the_values_scope_takes():
    line = line_of("lesson.add")
    assert "applies_to?: {" in line
    assert 'scope?: "workspace" | "projects"' in line
    assert "projects?: [project id]" in line and "except?: [project id]" in line
    assert "evidence?: {quote}" in line
    assert "records?: [text]" in line and "filter?: {field: value}" in line


def test_a_questions_links_are_shown_as_a_list_of_label_and_address():
    assert "links?: [{label, url}]" in line_of("question.add")


def _nested(annotation) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    return [m for arg in getattr(annotation, "__args__", ()) for m in _nested(arg)]


def test_every_nested_field_of_every_core_op_names_each_key_it_accepts():
    for name, model in OP_MODELS.items():
        line = line_of(name)
        for field in model.model_fields.values():
            for inner in _nested(field.annotation):
                for key, info in inner.model_fields.items():
                    assert (info.alias or key) in line, (name, inner.__name__, key)


def test_the_reference_shows_the_op_field_every_op_carries_so_no_prompt_has_to():
    reference = reference_for(["lesson.add", "action.add"])
    first = reference.splitlines()[0]
    assert first.startswith('Each op is one JSON object: an "op" field naming it')
    assert first.endswith('{"op": "lesson.add", ...}.')
    assert reference_for([]) == ""


def test_the_learning_check_asks_for_the_op_field_in_its_example_and_its_reference():
    from engine.ai.learning_check import task
    from engine.config import load_config
    from tests.conftest import DEMO_B

    asked = task(load_config(DEMO_B / "config", env={}))
    assert '{"op": "lesson.add"' in asked.instructions
    assert '{"op": "lesson.add", ...}' in asked.stable
