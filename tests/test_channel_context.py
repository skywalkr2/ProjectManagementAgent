"""A channel's context (plugin API 0.3.89): `send`, `status` and `undo` get a `ChannelContext` built for the act's own
account, with a web client limited to the plugin's declared hosts and the account's own token and scopes. A channel
written without the context parameter is still called as before. Names and addresses come from the fixtures."""

import pytest

from engine.channels import ChannelContext, ChannelRegistration, ChannelSent, FakeChannel, accepts_context
from engine.config import load_config
from engine.connectors import ConnectorError
from engine.plugin_api.testing import Reply, channel_context
from engine.storage import Store
from tests.test_act_actions import ACCOUNT, draft_target, env, saved_message  # noqa: F401  (the fixtures)
from tests.test_sign_in import N
from tests.test_sign_in_accounts import ALICE, BOB, sign_in, world  # noqa: F401  (the fixtures)

ACCOUNT_KIND = "p18/service"
OTHER_HOST = "elsewhere." + N["auth_host"]  # a host the plugin never declared


def test_the_publisher_hands_each_call_a_context_for_the_acts_own_account(env):  # noqa: F811
    act_id = env.ready(account=ACCOUNT)
    assert env.publisher.send(act_id).status == "sent"
    context = env.fake.contexts[-1]
    assert isinstance(context, ChannelContext) and context.account == ACCOUNT
    assert context.web is None and context.access_token() is None and context.granted == frozenset()  # a core channel


def test_undo_gets_the_acts_account_too(env):  # noqa: F811
    mail = saved_message(env, "thread")
    act_id = draft_target(env, {"kind": "mailbox", "action": "archive", "about": [mail]})
    env.yes(act_id)
    env.publisher.send(act_id)
    env.person_op("act.undo", act_id)
    assert env.publisher.undo(act_id).status == "undone"
    assert env.fake.contexts[-1].account == ACCOUNT and len(env.fake.contexts) == 2


def test_status_gets_the_acts_account_too(env):  # noqa: F811
    act_id = env.ready(account=ACCOUNT)
    env.fake.mode = "timeout_after_send"
    assert env.publisher.send(act_id).status == "sending"
    env.publisher.resume()
    assert env.act(act_id)["status"] == "sent"
    sent, asked = env.fake.contexts[0], env.fake.contexts[1]
    assert sent.account == asked.account == ACCOUNT


def test_a_channel_written_without_a_context_is_still_called(env):  # noqa: F811
    seen: list[tuple] = []

    def send(act, key):
        seen.append(("send", key))
        return ChannelSent("old-id")

    def status(key):
        seen.append(("status", key))
        return ChannelSent("old-id")

    env.store.plugins.core_channels["fake"] = ChannelRegistration(
        "fake",
        "Old",
        ("message",),
        send=send,
        status=status,
        actions={"message": ("send",)},
        accounts=("mailbox",),
    )
    act_id = env.ready(account=ACCOUNT)
    assert env.publisher.send(act_id).status == "sent"
    assert seen == [("send", "attempt-1")] and env.act(act_id)["service_id"] == "old-id"


def test_a_function_gets_a_context_only_when_it_takes_one():
    assert not accepts_context(lambda act, key: None, 2)
    assert accepts_context(lambda act, key, context: None, 2)
    assert accepts_context(lambda act, key, extra=None: None, 2)
    assert accepts_context(lambda *args: None, 2)
    assert accepts_context(lambda key, context: None, 1) and not accepts_context(lambda key: None, 1)
    assert accepts_context(FakeChannel().send, 2) and accepts_context(FakeChannel().status, 1)


# ---- a plugin's channel: its hosts and its account ------------------------------------------------------------------


def test_a_plugins_channel_context_reaches_only_its_hosts_and_the_acts_own_account(world):  # noqa: F811
    ws, c, api = world
    sign_in(c, api, "alice")
    sign_in(c, api, "bob")
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    try:
        plugins = store.plugins
        mine = plugins.channel_context("p18/post", f"{ACCOUNT_KIND}:{ALICE}", ws.root)
        assert mine.account == f"{ACCOUNT_KIND}:{ALICE}"
        assert mine.access_token() == "tok-alice" and mine.granted == frozenset({"read"})
        theirs = plugins.channel_context("p18/post", f"{ACCOUNT_KIND}:{BOB}", ws.root)
        assert theirs.access_token() == "tok-bob"  # each act's own account, never the other
        with pytest.raises(ConnectorError) as undeclared:
            mine.web.get(f"https://{OTHER_HOST}/me")
        assert undeclared.value.kind == "no_access"
        mine.web.close(), theirs.web.close()
        # an account that isn't one of this plugin's sign-ins has no token and no scopes
        for account in ("mailbox:work-mail", "someone-else/service:" + ALICE, None):
            other = plugins.channel_context("p18/post", account, ws.root)
            assert other.access_token() is None and other.granted == frozenset() and other.account == account
            other.web.close()
        # a signed-out account is an auth failure the channel can answer
        gone = plugins.channel_context("p18/post", f"{ACCOUNT_KIND}:nobody@example.com", ws.root)
        with pytest.raises(ConnectorError) as out:
            gone.access_token()
        assert out.value.kind == "auth"
        gone.web.close()
        # a core channel has no web client at all
        core = plugins.channel_context("mailbox", f"{ACCOUNT_KIND}:{ALICE}", ws.root)
        assert core.web is None and core.access_token() is None
    finally:
        store.close()


# ---- the testing helper ---------------------------------------------------------------------------------------------


def test_the_testing_helper_answers_from_recorded_replies_and_refuses_other_hosts():
    asked = []

    def service(request):
        asked.append(request.path)
        return Reply(json={"id": "m1"})

    context = channel_context(
        service, network=[N["auth_host"]], account="example/account:me@example.com", token="tok", granted={"send"}
    )
    assert context.access_token() == "tok" and context.granted == frozenset({"send"})
    assert context.account == "example/account:me@example.com"
    assert context.web.get(f"https://{N['auth_host']}/v1/messages").json() == {"id": "m1"} and asked == ["/v1/messages"]
    with pytest.raises(ConnectorError) as refused:
        context.web.get(f"https://{OTHER_HOST}/v1/messages")
    assert refused.value.kind == "no_access"
    bare = channel_context(service, network=[])
    assert bare.access_token() is None and bare.account is None and bare.granted == frozenset()
