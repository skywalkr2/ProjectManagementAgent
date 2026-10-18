from datetime import UTC, datetime, timedelta, timezone
from email.headerregistry import Address
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import SMTP
from email.utils import parsedate_to_datetime

import pytest

from engine.reminder_mail import Unknown, reminder_message


def build(**changes):
    values = {
        "to": "Mira Fen <mira@example.com>",
        "sender": "Rowan Vale <rowan@example.com>",
        "subject": "Your reminder",
        "body": "Review the draft before noon.",
        "date": datetime(2027, 1, 5, 10, tzinfo=UTC),
        "message_domain": "example.com",
        "message_id_token": "fictional-001",
    }
    values.update(changes)
    return reminder_message(**values)


def test_required_headers():
    message = build()
    assert isinstance(message, EmailMessage)
    assert message["Auto-Submitted"] == "auto-generated"
    assert message["Message-ID"] == "<fictional-001@example.com>"
    assert parsedate_to_datetime(message["Date"]) == datetime(2027, 1, 5, 10, tzinfo=UTC)
    assert message["From"].addresses[0].addr_spec == "rowan@example.com"
    assert message["To"].addresses[0].addr_spec == "mira@example.com"


def test_plain_text_without_attachment():
    message = build()
    assert message.get_content_type() == "text/plain"
    assert not message.is_multipart()
    assert message.get_content().strip() == "Review the draft before noon."


def test_distinct_caller_tokens_give_distinct_ids():
    assert (
        build(message_id_token="fictional-001")["Message-ID"] != build(message_id_token="fictional-002")["Message-ID"]
    )


def test_same_inputs_preserve_id():
    assert build()["Message-ID"] == build()["Message-ID"]


def test_missing_token_unknown():
    result = build(message_id_token=None)
    assert isinstance(result, Unknown) and "unique" in result.reason


@pytest.mark.parametrize("token", ["", "a@b", "a b", "a\nb", ".start", "end.", "a..b", "x" * 201])
def test_invalid_id_tokens(token):
    assert isinstance(build(message_id_token=token), Unknown)


@pytest.mark.parametrize(
    "domain",
    [
        "",
        "example.com/path",
        "example.com:443",
        "a..example.com",
        "-bad.example.com",
        "example.com\r\nBcc: oren@example.com",
        "example.com.",
        " example.com",
    ],
)
def test_invalid_domains(domain):
    assert isinstance(build(message_domain=domain), Unknown)


def test_case_normalization():
    assert build(message_domain="EXAMPLE.COM")["Message-ID"] == "<fictional-001@example.com>"


def test_unicode_content_roundtrip():
    message = build(subject="Réunion — draft", body="Hello Mira,\nHere’s the café draft.\nRowan")
    parsed = BytesParser(policy=SMTP).parsebytes(message.as_bytes())
    assert str(parsed["Subject"]) == "Réunion — draft"
    assert "café" in parsed.get_content()
    assert not parsed.defects


@pytest.mark.parametrize(
    "attachment",
    ["BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n", b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"],
)
def test_calendar_attachment(attachment):
    message = build(ics=attachment)
    parsed = BytesParser(policy=SMTP).parsebytes(message.as_bytes())
    assert parsed.get_content_type() == "multipart/mixed"
    assert parsed.get_body(preferencelist=("plain",)).get_content().strip() == "Review the draft before noon."
    attachments = list(parsed.iter_attachments())
    assert len(attachments) == 1
    item = attachments[0]
    assert item.get_content_type() == "text/calendar"
    assert item.get_content_disposition() == "attachment"
    assert item.get_filename() == "reminder.ics"
    expected = attachment.encode("utf-8") if isinstance(attachment, str) else attachment
    assert item.get_payload(decode=True) == expected


def test_unicode_calendar_attachment_preserved():
    data = "BEGIN:VCALENDAR\r\nSUMMARY:Café review\r\nEND:VCALENDAR\r\n"
    attachment = next(build(ics=data).iter_attachments())
    assert attachment.get_payload(decode=True) == data.encode("utf-8")


def test_non_utc_date_preserved():
    value = datetime(2027, 1, 5, 10, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert parsedate_to_datetime(build(date=value)["Date"]) == value
    assert str(build(date=value)["Date"]).endswith("+0530")


def test_naive_date_unknown():
    value = datetime(2027, 1, 5, 10)  # noqa: DTZ001 -- Verify rejection of a floating Date header.
    assert isinstance(build(date=value), Unknown)


@pytest.mark.parametrize("field", ["to", "sender", "subject"])
def test_header_injection(field):
    assert isinstance(build(**{field: "Mira\r\nBcc: oren@example.com"}), Unknown)


def test_multiple_recipients():
    message = build(to=[Address("Mira", "mira", "example.com"), "oren@example.com"])
    assert [item.addr_spec for item in message["To"].addresses] == ["mira@example.com", "oren@example.com"]


def test_comma_separated_recipients():
    assert len(build(to="mira@example.com, oren@example.com")["To"].addresses) == 2


@pytest.mark.parametrize("address", ["", "Mira", "mira@", "group: mira@example.com;", "mira@example.com garbage"])
def test_bad_recipient(address):
    assert isinstance(build(to=address), Unknown)


def test_multiple_senders_rejected():
    assert isinstance(build(sender="rowan@example.com, mira@example.com"), Unknown)


@pytest.mark.parametrize("attachment", ["", b"", 123])
def test_bad_attachment(attachment):
    assert isinstance(build(ics=attachment), Unknown)


def test_body_is_not_header_data():
    message = build(body="Bcc: oren@example.com\nNot a header.")
    assert message["Bcc"] is None
    assert "Bcc: oren@example.com" in message.get_content()


def test_messages_are_independent():
    first = build()
    first["X-Note"] = "Fictional"
    assert build()["X-Note"] is None


def test_serialization_is_deterministic_with_attachment():
    content = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
    assert build(ics=content).as_bytes() == build(ics=content).as_bytes()


def test_bad_calendar_encoding_unknown():
    assert isinstance(build(ics=b"\xff"), Unknown)


def test_subject_control_unknown():
    assert isinstance(build(subject="Reminder\x00hidden"), Unknown)


def test_the_reminder_reads_back_as_generated_mail_not_a_message_to_act_on():
    from engine.automatic_mail import classify_automatic

    message = build()
    assert classify_automatic(message, str(message["Subject"]), message.get_content_type()).kind == "generated"
