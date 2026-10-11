"""Plugin API 0.3.35: a service's "wait" is honored and not counted as a failure, connectors read the service's own
error, change-only reads report removals, and plugins test connectors through engine.plugin_api.testing."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from engine.connectors import ConnectorError, Poll, SourceItem
from engine.plugin_api.testing import Reply, connector_context, read

N = yaml.safe_load((Path(__file__).parent / "fixtures" / "network" / "network.yaml").read_text())
API = f"https://{N['api_host']}"


def listing(settings, state, context):
    answer = context.web.get(
        f"{API}/v1/changes",
        params={"since": state.get("marker", "")},
        headers={"Authorization": f"Bearer {context.access_token('p/account')}"},
    )
    body = answer.json()
    return Poll(
        [SourceItem(i["id"], i["title"], i["text"]) for i in body["items"]],
        {"marker": body["next"]},
        complete=False,
        removed=body.get("deleted", []),
    )


def test_the_testing_helper_answers_requests_and_checks_the_poll():
    seen = []

    def service(asked):
        seen.append(asked)
        return Reply(json={"items": [{"id": "a", "title": "A", "text": "one"}], "next": "m2", "deleted": ["b"]})

    context = connector_context(service, network=[N["api_host"]], tokens={"p/account": "t1"})
    poll = read(listing, None, {"marker": "m1"}, context)
    assert [i.key for i in poll.items] == ["a"] and poll.removed == ["b"] and poll.state == {"marker": "m2"}
    assert seen[0].query == {"since": ["m1"]} and seen[0].headers["authorization"] == "Bearer t1"
    with pytest.raises(ConnectorError) as signed_out:
        read(listing, None, {}, connector_context(service, network=[N["api_host"]]))
    assert signed_out.value.kind == "auth"
    with pytest.raises(ValueError, match="complete=False"):
        read(lambda s, st, c: Poll([], removed=["x"]), None, {}, context)


def test_a_wait_and_the_services_own_error_reach_the_connector():
    replies = iter(
        [
            Reply(status=429, headers={"Retry-After": "120"}),
            Reply(status=403, json={"error": {"code": "rateLimitExceeded"}}),
            Reply(status=503, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}),
            Reply(status=410, json={"error": "marker expired"}),
        ]
    )
    context = connector_context(lambda asked: next(replies), network=[N["api_host"]])
    with pytest.raises(ConnectorError) as wait:
        context.web.get(f"{API}/x")
    assert wait.value.kind == "throttled" and wait.value.retry_after == 120
    with pytest.raises(ConnectorError) as refused:
        context.web.get(f"{API}/x")
    assert refused.value.status == 403 and refused.value.json()["error"]["code"] == "rateLimitExceeded"
    with pytest.raises(ConnectorError) as dated:
        context.web.get(f"{API}/x")
    assert dated.value.kind == "throttled" and dated.value.retry_after == 24 * 3600  # capped
    assert context.web.get(f"{API}/x").status == 410  # other statuses come back to read


def test_the_watcher_waits_when_asked_and_reports_removals_from_change_lists(tmp_path):
    from engine import watch
    from engine.connectors import CORE, Connector, FakeSettings
    from engine.storage import Store
    from engine.workspace import init_workspace
    from tests.conftest import DEMO_B

    answers = []

    def poll(settings, state, context):
        return answers.pop(0)() if callable(answers[0]) else answers.pop(0)

    def throttle():
        raise ConnectorError("throttled", "wait", retry_after=600)

    CORE["changes-fake"] = Connector("changes-fake", "Changes", FakeSettings, poll)
    try:
        ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
        data = yaml.safe_load((ws.config_dir / "watch.yaml").read_text())
        data["sources"] = [
            {
                "id": "changes",
                "connector": "changes-fake",
                "every_minutes": 5,
                "settings": {},
                "first_run": "baseline",
                "report_removed": True,
            }
        ]
        (ws.config_dir / "watch.yaml").write_text(yaml.safe_dump(data))
        cfg = ws.config()
        store = Store(ws.db_path, cfg=cfg)
        now = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)
        answers += [
            Poll([SourceItem("a", "A", "one"), SourceItem("b", "B", "two")], {"marker": "m1"}, complete=False),
            throttle,
            Poll([], {"marker": "m2"}, complete=False, removed=["b", "never-seen"]),
        ]
        assert watch.refresh(ws, store, cfg, "changes", now).outcome == "baseline"
        assert watch.refresh(ws, store, cfg, "changes", now + timedelta(minutes=5)).outcome == "throttled"
        assert watch.failures_in_a_row(store, "changes") == 0
        assert "changes" not in watch.due(store, cfg, now + timedelta(minutes=12))  # still within the wait
        assert "changes" in watch.due(store, cfg, now + timedelta(minutes=16))
        result = watch.refresh(ws, store, cfg, "changes", now + timedelta(minutes=16))
        assert result.outcome == "ok" and len(result.removed) == 1
        last = watch.last_run(store, "changes")
        assert last.data["state"] == {"marker": "m2"}
        store.close()
    finally:
        CORE.pop("changes-fake", None)
