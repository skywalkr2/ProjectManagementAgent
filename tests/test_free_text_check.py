"""The free-text check: every API route that takes free text from the person is declared (design 6.5).

The fake routes here stand in for a new screen's route, so the check is proved without touching the real API.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from api.free_text import LOCAL_ONLY, ROUTES, TO_ASSISTANT, Declared
from engine.selfcheck.free_text import check_free_text, routes_with_free_text


class Remark(BaseModel):
    note: str = ""
    status: Literal["open", "done"] = "open"


class Nested(BaseModel):
    label: str = ""
    inner: Remark = Field(default_factory=Remark)


class Freeform(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class Picked(BaseModel):
    reason: Literal["a", "b"] = "a"
    person: str | None = None
    due: str | None = Field(None, json_schema_extra={"format": "date"})


def fake_schema() -> dict[str, Any]:
    app = FastAPI()

    @app.post("/api/remarks")
    def remark(body: Remark) -> dict[str, str]:
        return {}

    @app.post("/api/nested")
    def nested(body: Nested) -> dict[str, str]:
        return {}

    @app.post("/api/freeform")
    def freeform(body: Freeform) -> dict[str, str]:
        return {}

    @app.post("/api/picked")
    def picked(body: Picked) -> dict[str, str]:
        return {}

    @app.post("/api/nothing")
    def nothing() -> dict[str, str]:
        return {}

    @app.get("/api/read")
    def read(note: str = "") -> dict[str, str]:
        return {}

    return app.openapi()


def test_the_rule_finds_free_text_at_any_depth_and_ignores_picks_and_other_methods():
    assert routes_with_free_text(fake_schema()) == {
        "POST /api/remarks": ["note"],
        "POST /api/nested": ["inner.note"],
        "POST /api/freeform": ["values"],
    }


def test_a_route_with_free_text_that_is_neither_wired_nor_declared_fails_the_check():
    findings = check_free_text(fake_schema(), {})
    assert sorted(f.message.split(" takes")[0] for f in findings) == [
        "POST /api/freeform",
        "POST /api/nested",
        "POST /api/remarks",
    ]
    assert all("neither handed to the assistant nor declared local-only" in f.message for f in findings)


def test_declaring_each_route_clears_the_check():
    declared = {
        "POST /api/remarks": Declared(TO_ASSISTANT, "the note goes through the note helper"),
        "POST /api/nested": Declared(LOCAL_ONLY, "a label kept as the person's record"),
        "POST /api/freeform": Declared(LOCAL_ONLY, "settings kept as configuration"),
    }
    assert check_free_text(fake_schema(), declared) == []


def test_a_declaration_needs_a_known_kind_and_a_reason_and_a_route_that_takes_free_text():
    declared = {
        "POST /api/remarks": Declared("maybe", "x"),
        "POST /api/nested": Declared(LOCAL_ONLY, "  "),
        "POST /api/freeform": Declared(LOCAL_ONLY, "settings"),
        "POST /api/gone": Declared(LOCAL_ONLY, "a route that no longer exists"),
        "POST /api/picked": Declared(LOCAL_ONLY, "takes only picks"),
    }
    messages = [f.message for f in check_free_text(fake_schema(), declared)]
    assert any("POST /api/remarks is declared as 'maybe'" in m for m in messages)
    assert any("POST /api/nested is declared without a reason" in m for m in messages)
    assert any("POST /api/gone is declared but there is no such route" in m for m in messages)
    assert any("POST /api/picked is declared but takes no free text" in m for m in messages)
    assert not any("POST /api/freeform" in m for m in messages)


def test_the_apis_routes_with_free_text_are_all_declared():
    assert check_free_text() == []


def test_the_notes_on_actions_and_questions_are_declared_as_going_to_the_assistant():
    for route in (
        "POST /api/actions/{action_id}/status",
        "POST /api/followups/{person}/actions/{action_id}/finished",
        "POST /api/followups/{person}/actions/{action_id}/followed-up",
        "POST /api/questions/{qid}/pick-owner",
        "POST /api/questions/{qid}/answer",
        "POST /api/records/edit",
        "POST /api/handin",
        "POST /api/ask",
        "POST /api/changesets/{cs_id}/send-back",
        "POST /api/questions/{qid}/reply",
    ):
        assert ROUTES[route].kind == TO_ASSISTANT, route
