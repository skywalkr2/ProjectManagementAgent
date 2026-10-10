import pytest
import yaml

from engine.config import ConfigError, load_config


def config(tmp_path, stages):
    (tmp_path / "stages.yaml").write_text(yaml.safe_dump(stages))
    return load_config(tmp_path, env={})


@pytest.mark.parametrize(
    "stages, message",
    [
        ({"missing": []}, "unknown record type missing"),
        ({"project": [{"id": "x"}, {"id": "x"}]}, "unique"),
        ({"project": [{"id": "x", "entry": ["missing"]}]}, "unknown entry check missing"),
        ({"project": [{"id": "x", "starts": ["missing"]}]}, "unknown task kind missing"),
        ({"moves": "assistant"}, "person"),
    ],
)
def test_invalid_config(tmp_path, stages, message):
    with pytest.raises(ConfigError, match=message):
        config(tmp_path, stages)


def test_order_wording_and_mode_override(tmp_path):
    cfg = config(
        tmp_path,
        {
            "moves": "rule",
            "project": {
                "moves": "person",
                "stages": [{"id": "draft", "label": "Draft"}, {"id": "ready", "label": "Ready", "starts": ["notes"]}],
            },
        },
    )
    assert cfg.stages.moves == "rule"
    assert cfg.stages.types["project"].moves == "person"
    assert [s.id for s in cfg.stages.types["project"].stages] == ["draft", "ready"]
