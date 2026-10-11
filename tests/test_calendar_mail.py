"""The calendar and mailbox connectors: events in a window from a calendar file, and new messages from a mail folder,
read without changing anything there."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml

from engine.connectors import ConnectorContext, ConnectorError
from engine.connectors.calendar import CalendarSettings, items, read_calendar
from engine.connectors.mailbox import MailboxSettings, message_item, read_mailbox

FIXTURES = Path(__file__).parent / "fixtures" / "network"
N = yaml.safe_load((FIXTURES / "network.yaml").read_text())
ICS = (FIXTURES / "calendar.ics").read_text()
MESSAGE = (FIXTURES / "message.eml").read_bytes()
NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)


def test_events_in_the_window_become_items_with_readable_text():
    found = {i.title: i for i in items(ICS, NOW, days_back=1, days_ahead=30)}
    assert set(found) == {"Floor plan review", "Print slot", "Weekly sync"}  # "Long ago" is outside the window
    review = found["Floor plan review"]
    assert "Where: Room 4, second floor" in review.text and "Organizer: " in review.text
    assert "We decide on the vendor list too." in review.text and "Not the event" not in review.text
    assert "(all day)" in found["Print slot"].text and "Repeats: FREQ=WEEKLY" in found["Weekly sync"].text


def test_events_say_when_and_where_for_the_agenda():
    from engine.connectors import Poll, checked_poll

    found = {i.title: i for i in items(ICS, NOW, days_back=1, days_ahead=30)}
    review = found["Floor plan review"].event
    assert review is not None and not review.all_day and review.where == "Room 4, second floor"
    assert datetime.fromisoformat(review.start).tzinfo is not None and review.end > review.start
    assert found["Print slot"].event.all_day and len(found["Print slot"].event.start) == 10
    assert found["Weekly sync"].event.repeats.startswith("FREQ=WEEKLY")
    checked_poll(Poll(list(found.values())))


def test_the_calendar_address_is_a_secret_and_read_through_the_web_client(tmp_path, monkeypatch):
    import engine.net

    url = f"https://{N['calendar_host']}/private/basic.ics"
    monkeypatch.setenv("CAL_ADDRESS", url)
    monkeypatch.setattr(
        engine.net,
        "TRANSPORT",
        httpx.MockTransport(lambda r: httpx.Response(200, text=ICS) if str(r.url) == url else httpx.Response(404)),
    )
    poll = read_calendar(CalendarSettings(address="env:CAL_ADDRESS", days_ahead=30), {}, ConnectorContext(tmp_path))
    assert poll.complete is False and "Weekly sync" in [i.title for i in poll.items]  # a repeating event is always on
    monkeypatch.delenv("CAL_ADDRESS")
    with pytest.raises(ConnectorError) as missing:
        read_calendar(CalendarSettings(address="env:CAL_ADDRESS"), {}, ConnectorContext(tmp_path))
    assert missing.value.kind == "auth"


def test_a_message_becomes_an_item_with_its_plain_text():
    item = message_item(MESSAGE)
    assert item.key == "<msg-1@mail.example.com>" and item.title == "Revised floor plan"
    assert item.text.startswith("From: ") and "send the vendor quotes by Friday" in item.text
    assert "<b>" not in item.text
    assert item.message is not None and item.message.sender == item.author
    assert datetime.fromisoformat(item.message.received) == datetime(2030, 3, 5, 9, 15, tzinfo=UTC)


class FakeImap:
    """A stand-in IMAP server holding three messages in INBOX, recording what was asked of it."""

    asked: list = []

    def __init__(self, host, port, ssl_context=None, timeout=None):
        self.messages = {
            7: MESSAGE,
            8: MESSAGE.replace(b"msg-1", b"msg-2"),
            9: MESSAGE.replace(b"msg-1", b"msg-3"),
        }

    def login(self, user, password):
        import imaplib

        if password != "app-password":
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    def select(self, folder, readonly=False):
        FakeImap.asked.append(("select", folder, readonly))
        return ("OK", [b"3"]) if folder == '"INBOX"' else ("NO", [b""])

    def response(self, name):
        return name, [b"42"]

    def uid(self, command, *args):
        FakeImap.asked.append((command, *args))
        if command == "SEARCH":
            low = int(args[1].split()[1].split(":")[0]) if args[1].startswith("UID") else 1
            return "OK", [b" ".join(str(u).encode() for u in self.messages if u >= low)]
        return "OK", [(b"1 (BODY[] {10}", self.messages[int(args[0])]), b")"]

    def logout(self):
        pass


def test_new_messages_are_read_without_marking_them(tmp_path, monkeypatch):
    import imaplib

    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeImap)
    monkeypatch.setenv("MAIL_PASSWORD", "app-password")
    settings = MailboxSettings(host=N["mail_host"], user=N["mail_user"], password="env:MAIL_PASSWORD", first_read=2)
    first = read_mailbox(settings, {}, ConnectorContext(tmp_path))
    assert [i.key for i in first.items] == ["<msg-2@mail.example.com>", "<msg-3@mail.example.com>"]
    assert first.state == {"validity": "42", "last_uid": 9} and first.complete is False
    assert ("select", '"INBOX"', True) in FakeImap.asked
    assert all("PEEK" in a[2] for a in FakeImap.asked if a[0] == "FETCH")
    again = read_mailbox(settings, first.state, ConnectorContext(tmp_path))
    assert again.items == []


def test_a_refused_password_and_a_missing_folder_are_classified(tmp_path, monkeypatch):
    import imaplib

    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeImap)
    monkeypatch.setenv("MAIL_PASSWORD", "wrong")
    settings = MailboxSettings(host=N["mail_host"], user=N["mail_user"], password="env:MAIL_PASSWORD")
    with pytest.raises(ConnectorError) as refused:
        read_mailbox(settings, {}, ConnectorContext(tmp_path))
    assert refused.value.kind == "auth"
    monkeypatch.setenv("MAIL_PASSWORD", "app-password")
    with pytest.raises(ConnectorError) as missing:
        read_mailbox(settings.model_copy(update={"folder": "Projects"}), {}, ConnectorContext(tmp_path))
    assert missing.value.kind == "not_found"
