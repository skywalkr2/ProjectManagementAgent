"""Plugin API 0.3.40: `retry_after` for connectors, and testing helpers that read a request as a service would."""

from engine.plugin_api import retry_after
from engine.plugin_api.testing import Reply, connector_context
from tests.test_plugin_api_0335 import API, N


def test_retry_after_reads_seconds_and_dates():
    assert retry_after({"Retry-After": "30"}) == 30
    assert retry_after({"retry-after": "Thu, 01 Jan 2026 00:01:00 GMT"}, now=1767225600) == 60
    assert retry_after({}) is None and retry_after({"Retry-After": "soon"}) is None


def test_a_request_is_read_decoded_with_blank_values_kept():
    seen = []

    def service(asked):
        seen.append(asked)
        return Reply(json={})

    context = connector_context(service, network=[N["api_host"]])
    response = context.web.get(f"{API}/items/a%3Db", params={"q": "", "page": "2"})
    asked = seen[0]
    assert asked.path == "/items/a=b" and asked.raw_path == "/items/a%3Db"
    assert asked.query["q"] == [""] and asked.param("page") == "2" and asked.param("none", "x") == "x"
    assert response.json() == {}


def test_granted_is_answered_only_when_given():
    def service(asked):
        return Reply()

    plain = connector_context(service, network=[N["api_host"]], tokens={"p/account": "t"})
    assert plain.granted is None
    scoped = connector_context(
        service, network=[N["api_host"]], tokens={"p/account": "t"}, granted={"p/account": {"read"}}
    )
    assert scoped.granted("p/account") == {"read"} and scoped.granted("p/other") == set()
