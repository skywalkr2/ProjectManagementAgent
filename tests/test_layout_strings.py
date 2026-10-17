"""The layout stress strings the page-width browser test renders are well formed and use only reserved domains."""

import base64
import json
import re
from pathlib import Path

import pytest

STRINGS = Path(__file__).parents[1] / "web" / "e2e" / "fixtures" / "layout-strings.json"


@pytest.fixture
def samples():
    return json.loads(STRINGS.read_text(encoding="utf-8"))


def test_structure(samples):
    assert len(samples) == 50
    assert len({sample["id"] for sample in samples}) == 50
    for sample in samples:
        assert set(sample) == {"id", "text", "note"}
        assert all(isinstance(value, str) and value for value in sample.values())


def test_required_categories(samples):
    prefixes = {sample["id"].split("-")[0] for sample in samples}
    assert prefixes == {"web", "token", "base64", "email", "path", "cjk", "bidi", "emoji", "invisible", "mail"}


def test_only_reserved_domains(samples):
    for sample in samples:
        domains = re.findall(r"(?:https?://|@|\\\\)([a-zA-Z0-9.-]+)", sample["text"])
        assert all(
            domain.rstrip(".") == "example.com" or domain.rstrip(".").endswith(".example.com") for domain in domains
        )


def test_long_values(samples):
    indexed = {sample["id"]: sample["text"] for sample in samples}
    assert len(indexed["web-02"]) > 3000
    assert len(indexed["token-01"]) == 4096
    assert len(indexed["mail-01"]) > 3000
    assert "[AUTHENTICATIONFAILED]" in indexed["mail-01"]


@pytest.mark.parametrize("identifier", ["base64-01", "base64-02", "base64-04"])
def test_standard_base64(samples, identifier):
    text = next(sample["text"] for sample in samples if sample["id"] == identifier)
    decoded = base64.b64decode("".join(text.splitlines()), validate=True)
    assert decoded


def test_urlsafe_base64(samples):
    text = next(sample["text"] for sample in samples if sample["id"] == "base64-03")
    assert base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    assert "=" not in text


def test_invisible_characters(samples):
    indexed = {sample["id"]: sample["text"] for sample in samples}
    assert "\u200d" in indexed["emoji-01"]
    assert "\u200b" in indexed["invisible-01"]
    assert "\u2060" in indexed["invisible-03"]
    assert indexed["bidi-05"].count("\u2069") == 2
    assert indexed["bidi-06"].count("\u202e") == indexed["bidi-06"].count("\u202c") == 1


def test_json_round_trip(samples):
    assert json.loads(json.dumps(samples, ensure_ascii=True)) == samples


def test_non_ascii_prose_has_no_spaces(samples):
    indexed = {sample["id"]: sample["text"] for sample in samples}
    for identifier in ("cjk-01", "cjk-02", "cjk-03", "cjk-04"):
        assert not any(character.isspace() for character in indexed[identifier])
