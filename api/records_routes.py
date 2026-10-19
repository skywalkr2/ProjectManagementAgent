"""Routes for the records screens (design 7.14): what the assistant filed under no project, and the pages of a series
and a fact that need more than a record's own fields."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from api.schemas import Applied, SeriesPageView, UnfiledFile, UnfiledItem, UnfiledView
from engine import series_page
from engine import unfiled as unfiled_module
from engine.applier import apply_as_person
from engine.config import Config
from engine.storage import Store, StoreError
from engine.today import zone
from engine.worker import Events


def build_records_router(cfg: Config, store: Store, events: Events) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/unfiled")
    def unfiled() -> UnfiledView:
        """The notes, actions, questions and facts the assistant filed under no project (or under one since removed),
        newest first."""
        items = [
            UnfiledItem(
                kind=i.kind,  # type: ignore[arg-type]
                id=i.id,
                version=i.version,
                text=i.text,
                created_at=i.created_at or None,
                trust=i.trust,  # type: ignore[arg-type]
            )
            for i in unfiled_module.unfiled(store.read())
        ]
        return UnfiledView(count=len(items), items=items)

    @r.post("/unfiled/file")
    def file_unfiled(body: UnfiledFile) -> Applied:
        """File several items under one project as the person's own edit, in one change with Undo. Each item's
        project is an edit of the assistant's work, so each is recorded as a correction."""
        view = store.read()
        if view.get("project", body.project) is None:
            raise HTTPException(status_code=404, detail=f"There is no project {body.project}.")
        try:
            ops = unfiled_module.file_ops(view, [(i.kind, i.id, i.read_version) for i in body.items], body.project)
            cs_id = apply_as_person(store, cfg, ops, "Filed under a project on screen")
        except (StoreError, ValueError) as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        events.changed()
        return Applied(changeset=cs_id)

    @r.get("/series/{series_id}/page")
    def series(series_id: str) -> SeriesPageView:
        """A series' page: the next meeting with what is open for it by person (the person last), and the meetings
        that passed, each with what was settled and what moved on."""
        here = zone(cfg)
        found = series_page.page(
            store.read(),
            series_id,
            datetime.now(UTC).astimezone(here).date(),
            here,
            pm=cfg.workspace.user.person,
            owner_format=cfg.workspace.owner_format,
        )
        if found is None:
            raise HTTPException(status_code=404, detail=f"There is no series {series_id}.")
        return SeriesPageView(**found)

    return r
