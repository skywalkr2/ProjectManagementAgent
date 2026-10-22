"""The web client a connector or channel gets reaches its allowed hosts with every method an API needs."""

import pytest

from engine.connectors import ConnectorError
from engine.plugin_api.testing import Reply, channel_context

HOST = "api." + "example.com"


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_put_patch_and_delete_reach_an_allowed_host_and_never_another(method):
    seen: list[str] = []

    def service(asked):
        seen.append(asked.method)
        return Reply(200, {"ok": True})

    context = channel_context(service, network=[HOST])
    answer = getattr(context.web, method)(f"https://{HOST}/v1/items/1", json={"a": 1})
    assert answer.status == 200 and seen == [method.upper()]
    with pytest.raises(ConnectorError) as refused:
        getattr(context.web, method)("https://other." + "example.org/v1/items/1")
    assert refused.value.kind == "no_access"
