"""The fake outside services the journeys stand on (tests/fake_services.py): the made-up sign-in checks what a real one
checks (the client, the address, the PKCE verifier, a code used once), the mail and calendar answer only to a token it
issued, the catalog lists a wheel the app can install, and the app trusts the throwaway authority only when told to,
by the standard environment variable. A journey that passed against a lenient fake would prove nothing."""

import base64
import hashlib
import json
import socket
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml
from starlette.testclient import TestClient

from engine import pack_install, packs
from engine.connectors import ConnectorError
from engine.net import WebClient
from tests import fake_services, fake_tls
from tests.fake_services import CLIENT_ID, SECURE_SERVICES, State, build_app

WEB = "https" + "://"
REDIRECT = "http://127.0.0.1:8783/api/sign-ins/callback"
VERIFIER = "v" * 60


def challenge(verifier: str = VERIFIER) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


@pytest.fixture
def service(tmp_path):
    state = State(tmp_path)
    return state, TestClient(build_app(state, 0, SECURE_SERVICES, helpers=False), follow_redirects=False)


def sign_in_page(client, **changes):
    query = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT,
        "scope": "mail.read",
        "state": "s1",
        "code_challenge": challenge(),
        "code_challenge_method": "S256",
        **changes,
    }
    return client.get("/account/authorize", params={k: v for k, v in query.items() if v is not None})


def exchange(client, code, **changes):
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "client_id": CLIENT_ID,
        "code_verifier": VERIFIER,
        **changes,
    }
    return client.post("/account/token", data=form)


def code_from(response) -> str:
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["state"] == ["s1"]
    return query["code"][0]


def test_the_client_the_mail_add_on_ships_is_the_one_the_service_knows():
    from tests.fixtures.plugins import journey_mail

    assert journey_mail.DEFAULT_CLIENT_ID == CLIENT_ID


def test_the_sign_in_page_sends_the_person_back_with_a_code_and_the_token_needs_the_verifier(service):
    state, client = service
    code = code_from(sign_in_page(client))
    assert exchange(client, code, code_verifier="wrong").status_code == 400  # the code is spent by a wrong verifier
    assert exchange(client, code).status_code == 400
    code = code_from(sign_in_page(client))
    granted = exchange(client, code)
    assert granted.status_code == 200
    body = granted.json()
    assert body["access_token"] in state.access and body["refresh_token"] in state.refresh
    assert exchange(client, code).status_code == 400  # a code works once
    assert state.seen["exchanges"] == 1 and state.seen["authorizations"] == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"client_id": "someone-else"},
        {"redirect_uri": WEB + "elsewhere.example.com/api/sign-ins/callback"},
        {"code_challenge_method": "plain"},
        {"code_challenge": None},
        {"state": None},
    ],
)
def test_a_sign_in_request_missing_what_a_real_one_needs_is_refused(service, changes):
    _, client = service
    assert sign_in_page(client, **changes).status_code == 400


def test_a_code_is_only_good_for_the_address_it_was_asked_for_and_a_token_needs_the_client(service):
    _, client = service
    assert exchange(client, code_from(sign_in_page(client)), redirect_uri=REDIRECT + "/x").status_code == 400
    assert exchange(client, code_from(sign_in_page(client)), client_id="someone-else").status_code == 401


def test_mail_and_calendar_answer_only_to_a_token_the_service_issued_and_stop_at_revoking(service):
    state, client = service
    assert client.get("/mail/v1/messages").status_code == 401
    assert client.get("/calendar/v1/events", headers={"Authorization": "Bearer made-up"}).status_code == 401
    tokens = exchange(client, code_from(sign_in_page(client))).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert {m["subject"] for m in client.get("/mail/v1/messages", headers=headers).json()["messages"]}
    assert client.get("/calendar/v1/events", headers=headers).json()["events"]
    assert client.get("/account/v1/me", headers=headers).json()["email"].endswith("@example.com")
    renewed = client.post(
        "/account/token",
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": CLIENT_ID},
    )
    assert renewed.status_code == 200 and renewed.json()["access_token"] in state.access
    client.post("/account/revoke", data={"token": tokens["access_token"]})
    assert client.get("/mail/v1/messages", headers=headers).status_code == 401
    assert state.seen["unauthorized"] == 3 and state.seen["mail_reads"] == 1


def test_the_mailbox_has_recent_and_old_items_in_the_shapes_the_assistant_reads():
    from datetime import UTC, datetime

    split = fake_services.recent_items(datetime.now(UTC))
    assert split["mail"] and split["events"] and split["noted"]
    assert not set(split["noted"]) & {*split["mail"], *split["events"]}


def test_the_catalog_lists_a_wheel_the_app_installs(tmp_path):
    wheel = fake_services.build_wheel(fake_services.PLUGINS / "journey_panel", tmp_path)
    feed = packs.parse("https://127.0.0.1/catalog", fake_services.catalog_feed(wheel, "https://127.0.0.1:1"))
    assert feed.error is None and feed.notes == [] and [e.id for e in feed.entries] == ["journey-panel"]
    entry = feed.entries[0]
    assert entry.release is not None and entry.release.sha256 == hashlib.sha256(wheel.read_bytes()).hexdigest()
    place = tmp_path / "site"
    done = pack_install.install(wheel.read_bytes(), place)
    assert (done.name, done.version) == ("journey-panel", "0.1.0")
    assert (place / "journey_panel" / "plugin.yaml").is_file()
    assert "pm_cockpit.plugins" in (place / "journey_panel-0.1.0.dist-info" / "entry_points.txt").read_text()
    assert pack_install.installed_here("journey-panel", place)
    pack_install.remove("journey-panel", place)
    assert not (place / "journey_panel").exists()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((fake_services.HOST, 0))
        return probe.getsockname()[1]


def test_the_app_trusts_the_throwaway_authority_only_through_the_standard_variable(tmp_path, monkeypatch):
    """The services answer over HTTPS with a certificate the app has no reason to trust, until `SSL_CERT_FILE` names
    the authority that made it; nothing in the app's own code is involved."""
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    state = State(tmp_path)
    port = free_port()
    server = fake_services.start_secure(state, port)
    try:
        url = f"https://{fake_services.HOST}:{port}/catalog/packs.yaml"
        monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "tls" / "authority.pem"))
        client = WebClient([fake_services.HOST])
        try:
            answer = client.get(url)
        finally:
            client.close()
        assert answer.status == 200 and yaml.safe_load(answer.text)["packs"][0]["id"] == "journey-panel"
        # Trusting some other authority instead: the same address can't be verified, so it isn't read.
        monkeypatch.setenv("SSL_CERT_FILE", str(fake_tls.make(tmp_path / "other").authority))
        client = WebClient([fake_services.HOST])
        try:
            with pytest.raises(ConnectorError):
                client.get(url)
        finally:
            client.close()
    finally:
        server.should_exit = True


def test_a_sorting_packet_gets_an_answer_for_every_id_and_is_counted_apart_from_work(tmp_path):
    state = State(tmp_path)
    client = TestClient(build_app(state, 0), follow_redirects=False)
    headers = "\n".join(f'{{"id": "m{n}", "from": "a", "subject": "s{n}", "categories": []}}' for n in (1, 2, 3))
    packet = f"{fake_services.SORTING_MARK}\n{headers}\n</untrusted>"
    sent = client.post(
        "/ai/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "system", "content": "sort"}, {"role": "user", "content": packet}]},
    )
    answers = json.loads(sent.json()["choices"][0]["message"]["content"])["answers"]
    assert [a["id"] for a in answers] == ["m1", "m2", "m3"]
    assert {a["answer"] for a in answers} == {"work"}
    seen = client.get("/__e2e/ai-requests").json()
    assert (seen["sorting"], seen["work"], seen["smoke"]) == (1, 0, 0)
