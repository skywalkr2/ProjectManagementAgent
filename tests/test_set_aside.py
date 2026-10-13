"""Mail set aside as not work (design 6.5): the matchers, the built-in sorting, the Set aside folder, the person's
corrections and their sender rules, and confirming (which deletes the message's content from the app)."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from engine.config import load_config
from engine.connectors.mailbox import message_item
from tests.conftest import DEMO_B

NOW = datetime.now(UTC).replace(microsecond=0)
LISTS = "lists.example.com"
SHOP = "shop.example.com"
WORK = "colleague@work.example.com"
OWN = "own-mail.example.com"  # a public mail domain the person adds in the settings
CLUB = "club.example.com"
UNIQUE = "zebra-quartz-marmalade"  # a phrase that is only in the messages under test


def mail(key, sender, *, bulk=None, categories=(), subject=None, body=None, hours=1):
    """A fake source's item that is a mail message from `sender`, received `hours` before NOW."""
    subject = subject or f"Subject of {key}"
    received = (NOW - timedelta(hours=hours)).isoformat()
    return {
        "key": key,
        "title": subject,
        "text": f"From: Someone <{sender}>\nSubject: {subject}\n\n{body or 'Plain words.'}",
        "author": f"Someone <{sender}>",
        "message": {
            "sender": f"Someone <{sender}>",
            "received": received,
            "unread": True,
            "bulk": bulk,
            "categories": list(categories),
        },
    }


def make(tmp_path, items, first_run="all", **watch):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    source = {"id": "m", "connector": "fake", "label": "Inbox", "first_run": first_run, "settings": {"items": items}}
    # These tests are about the rules; the assistant's own sorting has its tests in test_mail_sorting.py.
    (ws.config_dir / "watch.yaml").write_text(
        yaml.safe_dump({"version": 1, "sources": [source], "sorting": "rules", **watch})
    )
    cfg = load_config(ws.config_dir, env={})
    return ws, cfg, Store(ws.db_path, cfg=cfg)


def requests_in(store, state):
    return [r for r in store.read().list("request") if r.data["state"] == state]


# ---- the matchers --------------------------------------------------------------------------------------------------


def change(sender=None, **message):
    details = {"sender": sender, "bulk": None, "categories": [], **message} if sender or message else None
    return {"source": "m", "key": "k", "title": "t", "now": "", "author": None, "message": details}


def test_bulk_mail_matches_only_a_message_that_says_it_is_bulk():
    from engine.triage import bulk_mail

    assert bulk_mail(change(f"a@{LISTS}", bulk=True), {})
    assert bulk_mail(change(f"a@{LISTS}", bulk=False), {}) is None
    assert bulk_mail(change(f"a@{LISTS}"), {}) is None  # unknown
    assert bulk_mail({**change(), "message": None}, {}) is None


def test_service_category_matches_any_of_the_rules_categories_in_any_case():
    from engine.triage import service_category

    params = {"categories": ["Promotions", "social"]}
    assert service_category(change(categories=["social", "inbox"]), params)
    assert service_category(change(categories=["promotions"]), params)
    assert service_category(change(categories=["updates"]), params) is None
    assert service_category(change(categories=["social"]), {"categories": []}) is None


def test_sender_rule_matches_an_address_or_a_domain_and_its_subdomains_in_any_case():
    from engine.triage import sender_rule

    params = {"senders": ["News@Lists.Example.com"], "domains": ["@Shop.example.com"]}
    assert sender_rule(change(f"Someone <NEWS@{LISTS}>"), params)
    assert sender_rule(change(f"a@{SHOP}"), params)
    assert sender_rule(change(f"a@deals.{SHOP}"), params)  # a domain matches its subdomains
    assert sender_rule(change(f"a@not{SHOP}"), params) is None  # but not a domain that merely ends the same way
    assert sender_rule(change(f"other@{LISTS}"), params) is None
    only_author = {**change(), "author": f"Someone <a@{SHOP}>", "message": {"sender": None}}
    assert sender_rule(only_author, params), "the author is read when the message has no sender"
    from_line = {**change(), "now": f"From: Someone <a@{SHOP}>\n\nHi"}
    assert sender_rule(from_line, params), "the text's From line is the last place the address is read"


def test_a_keep_rule_goes_first_and_wins_over_set_aside_rules_and_the_built_in_sorting(tmp_path):
    from engine.triage import first_match

    items = [change(f"a@{LISTS}", bulk=True)]
    ws, cfg, store = make(
        tmp_path,
        [],
        triage=[
            {"name": "Keep", "kind": "sender-rule", "params": {"senders": [f"a@{LISTS}"]}, "set_aside": "never"},
            {"name": "Lists", "kind": "sender-rule", "params": {"domains": [LISTS]}, "set_aside": "sales"},
        ],
    )
    try:
        assert first_match(store, cfg, items[0]) is None
        other = change(f"b@{LISTS}", bulk=True)
        assert first_match(store, cfg, other)["section"] == "sales"
    finally:
        store.close()


# ---- built in, without a setting to edit ---------------------------------------------------------------------------


def test_a_fresh_workspace_sets_aside_bulk_and_category_mail_with_no_rule_to_write(tmp_path):
    from engine.triage import first_match
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "fresh", git=False)
    cfg = ws.config(env={})
    from engine.storage import Store

    store = Store(ws.db_path, cfg=cfg)
    try:
        assert cfg.watch.set_aside_defaults is True and cfg.watch.triage == []
        bulk = first_match(store, cfg, change(f"a@{LISTS}", bulk=True))
        assert bulk["section"] == "sales" and "many people" in bulk["reason"]
        social = first_match(store, cfg, change(f"a@{LISTS}", categories=["social"]))
        assert social["section"] == "sales" and "social" in social["reason"]
        assert first_match(store, cfg, change(f"a@{LISTS}", categories=["primary"])) is None
        assert first_match(store, cfg, change(f"a@{LISTS}", bulk=False)) is None
    finally:
        store.close()


def test_a_workspace_with_its_own_rules_or_written_earlier_still_sets_aside_bulk_and_category_mail(tmp_path):
    from engine.watch import refresh

    own = [
        {"name": "Spacing", "kind": "cosmetic"},
        {"name": "Scratch", "kind": "name-matches", "params": {"patterns": ["*.tmp"]}},
    ]
    items = [
        mail("bulk", f"a@{LISTS}", bulk=True),
        mail("promo", f"b@{SHOP}", categories=["promotions"]),
        mail("work", WORK),
    ]
    for watch in ({"triage": own}, {}):  # a filled list, and a file with no triage list at all
        ws, cfg, store = make(tmp_path / ("own" if watch else "old"), items, **watch)
        try:
            assert "set_aside_defaults" not in (ws.config_dir / "watch.yaml").read_text()
            result = refresh(ws, store, cfg, "m", NOW)
            sections = {
                store.read().get("source", store.read().get("request", r).data["source"]).data["title"]: store.read()
                .get("request", r)
                .data.get("set_aside")
                for r in result.new
            }
            assert sections["Subject of bulk"]["section"] == "sales"
            assert sections["Subject of promo"]["section"] == "sales"
            assert sections["Subject of work"] is None
        finally:
            store.close()


def test_the_set_aside_count_is_what_the_folder_holds_so_a_confirmed_item_is_not_in_it(tmp_path):
    """Came in's "N set aside" opens the Set aside folder, so it counts what that folder lists: an item the person
    confirmed has left the folder (and is later deleted down to a marker) and is no longer counted."""
    from engine import today
    from engine.set_aside import confirm_items, folder, purge

    items = [mail("bulk", f"a@{LISTS}", bulk=True), mail("social", f"b@{SHOP}", categories=["social"])]
    ws, cfg, store = make(tmp_path, items)
    try:
        from engine.watch import refresh

        refresh(ws, store, cfg, "m", NOW)
        assert today.arrived(store, cfg, NOW).set_aside == 2 == len(folder(ws, store, cfg))
        first = next(s.id for s in store.read().list("snapshot") if s.data["key"] == "bulk")
        confirm_items(store, [first], NOW)
        assert today.arrived(store, cfg, NOW).set_aside == 1 == len(folder(ws, store, cfg))
        assert purge(ws, store, [first]) == 1
        assert today.arrived(store, cfg, NOW).set_aside == 1 == len(folder(ws, store, cfg))
    finally:
        store.close()


def test_the_setting_turns_the_built_in_sorting_off(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = make(tmp_path, [mail("bulk", f"a@{LISTS}", bulk=True)], set_aside_defaults=False)
    try:
        result = refresh(ws, store, cfg, "m", NOW)
        assert store.read().get("request", result.new[0]).data["state"] == "queued"
    finally:
        store.close()


# ---- set aside: no request for the assistant, no AI call, counted apart --------------------------------------------


def test_a_bulk_item_is_set_aside_with_nothing_queued_and_no_ai_call(tmp_path):
    from engine import today
    from engine.watch import refresh

    items = [
        mail("bulk", f"a@{LISTS}", bulk=True),
        mail("social", f"b@{SHOP}", categories=["social"]),
        mail("work", WORK),
    ]
    ws, cfg, store = make(tmp_path, items)
    try:
        result = refresh(ws, store, cfg, "m", NOW)
        assert len(result.new) == 3
        assert len(requests_in(store, "queued")) == 1  # only the work mail
        done = [r for r in requests_in(store, "done") if r.data.get("set_aside")]
        assert {r.data["set_aside"]["section"] for r in done} == {"sales"} and len(done) == 2
        assert not any(r.data.get("auto_closed") for r in done), "set-aside mail isn't under Auto-closed"
        assert not store.read().has("run") and not store.read().has("signal")
        inbox = today.arrived(store, cfg, NOW)
        assert [a.title for a in inbox.items] == ["Subject of work"]
        assert inbox.set_aside == 2 and inbox.left_out == 0
        snaps = {s.data["key"]: s.data for s in store.read().list("snapshot")}
        assert snaps["bulk"]["set_aside"]["section"] == "sales" and snaps["bulk"]["closed_by"] is None
        assert snaps["bulk"]["message"]["bulk"] is True and snaps["social"]["message"]["categories"] == ["social"]
    finally:
        store.close()


def test_a_second_read_of_unchanged_mail_does_nothing_new(tmp_path):
    from engine.watch import refresh

    ws, cfg, store = make(tmp_path, [mail("bulk", f"a@{LISTS}", bulk=True)])
    try:
        refresh(ws, store, cfg, "m", NOW)
        again = refresh(ws, store, cfg, "m", NOW + timedelta(minutes=5))
        assert again.new == [] and again.changed == []
        assert len(store.read().list("request")) == 1
    finally:
        store.close()


def test_the_mailbox_connector_fills_bulk_from_the_headers():
    plain = (
        b"Message-ID: <a@x.example.com>\nFrom: A <a@x.example.com>\nDate: Tue, 05 Mar 2030 09:15:00 +0000\n"
        b"Subject: Hi\n\nBody"
    )
    assert message_item(plain).message.bulk is False
    unsubscribe = plain.replace(b"Subject: Hi", b"List-Unsubscribe: <mailto:u@x.example.com>\nSubject: Hi")
    assert message_item(unsubscribe).message.bulk is True
    for precedence in (b"bulk", b"List", b"LIST"):
        marked = plain.replace(b"Subject: Hi", b"Precedence: " + precedence + b"\nSubject: Hi")
        assert message_item(marked).message.bulk is True
    junk = plain.replace(b"Subject: Hi", b"Precedence: first-class\nSubject: Hi")
    assert message_item(junk).message.bulk is False


# ---- the folder, corrections and rules through the screens' routes -------------------------------------------------


@pytest.fixture
def app(tmp_path):
    from api.app import create_app

    items = [
        mail("bulk", f"a@{LISTS}", bulk=True, body=f"Big sale {UNIQUE}"),
        mail("social", f"b@{SHOP}", categories=["social"]),
        mail("work", WORK),
    ]
    ws, cfg, store = make(tmp_path, items)
    store.close()
    created = create_app(ws, cfg, "t", start_worker=False)
    client = TestClient(created)
    client.headers["Authorization"] = "Bearer t"
    base = cfg.server.base_path.rstrip("/") + "/api"
    yield ws, cfg, created.state.store, client, base
    created.state.store.close()


def read(ws, store):
    from engine.watch import refresh

    return refresh(ws, store, load_config(ws.config_dir, env={}), "m", NOW)


def fingerprint(client, base):
    return client.get(f"{base}/settings").json()["fingerprint"]


def folder(client, base):
    return client.get(f"{base}/set-aside").json()


def test_the_folder_lists_what_was_set_aside_with_its_sender_and_reason(app):
    ws, cfg, store, client, base = app
    read(ws, store)
    listing = folder(client, base)
    assert {i["title"] for i in listing["items"]} == {"Subject of bulk", "Subject of social"}
    bulk = next(i for i in listing["items"] if i["title"] == "Subject of bulk")
    assert bulk["section"] == "sales" and bulk["source"] == "Inbox" and "many people" in bulk["reason"]
    assert bulk["address"] == f"a@{LISTS}" and bulk["domain"] == LISTS
    came_in = client.get(f"{base}/today/arrived").json()
    assert came_in["set_aside"] == 2 and [i["title"] for i in came_in["items"]] == ["Subject of work"]
    changes = client.get(f"{base}/changes").json()
    assert [c for c in changes if "bulk" in str(c["source_title"] or "")] == [], "not listed under What changed"


def test_this_is_work_hands_it_in_records_a_pulled_back_signal_and_shows_it_in_came_in(app):
    ws, cfg, store, client, base = app
    read(ws, store)
    item = next(i for i in folder(client, base)["items"] if i["title"] == "Subject of bulk")
    stale = client.post(f"{base}/set-aside/{item['id']}/work", json={"read_version": item["version"] + 5})
    assert stale.status_code == 409
    assert client.post(f"{base}/set-aside/{item['id']}/work", json={"read_version": item["version"]}).status_code == 200
    queued = [r for r in requests_in(store, "queued") if r.data["source"]]
    assert len(queued) == 2 and all(not r.data.get("set_aside") for r in queued)
    signals = [s for s in store.read().list("signal") if s.data["kind"] == "pulled_back"]
    assert len(signals) == 1 and "many people" in signals[0].data["note"]
    assert {i["title"] for i in folder(client, base)["items"]} == {"Subject of social"}
    came_in = client.get(f"{base}/today/arrived").json()
    assert came_in["set_aside"] == 1 and {i["title"] for i in came_in["items"]} == {
        "Subject of work",
        "Subject of bulk",
    }


def test_this_is_work_hands_in_mail_that_was_set_aside_before_it_was_ever_handed_in(tmp_path):
    from engine.watch import hand_in_snapshot, refresh

    ws, cfg, store = make(tmp_path, [mail("old", f"a@{LISTS}", bulk=True, hours=500)], first_run="recent")
    try:
        assert refresh(ws, store, cfg, "m", NOW).outcome == "baseline"
        assert store.read().list("request") == []
        snap = store.read().list("snapshot")[0]
        assert snap.data["set_aside"]["section"] == "sales"
        assert hand_in_snapshot(ws, store, cfg, snap.id, NOW)
        assert len(requests_in(store, "queued")) == 1
    finally:
        store.close()


def test_set_aside_by_hand_closes_a_waiting_request_and_put_back_restores_it(app):
    ws, cfg, store, client, base = app
    read(ws, store)
    work = next(s for s in store.read().list("snapshot") if s.data["key"] == "work")
    waiting = requests_in(store, "queued")
    assert len(waiting) == 1
    done = client.post(f"{base}/mail/{work.id}/set-aside", json={"section": "personal"})
    assert done.json()["address"] == WORK and done.json()["domain"] == "work.example.com"
    assert requests_in(store, "queued") == []
    closed = store.read().get("request", waiting[0].id).data
    assert closed["state"] == "done" and closed["set_aside"]["from_state"] == "queued"
    assert {i["section"] for i in folder(client, base)["items"]} == {"sales", "personal"}
    assert store.read().get("snapshot", work.id).data["set_aside"]["section"] == "personal"
    version = done.json()["version"]
    assert client.post(f"{base}/set-aside/{work.id}/put-back", json={"read_version": version}).status_code == 200
    assert [r.id for r in requests_in(store, "queued")] == [waiting[0].id]
    signals = store.read().list("signal")
    assert len(signals) == 1, "putting it back as an undo is not a correction of the rules"


def test_set_aside_by_hand_records_a_set_aside_signal_and_putting_it_back_records_none(app):
    ws, cfg, store, client, base = app
    read(ws, store)
    work = next(s for s in store.read().list("snapshot") if s.data["key"] == "work")
    waiting = requests_in(store, "queued")[0]
    done = client.post(f"{base}/mail/{work.id}/set-aside", json={"section": "personal"}).json()
    signals = store.read().list("signal")
    assert [(s.data["kind"], s.data["refs"]) for s in signals] == [("set_aside", [waiting.id])]
    assert signals[0].data["note"].startswith("personal") and "rule" in signals[0].data["note"]
    # Nothing was waiting for an item a rule had set aside, so the signal refers to the message.
    bulk = next(s for s in store.read().list("snapshot") if s.data["key"] == "bulk")
    assert client.post(f"{base}/mail/{bulk.id}/set-aside", json={"section": "personal"}).status_code == 200
    again = store.read().list("signal")[-1].data
    assert again["kind"] == "set_aside" and again["refs"] == [bulk.id]
    version = done["version"]
    assert client.post(f"{base}/set-aside/{work.id}/put-back", json={"read_version": version}).status_code == 200
    assert len(store.read().list("signal")) == 2


def test_learning_reads_requests_and_snapshots_only_through_a_guard_that_leaves_out_set_aside_ones(app):
    from engine.set_aside import learnable

    ws, cfg, store, client, base = app
    read(ws, store)
    keys = lambda: {s.data["key"] for s in learnable(store.read(), "snapshot")}  # noqa: E731
    assert keys() == {"work"}, "mail a rule set aside is left out"
    assert {r.id for r in learnable(store.read(), "request")} == {
        r.id for r in store.read().list("request") if not r.data.get("set_aside")
    }
    work = next(s for s in store.read().list("snapshot") if s.data["key"] == "work")
    client.post(f"{base}/mail/{work.id}/set-aside", json={"section": "personal"})
    assert keys() == set(), "mail the person set aside is left out, with the request it closed"
    assert all(not r.data.get("set_aside") for r in learnable(store.read(), "request"))
    assert len(learnable(store.read(), "request")) < len(store.read().list("request"))
    version = store.read().get("snapshot", work.id).version
    client.post(f"{base}/set-aside/{work.id}/put-back", json={"read_version": version})
    assert keys() == {"work"}
    with pytest.raises(ValueError):
        learnable(store.read(), "signal")


def test_a_confirmed_set_asides_redaction_matches_its_original_when_two_histories_are_compared(app):
    from engine.handover import _local_ledger as ledger_of
    from engine.handover import apply_redactions, backup_local, compare
    from engine.set_aside import confirm_items, purge

    class Computer:  # what the comparison reads of a workspace: where its database is
        def __init__(self, db_path):
            self.db_path = db_path

    ws, cfg, store, client, base = app
    read(ws, store)
    ids = [i["id"] for i in folder(client, base)["items"]]
    confirm_items(store, ids)
    other = Computer(backup_local(ws, "other"))  # the other computer, before the content was deleted
    assert purge(ws, store, ids) == 2
    deleted, original = ledger_of(ws), ledger_of(other)
    assert deleted[: len(original)] != original, "the deletion rewrote earlier entries, so a plain comparison fails"
    assert compare(original, deleted) == "folder_newer" and compare(deleted, original) == "newer_here"
    # Work done apart is still a divergence.
    store.close()
    extra = sqlite3.connect(other.db_path)
    extra.execute("UPDATE ledger SET actor = 'someone' WHERE seq = (SELECT MAX(seq) FROM ledger)")
    extra.commit()
    extra.close()
    assert compare(ledger_of(other), deleted) == "diverged"
    assert apply_redactions([], []) == ([], [])


def test_a_rule_written_by_the_corrections_route_applies_to_the_next_matching_item(app):
    ws, cfg, store, client, base = app
    read(ws, store)
    work = next(s for s in store.read().list("snapshot") if s.data["key"] == "work")
    client.post(f"{base}/mail/{work.id}/set-aside", json={"section": "personal"})
    saved = client.post(
        f"{base}/watch/sorting",
        json={"fingerprint": fingerprint(client, base), "choice": "personal", "senders": [WORK], "domains": []},
    )
    assert saved.status_code == 200 and saved.json()["needs_restart"] is False
    rules = load_config(ws.config_dir, env={}).watch.triage
    assert [(r.name, r.set_aside, r.params) for r in rules] == [
        ("Personal mail you set aside", "personal", {"senders": [WORK]})
    ]
    # The next mail from that sender, which says nothing about itself, is set aside as personal mail.
    settings = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
    settings["sources"][0]["settings"]["items"].append(mail("later", WORK, hours=0))
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(settings))
    read(ws, store)
    later = next(s for s in store.read().list("snapshot") if s.data["key"] == "later")
    assert later.data["set_aside"]["section"] == "personal" and "colleague" in later.data["set_aside"]["reason"]
    assert len(requests_in(store, "queued")) == 0
    # Undo, as the screen does: the settings go back as they were.
    change = saved.json()["changes"][0]
    undone = client.post(
        f"{base}/settings",
        json={"changes": {change["key"]: change["before"]}, "reset": [], "fingerprint": fingerprint(client, base)},
    )
    assert undone.status_code == 200 and load_config(ws.config_dir, env={}).watch.triage == []


def test_a_keep_rule_from_this_is_work_always_goes_first_and_beats_the_built_in_sorting(app):
    ws, cfg, store, client, base = app
    for choice, sender in (("sales", f"x@{SHOP}"), ("never", f"a@{LISTS}"), ("personal", f"y@{SHOP}")):
        body = {"fingerprint": fingerprint(client, base), "choice": choice, "senders": [sender], "domains": []}
        assert client.post(f"{base}/watch/sorting", json=body).status_code == 200
    rules = load_config(ws.config_dir, env={}).watch.triage
    assert [r.set_aside for r in rules] == ["never", "personal", "sales"]
    read(ws, store)
    kept = next(s for s in store.read().list("snapshot") if s.data["key"] == "bulk")
    assert kept.data["set_aside"] is None, "the bulk mail from a kept sender stays with the assistant"
    assert len(requests_in(store, "queued")) == 2  # the kept sender's mail and the work mail
    # Moving a sender to another choice takes it out of the first.
    body = {"fingerprint": fingerprint(client, base), "choice": "sales", "senders": [f"y@{SHOP}"], "domains": []}
    client.post(f"{base}/watch/sorting", json=body)
    rules = load_config(ws.config_dir, env={}).watch.triage
    assert [r.set_aside for r in rules] == ["never", "sales"] and rules[1].params["senders"] == [
        f"x@{SHOP}",
        f"y@{SHOP}",
    ]


# ---- confirming: learn the sender, then delete the content ---------------------------------------------------------


def confirm(client, base, ids):
    return client.post(f"{base}/set-aside/confirm", json={"fingerprint": fingerprint(client, base), "ids": ids})


def test_confirming_writes_a_sender_rule_and_the_next_mail_from_that_sender_is_set_aside(app):
    ws, cfg, store, client, base = app
    read(ws, store)
    item = next(i for i in folder(client, base)["items"] if i["title"] == "Subject of social")
    done = confirm(client, base, [item["id"]])
    assert done.status_code == 200
    body = done.json()
    assert body["confirmed"] == 1 and body["senders"] == [f"b@{SHOP}"] and body["section"] == "sales"
    assert len(body["saved"]["changes"]) == 1 and body["domain_offers"] == []
    rules = load_config(ws.config_dir, env={}).watch.triage
    assert (
        rules[0].kind == "sender-rule"
        and rules[0].set_aside == "sales"
        and rules[0].params == {"senders": [f"b@{SHOP}"]}
    )
    # A new mail from that sender, which the service files under nothing special, is set aside by the new rule.
    settings = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
    settings["sources"][0]["settings"]["items"].append(mail("next", f"B@{SHOP}", hours=0))
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(settings))
    read(ws, store)
    nxt = next(s for s in store.read().list("snapshot") if s.data["key"] == "next")
    assert nxt.data["set_aside"]["section"] == "sales" and not any(
        r.data["source"] and "next" in r.data["source"] for r in requests_in(store, "queued")
    )


def test_confirm_all_writes_one_save_with_one_undo_and_offers_a_domain_at_three_senders(app):
    ws, cfg, store, client, base = app
    items = [mail(f"s{n}", f"person{n}@{SHOP}", categories=["promotions"]) for n in range(3)]
    items.append(mail("other", f"x@{LISTS}", bulk=True))
    settings = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
    settings["sources"][0]["settings"]["items"] += items
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(settings))
    read(ws, store)
    ids = [i["id"] for i in folder(client, base)["items"]]
    assert len(ids) == 6
    before = len(store.read().list("setting_change"))
    done = confirm(client, base, ids).json()
    assert done["confirmed"] == 6 and len(done["senders"]) == 6
    assert len(store.read().list("setting_change")) == before + 1, "one save for all the senders"
    assert [(o["domain"], o["senders"]) for o in done["domain_offers"]] == [(SHOP, 4)]
    assert len(load_config(ws.config_dir, env={}).watch.triage[0].params["senders"]) == 6
    assert folder(client, base)["items"] == []
    # One Undo: the settings back as they were.
    change = done["saved"]["changes"][0]
    assert change["key"] == "watch.triage"
    undone = client.post(
        f"{base}/settings",
        json={"changes": {"watch.triage": change["before"]}, "reset": [], "fingerprint": fingerprint(client, base)},
    )
    assert undone.status_code == 200 and load_config(ws.config_dir, env={}).watch.triage == []
    # A domain rule is one more sorting rule.
    domain = client.post(
        f"{base}/watch/sorting",
        json={"fingerprint": fingerprint(client, base), "choice": "sales", "senders": [], "domains": [SHOP]},
    )
    assert domain.status_code == 200
    assert load_config(ws.config_dir, env={}).watch.triage[0].params == {"domains": [SHOP]}


# ---- no rule for a whole public mail domain -----------------------------------------------------------------------


def public_domain():
    """A domain from the shipped list of public mail domains."""
    from engine.set_aside import shipped_public_domains

    return sorted(shipped_public_domains())[0]


def add_items(ws, items):
    settings = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
    settings["sources"][0]["settings"]["items"] += items
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(settings))


def test_a_public_mail_domain_is_the_shipped_list_plus_the_persons_own_and_matches_exactly(tmp_path):
    from engine.set_aside import is_public_domain, offerable_domain

    ws, cfg, store = make(tmp_path, [], public_mail_domains_extra=[OWN.upper()])
    store.close()
    shipped = public_domain()
    own = [OWN]
    assert is_public_domain(shipped, cfg) and is_public_domain(shipped.upper(), cfg)
    assert is_public_domain(f"@{shipped}", cfg)
    assert is_public_domain(own[0], cfg), "a domain from the setting counts"
    assert not is_public_domain(LISTS, cfg) and not is_public_domain("", cfg)
    assert not is_public_domain(f"team.{shipped}", cfg), "a subdomain is not the listed domain"
    assert offerable_domain(f"a@{shipped}", cfg) is None and offerable_domain(f"a@{own[0]}", cfg) is None
    assert offerable_domain(f"a@{LISTS}", cfg) == LISTS and offerable_domain("no-address", cfg) is None


def test_a_set_aside_row_and_this_is_work_offer_no_domain_for_a_public_domain(app):
    ws, cfg, store, client, base = app
    add_items(ws, [mail("personal", f"friend@{public_domain()}", bulk=True)])
    read(ws, store)
    rows = {i["address"]: i for i in folder(client, base)["items"]}
    friend = rows[f"friend@{public_domain()}"]
    assert friend["domain"] is None and friend["address"], "only the sender rule is offered"
    assert rows[f"a@{LISTS}"]["domain"] == LISTS, "a company sender still offers both"
    work = client.post(f"{base}/set-aside/{friend['id']}/work", json={"read_version": friend["version"]}).json()
    assert work["domain"] is None and work["address"] == friend["address"]
    by_hand = client.post(f"{base}/mail/{friend['id']}/set-aside", json={"section": "personal"}).json()
    assert by_hand["domain"] is None and by_hand["address"] == friend["address"]


def test_confirm_all_offers_no_domain_for_three_senders_on_a_public_domain_but_does_for_a_company(app):
    ws, cfg, store, client, base = app
    add_items(
        ws,
        [mail(f"p{n}", f"person{n}@{public_domain()}", bulk=True) for n in range(3)]
        + [mail(f"c{n}", f"person{n}@{CLUB}", bulk=True) for n in range(3)],
    )
    read(ws, store)
    items = folder(client, base)["items"]
    public = [i["id"] for i in items if i["domain"] is None]
    company = [i["id"] for i in items if i["domain"] == CLUB]
    assert len(public) == 3 and len(company) == 3
    only_public = confirm(client, base, public).json()
    assert len(only_public["senders"]) == 3 and only_public["domain_offers"] == []
    both = confirm(client, base, company).json()
    assert [(o["domain"], o["senders"]) for o in both["domain_offers"]] == [(CLUB, 3)]


def test_a_domain_rule_for_a_public_domain_is_refused_in_plain_words_and_nothing_is_saved(app):
    ws, cfg, store, client, base = app
    own = OWN
    settings = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump({**settings, "public_mail_domains_extra": [own]}))

    def save(domains):
        body = {"fingerprint": fingerprint(client, base), "choice": "sales", "senders": [], "domains": domains}
        return client.post(f"{base}/watch/sorting", json=body)

    for domain in (public_domain(), f"@{public_domain().upper()}", own):
        refused = save([SHOP, domain])
        assert refused.status_code == 400
        words = refused.json()["detail"]
        assert domain.lstrip("@").lower() in words.lower() and "sender" in words
        assert "watch" not in words and ".yaml" not in words and "_" not in words
    assert load_config(ws.config_dir, env={}).watch.triage == [], "the stale screen wrote nothing"
    assert save([SHOP]).status_code == 200, "a company domain is still saved"
    # A domain the person adds to the setting is refused at once, with no restart.
    settings = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
    settings["public_mail_domains_extra"] = [own, LISTS]
    (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(settings))
    assert save([LISTS]).status_code == 400


def all_text(ws):
    """Everything the app holds as text: the whole database and every file outside the history and the settings (the
    stand-in source keeps its fake mailbox in its settings, as a real one keeps it in the mailbox)."""
    conn = sqlite3.connect(ws.db_path)
    dump = "\n".join(conn.iterdump())
    conn.close()
    files = "\n".join(
        p.read_bytes().decode("utf-8", "replace")
        for p in ws.root.rglob("*")
        if p.is_file()
        and ".git" not in p.parts
        and ws.config_dir not in p.parents
        and p != ws.db_path
        and not p.name.startswith(ws.db_path.name)
    )
    return dump + "\n" + files


def test_after_the_undo_time_no_text_of_a_confirmed_message_remains_and_it_is_never_handed_in_again(app):
    ws, cfg, store, client, base = app
    (ws.config_dir / "watch.yaml").write_text(
        yaml.safe_dump({**yaml.safe_load((ws.config_dir / "watch.yaml").read_text()), "set_aside_keep_seconds": 60})
    )
    read(ws, store)
    assert UNIQUE in all_text(ws)
    ids = [i["id"] for i in folder(client, base)["items"]]
    done = confirm(client, base, ids).json()
    # Within the undo time the copy is held, but the messages are gone from the folder.
    assert folder(client, base)["items"] == [] and UNIQUE in all_text(ws)
    from engine.set_aside import purge_due

    assert purge_due(ws, store, load_config(ws.config_dir, env={}), NOW) == 0
    later = datetime.now(UTC) + timedelta(seconds=61)
    assert purge_due(ws, store, load_config(ws.config_dir, env={}), later) == 2
    text = all_text(ws)
    assert UNIQUE not in text and "Subject of bulk" not in text and "Subject of social" not in text
    marker = next(s for s in store.read().list("snapshot") if s.data["key"] == "bulk").data
    assert marker["deleted"] is True and marker["title"] == "" and marker["content_hash"] == ""
    assert marker["message"]["sender"] == f"a@{LISTS}" and marker["set_aside"] == {
        "section": "sales",
        "rule": "Bulk mail",
    }
    assert folder(client, base)["deleted"] == 2
    # The ledger keeps that the content was removed, and by whom, but not the content.
    entries = [e for e in store.read().ledger(kind="snapshot", record_id=marker["id"]) if e["field"] == "title"]
    assert entries and all(e["before"] is None and e["after"] is None for e in entries)
    assert any(e["op"] == "set_aside.delete" for e in entries)
    # The next read finds the same message and doesn't hand it in again, or bring it back.
    again = read(ws, store)
    assert again.new == [] and again.changed == []
    assert folder(client, base)["items"] == [] and done["confirmed"] == 2
    # Undo after the time is refused.
    refused = client.post(f"{base}/set-aside/unconfirm", json={"ids": ids})
    assert refused.status_code == 409


def test_undo_within_the_undo_time_brings_the_messages_back(app):
    ws, cfg, store, client, base = app
    (ws.config_dir / "watch.yaml").write_text(
        yaml.safe_dump({**yaml.safe_load((ws.config_dir / "watch.yaml").read_text()), "set_aside_keep_seconds": 60})
    )
    read(ws, store)
    ids = [i["id"] for i in folder(client, base)["items"]]
    confirm(client, base, ids)
    assert client.post(f"{base}/set-aside/unconfirm", json={"ids": ids}).status_code == 200
    assert {i["title"] for i in folder(client, base)["items"]} == {"Subject of bulk", "Subject of social"}
    assert UNIQUE in all_text(ws)


def test_with_no_wait_a_confirmed_message_is_deleted_at_once(app):
    ws, cfg, store, client, base = app
    (ws.config_dir / "watch.yaml").write_text(
        yaml.safe_dump({**yaml.safe_load((ws.config_dir / "watch.yaml").read_text()), "set_aside_keep_seconds": 0})
    )
    read(ws, store)
    ids = [i["id"] for i in folder(client, base)["items"]]
    confirm(client, base, ids)
    assert UNIQUE not in all_text(ws) and folder(client, base)["deleted"] == 2


def test_the_sorting_rules_module_keeps_one_rule_per_choice():
    from engine.sorting_rules import with_sender_rules

    rules = with_sender_rules(
        [{"name": "Other", "kind": "cosmetic"}], "sales", ["A@x.example.com", "a@x.example.com"], []
    )
    assert [r["name"] for r in rules] == ["Sales mail you set aside", "Other"]
    assert rules[0]["params"] == {"senders": ["a@x.example.com"]}
    rules = with_sender_rules(rules, "never", ["a@x.example.com"], [])
    assert [r.get("set_aside") for r in rules] == ["never", None], "the emptied sales rule goes"
    with pytest.raises(ValueError):
        with_sender_rules(rules, "work", ["a@x.example.com"], [])
