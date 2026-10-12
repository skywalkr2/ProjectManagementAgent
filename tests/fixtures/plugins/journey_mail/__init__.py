"""A fictional mail and calendar add-on for the journey tests. It signs in to a made-up service through that service's
own sign-in page, and its two connectors read a small JSON API over HTTPS: the messages in the inbox and the events on
the main calendar. It changes nothing there. The service's address comes from the environment of the process that runs
the app, so the same files serve any port.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from engine.plugin_api import ConnectorError, EventDetails, MessageDetails, Poll, Settings, SourceItem

SERVICE = os.environ.get("JOURNEY_SERVICE_ADDRESS", "https://127.0.0.1:1").rstrip("/")
SIGN_IN = "journey-mail/account"
#: The app registration this add-on ships, as the made-up service knows it.
DEFAULT_CLIENT_ID = "journey-mail-app"


class Config(Settings):
    pass


class InboxSettings(BaseModel):
    folder: str = Field("inbox", description="Which folder of the mailbox to read.")


class CalendarSettings(BaseModel):
    calendar: str = Field("main", description="Which calendar to read.")


def _get(context, path: str, params: dict[str, str] | None = None) -> dict:
    token = context.access_token(SIGN_IN)
    response = context.web.get(f"{SERVICE}{path}", params=params or {}, headers={"Authorization": f"Bearer {token}"})
    try:
        body = response.json()
    except ValueError:
        raise ConnectorError("outage", "the service's answer couldn't be read") from None
    if not isinstance(body, dict):
        raise ConnectorError("outage", "the service's answer wasn't what was expected")
    return body


def poll_inbox(settings: InboxSettings, state: dict, context) -> Poll:
    items = []
    for message in _get(context, "/mail/v1/messages", {"folder": settings.folder}).get("messages", []):
        sender = message["from"]
        who = f"{sender['name']} <{sender['address']}>"
        text = f"From: {who}\nReceived: {message['received']}\n\n{message['body']}"
        items.append(
            SourceItem(
                key=message["id"],
                title=message["subject"],
                text=text,
                author=sender["name"],
                changed_at=message["received"],
                message=MessageDetails(
                    sender=who,
                    received=message["received"],
                    unread=message["unread"],
                    bulk=message.get("bulk"),
                    categories=tuple(message.get("categories", ())),
                ),
            )
        )
    return Poll(items, {})


def poll_calendar(settings: CalendarSettings, state: dict, context) -> Poll:
    items = []
    for event in _get(context, "/calendar/v1/events", {"calendar": settings.calendar}).get("events", []):
        text = (
            f"{event['title']}\nWhen: {event['start']} to {event['end']}\nWhere: {event['where']}\n\n{event['notes']}"
        )
        items.append(
            SourceItem(
                key=event["id"],
                title=event["title"],
                text=text,
                author=event.get("organizer"),
                changed_at=event["start"],
                event=EventDetails(
                    start=event["start"], end=event["end"], where=event["where"], cancelled=event["cancelled"]
                ),
            )
        )
    return Poll(items, {})


def account(context) -> str:
    return str(_get(context, "/account/v1/me")["email"])


def register(registrar) -> None:
    registrar.connector(
        "journey-mail/mail", label="Example mail", settings=InboxSettings, poll=poll_inbox, reads="mail"
    )
    registrar.connector(
        "journey-mail/calendar",
        label="Example calendar",
        settings=CalendarSettings,
        poll=poll_calendar,
        reads="calendar",
    )
    registrar.sign_in(
        SIGN_IN,
        label="Example mail",
        authorize_url=f"{SERVICE}/account/authorize",
        token_url=f"{SERVICE}/account/token",
        revoke_url=f"{SERVICE}/account/revoke",
        scopes=["mail.read", "calendar.read", "offline"],
        allows=["Read your mail", "Read your calendar"],
        account=account,
        default_client_id=DEFAULT_CLIENT_ID,
        default_redirects=["http://127.0.0.1/api/sign-ins/callback"],
        sources=[
            {"connector": "journey-mail/mail", "label": "Your inbox", "settings": {}, "every_minutes": 15},
            {"connector": "journey-mail/calendar", "label": "Your calendar", "settings": {}, "every_minutes": 15},
        ],
    )
