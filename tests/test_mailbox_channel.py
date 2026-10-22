"""The core's `mailbox` channel: a plain mailbox acts through its own servers (design 6.12, S1b-2b). The outgoing and
the incoming servers are stand-ins that record every call; nothing reaches a network. Addresses are on example.com."""

from __future__ import annotations

import email
import email.policy
import imaplib
import smtplib
from datetime import UTC, datetime
from typing import Any

import pytest

from engine.channels import (
    ChannelFailed,
    ChannelNotSent,
    ChannelSent,
    ChannelUndone,
    ChannelUnknown,
    OutgoingAbout,
    OutgoingAct,
    OutgoingRecipient,
)
from engine.channels_mailbox import MailboxChannel, message_id
from engine.config.schema import WatchSource
from engine.connectors.mailbox import MailboxSettings, parse_folders
from tests.test_act_actions import ACCOUNT, BODY, MAILBOX, calendar_entry, draft_target, saved_message
from tests.test_calendar_mail import N
from tests.test_publisher import Env

NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)
ME = N["mail_user"]
THEM = "first.recipient@example.com"
ALSO = "second.recipient@example.com"
ORIGINAL = "<thread@example.com>"
LISTING = [
    b'(\\HasNoChildren) "/" "INBOX"',
    b'(\\HasNoChildren \\Sent) "/" "Sent Items"',
    b'(\\HasNoChildren \\Archive) "/" "Old Mail"',
    b'(\\HasNoChildren) "/" "Projects"',
]


# ---- the stand-in servers -------------------------------------------------------------------------------------------


class Outgoing:
    """What the outgoing server does, and what it was asked."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.connect_error: Exception | None = None
        self.login_error: Exception | None = None
        self.starttls_error: Exception | None = None
        self.mail_code = 250
        self.rcpt_codes: dict[str, int] = {}
        self.data_code = 250
        self.data_error: Exception | None = None
        self.kept_in: Mail | None = None  # a server that saves its own copy in this mailbox's sent folder
        self.delivered: list[bytes] = []

    def of(self, name: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == name]


def smtp_class(server: Outgoing, kind: str):
    class Connection:
        def __init__(self, host, port, timeout=None, context=None):
            if server.connect_error is not None:
                raise server.connect_error
            server.calls.append((kind, host, port, timeout))

        def ehlo(self):
            server.calls.append(("ehlo",))
            return 250, b"ok"

        def starttls(self, context=None):
            server.calls.append(("starttls",))
            if server.starttls_error is not None:
                raise server.starttls_error
            return 220, b"go"

        def login(self, user, password):
            server.calls.append(("login", user, password))
            if server.login_error is not None:
                raise server.login_error

        def mail(self, sender):
            server.calls.append(("mail", sender))
            return server.mail_code, b""

        def rcpt(self, address):
            server.calls.append(("rcpt", address))
            return server.rcpt_codes.get(address, 250), b""

        def data(self, raw):
            server.calls.append(("data",))
            if server.data_error is not None:
                raise server.data_error
            if 200 <= server.data_code < 300:
                server.delivered.append(raw)
                if server.kept_in is not None:
                    server.kept_in.folders["Sent Items"].append(Stored(raw=raw))
            return server.data_code, b""

        def quit(self):
            server.calls.append(("quit",))

    return Connection


class Stored:
    """One message in a folder of the stand-in mailbox."""

    count = 0

    def __init__(self, id: str | None = None, raw: bytes = b""):
        Stored.count += 1
        self.uid = Stored.count
        self.flags: set[str] = set()
        self.raw = raw
        self.id = id or str(email.message_from_bytes(raw)["Message-ID"])


class Mail:
    """The stand-in mailbox: folders of messages, what the server offers, and every command it was sent."""

    def __init__(self, capabilities=("IMAP4REV1", "MOVE", "UIDPLUS")):
        self.folders: dict[str, list[Stored]] = {"INBOX": [], "Sent Items": [], "Old Mail": [], "Projects": []}
        self.listing = LISTING
        self.capabilities = capabilities
        self.commands: list[tuple] = []
        self.logins = 0
        self.append_error: Exception | None = None

    def put(self, folder: str, id: str) -> Stored:
        found = Stored(id)
        self.folders[folder].append(found)
        return found

    def ids(self, folder: str) -> list[str]:
        return [m.id for m in self.folders[folder]]

    def of(self, name: str) -> list[tuple]:
        return [c for c in self.commands if c[0] == name]


def imap_class(mail: Mail):
    class Connection:
        def __init__(self, host, port, ssl_context=None, timeout=None):
            self.capabilities = mail.capabilities
            self.folder = ""

        def login(self, user, password):
            mail.logins += 1
            mail.commands.append(("login", user))

        def logout(self):
            mail.commands.append(("logout",))

        def list(self):
            return "OK", list(mail.listing)

        def select(self, folder, readonly=False):
            name = folder.strip('"')
            mail.commands.append(("select", name, readonly))
            if name not in mail.folders:
                return "NO", [b"no such folder"]
            self.folder = name
            return "OK", [b"1"]

        def append(self, folder, flags, when, raw):
            mail.commands.append(("append", folder.strip('"'), flags))
            if mail.append_error is not None:
                raise mail.append_error
            mail.folders[folder.strip('"')].append(Stored(raw=raw))
            return "OK", [b"done"]

        def uid(self, command, *args):
            mail.commands.append(("uid", command, *args))
            here = mail.folders[self.folder]
            if command == "SEARCH":
                wanted = args[-1].strip('"')
                return "OK", [" ".join(str(m.uid) for m in here if wanted in m.id).encode()]
            found = next(m for m in here if str(m.uid) == args[0])
            if command == "MOVE":
                return self.relocate(found, args[1].strip('"'), keep=False)
            if command == "COPY":
                return self.relocate(found, args[1].strip('"'), keep=True)
            if command == "STORE":
                flag = args[2].strip("()")
                (found.flags.add if args[1] == "+FLAGS" else found.flags.discard)(flag)
                return "OK", [b""]
            if command == "EXPUNGE":
                here[:] = [m for m in here if not (m is found and "\\Deleted" in m.flags)]
                return "OK", [b""]
            raise AssertionError(command)

        def relocate(self, found: Stored, to: str, *, keep: bool):
            if to not in mail.folders:
                return "NO", [b"TRYCREATE"]
            if not keep:
                mail.folders[self.folder].remove(found)
            copy = Stored(found.id)
            mail.folders[to].append(copy)
            return "OK", [b""]

    return Connection


@pytest.fixture
def servers(monkeypatch):
    monkeypatch.setenv("MAIL_PASSWORD", "app-password")
    outgoing, mail = Outgoing(), Mail()
    monkeypatch.setattr(smtplib, "SMTP_SSL", smtp_class(outgoing, "ssl"))
    monkeypatch.setattr(smtplib, "SMTP", smtp_class(outgoing, "plain"))
    monkeypatch.setattr(imaplib, "IMAP4_SSL", imap_class(mail))
    return outgoing, mail


def settings(**more: Any) -> MailboxSettings:
    return MailboxSettings(host="imap." + "example.com", user=ME, password="env:MAIL_PASSWORD", **more)


def channel(mailbox: MailboxSettings | None = None, **more: Any) -> MailboxChannel:
    found = mailbox or settings()
    return MailboxChannel(
        lambda account: found if account == ACCOUNT else None,
        lambda: [ACCOUNT],
        more.pop("saved_text", None),
        lambda: NOW,
    )


def message_act(action: str = "send", *, parts: dict | None = None, about: tuple = (), **more: Any) -> OutgoingAct:
    return OutgoingAct(
        id="act-1",
        kind="message",
        parts=parts or {"subject": "The proofs", "body": "The proofs ship on Monday."},
        recipients=more.pop("recipients", (OutgoingRecipient(THEM), OutgoingRecipient(ALSO, "cc"))),
        action=action,
        about=about,
        account=more.pop("account", ACCOUNT),
        **more,
    )


def mailbox_act(action: str, ids: tuple[str, ...] = (ORIGINAL,), **more: Any) -> OutgoingAct:
    return OutgoingAct(
        id="act-2",
        kind="mailbox",
        parts={},
        action=action,
        about=tuple(OutgoingAbout(id=f"source-{n}", service_id=i) for n, i in enumerate(ids)),
        account=ACCOUNT,
        **more,
    )


def sent_message(outgoing: Outgoing, n: int = 0) -> email.message.EmailMessage:
    return email.message_from_bytes(outgoing.delivered[n], policy=email.policy.default)  # type: ignore[return-value]


# ---- sending --------------------------------------------------------------------------------------------------------


def test_a_send_hands_the_exact_parts_and_recipients_with_a_message_id_made_from_the_key(servers):
    outgoing, mail = servers
    answer = channel().send(message_act(), "key-1")

    assert answer == ChannelSent(message_id("key-1", ME)) and answer.service_id == f"<key-1@{ME.split('@')[1]}>"
    assert [c[:3] for c in outgoing.of("ssl")] == [
        ("ssl", "smtp.example.com", 465)
    ]  # imap. made smtp., TLS from the start
    assert outgoing.of("login") == [("login", ME, "app-password")]
    assert outgoing.of("mail") == [("mail", ME)]
    assert [c[1] for c in outgoing.of("rcpt")] == [THEM, ALSO]
    sent = sent_message(outgoing)
    assert (sent["From"], sent["To"], sent["Cc"], sent["Subject"]) == (ME, THEM, ALSO, "The proofs")
    assert sent["Message-ID"] == answer.service_id
    assert sent.get_content().strip() == "The proofs ship on Monday."
    assert sent["In-Reply-To"] is None
    assert outgoing.of("quit") and outgoing.of("starttls") == []


def test_the_same_key_gives_the_same_message_id_and_another_key_another(servers):
    outgoing, _ = servers
    first = channel().send(message_act(), "key-1")
    again = channel().send(message_act(), "key-1")
    other = channel().send(message_act(), "key-2")
    assert first.service_id == again.service_id != other.service_id
    assert sent_message(outgoing, 0)["Message-ID"] == sent_message(outgoing, 1)["Message-ID"]


def test_the_outgoing_server_settings_have_defaults_from_the_incoming_host():
    assert settings().outgoing_host == "smtp.example.com" and settings().smtp_port == 465
    assert MailboxSettings(host=N["mail_host"], user=ME, password="env:X").outgoing_host == N["mail_host"]
    assert settings(smtp_host="out.example.com").outgoing_host == "out.example.com"
    assert settings().sender == ME
    assert MailboxSettings(host="h", user="not-an-address", password="env:X").sender == ""
    assert MailboxSettings(host="h", user="u", password="env:X", from_address=THEM).sender == THEM


def test_port_587_connects_and_then_makes_the_connection_secure(servers):
    outgoing, _ = servers
    assert isinstance(channel(settings(smtp_port=587)).send(message_act(), "key-1"), ChannelSent)
    names = [c[0] for c in outgoing.calls]
    assert names[:5] == ["plain", "ehlo", "starttls", "ehlo", "login"] and "ssl" not in names


def test_a_reply_carries_in_reply_to_and_references_from_the_originals_service_id(servers):
    outgoing, _ = servers
    about = (OutgoingAbout(id="source-1", service_id=ORIGINAL),)
    for action in ("reply", "reply_all"):
        channel().send(message_act(action, about=about), f"key-{action}")
    for n in (0, 1):
        sent = sent_message(outgoing, n)
        assert sent["In-Reply-To"] == ORIGINAL and sent["References"] == ORIGINAL


def test_a_forward_quotes_the_saved_text_as_plain_text_and_is_no_reply(servers):
    outgoing, _ = servers
    about = (OutgoingAbout(id="source-1", service_id=ORIGINAL),)
    saved = {"source-1": "From: ana\nSubject: Proofs\n\nThe proofs are late."}
    found = channel(saved_text=None)
    found.saved_text = lambda record: saved[record]
    found.send(message_act("forward", about=about), "key-1")
    sent = sent_message(outgoing)
    body = sent.get_content()
    assert "The proofs ship on Monday." in body and "> The proofs are late." in body and "> Subject: Proofs" in body
    assert sent["In-Reply-To"] is None


def test_a_copy_is_saved_in_the_sent_folder_the_server_marks_unless_the_server_keeps_its_own(servers):
    outgoing, mail = servers
    channel().send(message_act(), "key-1")
    assert [c[1] for c in mail.of("append")] == ["Sent Items"]  # the folder flagged as sent mail
    assert mail.ids("Sent Items") == [message_id("key-1", ME)]

    channel(settings(sent_folder="Projects")).send(message_act(), "key-2")
    assert mail.ids("Projects") == [message_id("key-2", ME)]  # the folder the setting names wins

    before = len(mail.of("append"))
    channel(settings(server_keeps_sent=True)).send(message_act(), "key-3")
    assert len(mail.of("append")) == before

    mail.listing = [b'(\\HasNoChildren) "/" "INBOX"']
    mail.folders["Sent"] = []
    channel().send(message_act(), "key-4")
    assert mail.ids("Sent") == [message_id("key-4", ME)]  # no mark and no setting: Sent


def test_a_copy_that_cannot_be_saved_does_not_change_the_answer(servers):
    _, mail = servers
    mail.append_error = imaplib.IMAP4.error("no room")
    assert isinstance(channel().send(message_act(), "key-1"), ChannelSent)


def test_a_message_with_nowhere_to_come_from_or_go_is_refused_before_any_connection(servers):
    outgoing, _ = servers
    no_address = MailboxSettings(host="h", user="not-an-address", password="env:MAIL_PASSWORD")
    for found, act in ((no_address, message_act()), (settings(), message_act(recipients=()))):
        answer = channel(found).send(act, "key-1")
        assert isinstance(answer, ChannelFailed) and answer.kind == "refused"
    gone = channel().send(message_act(account="mailbox:somewhere-else"), "key-1")
    assert isinstance(gone, ChannelFailed) and gone.kind == "refused"
    assert outgoing.calls == []


# ---- what the outgoing server says ----------------------------------------------------------------------------------


def test_a_refused_sign_in_is_auth_and_names_the_account(servers):
    outgoing, _ = servers
    for error in (
        smtplib.SMTPAuthenticationError(535, b"refused"),
        smtplib.SMTPResponseException(530, b"sign in first"),
    ):
        outgoing.login_error = error
        answer = channel().send(message_act(), "key-1")
        assert isinstance(answer, ChannelFailed) and answer.kind == "auth" and ME in answer.reason
    assert outgoing.of("mail") == [] and outgoing.delivered == []


def test_a_5xx_refusal_is_refused_naming_the_address_and_nothing_is_handed_over(servers):
    outgoing, _ = servers
    outgoing.rcpt_codes[ALSO] = 550
    answer = channel().send(message_act(), "key-1")
    assert isinstance(answer, ChannelFailed) and answer.kind == "refused" and ALSO in answer.reason
    assert outgoing.of("data") == [] and outgoing.delivered == []  # one recipient refused: none is sent to

    outgoing.rcpt_codes.clear()
    outgoing.mail_code = 553
    assert channel().send(message_act(), "key-2").kind == "refused"
    outgoing.mail_code = 250
    outgoing.data_code = 554
    assert channel().send(message_act(), "key-3").kind == "refused"


def test_a_try_later_is_an_outage_and_is_never_retried(servers):
    outgoing, _ = servers
    outgoing.rcpt_codes[THEM] = 451
    answer = channel().send(message_act(), "key-1")
    assert isinstance(answer, ChannelFailed) and answer.kind == "outage"
    assert len(outgoing.of("rcpt")) == 1 and outgoing.of("data") == []
    outgoing.rcpt_codes.clear()
    outgoing.data_code = 421
    assert channel().send(message_act(), "key-2").kind == "outage"
    assert len(outgoing.of("data")) == 1
    outgoing.login_error = smtplib.SMTPResponseException(454, b"later")
    assert channel().send(message_act(), "key-3").kind == "outage"


def test_a_server_that_cannot_be_reached_is_offline_and_one_that_hangs_up_before_data_is_an_outage(servers):
    outgoing, _ = servers
    outgoing.connect_error = ConnectionRefusedError("refused")
    assert channel().send(message_act(), "key-1") == ChannelFailed("offline", "couldn't reach the outgoing mail server")
    outgoing.connect_error = TimeoutError("slow")
    assert channel().send(message_act(), "key-2").kind == "offline"
    outgoing.connect_error = None
    outgoing.login_error = smtplib.SMTPServerDisconnected("gone")
    assert channel().send(message_act(), "key-3").kind == "outage"


def test_a_connection_lost_while_the_message_goes_over_is_no_clear_answer_and_saves_no_copy(servers):
    outgoing, mail = servers
    outgoing.data_error = smtplib.SMTPServerDisconnected("lost")
    assert channel().send(message_act(), "key-1") == ChannelUnknown()
    assert mail.of("append") == []


def test_a_server_that_does_not_offer_a_secure_connection_is_never_used_without_one(servers):
    outgoing, _ = servers
    outgoing.starttls_error = smtplib.SMTPNotSupportedError("no STARTTLS")
    answer = channel(settings(smtp_port=587)).send(message_act(), "key-1")
    assert isinstance(answer, ChannelFailed) and answer.kind == "refused"
    assert outgoing.of("login") == [] and outgoing.delivered == []


# ---- status ---------------------------------------------------------------------------------------------------------


def test_status_finds_the_message_id_in_the_sent_folder_and_otherwise_cannot_say(servers):
    _, mail = servers
    mail.put("Sent Items", message_id("key-1", ME))
    found = channel().status("key-1")
    assert found == ChannelSent(message_id("key-1", ME))
    for missing in (channel().status("key-9"), channel().status("key-")):
        assert missing == ChannelUnknown() and not isinstance(missing, ChannelNotSent)
    assert ("select", "Sent Items", True) in mail.of("select")  # read-only: nothing there changes


def test_status_looks_only_in_mailboxes_acting_is_on_for_and_a_failure_is_unknown(servers, monkeypatch):
    _, mail = servers
    nobody = MailboxChannel(lambda account: settings(), lambda: [], None, lambda: NOW)
    assert nobody.status("key-1") == ChannelUnknown() and mail.logins == 0

    class Refusing:
        def __init__(self, *args, **kwargs):
            pass

        def login(self, user, password):
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] no")

        def logout(self):
            pass

    monkeypatch.setattr(imaplib, "IMAP4_SSL", Refusing)
    assert channel().status("key-1") == ChannelUnknown()


# ---- mailbox acts ---------------------------------------------------------------------------------------------------


def uid_commands(mail: Mail, name: str) -> list[tuple]:
    return [c for c in mail.of("uid") if c[1] == name]


def test_archive_moves_the_message_found_by_its_message_id_to_the_archive_folder(servers):
    _, mail = servers
    found = mail.put("INBOX", ORIGINAL)
    mail.put("INBOX", "<other@example.com>")
    answer = channel().send(mailbox_act("archive"), "key-1")
    assert answer == ChannelSent(ORIGINAL)
    assert ("uid", "SEARCH", None, "HEADER", "Message-ID", f'"{ORIGINAL}"') in mail.of("uid")
    assert uid_commands(mail, "MOVE") == [("uid", "MOVE", str(found.uid), '"Old Mail"')]  # the server's own archive
    assert mail.ids("INBOX") == ["<other@example.com>"] and mail.ids("Old Mail") == [ORIGINAL]

    mail.put("INBOX", "<second@example.com>")
    channel(settings(archive_folder="Projects")).send(mailbox_act("archive", ("<second@example.com>",)), "key-2")
    assert mail.ids("Projects") == ["<second@example.com>"]  # the setting wins


def test_archive_with_no_archive_folder_is_refused_with_a_plain_reason(servers):
    _, mail = servers
    mail.listing = [b'(\\HasNoChildren) "/" "INBOX"']
    mail.put("INBOX", ORIGINAL)
    answer = channel().send(mailbox_act("archive"), "key-1")
    assert isinstance(answer, ChannelFailed) and answer.kind == "refused" and "archive folder" in answer.reason
    assert mail.ids("INBOX") == [ORIGINAL] and uid_commands(mail, "MOVE") == []


def test_move_label_and_mark_read_use_move_and_store_by_message_id(servers):
    _, mail = servers
    first, second = mail.put("INBOX", ORIGINAL), mail.put("INBOX", "<two@example.com>")
    assert isinstance(channel().send(mailbox_act("move", folder="Projects"), "key-1"), ChannelSent)
    assert uid_commands(mail, "MOVE")[0][3] == '"Projects"' and mail.ids("Projects") == [ORIGINAL]

    assert isinstance(
        channel().send(mailbox_act("label", ("<two@example.com>",), label="Needs review"), "key-2"), ChannelSent
    )
    assert uid_commands(mail, "STORE")[0][3:] == ("+FLAGS", "(Needs-review)")  # an IMAP keyword has no spaces
    assert second.flags == {"Needs-review"}

    channel().send(mailbox_act("mark_read", ("<two@example.com>",)), "key-3")
    assert uid_commands(mail, "STORE")[1][3:] == ("+FLAGS", "(\\Seen)") and first.flags == set()


def test_a_server_without_move_copies_then_flags_and_expunges_only_that_message(servers):
    _, mail = servers
    mail.capabilities = ("IMAP4REV1", "UIDPLUS")
    mail.put("INBOX", ORIGINAL)
    keep = mail.put("INBOX", "<keep@example.com>")
    keep.flags.add("\\Deleted")  # someone else's message already marked deleted must stay
    assert isinstance(channel().send(mailbox_act("archive"), "key-1"), ChannelSent)
    assert [c[1] for c in mail.of("uid") if c[1] in ("COPY", "STORE", "EXPUNGE")] == ["COPY", "STORE", "EXPUNGE"]
    assert mail.of("uid")[-1][1] == "EXPUNGE" and len(mail.of("uid")[-1]) == 3  # UID EXPUNGE <uid>, never a bare one
    assert mail.ids("INBOX") == ["<keep@example.com>"] and mail.ids("Old Mail") == [ORIGINAL]

    mail.capabilities = ("IMAP4REV1",)
    mail.put("INBOX", "<third@example.com>")
    answer = channel().send(mailbox_act("archive", ("<third@example.com>",)), "key-2")
    assert isinstance(answer, ChannelFailed) and answer.kind == "refused"
    assert "<third@example.com>" in mail.ids("INBOX")


def test_a_message_that_is_not_there_is_refused_and_nothing_changes(servers):
    _, mail = servers
    mail.put("INBOX", ORIGINAL)
    answer = channel().send(mailbox_act("archive", (ORIGINAL, "<gone@example.com>")), "key-1")
    assert isinstance(answer, ChannelFailed) and answer.kind == "refused" and "moved or deleted" in answer.reason
    assert mail.ids("INBOX") == [ORIGINAL] and uid_commands(mail, "MOVE") == []  # none moved: the check came first


def test_a_folder_that_does_not_exist_is_refused(servers):
    _, mail = servers
    mail.put("INBOX", ORIGINAL)
    answer = channel().send(mailbox_act("move", folder="Nowhere"), "key-1")
    assert isinstance(answer, ChannelFailed) and answer.kind == "refused"
    assert mail.ids("INBOX") == [ORIGINAL]


def test_a_mailbox_act_never_deletes_and_a_refused_sign_in_is_auth(servers, monkeypatch):
    _, mail = servers
    mail.put("INBOX", ORIGINAL)
    assert channel().send(mailbox_act("delete"), "key-1").kind == "refused"
    assert not [c for c in mail.of("uid") if "Deleted" in str(c)] and mail.ids("INBOX") == [ORIGINAL]

    class Refusing:
        def __init__(self, *args, **kwargs):
            pass

        def login(self, user, password):
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] wrong")

        def logout(self):
            pass

    monkeypatch.setattr(imaplib, "IMAP4_SSL", Refusing)
    answer = channel().send(mailbox_act("archive"), "key-2")
    assert isinstance(answer, ChannelFailed) and answer.kind == "auth" and ME in answer.reason


# ---- undo -----------------------------------------------------------------------------------------------------------


def test_undo_moves_a_message_back_to_its_folder_and_takes_the_label_and_the_read_mark_off(servers):
    _, mail = servers
    mail.put("INBOX", ORIGINAL)
    for action, extra in (("archive", {}), ("move", {"folder": "Projects"})):
        act = mailbox_act(action, **extra)
        assert isinstance(channel().send(act, "key-1"), ChannelSent) and mail.ids("INBOX") == []
        assert channel().undo(act, ORIGINAL) == ChannelUndone()
        assert mail.ids("INBOX") == [ORIGINAL]

    labelled = mailbox_act("label", label="Needs review")
    channel().send(labelled, "key-2")
    assert channel().undo(labelled, ORIGINAL) == ChannelUndone()
    assert mail.folders["INBOX"][0].flags == set() and uid_commands(mail, "STORE")[-1][3] == "-FLAGS"

    read = mailbox_act("mark_read")
    channel().send(read, "key-3")
    assert mail.folders["INBOX"][0].flags == {"\\Seen"}
    assert channel().undo(read, ORIGINAL) == ChannelUndone() and mail.folders["INBOX"][0].flags == set()


def test_undo_says_so_when_the_message_was_moved_again_and_never_takes_back_a_sent_message(servers):
    _, mail = servers
    mail.put("INBOX", ORIGINAL)
    act = mailbox_act("archive")
    channel().send(act, "key-1")
    mail.folders["Old Mail"].clear()  # the person moved it on in their mail program
    answer = channel().undo(act, ORIGINAL)
    assert isinstance(answer, ChannelFailed) and answer.kind == "refused"
    assert channel().undo(message_act(), "<x@example.com>").kind == "refused"


# ---- answering an invitation ----------------------------------------------------------------------------------------


def answer_act(answer: str = "accepted", **more: Any) -> OutgoingAct:
    return OutgoingAct(
        id="act-3",
        kind="calendar",
        parts=more.pop("parts", {}),
        recipients=(OutgoingRecipient("organizer@example.com"),),
        action="answer",
        about=(OutgoingAbout(id="event-1", service_id="uid-7", uid="uid-7", sequence=2),),
        account=ACCOUNT,
        answer=answer,
        title="Planning session",
        start="2030-03-10T09:00:00+00:00",
        **more,
    )


def test_an_answer_goes_as_mail_to_the_organizer_with_the_itip_reply_attached(servers):
    outgoing, mail = servers
    answer = channel().send(answer_act("tentative"), "key-1")
    assert isinstance(answer, ChannelSent) and answer.service_id == message_id("key-1", ME)
    sent = sent_message(outgoing)
    assert (sent["To"], sent["From"], sent["Subject"]) == ("organizer@example.com", ME, "Planning session")
    (reply,) = [p for p in sent.iter_attachments() if p.get_content_type() == "text/calendar"]
    assert reply.get_param("method") == "REPLY"
    text = reply.get_content()
    assert "METHOD:REPLY" in text and "UID:uid-7" in text and "SEQUENCE:2" in text
    assert "PARTSTAT=TENTATIVE" in text and ME in text and "organizer@example.com" in text
    assert mail.ids("Sent Items") == [message_id("key-1", ME)]  # kept like any sent message


def test_each_answer_has_its_own_status_and_a_new_time_cannot_be_proposed_by_mail(servers):
    outgoing, _ = servers
    for n, (said, state) in enumerate((("accepted", "ACCEPTED"), ("declined", "DECLINED"))):
        channel().send(answer_act(said), f"key-{n}")
        (reply,) = [p for p in sent_message(outgoing, n).iter_attachments()]
        assert f"PARTSTAT={state}" in reply.get_content()
    answer = channel().send(answer_act("propose"), "key-9")
    assert isinstance(answer, ChannelFailed) and answer.kind == "refused" and len(outgoing.delivered) == 2


# ---- the channel as the core registers it, through the publisher ----------------------------------------------------


@pytest.fixture
def env(tmp_path, demo, servers):
    e = Env(tmp_path, demo)
    e.cfg.watch.sources.append(
        WatchSource(
            id=MAILBOX,
            connector="mailbox",
            label="Work mail",
            settings={"host": "imap." + "example.com", "user": ME, "password": "env:MAIL_PASSWORD"},
        )
    )
    e.cfg.watch.acting.append(ACCOUNT)
    yield e
    e.close()


def ready_target(env: Env, target: dict, **more: Any) -> str:
    act_id = draft_target(env, target, **more)
    env.yes(act_id)
    return act_id


def test_the_core_registers_the_mailbox_channel_for_mailbox_accounts_with_its_actions():
    assert parse_folders(LISTING).archive == "Old Mail"
    from engine.channels_mailbox import for_workspace

    class Quiet:
        path = None

    registered = for_workspace(Quiet(), lambda: None).registration()
    assert (registered.name, registered.accounts, registered.manual) == ("mailbox", ("mailbox",), False)
    assert registered.actions["message"] == ("send", "reply", "reply_all", "forward")
    assert registered.actions["mailbox"] == ("archive", "move", "label", "mark_read")
    assert registered.actions["calendar"] == ("answer",) and registered.undo and registered.status


def test_an_approved_message_goes_out_through_the_publisher_and_is_sent_with_its_message_id(env, servers):
    outgoing, mail = servers
    act_id = env.ready(channel="mailbox", account=ACCOUNT)
    assert env.act(act_id)["channel"] == "mailbox"
    assert env.publisher.send(act_id).status == "sent"
    data = env.act(act_id)
    assert data["service_id"] == message_id("attempt-1", ME)
    sent = sent_message(outgoing)
    assert sent["To"] == env.address[env.ana] and sent["Subject"] == "The proofs"
    assert mail.ids("Sent Items") == [data["service_id"]]


def test_a_reply_through_the_publisher_is_handed_the_saved_messages_own_id(env, servers):
    outgoing, _ = servers
    original = saved_message(env, "thread")
    target = {"kind": "message", "action": "reply", "recipients": [{"person": env.ana, "kind": "email"}]}
    act_id = ready_target(env, target, parts=BODY, in_reply_to=original, channel="mailbox")
    assert env.publisher.send(act_id).status == "sent"
    assert sent_message(outgoing)["In-Reply-To"] == ORIGINAL


def test_a_lost_answer_is_settled_by_asking_the_sent_folder_and_never_sent_twice(env, servers, monkeypatch):
    outgoing, mail = servers
    outgoing.kept_in = mail  # the server saves its own copy
    outgoing.data_error = None
    act_id = env.ready(channel="mailbox", account=ACCOUNT)

    real = smtplib.SMTP_SSL

    class LostAnswer(real):
        def data(self, raw):
            super().data(raw)
            raise smtplib.SMTPServerDisconnected("the answer was lost")

    monkeypatch.setattr(smtplib, "SMTP_SSL", LostAnswer)
    assert env.publisher.send(act_id).status == "sending"
    monkeypatch.setattr(smtplib, "SMTP_SSL", real)
    assert env.act(act_id)["status"] == "sending" and len(outgoing.delivered) == 1

    env.new_publisher().resume()
    assert env.act(act_id)["status"] == "sent" and len(outgoing.delivered) == 1
    assert env.act(act_id)["service_id"] == message_id("attempt-1", ME)


def test_a_lost_answer_with_no_copy_to_find_is_uncertain_not_reopened(env, servers):
    outgoing, mail = servers
    act_id = env.ready(channel="mailbox", account=ACCOUNT)
    outgoing.data_error = smtplib.SMTPServerDisconnected("lost")
    assert env.publisher.send(act_id).status == "sending"
    env.new_publisher().resume()
    assert env.act(act_id)["status"] == "uncertain"  # never "approved again": the server may have sent it


def test_an_archive_goes_through_the_publisher_and_undo_puts_it_back(env, servers):
    _, mail = servers
    original = saved_message(env, "thread")
    mail.put("INBOX", ORIGINAL)
    act_id = ready_target(env, {"kind": "mailbox", "action": "archive", "about": [original]}, channel="mailbox")
    assert env.publisher.send(act_id).status == "sent" and mail.ids("Old Mail") == [ORIGINAL]
    env.person_op("act.undo", act_id)
    assert env.publisher.undo(act_id).status == "undone" and mail.ids("INBOX") == [ORIGINAL]


def test_an_invitation_answer_goes_through_the_publisher_as_mail(env, servers):
    outgoing, _ = servers
    entry = calendar_entry(env, "uid-9", source=saved_message(env, "invite"))
    act_id = ready_target(
        env, {"kind": "calendar", "action": "answer", "about": [entry], "answer": "accepted"}, channel="mailbox"
    )
    assert env.publisher.send(act_id).status == "sent"
    (reply,) = [p for p in sent_message(outgoing).iter_attachments()]
    assert "UID:uid-9" in reply.get_content() and "PARTSTAT=ACCEPTED" in reply.get_content()
