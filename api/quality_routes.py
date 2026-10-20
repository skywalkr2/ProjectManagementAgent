"""API route for the quality view (design 6.20, 6.13): how well the loop of correcting and learning is working, from the
records alone."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

from api.schemas import (
    Ok,
    QualityCloseDay,
    QualityCloses,
    QualityCountBefore,
    QualityCountDay,
    QualityCountIn,
    QualityCounts,
    QualityCountSaved,
    QualityCountUndo,
    QualityEndingDay,
    QualityEndings,
    QualityKnowledgeUsed,
    QualityMissedWeek,
    QualityMissingGroup,
    QualityMissingWeek,
    QualityRepeatWeek,
    QualityReplays,
    QualityView,
)
from engine import gate_measures, quality
from engine.config import Config
from engine.names import People
from engine.storage import Store, StoreError
from engine.today import zone
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_quality_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/quality")
    def quality_view() -> QualityView:
        """The knowledge-used rate for each kind of work, the repeat-correction rate for each kind of work and week
        (only weeks with enough corrections have a rate), and the weekly list of what runs said no op could do,
        grouped by wording with counts, and "Missed one" for each person and week (design 6.32), over the configured
        window; and the gate week's instruments, each a count with its denominator for each day and for the window:
        silent closes out of all closes, wrong endings out of endings made, the person's own missed out of present,
        and the replay set."""
        view = store.read()
        people = People(store, cfg)
        now = worker.now()
        settings = cfg.dispatch.knowledge
        days, here = settings.quality_window_days, zone(cfg)
        span = gate_measures.window(now, days, here)
        shut = gate_measures.closes_measure(view, span, here)
        ended = gate_measures.endings_measure(view, view.ledger(kind="action"), span, here)
        person = people.pm
        counted = gate_measures.counts_measure(view, person, span)
        return QualityView(
            since=span.since,
            until=span.until,
            closes=QualityCloses(
                total=shut.total,
                silent=shut.silent,
                days=[QualityCloseDay(day=d.day, total=d.total, silent=d.silent) for d in shut.days],
            ),
            endings=QualityEndings(
                made=ended.made,
                wrong=ended.wrong,
                declined=ended.declined,
                undone=ended.undone,
                reopened=ended.reopened,
                days=[QualityEndingDay(day=d.day, made=d.made, wrong=d.wrong) for d in ended.days],
            ),
            counts=QualityCounts(
                person=person,
                present=counted.present,
                missed=counted.missed,
                entered=counted.entered,
                days=[QualityCountDay(day=d.day, present=d.present, missed=d.missed) for d in counted.days],
            ),
            replays=QualityReplays(count=gate_measures.replay_count(ws.root)),
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
            missed=[
                QualityMissedWeek(
                    person=w.person,
                    person_name=people.name(w.person),
                    week=w.week,
                    week_end=w.week + timedelta(days=6),
                    count=w.count,
                )
                for w in quality.missed_per_week(view, now, days, here)
            ],
        )

    @r.put("/quality/counts/{day}")
    def save_count(day: date, body: QualityCountIn) -> QualityCountSaved:
        """Save the person's own count for a day, or correct it: how many promises they counted on their own list
        (`present`) and how many of those the app didn't have (`missed`). Returns what the day held before, which
        Undo takes."""
        try:
            previous = gate_measures.save_count(store, cfg, day, body.present, body.missed, now=worker.now())
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        found = next(
            c
            for c in store.read().list("promise_count")
            if c.data.get("person") == People(store, cfg).pm and str(c.data["day"]) == day.isoformat()
        )
        events.changed()
        return QualityCountSaved(
            id=found.id,
            day=day,
            present=body.present,
            missed=body.missed,
            previous=QualityCountBefore(**previous) if previous else None,
        )

    @r.post("/quality/counts/{day}/undo")
    def undo_count(day: date, body: QualityCountUndo) -> Ok:
        """Undo a save: the day holds what it held before, or nothing."""
        try:
            gate_measures.restore_count(
                store, cfg, day, body.previous.model_dump() if body.previous is not None else None
            )
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None
        events.changed()
        return Ok(ok=day.isoformat())

    return r
