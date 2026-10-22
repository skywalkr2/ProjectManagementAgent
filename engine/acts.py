"""The outward act (design 6.12): its fingerprint, the recipients called out, and what each act op does.

An act is one record (`act`) for everything the app does outside the workspace on the person's behalf. The person's
yes covers a **fingerprint**: a hash of the channel, the target as it resolves now (each recipient's current address,
not only their id), the content parts and the template the content was rendered from, with the version that template
has now. `fingerprint` recomputes it from the act and the workspace as they are; any difference from the one the yes
recorded means the yes no longer covers this act.

Every change of state is an op the applier checks and writes to the ledger. The person's ops are `act.draft` (also the
assistant's and an add-on's, which wait for the person), `act.edit`, `act.approve`, `act.withdraw`, `act.confirm_sent`,
`act.resend` and `act.undo`; the publisher's own are `act.sending`, `act.sent`, `act.failed`, `act.uncertain`,
`act.stale`, `act.reopen`, `act.undone` and `act.undo_failed` (`engine/publisher.py`). Nothing here calls a channel.

An act says what it does (`action`), what it is about (`about`: saved messages, or a calendar entry) and which account
carries it. The yes covers the action, each thing it is about with the service's own id as it resolves now, the event
fields and the account.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from engine import act_accounts, audience, outward
from engine.channels import COPY, OutgoingAbout, OutgoingAct, OutgoingRecipient
from engine.ops import (
    ACT_ACTIONS,
    ACT_UNDOABLE,
    ActApproveOp,
    ActConfirmSentOp,
    ActDraftOp,
    ActEditOp,
    ActFailedOp,
    ActRecipientIn,
    ActReopenOp,
    ActResendOp,
    ActSendingOp,
    ActSentOp,
    ActStaleOp,
    ActUncertainOp,
    ActUndoFailedOp,
    ActUndoneOp,
    ActUndoOp,
    ActWithdrawOp,
    OpModel,
)
from engine.storage import StoreError, WriteContext
from engine.storage.store import Tx

#: The states an act can be in (design 6.12).
STATES = ("draft", "approved", "sending", "sent", "failed", "uncertain", "stale", "withdrawn", "undone")
#: Where a person's edit, a take-back or a new yes may start from.
EDITABLE = ("draft", "approved", "stale", "failed")
#: The event fields of a target, kept in the fingerprint when set.
EVENT_FIELDS = ("start", "end", "title", "alarm_minutes", "answer", "proposed_start", "proposed_end", "label")
APPROVABLE = ("draft", "stale", "failed")
#: What a callout says about a recipient, in the order they are listed.
CALLOUT_REASONS = ("new", "outside", "untrusted", "flagged")
LEVELS = ("open", "internal", "restricted")


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def recipient_key(person: str | None, address: str) -> str:
    """What a recipient is called when the person acknowledges them: the person's id, else the lowercased address."""
    return person or address.strip().lower()


def current_address(view: Any, recipient: Mapping[str, Any]) -> str:
    """The address a recipient resolves to now: a known person's record is read again for the way of reaching them the
    act used, so an address that moved is a different one; anyone else keeps the address the act holds. Lowercased."""
    person = recipient.get("person")
    if person:
        found = view.get("person", person)
        kind = recipient.get("kind")
        if found is None:
            return ""
        if kind:
            return str((found.data.get("how_to_reach") or {}).get(kind, "")).strip().lower()
    return str(recipient.get("address", "")).strip().lower()


def channel_of(plugins: Any, name: str) -> Any:
    """The registered channel of that name (the core's or a running plugin's), or None."""
    return plugins.channels().get(name)


def template_version_now(plugins: Any, data: Mapping[str, Any]) -> str | None:
    """The version the act's template has now, as its channel says; None when the act has no template or the channel
    can't say."""
    template = data.get("template")
    channel = channel_of(plugins, data["channel"])
    if not template or channel is None or channel.template_version is None:
        return None
    return channel.template_version(template["name"])


def service_ref(view: Any, record_id: str) -> dict[str, Any]:
    """What a record an act is about is to the service, as it resolves now: a saved message's service id (the key the
    watched source gave it, a Message-ID for a plain mailbox) and a calendar entry's UID (its source key), with the
    entry's time and state, which move when its organizer changes it. A record that is gone says so."""
    found = view.get("source", record_id)
    if found is not None:
        watched = found.data.get("watched") or {}
        return {"id": record_id, "service_id": watched.get("key"), "source": watched.get("source")}
    entry = view.get("event", record_id)
    if entry is not None:
        data = entry.data
        return {
            "id": record_id,
            "service_id": data.get("key"),
            "uid": data.get("key"),
            "sequence": None,
            "start": data.get("start"),
            "end": data.get("end"),
            "cancelled": bool(data.get("cancelled")),
        }
    return {"id": record_id, "missing": True}


def about_refs(view: Any, data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The records the act is about, each as it resolves now."""
    return [service_ref(view, rid) for rid in data["target"].get("about") or []]


def what(data: Mapping[str, Any]) -> str:
    """The action an act does: the one it names, else the first of its kind's (an act made before acts named one)."""
    target = data["target"]
    return target.get("action") or ACT_ACTIONS[target["kind"]][0]


def components(view: Any, data: Mapping[str, Any], template_now: str | None) -> dict[str, str]:
    """The parts of the fingerprint, each hashed on its own, so a difference can say what changed. What an act did not
    use before acts named an action, their things, an event or an account adds nothing, so an older yes still holds."""
    target = data["target"]
    resolved: dict[str, Any] = {
        "kind": target["kind"],
        "recipients": [
            {
                "key": recipient_key(r.get("person"), r["address"]),
                "role": r["role"],
                "address": current_address(view, r),
            }
            for r in target.get("recipients") or []
        ],
        "calendar": target.get("calendar"),
        "when": target.get("when"),
        "folder": target.get("folder"),
    }
    if target.get("action") and target["action"] != ACT_ACTIONS[target["kind"]][0]:
        resolved["action"] = target["action"]
    for name in EVENT_FIELDS:
        if target.get(name) is not None:
            resolved[name] = target[name]
    template = data.get("template")
    parts = {
        "channel": _hash(data["channel"]),
        "target": _hash(resolved),
        "content": _hash(dict(data.get("parts") or {})),
        "template": _hash(None if not template else {**template, "now": template_now}),
    }
    if target.get("about"):
        parts["about"] = _hash(about_refs(view, data))
    if data.get("account"):
        parts["account"] = _hash(data["account"].lower())
    return parts


def fingerprint(view: Any, data: Mapping[str, Any], template_now: str | None = None) -> str:
    """The stable hash the person's yes covers, from the act and the workspace as it is now."""
    return _hash(components(view, data, template_now))


def current_fingerprint(view: Any, plugins: Any, data: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
    """The fingerprint of an act now, with its parts, reading the template's version from its channel."""
    parts = components(view, data, template_version_now(plugins, data))
    return _hash(parts), parts


def what_changed(covered: Mapping[str, str], now: Mapping[str, str]) -> list[str]:
    """Which parts of what the yes covered are different now (`channel`, `target`, `about`, `account`, `content`,
    `template`)."""
    names = ("channel", "target", "about", "account", "content", "template")
    return [name for name in names if covered.get(name) != now.get(name)]


@dataclass(frozen=True)
class Callout:
    """A recipient the person must look at before their yes, with why: `new` (never written to before), `outside` (not
    one of the workspace's people), `untrusted` (taken from outside text) or `flagged` (whoever made the act asked)."""

    key: str
    person: str | None
    address: str
    reasons: tuple[str, ...]


def written_to(view: Any, key: str, *, except_act: str | None = None) -> bool:
    """Whether the person has written to this recipient before: an act that went out, or a message they copied."""
    for found in view.list("act"):
        if found.id == except_act or found.data["status"] != "sent":
            continue
        if any(
            recipient_key(r.get("person"), r["address"]) == key for r in found.data["target"].get("recipients") or []
        ):
            return True
    return any(c.data.get("person") == key for c in view.list("copy"))


def callouts(view: Any, pm: str | None, data: Mapping[str, Any], *, act_id: str | None = None) -> list[Callout]:
    """Each recipient of the act the person must acknowledge: new, outside the workspace's people, taken from untrusted
    text or flagged by whoever made the act. The person themselves is never called out."""
    found: list[Callout] = []
    for r in data["target"].get("recipients") or []:
        person = r.get("person")
        if person is not None and person == pm:
            continue
        key = recipient_key(person, r["address"])
        why = {
            "new": not written_to(view, key, except_act=act_id),
            "outside": person is None,
            "untrusted": bool(r.get("from_text")),
            "flagged": bool(r.get("called_out")),
        }
        reasons = tuple(name for name in CALLOUT_REASONS if why[name])
        if reasons:
            found.append(Callout(key, person, current_address(view, r), reasons))
    return found


def outgoing(view: Any, act_id: str, data: Mapping[str, Any]) -> OutgoingAct:
    """What the channel is handed: the act's exact content with each recipient's address as it resolves now, and each
    thing it is about with the service's id as it resolves now."""
    target = data["target"]
    template = data.get("template")
    return OutgoingAct(
        id=act_id,
        kind=target["kind"],
        parts=dict(data.get("parts") or {}),
        recipients=tuple(
            OutgoingRecipient(address=current_address(view, r), role=r["role"], person=r.get("person"))
            for r in target.get("recipients") or []
        ),
        calendar=target.get("calendar"),
        when=target.get("when"),
        folder=target.get("folder"),
        template=(template["name"], template["version"]) if template else None,
        action=what(data),
        about=tuple(
            OutgoingAbout(
                id=ref["id"], service_id=ref.get("service_id"), uid=ref.get("uid"), sequence=ref.get("sequence")
            )
            for ref in about_refs(view, data)
        ),
        account=data.get("account"),
        label=target.get("label"),
        start=target.get("start"),
        end=target.get("end"),
        title=target.get("title"),
        alarm_minutes=target.get("alarm_minutes"),
        answer=target.get("answer"),
        proposed_start=target.get("proposed_start"),
        proposed_end=target.get("proposed_end"),
    )


def _target_name(view: Any, data: Mapping[str, Any]) -> str:
    target = data["target"]
    if target["kind"] == "file":
        return str(target.get("folder") or "")
    if target["kind"] == "mailbox":
        return ""
    if target["kind"] == "calendar" and not target.get("recipients"):
        return str(target.get("title") or target.get("calendar") or "")
    names = []
    for r in target.get("recipients") or []:
        found = view.get("person", r["person"]) if r.get("person") else None
        names.append(found.data["full_name"] if found is not None else r["address"])
    return ", ".join(names)


def part_labels(view: Any, cfg: Any, data: Mapping[str, Any]) -> dict[str, str]:
    """Where each part of the act sits, in the words the name check says it in ("the message to Ana"); with more than
    one part, each is named after the place."""
    where = cfg.language.messages.withheld_where.format(name=_target_name(view, data))
    parts = data.get("parts") or {}
    return {(f"{where} ({name})" if len(parts) > 1 else where): text for name, text in parts.items()}


def name_problem(view: Any, cfg: Any, data: Mapping[str, Any]) -> str | None:
    """Why the act's content isn't offered or sent: a part still names the assistant. None when it is clean."""
    return outward.outgoing_problem(view, cfg, part_labels(view, cfg, data))


def highest(levels: list[str | None]) -> str:
    """The most sensitive of some data levels; internal when there are none."""
    known = [lv for lv in levels if lv in LEVELS]
    return max(known, key=LEVELS.index) if known else "internal"


def sensitivity_of(view: Any, sources: list[str]) -> str:
    """The act's data level: the highest level of the saved inputs it draws on."""
    found = (view.get("source", s) for s in sources)
    return highest(["internal", *(r.data.get("sensitivity") for r in found if r is not None)])


def route(
    tx: Any,
    ctx: Any,
    channel_name: str,
    kind: str,
    action: str,
    account: str | None,
    *,
    about: list[str],
    in_reply_to: str | None,
) -> tuple[str, str | None, str | None]:
    """The channel and account an act goes through: the channel the draft names (or, for an edit, the one it first
    named), the account (named, or the one the message or invitation came in on, or the one last picked) and, when
    acting is off for that account, Copy instead. Returns (channel, intended channel or None, account). Raises
    StoreError
    with the reason when the channel can't do it or doesn't serve the account."""
    channel = channel_of(ctx.store.plugins, channel_name)
    if channel is None:
        raise StoreError(f"there is no channel {channel_name}")
    if kind not in channel.kinds:
        raise StoreError(f"the channel {channel_name} doesn't take a {kind}")
    if not channel.manual and not channel.takes(kind, action):
        declared = ", ".join(channel.actions.get(kind) or ACT_ACTIONS[kind][:1])
        raise StoreError(f"the channel {channel_name} can't {action} for a {kind} act: it can {declared}")
    if account is None:
        ids = [in_reply_to] if action in ("reply", "reply_all", "forward") and in_reply_to else list(about)
        came_in = {a.lower(): a for rid in ids if (a := act_accounts.of_record(tx, ctx.store, ctx.cfg, rid))}
        if len(came_in) > 1:
            raise StoreError("these came in on different accounts; draft one act for each account")
        account = next(iter(came_in.values()), None)
        if account is None and action in ("send", "create"):
            account = act_accounts.last_picked(tx)
    if channel.accounts:
        if account is None:
            raise StoreError("say which account carries it")
        if act_accounts.kind_of(account) not in channel.accounts:
            raise StoreError(f"the channel {channel_name} doesn't serve that account")
        if not act_accounts.acting_on(ctx.cfg, account):
            return COPY.name, channel_name, account
    return channel_name, None, account


def acting_problem(cfg: Any, plugins: Any, data: Mapping[str, Any]) -> str | None:
    """Why the publisher may not call the act's channel: its account isn't switched on for acting (the person turned it
    off after the yes). None when it may."""
    channel = channel_of(plugins, data["channel"])
    account = data.get("account")
    if channel is None or channel.manual or not channel.accounts or account is None:
        return None
    if not act_accounts.acting_on(cfg, account):
        return "acting is off for the account this goes through: turn it on in Settings, or copy it"
    return None


def undoable(data: Mapping[str, Any]) -> bool:
    """Whether the act's action is one that can be taken back once it went out (a mailbox act, an event created)."""
    return (data["target"]["kind"], what(data)) in ACT_UNDOABLE


# ---- the checks the applier runs (they name no state of their own) -------------------------------------------------


def _recipient_known(ctx: Any, r: ActRecipientIn) -> bool:
    if (r.person or "").strip():
        return ctx.people.resolve(r.person).status == "ok"
    return any(
        (r.address or "").strip().lower() in audience.addresses_of(ctx.people, person) for person in ctx.people.records
    )


def thread_people(ctx: Any, in_reply_to: str | None) -> set[str]:
    """The people (known ones by id, anyone else by lowercased address) in the message an act answers."""
    from engine.intake import source_text
    from engine.workspace import Workspace

    if not in_reply_to:
        return set()
    text = source_text(Workspace(ctx.store.path.parent), ctx.store, in_reply_to)
    return set(audience.people_of(text, ctx.people))


def stranger_problem(ctx: Any, op: ActDraftOp) -> str | None:
    """Why an act drafted by the assistant or an add-on may not address someone: they are neither a known person nor in
    the message it answers, and the draft doesn't call them out. None when every recipient is one it may address."""
    in_thread = thread_people(ctx, op.in_reply_to)
    for r in op.target.recipients:
        if r.called_out or _recipient_known(ctx, r) or (r.address or "").strip().lower() in in_thread:
            continue
        who = (r.person or r.address or "").strip()
        return (
            f"{who} isn't someone the workspace knows or in the message this answers; an address from anywhere else "
            "comes from outside text, so flag the recipient as called out and the person decides"
        )
    return None


def audience_problem(view: Any, people: Any, sources: list[str], written: list[str]) -> str | None:
    """Why an act can't go to one of these recipients: a saved message it draws on was limited to people they aren't
    among (design 6.35)."""
    for who in written:
        why = audience.recipient_problem(view, people, sources, who)
        if why is not None:
            return why
    return None


def op_recipients(op: ActDraftOp | ActEditOp) -> list[str]:
    """The recipients an op names, as written, for the audience check."""
    entries = op.target.recipients if isinstance(op, ActDraftOp) else (op.recipients or [])
    return [(r.person or r.address or "").strip() for r in entries]


def act_recipients(view: Any, data: Mapping[str, Any]) -> list[str]:
    """The recipients of a stored act, as the audience check reads them: a known person's id, else the address."""
    return [r.get("person") or r["address"] for r in data["target"].get("recipients") or []]


# ---- applying -------------------------------------------------------------------------------------------------------


def _resolved(tx: Tx, ctx: Any, entries: list[ActRecipientIn]) -> list[dict[str, Any]]:
    """The recipients as an act keeps them: a person by id with the address their record gives for the way they are
    reached, an address of a known person turned back into that person, anyone else by address and marked as taken from
    outside text when the assistant or an add-on wrote it."""
    person_made = ctx.actor == "pm"
    found: list[dict[str, Any]] = []
    for r in entries:
        pid: str | None = None
        kind = r.kind
        address = (r.address or "").strip()
        if (r.person or "").strip():
            resolved = ctx.people.resolve(r.person)
            if resolved.status != "ok":
                raise StoreError(f"{r.person!r} isn't one known person")
            pid = resolved.person
            reach = (tx.get("person", pid).data.get("how_to_reach") or {}) if pid else {}
            if kind is None and len(reach) == 1:
                kind = next(iter(reach))
            if kind is None or not str(reach.get(kind, "")).strip():
                raise StoreError(f"{ctx.people.name(pid)} has no {kind or 'way to reach them'} on file")
            address = str(reach[kind]).strip()
        else:
            for person in ctx.people.records:
                match = next(
                    (
                        k
                        for k, v in (tx.get("person", person).data.get("how_to_reach") or {}).items()
                        if str(v).strip().lower() == address.lower()
                    ),
                    None,
                )
                if match is not None:
                    pid, kind, address = (
                        person,
                        match,
                        str(tx.get("person", person).data["how_to_reach"][match]).strip(),
                    )
                    break
        key = recipient_key(pid, address)
        if any(recipient_key(x["person"], x["address"]) == key for x in found):
            raise StoreError("a recipient is listed twice")
        found.append(
            {
                "person": pid,
                "address": address,
                "kind": kind if pid else None,
                "role": r.role,
                "from_text": bool(r.from_text or (pid is None and not person_made)),
                "called_out": r.called_out,
            }
        )
    return found


def _get(tx: Tx, act_id: str) -> Any:
    found = tx.get("act", act_id)
    if found is None:
        raise StoreError(f"act {act_id} doesn't exist")
    return found


def _need(found: Any, states: tuple[str, ...], what: str) -> None:
    if found.data["status"] not in states:
        raise StoreError(f"{what}: this act is {found.data['status']}")


def _made_by(ctx: Any) -> str:
    return "person" if ctx.actor == "pm" else "assistant"


def _about(tx: Tx, op: ActDraftOp) -> list[str]:
    """The records a mailbox act or an event act is about, each checked to be the right kind of record."""
    target = op.target
    kind = "source" if target.kind == "mailbox" else "event"
    for rid in target.about:
        if tx.get(kind, rid) is None:
            raise StoreError(f"{rid} isn't {'a saved message' if kind == 'source' else 'a calendar entry'}")
    if target.kind not in ("mailbox", "calendar") and target.about:
        raise StoreError("only a mailbox or calendar act is about saved records")
    return list(dict.fromkeys(target.about))


def _organizer(tx: Tx, op: ActDraftOp) -> list[ActRecipientIn]:
    """The recipient of an answer to an invitation: the organizer the calendar entry names, whose address came from the
    invitation's own text when the entry did."""
    if op.target.kind != "calendar" or op.target.what != "answer":
        return list(op.target.recipients)
    entry = tx.get("event", op.target.about[0])
    organizer = (entry.data.get("organizer") or {}) if entry is not None else {}
    address = (organizer.get("address") or "").strip()
    if not address:
        raise StoreError("that invitation names no organizer to answer")
    return [ActRecipientIn(address=address, from_text=entry.data.get("trust") == "untrusted")]


def _draft(tx: Tx, op: ActDraftOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    about = _about(tx, op)
    channel, intended, account = route(
        tx,
        ctx,
        op.channel,
        op.target.kind,
        op.target.what,
        op.account,
        about=about,
        in_reply_to=op.in_reply_to,
    )
    for source in [*op.sources, *([op.in_reply_to] if op.in_reply_to else [])]:
        if tx.get("source", source) is None:
            raise StoreError(f"source {source} doesn't exist")
    saved_about = about if op.target.kind == "mailbox" else []
    sources = list(dict.fromkeys([*op.sources, *([op.in_reply_to] if op.in_reply_to else []), *saved_about]))
    target = op.target
    made = tx.create(
        "act",
        {
            "channel": channel,
            "account": account,
            "intended_channel": intended,
            "target": {
                "kind": target.kind,
                "action": target.what,
                "recipients": _resolved(tx, ctx, _organizer(tx, op)),
                "about": about,
                "calendar": target.calendar,
                "when": target.when,
                "folder": target.folder,
                "label": target.label,
                "start": target.start,
                "end": target.end,
                "title": target.title,
                "alarm_minutes": target.alarm_minutes,
                "answer": target.answer,
                "proposed_start": target.proposed_start,
                "proposed_end": target.proposed_end,
            },
            "parts": dict(op.parts),
            "template": op.template.model_dump(mode="json") if op.template else None,
            "status": "draft",
            "made_by": _made_by(ctx),
            "run": ctx.run,
            "sources": sources,
            "in_reply_to": op.in_reply_to,
            "project": op.project,
            "sensitivity": sensitivity_of(tx, sources),
        },
        w,
    )
    return [{"kind": "act", "id": made.id}]


def _clear_yes(found: Any, tx: Tx, changes: dict[str, Any], w: WriteContext) -> list[dict[str, Any]]:
    tx.update(
        "act",
        found.id,
        {**changes, "status": "draft", "approved": None, "failure": None, "why": []},
        w,
        read_version=found.version,
    )
    return [{"kind": "act", "id": found.id}]


def _edit(tx: Tx, op: ActEditOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    if found.version != op.read_version:
        raise StoreError("this act changed since you looked at it")
    _need(found, EDITABLE, "it can't be changed")
    changes: dict[str, Any] = {}
    if op.parts is not None:
        if found.data["target"]["kind"] == "mailbox":
            raise StoreError("a mailbox act has no content to change")
        if found.data["target"]["kind"] in ("message", "file") and not any(str(v).strip() for v in op.parts.values()):
            raise StoreError("an act has some content")
        changes["parts"] = dict(op.parts)
    if op.account is not None:
        target = found.data["target"]
        channel, intended, account = route(
            tx,
            ctx,
            found.data.get("intended_channel") or found.data["channel"],
            target["kind"],
            what(found.data),
            op.account,
            about=target.get("about") or [],
            in_reply_to=found.data.get("in_reply_to"),
        )
        changes.update({"channel": channel, "intended_channel": intended, "account": account})
    if op.recipients is not None:
        if found.data["target"]["kind"] != "message":
            raise StoreError("only a message has recipients")
        if not any(r.role == "to" for r in op.recipients):
            raise StoreError("a message goes to at least one person")
        changes["target"] = {**found.data["target"], "recipients": _resolved(tx, ctx, op.recipients)}
    return _clear_yes(found, tx, changes, w)


def _pm(ctx: Any) -> str:
    person = ctx.people.pm
    if person is None:
        raise StoreError("there is no person to say yes as")
    return person


def _approve(tx: Tx, op: ActApproveOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _need(found, APPROVABLE, "it can't be approved")
    data = found.data
    outward.check_outgoing(tx, ctx.cfg, part_labels(tx, ctx.cfg, data))
    if (why := audience_problem(tx, ctx.people, data["sources"], act_recipients(tx, data))) is not None:
        raise StoreError(why)
    now, parts = current_fingerprint(tx, ctx.store.plugins, data)
    if now != op.fingerprint:
        raise StoreError("this act is different from the one you were shown; look at it again")
    pm = ctx.people.pm
    called = callouts(tx, pm, data, act_id=found.id)
    missing = [c for c in called if c.key not in set(op.acknowledged)]
    if missing:
        raise StoreError("acknowledge each recipient called out: " + ", ".join(c.key for c in missing))
    keys = {c.key for c in called}
    tx.update(
        "act",
        found.id,
        {
            "status": "approved",
            "approved": {
                "fingerprint": now,
                "covers": parts,
                "by": _pm(ctx),
                "at": ctx.store.clock(),
                "acknowledged": sorted(k for k in op.acknowledged if k in keys),
            },
            "failure": None,
            "why": [],
        },
        w,
        read_version=found.version,
    )
    return [{"kind": "act", "id": found.id}]


def _withdraw(tx: Tx, op: ActWithdrawOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _need(found, EDITABLE, "it can't be taken back")
    tx.update("act", found.id, {"status": "withdrawn", "approved": None}, w, read_version=found.version)
    return [{"kind": "act", "id": found.id}]


def _confirm_sent(tx: Tx, op: ActConfirmSentOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    channel = channel_of(ctx.store.plugins, found.data["channel"])
    by_hand = found.data["status"] == "approved" and channel is not None and channel.manual
    if found.data["status"] != "uncertain" and not by_hand:
        raise StoreError(f"it can't be marked sent: this act is {found.data['status']}")
    if by_hand:
        outward.check_outgoing(tx, ctx.cfg, part_labels(tx, ctx.cfg, found.data))
        if current_fingerprint(tx, ctx.store.plugins, found.data)[0] != found.data["approved"]["fingerprint"]:
            raise StoreError("this act changed since you approved it; approve it again")
    tx.update(
        "act",
        found.id,
        {"status": "sent", "sent_at": ctx.store.clock(), "sent_by": "person", "failure": None, "why": []},
        w,
        read_version=found.version,
    )
    return [{"kind": "act", "id": found.id}]


def _resend(tx: Tx, op: ActResendOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _need(found, ("uncertain",), "it can't be sent again")
    now, parts = current_fingerprint(tx, ctx.store.plugins, found.data)
    covered = found.data["approved"]
    if covered is None or now != covered["fingerprint"]:
        changed = what_changed(covered["covers"] if covered else {}, parts) or ["content"]
        tx.update("act", found.id, {"status": "stale", "approved": None, "why": changed}, w, read_version=found.version)
    else:
        tx.update("act", found.id, {"status": "approved", "why": []}, w, read_version=found.version)
    return [{"kind": "act", "id": found.id}]


def _attempt(found: Any, op: Any) -> None:
    if found.data["status"] != "sending" or found.data["attempt_key"] != op.attempt_key:
        raise StoreError("that attempt isn't the one waiting for an answer")


def _sending(tx: Tx, op: ActSendingOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _need(found, ("approved",), "it can't be sent")
    covered = found.data["approved"]
    now = current_fingerprint(tx, ctx.store.plugins, found.data)[0]
    if covered is None or not (covered["fingerprint"] == op.fingerprint == now):
        raise StoreError("what the yes covered is different now")
    tx.update(
        "act",
        found.id,
        {"status": "sending", "attempt_key": op.attempt_key, "attempt_at": op.at.isoformat()},
        w,
        read_version=found.version,
    )
    return [{"kind": "act", "id": found.id}]


def _sent(tx: Tx, op: ActSentOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _attempt(found, op)
    tx.update(
        "act",
        found.id,
        {"status": "sent", "service_id": op.service_id, "sent_at": op.at.isoformat(), "sent_by": "publisher"},
        w,
        read_version=found.version,
    )
    return [{"kind": "act", "id": found.id}]


def _failed(tx: Tx, op: ActFailedOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _attempt(found, op)
    failure = {"kind": op.kind, "reason": op.reason, "at": op.at.isoformat()}
    tx.update("act", found.id, {"status": "failed", "failure": failure}, w, read_version=found.version)
    return [{"kind": "act", "id": found.id}]


def _uncertain(tx: Tx, op: ActUncertainOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _need(found, ("sending",), "it can't be uncertain")
    tx.update("act", found.id, {"status": "uncertain", "why": [op.why]}, w, read_version=found.version)
    return [{"kind": "act", "id": found.id}]


def _stale(tx: Tx, op: ActStaleOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _need(found, ("approved",), "it can't go stale")
    tx.update(
        "act", found.id, {"status": "stale", "approved": None, "why": list(op.why)}, w, read_version=found.version
    )
    return [{"kind": "act", "id": found.id}]


def _reopen(tx: Tx, op: ActReopenOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _attempt(found, op)
    tx.update("act", found.id, {"status": "approved", "why": []}, w, read_version=found.version)
    return [{"kind": "act", "id": found.id}]


def _undo(tx: Tx, op: ActUndoOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _need(found, ("sent",), "it can't be taken back")
    data = found.data
    if data["sent_by"] != "publisher":
        raise StoreError("you carried this out yourself, so it can't be taken back from here")
    if not undoable(data):
        raise StoreError(f"it can't be taken back: a {what(data).replace('_', ' ')} can't be undone once it is out")
    channel = channel_of(ctx.store.plugins, data["channel"])
    if channel is None or channel.undo is None:
        raise StoreError("the channel that carried it out can't take it back")
    if data.get("undo_requested_at"):
        raise StoreError("taking it back was already asked for")
    tx.update(
        "act",
        found.id,
        {"undo_requested_at": ctx.store.clock(), "undo_failure": None},
        w,
        read_version=found.version,
    )
    return [{"kind": "act", "id": found.id}]


def _undone(tx: Tx, op: ActUndoneOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _need(found, ("sent",), "it can't be undone")
    tx.update(
        "act",
        found.id,
        {"status": "undone", "undone_at": op.at.isoformat(), "undo_requested_at": None},
        w,
        read_version=found.version,
    )
    return [{"kind": "act", "id": found.id}]


def _undo_failed(tx: Tx, op: ActUndoFailedOp, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    found = _get(tx, op.id)
    _need(found, ("sent",), "taking it back can't have failed")
    failure = {"kind": op.kind, "reason": op.reason, "at": op.at.isoformat()}
    tx.update("act", found.id, {"undo_failure": failure, "undo_requested_at": None}, w, read_version=found.version)
    return [{"kind": "act", "id": found.id}]


_APPLY: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "act.draft": _draft,
    "act.edit": _edit,
    "act.approve": _approve,
    "act.withdraw": _withdraw,
    "act.confirm_sent": _confirm_sent,
    "act.resend": _resend,
    "act.sending": _sending,
    "act.sent": _sent,
    "act.failed": _failed,
    "act.uncertain": _uncertain,
    "act.stale": _stale,
    "act.reopen": _reopen,
    "act.undo": _undo,
    "act.undone": _undone,
    "act.undo_failed": _undo_failed,
}


def apply(tx: Tx, op: OpModel, ctx: Any, w: WriteContext) -> list[dict[str, Any]]:
    """Apply one act op in the applier's transaction. Raises StoreError, which refuses that op alone."""
    return _APPLY[op.op](tx, op, ctx, w)


def undo_problem(tx: Tx, entries: list[dict[str, Any]]) -> str | None:
    """Why undoing these ledger entries is refused, or None. What the publisher wrote (an attempt, a result, a stale
    mark) is never undone: it records what happened outside the workspace. A draft can be undone only while it is
    still a draft, so a draft taken back never deletes an act that has moved on."""
    from engine.ops import ACT_PUBLISHER_OPS

    for e in entries:
        if e["kind"] != "act":
            continue
        name = e["op"].split("#", 1)[0]
        if name in ACT_PUBLISHER_OPS:
            return "what happened to an act outside the workspace can't be undone"
        if name == "act.undo":
            return "taking back what an act did outside the workspace can't be undone"
        if name == "act.draft":
            current = tx.get("act", e["record_id"], include_deleted=True)
            if current is not None and not current.deleted and current.data["status"] != "draft":
                return "an act that has moved on can't be taken away"
    return None
