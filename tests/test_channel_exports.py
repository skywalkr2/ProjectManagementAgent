"""Everything a channel returns or reads is built from the public plugin API."""

from pathlib import Path

import engine.plugin_api as api


def test_a_channel_builds_its_answers_and_reads_its_act_from_the_public_api():
    for name in ("ChannelUndone", "OutgoingAbout", "ChannelSent", "ChannelFailed", "ChannelContext", "OutgoingAct"):
        assert name in api.__all__ and hasattr(api, name)
    assert api.OutgoingAbout(id="t-1").service_id is None
    assert api.ChannelUndone() == api.ChannelUndone()
    guide = Path("docs/plugin-guide.md").read_text(encoding="utf-8")
    assert "### ChannelUndone" in guide and "### OutgoingAbout" in guide
