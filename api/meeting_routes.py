"""Prep and capture for calendar entries, and people memory (design 6.32, 7.14).

Reading writes nothing. Writing down what happened at an entry hands the person's words in like any note typed on a
record, so what comes out of them is read with evidence, reviewed and undone on its own. A prep note is one request of a
draft kind that goes the usual way (estimate, the person's go above the configured amount); nothing is sent."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas import (
    DatedView,
    HandedOver,
    KeptView,
    LeftOpenView,
    MeetingCaptured,
    MeetingCaptureIn,
    MeetingPrepView,
    OpenItemView,
    PersonMemoryView,
    PersonPrepView,
    PrepGuestView,
    PrepNoteAsk,
    PrepNoteView,
    ReachView,
    TouchView,
)
from engine import meeting_prep, people_memory
from engine.config import Config
from engine.intake import IntakeError
from engine.names import People
from engine.storage import Store, StoreError
from engine.worker import Events, Worker
from engine.workspace import Workspace


def build_meeting_router(ws: Workspace, cfg: Config, store: Store, events: Events, worker: Worker) -> APIRouter:
    r = APIRouter(prefix="/api")

    def items(found: list[people_memory.Item]) -> list[OpenItemView]:
        return [OpenItemView(**asdict(i)) for i in found]

    def touch(found: people_memory.Touch | None) -> TouchView | None:
        return TouchView(**asdict(found)) if found is not None else None

    @r.get("/meetings/{event_id}/prep")
    def get_prep(event_id: str) -> MeetingPrepView:
        """The prep for a calendar entry, by rules: who is coming, what is open with each of them, the last time in
        touch and what the last entry with them left open."""
        found = meeting_prep.prep(store, cfg, event_id, worker.now())
        if found is None:
            raise HTTPException(status_code=404, detail=f"There is no calendar entry {event_id}.")
        names = People(store, cfg)
        view = store.read()
        entry = view.get("event", event_id)
        return MeetingPrepView(
            event=found.event,
            title=found.title,
            start=found.start,
            end=found.end,
            where=found.where,
            untrusted=found.untrusted,
            over=found.over,
            captured_at=entry.data.get("captured_at") if entry is not None else None,
            coming=[
                PrepGuestView(
                    person=g.person,
                    name=names.name(g.person) if g.person else g.name,
                    address=g.address,
                    response=g.response,
                )
                for g in found.coming
            ],
            people=[
                PersonPrepView(
                    person=p.person,
                    name=names.name(p.person),
                    asked_of=items(p.asked_of),
                    asked_by=items(p.asked_by),
                    promised_to=items(p.promised_to),
                    promised_by=items(p.promised_by),
                    more=p.more,
                    last_in_touch=touch(p.last_in_touch),
                    left_open=LeftOpenView(
                        event=p.left_open.event,
                        title=p.left_open.title,
                        on=p.left_open.on,
                        items=items(p.left_open.items),
                        untrusted=p.left_open.untrusted,
                    )
                    if p.left_open is not None
                    else None,
                )
                for p in found.people
            ],
            note=PrepNoteView(**asdict(meeting_prep.note_state(view, event_id))),
        )

    @r.post("/meetings/{event_id}/capture")
    def capture(event_id: str, body: MeetingCaptureIn) -> MeetingCaptured:
        """Write down what happened at a calendar entry, as the person's own words typed on it, or say there is nothing
        to note. The words are read like any note; either way the entry's line on Today goes."""
        try:
            done = meeting_prep.capture(ws, store, cfg, event_id, body.text, worker.now())
        except (StoreError, IntakeError) as err:
            raise HTTPException(status_code=404 if "no calendar entry" in str(err) else 409, detail=str(err)) from None
        events.changed()
        worker.poke()
        return MeetingCaptured(request=done.request, captured_at=done.captured_at)

    @r.post("/meetings/{event_id}/prep-note")
    def ask_for_prep_note(event_id: str, body: PrepNoteAsk) -> HandedOver:
        """Ask the assistant to draft a prep note for a calendar entry. It is filed as a draft on the entry's page,
        estimated and held for the person's go like any draft."""
        try:
            request = meeting_prep.ask_for_note(store, event_id, body.note)
        except StoreError as err:
            raise HTTPException(status_code=404 if "no calendar entry" in str(err) else 409, detail=str(err)) from None
        events.changed()
        worker.poke()
        return HandedOver(request=request)

    @r.get("/people/{person_id}/memory")
    def get_memory(person_id: str) -> PersonMemoryView:
        """What the records say about one person, by rules, each part with the words or the record it rests on."""
        found = people_memory.memory(store, cfg, person_id, worker.now())
        if found is None:
            raise HTTPException(status_code=404, detail=f"There is no person {person_id}.")
        fields: dict[str, Any] = {
            "asked_of": items(found.asked_of),
            "asked_by": items(found.asked_by),
            "promised_to": items(found.promised_to),
            "promised_by": items(found.promised_by),
        }
        return PersonMemoryView(
            person=found.person,
            name=found.name,
            last_in_touch=touch(found.last_in_touch),
            reach=ReachView(**asdict(found.reach)),
            dates=[DatedView(**asdict(d)) for d in found.dates],
            matters=[KeptView(**asdict(k)) for k in found.matters],
            **fields,
        )

    return r
