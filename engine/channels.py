"""Channels: how an approved act is carried out (design 6.12).

A channel is registered by a plugin (`registrar.channel`) or shipped by the core. It is called only by the publisher,
and only for an act the person approved, whose fingerprint still matches. It declares what it can do: send, say what
happened to an attempt by its key, and undo. The core ships `copy`, whose send is the person's own (they copy the
approved text and mark it sent), and `FakeChannel`, which tests use to play every answer a service can give.

A channel never writes records and never sees anything but the act it is handed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class OutgoingRecipient:
    """One recipient of a message, with the address as the act resolved it now."""

    address: str
    role: Literal["to", "cc"] = "to"
    person: str | None = None  # the known person's id; None for an address no known person holds


@dataclass(frozen=True)
class OutgoingAct:
    """What a channel is handed to carry out: exactly what the person approved. `kind` is `message`, `calendar` or
    `file`; `parts` is the content by part name; `recipients` are those of a message, `calendar` and `when` those of an
    event and `folder` that of a file. `template` is the name and version of the template the content was rendered from,
    or None."""

    id: str
    kind: str
    parts: dict[str, str]
    recipients: tuple[OutgoingRecipient, ...] = ()
    calendar: str | None = None
    when: str | None = None
    folder: str | None = None
    template: tuple[str, str] | None = None


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
    send: Callable[[OutgoingAct, str], Any] | None
    status: Callable[[str], Any] | None = None
    undo: Callable[[str], Any] | None = None
    template_version: Callable[[str], str | None] | None = None
    #: True for a channel the person carries out themselves (`copy`): the publisher never calls it, and the act is
    #: sent only when the person says it was.
    manual: bool = False


#: The core's own channel: the person copies the approved text and marks it sent.
COPY = ChannelRegistration("copy", "Copy", ("message", "calendar", "file"), send=None, manual=True)


@dataclass
class FakeChannel:
    """A channel for tests, with no service behind it. `mode` is what `send` does: `succeed` (the act goes out and the
    answer is `ChannelSent`), `fail` (`ChannelFailed` with `failure`; nothing goes out), `timeout` (nothing goes out
    and the call raises `TimeoutError`) or `timeout_after_send` (it goes out, then the call raises `TimeoutError`).
    `answer` is what `status` says: `truth` (sent for a key that went out, not sent for any other), `unknown` (it can't
    say) or `no_status` for a channel that has no status capability at all. `templates` is the version each template
    has now. What went out is in `delivered`, one (act, attempt key) for each call that reached the service; `calls`
    is every call to `send` and `status_calls` the keys `status` was asked about."""

    mode: Literal["succeed", "fail", "timeout", "timeout_after_send"] = "succeed"
    failure: ChannelFailed = field(default_factory=lambda: ChannelFailed("outage", "The service was down."))
    answer: Literal["truth", "unknown", "no_status"] = "truth"
    templates: dict[str, str] = field(default_factory=dict)
    kinds: tuple[str, ...] = ("message", "calendar", "file")
    delivered: list[tuple[OutgoingAct, str]] = field(default_factory=list)
    calls: list[tuple[OutgoingAct, str]] = field(default_factory=list)
    status_calls: list[str] = field(default_factory=list)

    def _id_of(self, key: str) -> str:
        return f"fake-{key}"

    def send(self, act: OutgoingAct, attempt_key: str) -> Any:
        self.calls.append((act, attempt_key))
        if self.mode == "fail":
            return self.failure
        if self.mode == "timeout":
            raise TimeoutError("no answer")
        self.delivered.append((act, attempt_key))
        if self.mode == "timeout_after_send":
            raise TimeoutError("the answer was lost")
        return ChannelSent(self._id_of(attempt_key))

    def status(self, attempt_key: str) -> Any:
        self.status_calls.append(attempt_key)
        if self.answer == "unknown":
            return ChannelUnknown()
        if any(key == attempt_key for _, key in self.delivered):
            return ChannelSent(self._id_of(attempt_key))
        return ChannelNotSent()

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
            template_version=self.template_version,
        )
