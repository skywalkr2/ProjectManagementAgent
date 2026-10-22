"""The screens' wording sheet names everything the core can show."""

import json
import re
from pathlib import Path

from engine.ops import OP_MODELS

WORDING = Path(__file__).resolve().parents[1] / "web" / "src" / "wording" / "en.json"


def test_every_core_op_has_a_label_on_screen():
    """What the assistant did is shown in words, never as an internal name such as "op.answer"."""
    words = json.loads(WORDING.read_text(encoding="utf-8"))
    assert [name for name in OP_MODELS if f"op.{name}" not in words] == []


def test_an_answer_is_shown_whole(tmp_path):
    """The person's path: an answer longer than a one-line label reads to its end in What changed."""
    from api.routes import _op_view

    long = "Today is the home screen. " * 12
    entry = {
        "op": {"op": "answer", "text": long, "cites": []},
        "label": "Answer: " + long[:150],
        "records": [],
        "index": 0,
        "status": "applied",
        "group": "g1",
    }

    class _Store:
        def read(self):
            return self

        def get(self, *args, **kwargs):
            return None

    view = _op_view(entry, _Store(), None, {})
    assert view.title == long


# The product's own name is "PM Cockpit" until the installers rename it; it is the one place the words may appear.
_PRODUCT_NAME = "PM Cockpit"
# "PM" as a word of capitals; a time written "6 pm" is not it.
_PROJECT_MANAGER = re.compile(r"\bPMs?\b|[Pp]roject [Mm]anager")


def _said(text: str) -> str:
    return text.replace(_PRODUCT_NAME, "")


def test_no_screen_wording_talks_to_a_project_manager():
    """The core is for anyone juggling work: the person is "you" and the assistant is {assistant}, so no entry of the
    wording sheet says "PM" or "project manager" apart from the product's name."""
    words = json.loads(WORDING.read_text(encoding="utf-8"))
    found = {k: v for k, v in words.items() if isinstance(v, str) and _PROJECT_MANAGER.search(_said(v))}
    assert found == {}


def _descriptions(model, seen=None):
    """Every field description of a settings model, with the models nested in it."""
    from pydantic import BaseModel

    seen = seen if seen is not None else set()
    if model in seen:
        return
    seen.add(model)
    for field in model.model_fields.values():
        if field.description:
            yield field.description
        stack = [field.annotation]
        while stack:
            current = stack.pop()
            stack.extend(getattr(current, "__args__", ()))
            if isinstance(current, type) and issubclass(current, BaseModel):
                yield from _descriptions(current, seen)


def test_the_settings_prompts_and_guide_a_person_or_the_assistant_reads_say_the_user_not_a_project_manager():
    """What is shown in Settings, sent to the assistant as its instructions or practice, and written in the user guide
    reads for anyone juggling work."""
    from importlib import resources

    from engine.config.schema import FILES

    texts = {f"setting: {n}": d for n, m in FILES.items() for d in _descriptions(m)}
    for package in ("engine.prompts", "engine.playbook.guidance", "engine.guide"):
        for path in resources.files(package).iterdir():
            if path.name.endswith((".md", ".txt")):
                texts[f"{package}/{path.name}"] = path.read_text(encoding="utf-8")
    found = sorted(name for name, text in texts.items() if _PROJECT_MANAGER.search(_said(text)))
    assert found == []
