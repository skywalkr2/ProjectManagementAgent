"""A mailbox's sent folder is offered as a second source (design 6.33): the folders come from the server's own list, the
one it marks as sent is the suggestion, and adding it is a new source of the same mailbox with the person as its author,
taken in quietly like any new source. Nothing here reaches a network: the server is a stand-in."""

import imaplib

import pytest

from engine.connectors import ConnectorContext, ConnectorError
from engine.connectors.mailbox import MailboxSettings, list_folders, parse_folders, read_mailbox
from tests.test_calendar_mail import N
from tests.test_setup import client, make
from tests.test_typed_secrets import sources

LISTING = [
    b'(\\HasNoChildren) "/" "INBOX"',
    b'(\\HasNoChildren \\Sent) "/" "Sent Items"',
    b'(\\HasNoChildren \\Drafts) "/" Drafts',
    b'(\\Noselect \\HasChildren) "/" "[Archive]"',
    b'(\\HasNoChildren) "/" "Team \\"A\\""',
    b"garbage",
]


def stand_in(monkeypatch, listing=LISTING, *, refuse: bytes | None = None):
    class Server:
        def __init__(self, host, port, ssl_context=None, timeout=None):
            pass

        def login(self, user, password):
            if refuse:
                raise imaplib.IMAP4.error(refuse)

        def list(self):
            return "OK", list(listing)

        def logout(self):
            pass

    monkeypatch.setattr(imaplib, "IMAP4_SSL", Server)
    monkeypatch.setenv("MAIL_PASSWORD", "unused")


def test_the_servers_list_gives_the_selectable_folders_and_the_one_it_marks_as_sent():
    found = parse_folders(LISTING)
    assert found.names == ("INBOX", "Sent Items", "Drafts", 'Team "A"')  # not the unselectable one, not the garbage
    assert found.sent == "Sent Items"
    assert parse_folders([b'(\\HasNoChildren) "/" "Sent"']).sent is None  # no mark, so the person picks


def test_listing_the_folders_changes_nothing_and_a_refusal_is_the_usual_one(monkeypatch):
    settings = MailboxSettings(host=N["mail_host"], user=N["mail_user"], password="env:MAIL_PASSWORD")
    stand_in(monkeypatch)
    assert list_folders(settings).sent == "Sent Items"
    stand_in(monkeypatch, refuse=b"[AUTHENTICATIONFAILED] no")
    with pytest.raises(ConnectorError) as refused:
        list_folders(settings)
    assert refused.value.kind == "auth"
    with pytest.raises(ConnectorError) as same:
        read_mailbox(settings, {}, ConnectorContext(None))
    assert same.value.kind == "auth"  # reading goes through the same sign-in as listing


def add_mailbox(c, api):
    fingerprint = c.get(f"{api}/settings").json()["fingerprint"]
    added = c.post(
        f"{api}/watch/sources",
        json={
            "connector": "mailbox",
            "label": "Work mail",
            "settings": {"host": N["mail_host"], "user": N["mail_user"], "password": "env:MAIL_PASSWORD"},
            "fingerprint": fingerprint,
        },
    )
    assert added.status_code == 200, added.text
    return added.json()["fingerprint"]


def test_a_mailbox_source_offers_its_folders_with_the_sent_one_marked_and_what_is_already_read(tmp_path, monkeypatch):
    stand_in(monkeypatch)
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    add_mailbox(c, api)
    got = c.get(f"{api}/watch/work-mail/folders")
    assert got.status_code == 200, got.text
    assert got.json() == {
        "folders": ["INBOX", "Sent Items", "Drafts", 'Team "A"'],
        "sent": "Sent Items",
        "taken": ["INBOX"],
    }
    assert c.get(f"{api}/watch/nope/folders").status_code == 404
    assert c.get(f"{api}/watch/{sources(ws)[0].id}/folders").status_code in (
        200,
        409,
    )  # a demo source may not be a mailbox


def test_adding_the_sent_folder_makes_a_source_of_the_same_mailbox_credited_to_the_person(tmp_path, monkeypatch):
    stand_in(monkeypatch)
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fingerprint = add_mailbox(c, api)
    added = c.post(
        f"{api}/watch/work-mail/sent-folder",
        json={"folder": "Sent Items", "label": "Work mail, sent", "fingerprint": fingerprint},
    )
    assert added.status_code == 200, added.text
    mine = next(s for s in sources(ws) if s.label == "Work mail, sent")
    assert mine.connector == "mailbox" and mine.settings["folder"] == "Sent Items"
    assert (mine.settings["host"], mine.settings["user"]) == (N["mail_host"], N["mail_user"])
    assert mine.settings["password"] == "env:MAIL_PASSWORD" and mine.author == cfg.workspace.user.person
    # Once it is read, the offer is over: that folder is taken.
    assert "Sent Items" in c.get(f"{api}/watch/work-mail/folders").json()["taken"]
    again = c.post(
        f"{api}/watch/work-mail/sent-folder",
        json={"folder": "Sent Items", "label": "Again", "fingerprint": added.json()["fingerprint"]},
    )
    assert again.status_code == 400


def test_a_folder_the_server_doesnt_list_is_refused(tmp_path, monkeypatch):
    stand_in(monkeypatch)
    ws, cfg, store = make(tmp_path)
    c, api = client(ws, cfg, store)
    fingerprint = add_mailbox(c, api)
    refused = c.post(
        f"{api}/watch/work-mail/sent-folder", json={"folder": "Nowhere", "label": "x", "fingerprint": fingerprint}
    )
    assert refused.status_code == 400 and not any(s.label == "x" for s in sources(ws))
