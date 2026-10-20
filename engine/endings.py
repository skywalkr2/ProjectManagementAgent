"""How an action's ending is read from the words it quotes (design 6.33, endings).

The assistant proposes how something ended; the engine reads the exact words it quotes and decides whether that ending
stands. Done stands only with delivery words ("sent", "finished", "it's in"). Words about learning it elsewhere, moving
it to a meeting or it no longer mattering call the action off, with the person's words as the reason and nobody
credited. A bare "close" with neither is not an ending at all: it is one choice for the person, "Done by <owner>, or no
longer needed?", whoever's words they are. The three lists of words are language settings. The person's own act on a
screen is never read for words: they said what they meant by pressing the button.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, Literal

from engine.ops import ActionCloseOp, ActionDropOp
from engine.storage import StoreError

Reading = Literal["done", "called_off", "choice"]
Answer = Literal["done", "called_off"]

#: The words that say it was delivered: an ending with only these is done, and credits the owners.
DEFAULT_DELIVERY_WORDS = (
    *("sent", "finished", "delivered", "it's in", "its in", "did it", "done", "completed", "handed in", "turned in"),
    *("submitted", "shipped", "attached", "uploaded", "published", "emailed", "mailed", "posted", "paid", "booked"),
    *("signed", "returned", "taken care of", "took care of", "came through", "they did", "she did", "he did"),
    *("went out", "gone out", "is out", "handed over", "shared", "forwarded", "got it", "received", "arrived"),
)
#: The words that say it was learned elsewhere, moved to a meeting or no longer matters: an ending with only these is
#: called off, and credits nobody.
DEFAULT_CALLED_OFF_WORDS = (
    *("moot", "covered by", "covered in", "will cover", "we'll cover", "we will cover", "will be covered"),
    *("no longer needed", "no longer need", "not needed", "isn't needed", "no need", "don't need", "drop it"),
    *("drop this", "call it off", "called off", "cancel", "canceled", "cancelled", "never mind", "forget it"),
    *("we'll get it in", "we will get it in", "in our discussions", "in the discussions", "in our discussion"),
    *("in the planning sessions", "in our planning", "superseded", "obsolete", "unnecessary"),
)
#: The words that say it moved into a meeting: a call-off with one of these that names a meeting the workspace knows
#: puts the action on that meeting's agenda.
DEFAULT_MEETING_WORDS = (
    *("will cover", "we'll cover", "we will cover", "will be covered", "covered in", "covered at", "take it up"),
    *("in our discussions", "in the discussions", "in our discussion", "in the planning sessions", "in our planning"),
    *("we'll get it in", "we will get it in", "raise it", "bring it up", "discuss it", "move it to", "moved to"),
)
#: The words that only say it is closed: with neither of the other two, they are neither done nor called off.
DEFAULT_CLOSED_WORDS = ("close", "closed", "closing", "close out", "closed out")

#: The name of the check that holds a bare close, so a screen can tell the choice from any other hold.
CHOICE_CHECK = "ending-choice"
CHOICE_WAITS = "Done by the owner, or no longer needed? Say which."
#: What each answer is recorded as, for the assistant that learns from it.
ANSWER_DONE = "Done"
ANSWER_CALLED_OFF = "No longer needed"


def _plain(text: str) -> str:
    return " ".join(text.lower().replace("\u2019", "'").split())


def _has(text: str, markers: Sequence[str]) -> bool:
    """Whether a marker appears in the words, as whole words, ignoring case and the kind of apostrophe."""
    value = _plain(text)
    return any(
        re.search(rf"(?<![\w'])(?:{re.escape(marker)})(?![\w'])", value) for marker in map(_plain, markers) if marker
    )


def reading(quote: str, words: Any) -> Reading | None:
    """What the quoted words say about how it ended, by the language settings `words` (delivery, called-off and closed
    words): `done` (delivery words alone), `called_off` (call-off words alone, even beside "closed"), `choice` (both
    kinds, or "closed" with neither: not one answer) or None when the words say nothing about an ending."""
    delivered = _has(quote, words.delivery_words)
    called_off = _has(quote, words.called_off_words)
    if delivered and called_off:
        return "choice"
    if delivered:
        return "done"
    if called_off:
        return "called_off"
    return "choice" if _has(quote, words.closed_words) else None


def _reason(quote: str) -> str:
    """The person's words as the reason an action is called off."""
    return " ".join(quote.split())[:500]


def _read_here(ctx: Any) -> bool:
    """Whether the assistant's proposal is read for words: not the person's own act on a screen, and not an ending the
    person already confirmed."""
    return ctx.actor != "pm" and not ctx.confirmed_by_pm


def _quote(op: Any) -> str | None:
    evidence = getattr(op, "evidence", None)
    return evidence.quote if evidence is not None else None


def _credits_someone_else(op: Any, ctx: Any) -> bool:
    """Whether a done would credit someone other than the person: the action has an owner who isn't them."""
    found = ctx.store.read().get("action", op.id)
    owners = [o.get("person") for o in (found.data.get("owners") or [])] if found is not None else []
    return any(person and person != ctx.people.pm for person in owners)


def asks(op: Any, ctx: Any) -> bool:
    """Whether the ending the assistant proposed is one choice for the person: a done or a drop whose words are
    "closed" with neither kind, or both kinds; and a done that would credit someone else whose words say nothing of
    delivery, since crediting a person for work nobody did is the costly mistake."""
    quote = _quote(op)
    if not isinstance(op, (ActionCloseOp, ActionDropOp)) or not quote or not _read_here(ctx):
        return False
    found = reading(quote, ctx.cfg.language)
    if found == "choice":
        return True
    return found is None and isinstance(op, ActionCloseOp) and _credits_someone_else(op, ctx)


def _today(ctx: Any) -> date:
    """The person's day when the input was received (its source's time, else its request's, else now), so a check and
    the apply that follows name the same meetings."""
    from engine.today import zone

    view = ctx.store.read()
    request = view.get("request", ctx.inputs.request) if ctx.inputs.request else None
    source = view.get("source", ctx.inputs.source) if ctx.inputs.source else None
    for stored, key in ((source, "received_at"), (request, "created_at")):
        value = stored.data.get(key) if stored is not None else None
        if value:
            stamp = datetime.fromisoformat(str(value))
            return (stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)).astimezone(zone(ctx.cfg)).date()
    return datetime.now(zone(ctx.cfg)).date()


def moved_into(quote: str, ctx: Any) -> dict[str, str] | None:
    """The meeting a call-off's words move an action into, as the `event` or `series` field of the drop, or None: the
    words must hold one of the meeting words and name a meeting the workspace knows (a calendar entry still ahead,
    else a series), exactly one."""
    from engine.agenda import named_meeting

    if not _has(quote, ctx.cfg.language.meeting_words):
        return None
    found = named_meeting(ctx.store.read(), quote, _today(ctx))
    return {"series" if found[0] == "series" else "event": found[1]} if found is not None else None


def read_endings(cs: Any, ctx: Any) -> Any:
    """A done whose words only call it off becomes a drop with those words as the reason; a call-off whose words move
    it into a meeting the workspace knows names that meeting, so the action goes on its agenda. The same changeset
    always gives the same result, so a check and the apply that follows see the same ops."""
    if not _read_here(ctx):
        return cs
    ops = list(cs.ops)
    for i, op in enumerate(ops):
        quote = _quote(op)
        if not quote or reading(quote, ctx.cfg.language) != "called_off":
            continue
        if isinstance(op, ActionCloseOp):
            op = ops[i] = ActionDropOp(id=op.id, reason=_reason(quote), evidence=op.evidence, group=op.group)
        if isinstance(op, ActionDropOp) and op.event is None and op.series is None:
            meeting = moved_into(quote, ctx)
            if meeting is not None:
                ops[i] = op.model_copy(update=meeting)
    return cs if ops == list(cs.ops) else cs.model_copy(update={"ops": ops})


def called_off_notices(view: Any, ctx: Any, action: Any) -> list[dict[str, Any]]:
    """The one-line drafts, one to each person an action was already sent to, for the person to send: each is a
    question of the kind that tells someone about an action, to someone told or chased, never to the person and never
    to anyone they only watch or report to. Nothing is sent: a draft waits in To send."""
    from engine.followups import UNTOLD_STANCES
    from engine.scope import stance_of

    data = action.data
    reached = [*(data.get("told") or {}), *(data.get("followed_up") or {})]
    drafts = []
    for person in dict.fromkeys(reached):
        if person == ctx.people.pm or stance_of(view, ctx.cfg.steward, person) in UNTOLD_STANCES:
            continue
        item = " ".join(str(data["text"]).split())
        drafts.append(
            {
                "to": person,
                "title": ctx.cfg.language.messages.called_off_notice.format(item=item),
                "kind": "action-notice",
                "projects": [data["project"]] if data.get("project") else [],
            }
        )
    return drafts


def answer(store: Any, cfg: Any, changeset_id: str, index: int, ending: Answer, *, now: datetime | None = None) -> None:
    """The person's answer to "Done by <owner>, or no longer needed?": the held op becomes a close (crediting the
    owners) or a drop (crediting nobody, with the quoted words as the reason), applied now with Undo, and the answer is
    recorded as an answer to the assistant's question so it learns what that person means by "closed"."""
    from engine.applier import release
    from engine.dispatcher import signal

    cs = store.read().get("changeset", changeset_id)
    if cs is None:
        raise StoreError(f"there is no changeset {changeset_id}")
    ops = cs.data["ops"]
    if not 0 <= index < len(ops):
        raise StoreError("that item isn't waiting for you")
    outcome = ops[index]
    asked = any(p.get("check") == CHOICE_CHECK for p in outcome.get("problems") or [])
    if outcome["status"] != "held" or not asked:
        raise StoreError("that item isn't asking whether it is done or no longer needed")
    held = outcome["op"]
    action_id = held["id"]
    quote = (held.get("evidence") or {}).get("quote") or ""
    evidence = {"quote": quote} if quote else None
    if ending == "done":
        op: Any = ActionCloseOp(op="action.close", id=action_id, evidence=evidence)
    else:
        op = ActionDropOp(id=action_id, reason=_reason(quote) or ANSWER_CALLED_OFF, evidence=evidence)
    release(store, cfg, changeset_id, index, now=now, instead=op)
    signal(
        store,
        "answered_assistant",
        [action_id],
        note=ANSWER_DONE if ending == "done" else ANSWER_CALLED_OFF,
        now=now,
        changeset=changeset_id,
    )
