"""API route for the quality view (design 6.20, 6.13): how well the loop of correcting and learning is working, from the
records alone."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from api.schemas import (
    QualityKnowledgeUsed,
    QualityMissingGroup,
    QualityMissingWeek,
    QualityRepeatWeek,
    QualityView,
)
from engine import quality
from engine.config import Config
from engine.storage import Store
from engine.today import zone


def build_quality_router(cfg: Config, store: Store) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/quality")
    def quality_view() -> QualityView:
        """The knowledge-used rate for each kind of work, the repeat-correction rate for each kind of work and week
        (only weeks with enough corrections have a rate), and the weekly list of what runs said no op could do,
        grouped by wording with counts, over the configured window."""
        view = store.read()
        now = datetime.now(UTC)
        settings = cfg.dispatch.knowledge
        days, here = settings.quality_window_days, zone(cfg)
        return QualityView(
            days=days,
            min_corrections_per_week=settings.min_corrections_per_week,
            knowledge_used=[
                QualityKnowledgeUsed(
                    task=k.task, runs_given=k.given, runs_applied=k.applied, dropped=k.dropped, rate=k.rate
                )
                for k in quality.knowledge_used(view, now, days)
            ],
            repeat_corrections=[
                QualityRepeatWeek(
                    task=w.task,
                    week=w.week,
                    corrections=w.corrections,
                    repeats=w.repeats,
                    enough=w.enough,
                    rate=w.rate,
                )
                for w in quality.repeat_corrections(
                    view, store.plugins.records, now, days, settings.min_corrections_per_week, here
                )
            ],
            missing=[
                QualityMissingWeek(
                    week=w.week,
                    groups=[
                        QualityMissingGroup(
                            wording=g.wording,
                            count=g.count,
                            tasks=g.tasks,
                            changesets=g.changesets,
                            last_seen=g.last_seen,
                        )
                        for g in w.groups
                    ],
                )
                for w in quality.missing_list(view, now, days, here)
            ],
        )

    return r
