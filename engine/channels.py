"""Channels: how an approved act is carried out (design 6.12).

A channel is registered by a plugin (`registrar.channel`) or shipped by the core. It is called only by the publisher,
and only for an act the person approved, whose fingerprint still matches. It declares what it can do: send, say what
happened to an attempt by its key, and undo; which actions it takes for each kind of target; and which kinds of
account it serves. The core ships `copy`, whose send is the person's own (they copy the
approved text and mark it sent), and `FakeChannel`, which tests use to play every answer a service can give.

A channel never writes records and never sees anything but the act it is handed.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from engine.ops import ACT_ACTIONS


@dataclass(frozen=True)
class OutgoingRecipient:
    """One recipient of a message, with the address as the act resolved it now."""

    address: str
    role: Literal["to", "cc"] = "to"
    person: str | None = None  # the known person's id; None for an address no known person holds


@dataclass(frozen=True)
class OutgoingAbout:
    """One record an act is about, with the service's own id of it as it resolves now: `id` is the record's id in the
    workspace; `service_id` is what the service calls the saved message or calendar entry; `uid` and `sequence` are a
    calendar entry's, where the source gave them."""

    id: str
    service_id: str | None = None
    uid: str | None = None
    sequence: int | None = None


@dataclass(frozen=True)
class OutgoingAct:
    """What a channel is handed to carry out: exactly what the person approved. `kind` is `message`, `mailbox`,
    `calendar` or `file`, and `action` what it does (`send`, `reply`, `archive`, `answer` and so on). `parts` is the
    content by part name; `recipients` are those of a message (for an answer to an invitation, the organizer);
    `about` is what a mailbox act or an event act is about; `account` is the account that carries it. For an event,
    `calendar`, `when`, `start`, `end`, `title`, `alarm_minutes`; for an answer, `answer` (`accepted`, `tentative`,
    `declined` or `propose`) and the proposed times; `folder` is a file's folder or the one a mailbox act moves messages
    to, and `label` the label it applies. `template` is the name and version of the template the content was rendered
    from, or None."""

    id: str
    kind: str
    parts: dict[str, str]
    recipients: tuple[OutgoingRecipient, ...] = ()
    calendar: str | None = None
    when: str | None = None
    folder: str | None = None
    template: tuple[str, str] | None = None
    action: str = ""
    about: tuple[OutgoingAbout, ...] = ()
    account: str | None = None
    label: str | None = None
    start: str | None = None
    end: str | None = None
    title: str | None = None
    alarm_minutes: int | None = None
    answer: str | None = None
    proposed_start: str | None = None
    proposed_end: str | None = None


@dataclass(frozen=True)
class ChannelContext:
    """What a channel's `send`, `status` and `undo` get besides the act: built for each call by the publisher for the
    act's own account, and reaching nothing else. `web` is a client limited to the hosts the plugin declares in
    `requires.network` (None when it declares none); `access_token()` is a current token of the act's account when it
    is a sign-in's account (renewed by the core; it raises `ConnectorError` of kind `auth` or `no_access`, which the
    channel answers as `ChannelFailed`), and None for a plain mailbox or an act with no account; `account` is the act's
    account id; `granted` the scopes that account's sign-in holds (empty when it has none); `log` a logger for the
    channel. A channel never reaches another plugin's sign-in or another account."""

    web: Any = None  # engine.net.WebClient, or None when the channel may not reach the network
    access_token: Callable[[], str | None] = field(default=lambda: None)
    account: str | None = None
    granted: frozenset[str] = frozenset()
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("engine.channels"))


def accepts_context(fn: Callable[..., Any], plain: int) -> bool:
    """Whether a channel function takes a context after its `plain` leading arguments. A function written for the
    earlier signatures (no context) is still called without one; a function with a further positional parameter, a
    `context` parameter or `*args` gets it."""
    try:
        params = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return False
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL or p.name == "context" for p in params):
        return True
    kinds = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    positional = [p for p in params if p.kind in kinds]
    return len(positional) > plain


def call_channel(fn: Callable[..., Any], args: tuple[Any, ...], context: ChannelContext) -> Any:
    """Call a channel function with its arguments, and the context when it takes one."""
    return fn(*args, context) if accepts_context(fn, len(args)) else fn(*args)


@dataclass(frozen=True)
class ChannelSent:
    """The channel's answer when the act went out: the id the service gave it (kept on the act and used to find it
    again)."""

    service_id: str


@dataclass(frozen=True)
class ChannelFailed:
    """The channel's answer when it is sure the act did not go out: `kind` is one of `auth`, `refused`, `outage` or
    `offline`, and `reason` says why in plain words for the person (for `auth`, which account to sign in to again)."""

    kind: Literal["auth", "refused", "outage", "offline"]
    reason: str


@dataclass(frozen=True)
class ChannelUndone:
    """The answer to `undo` when the service took the act back."""


@dataclass(frozen=True)
class ChannelNotSent:
    """A status answer: the service has nothing for that attempt key, so it never went out."""


@dataclass(frozen=True)
class ChannelUnknown:
    """The channel can't say what happened: a send that got no clear answer, or a status it can't read."""


@dataclass(frozen=True)
class ChannelRegistration:
    """A registered channel (host side): its name, label, the kinds of target it takes and what it can do."""

    name: str
    label: str
    kinds: tuple[str, ...]
    #: `send(act, attempt_key, context)`, `status(attempt_key, context)` and `undo(act, service_id, context)` with a
    #: `ChannelContext`; the earlier signatures without the context still work.
    send: Callable[..., Any] | None
    status: Callable[..., Any] | None = None
    undo: Callable[..., Any] | None = None
    template_version: Callable[[str], str | None] | None = None
    #: What it does, by kind of target: `{"message": ["send", "reply"], "mailbox": ["archive"]}`. Empty means it takes
    #: the first action of each of its kinds only.
    actions: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: The kinds of account it serves (a sign-in's name, or `mailbox`); empty means it needs no account.
    accounts: tuple[str, ...] = ()
    #: True for a channel the person carries out themselves (`copy`): the publisher never calls it, and the act is
    #: sent only when the person says it was.
    manual: bool = False

    def takes(self, kind: str, action: str) -> bool:
        """Whether the channel declares this action for this kind of target. A channel that lists none takes the first
        action of each kind it serves."""
        if kind not in self.kinds:
            return False
        declared = self.actions.get(kind)
        return action in declared if declared else action == ACT_ACTIONS[kind][0]


#: The core's own channel: the person copies the approved text and marks it sent.
COPY = ChannelRegistration("copy", "Copy", ("message", "mailbox", "calendar", "file"), send=None, manual=True)


@dataclass
class FakeChannel:
    """A channel for tests, with no service behind it. `mode` is what `send` does: `succeed` (the act goes out and the
    answer is `ChannelSent`), `fail` (`ChannelFailed` with `failure`; nothing goes out), `timeout` (nothing goes out
    and the call raises `TimeoutError`) or `timeout_after_send` (it goes out, then the call raises `TimeoutError`).
    `undo_mode` is what `undo` does (a mailbox act or a created event taken back) and `undoes` False is a channel
    that declares no undo. It declares every action of every kind in `kinds`. `answer` is what `status` says: `truth`
    (sent for a key that went out, not sent for any other), `unknown` (it can't say) or `no_status` for a channel that
    has no status capability at all. `templates` is the version each template has now. What went out is in
    `delivered`, one (act, attempt key) for each call that reached the service; `calls` is every call to `send` and
    `status_calls` the keys `status` was asked about; `contexts` is the context each call to `send`, `status` and `undo`
    got, in order."""

    mode: Literal["succeed", "fail", "timeout", "timeout_after_send"] = "succeed"
    failure: ChannelFailed = field(default_factory=lambda: ChannelFailed("outage", "The service was down."))
    answer: Literal["truth", "unknown", "no_status"] = "truth"
    templates: dict[str, str] = field(default_factory=dict)
    kinds: tuple[str, ...] = ("message", "mailbox", "calendar", "file")
    accounts: tuple[str, ...] = ()
    undoes: bool = True
    undo_mode: Literal["succeed", "fail", "timeout"] = "succeed"
    undone: list[tuple[OutgoingAct, str]] = field(default_factory=list)
    delivered: list[tuple[OutgoingAct, str]] = field(default_factory=list)
    calls: list[tuple[OutgoingAct, str]] = field(default_factory=list)
    status_calls: list[str] = field(default_factory=list)
    contexts: list[ChannelContext | None] = field(default_factory=list)

    def _id_of(self, key: str) -> str:
        return f"fake-{key}"

    def send(self, act: OutgoingAct, attempt_key: str, context: ChannelContext | None = None) -> Any:
        self.contexts.append(context)
        self.calls.append((act, attempt_key))
        if self.mode == "fail":
            return self.failure
        if self.mode == "timeout":
            raise TimeoutError("no answer")
        self.delivered.append((act, attempt_key))
        if self.mode == "timeout_after_send":
            raise TimeoutError("the answer was lost")
        return ChannelSent(self._id_of(attempt_key))

    def status(self, attempt_key: str, context: ChannelContext | None = None) -> Any:
        self.contexts.append(context)
        self.status_calls.append(attempt_key)
        if self.answer == "unknown":
            return ChannelUnknown()
        if any(key == attempt_key for _, key in self.delivered):
            return ChannelSent(self._id_of(attempt_key))
        return ChannelNotSent()

    def undo(self, act: OutgoingAct, service_id: str, context: ChannelContext | None = None) -> Any:
        """Takes a sent act back: `undo_mode` says whether it works (`ChannelUndone`), is refused (`ChannelFailed`) or
        gets no answer (raises `TimeoutError`). Every call is in `undone`."""
        self.contexts.append(context)
        self.undone.append((act, service_id))
        if self.undo_mode == "fail":
            return self.failure
        if self.undo_mode == "timeout":
            raise TimeoutError("no answer")
        return ChannelUndone()

    def template_version(self, name: str) -> str | None:
        return self.templates.get(name)

    def registration(self, name: str = "fake") -> ChannelRegistration:
        """This channel as the publisher registers it, with `status` left out when `answer` is `no_status`."""
        return ChannelRegistration(
            name,
            "Fake",
            self.kinds,
            send=self.send,
            status=None if self.answer == "no_status" else self.status,
            undo=self.undo if self.undoes else None,
            template_version=self.template_version,
            actions={kind: tuple(ACT_ACTIONS[kind]) for kind in self.kinds},
            accounts=self.accounts,
        )
