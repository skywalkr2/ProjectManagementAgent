"""The screens' wording sheet names everything the core can show."""

import json
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
