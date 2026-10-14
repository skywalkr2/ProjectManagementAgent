"""API routes for what the assistant learned (design 6.22): the entries, and the person's own acts on them. Keep makes a
proposal active with the person as its author, Discard keeps it with the reason, Retire ends an active entry. Each acts
at once, with Undo through the change it makes, and records a signal (6.20)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException

from api.schemas import (
    Applied,
    KnowledgeDiscard,
    KnowledgeKeep,
    KnowledgeNarrow,
    KnowledgeView,
    ReadVersion,
    RuleReviewRule,
    RuleReviewView,
)
from engine import knowledge
from engine.applier import apply_as_person
from engine.config import Config
from engine.dispatcher import SAY_WHO_FIRST, signal
from engine.origin import origins
from engine.records import Rule, Scope
from engine.rule_review import due, review
from engine.storage import Store, StoreError
from engine.worker import Events

Kind = Literal["lesson", "glossary_entry", "routing_entry", "style_note"]
Status = Literal["proposed", "active", "discarded", "expired", "retired"]


def _view(stored: Any, origin: dict[str, Any] | None) -> KnowledgeView:
    data = dict(stored.data)
    own = {name: data.get(name) for names in knowledge.OWN_FIELDS.values() for name in names}
    return KnowledgeView(
        id=stored.id,
        kind=stored.kind,
        version=stored.version,
        text=data["text"],
        status=data["status"],
        learned_from=data["origin"],
        pack=data.get("pack"),
        trust=data["trust"],
        learned_at=data["learned_at"],
        kept_by=data.get("kept_by"),
        kept_at=data.get("kept_at"),
        discard_reason=data.get("discard_reason"),
        applies_to=data["applies_to"],
        evidence=data.get("evidence"),
        origin=origin,
        **{
            name: value
            for name, value in own.items()
            if name in knowledge.OWN_FIELDS[stored.kind] and (value is not None or name == "negative")
        },
    )


def build_knowledge_router(cfg: Config, store: Store, events: Events) -> APIRouter:
    r = APIRouter(prefix="/api")

    def entry(entry_id: str, read_version: int, *, rules: bool = False) -> Any:
        kind = knowledge.kind_of(entry_id) or ("rule" if rules and entry_id.startswith(f"{Rule.prefix}-") else None)
        found = store.read().get(kind, entry_id) if kind else None
        if found is None:
            raise HTTPException(status_code=404, detail=f"{entry_id} doesn't exist")
        if found.version != read_version:
            raise HTTPException(status_code=409, detail=f"{entry_id} changed since it was read")
        return found

    def act(found: Any, op: dict[str, Any], summary: str, kind: str) -> Applied:
        try:
            changeset = apply_as_person(store, cfg, [op], summary)
        except (StoreError, ValueError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        signal(store, kind, [found.id])
        events.changed()
        return Applied(changeset=changeset)

    def edit(found: Any, fields: dict[str, Any]) -> dict[str, Any]:
        return {
            "op": "record.edit",
            "record": {"kind": found.kind, "id": found.id},
            "fields": fields,
            "read_version": found.version,
        }

    @r.get("/knowledge")
    def entries(kind: Kind | None = None, status: Status | None = None) -> list[KnowledgeView]:
        """What the assistant learned, newest first, with where each piece came from; filter by kind and by status."""
        view = store.read()
        found = []
        for name in [kind] if kind else knowledge.KINDS:
            links = origins(view, name, [s.id for s in view.list(name)])
            found += [(s, links.get(s.id)) for s in view.list(name) if status is None or s.data["status"] == status]
        found.sort(key=lambda pair: (pair[0].data["learned_at"], pair[0].id), reverse=True)
        return [_view(stored, link) for stored, link in found]

    @r.post("/knowledge/{entry_id}/keep")
    def keep(entry_id: str, body: KnowledgeKeep) -> Applied:
        """Keep a proposed entry: it becomes active, and the person is its author, with the wording or target they
        changed here. Undo puts it back to proposed."""
        found = entry(entry_id, body.read_version)
        person = cfg.workspace.user.person
        if person is None:
            raise HTTPException(status_code=409, detail=SAY_WHO_FIRST)
        try:
            fields = knowledge.keep_fields(
                found,
                person,
                store.clock(),
                text=body.text,
                applies_to=body.applies_to.model_dump(mode="json", by_alias=True)
                if body.applies_to is not None
                else None,
            )
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        return act(found, edit(found, fields), "Kept what was learned", "kept")

    @r.post("/knowledge/{entry_id}/discard")
    def discard(entry_id: str, body: KnowledgeDiscard) -> Applied:
        """Discard a proposed entry. It is kept, with the reason if one is given. Undo puts it back to proposed."""
        found = entry(entry_id, body.read_version)
        try:
            fields = knowledge.discard_fields(found, body.reason)
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        return act(found, edit(found, fields), "Discarded what was learned", "discarded")

    @r.post("/knowledge/{entry_id}/retire")
    def retire(entry_id: str, body: ReadVersion) -> Applied:
        """Retire an active entry or standing rule: it stops guiding runs and stays on record, with the same `retired`
        signal for both. Undo makes it active again."""
        found = entry(entry_id, body.read_version, rules=True)
        op = "rule.retire" if found.kind == "rule" else "knowledge.retire"
        return act(found, {"op": op, "id": found.id}, "Retired what was learned", "retired")

    @r.get("/knowledge/rules/review")
    def rule_review() -> RuleReviewView:
        """The standing rules to look over: active rules given to runs over the review window and never shown to apply,
        most present first, with the size of what every run is sent and how many rules the latest run had moved out of
        it. A rule a code check enforces is never in the list."""
        view = store.read()
        now = datetime.now(UTC)
        settings = cfg.dispatch.knowledge
        found = review(view, settings, now)
        return RuleReviewView(
            days=found.days,
            flagged=[
                RuleReviewRule(
                    id=f.id,
                    version=f.version,
                    name=f.name,
                    text=f.text,
                    applies_to=Scope.model_validate(f.applies_to),
                    present=f.present,
                    applied=f.applied,
                )
                for f in found.flagged
            ],
            stable_chars=found.stable_chars,
            stable_budget=found.stable_budget,
            moved=found.moved,
            due=due(view, settings, now, found),
        )

    @r.post("/knowledge/{entry_id}/keep-rule")
    def keep_rule(entry_id: str, body: ReadVersion) -> Applied:
        """Keep a standing rule as it is in the review: the clock for its next review starts now. Undo puts the old
        clock back."""
        found = entry(entry_id, body.read_version, rules=True)
        if found.kind != "rule" or found.data["status"] != "active":
            raise HTTPException(status_code=409, detail=f"{entry_id} isn't an active rule")
        return act(found, edit(found, {"reviewed_at": store.clock()}), "Kept a standing rule", "kept")

    @r.post("/knowledge/{entry_id}/narrow")
    def narrow(entry_id: str, body: KnowledgeNarrow) -> Applied:
        """Narrow what an active rule or entry applies to. It is the person's own change of its scope, so Undo puts the
        old scope back."""
        found = entry(entry_id, body.read_version, rules=True)
        if found.data["status"] != "active":
            raise HTTPException(status_code=409, detail=f"{entry_id} isn't active")
        scope = body.applies_to.model_dump(mode="json", by_alias=True)
        return act(found, edit(found, {"applies_to": scope}), "Narrowed what was learned", "narrowed")

    return r
