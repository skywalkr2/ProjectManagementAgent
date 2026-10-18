import json

import pytest

from engine.voice_profile import voice_profile


def test_greetings_and_signoffs_frequencies():
    profile = voice_profile(
        [
            "Hi Mira,\nThe draft is attached.\nBest,\nRowan",
            "Hi Oren,\nPlease see the notes.\nBest,\nRowan",
            "Dear Tess,\nCould you review the plan?\nKind regards,\nRowan",
        ]
    )
    assert profile["greetings"]["usual"][0] == {"text": "hi", "count": 2, "share": 0.667}
    assert profile["signoffs"]["usual"][0] == {"text": "best", "count": 2, "share": 0.667}
    assert profile["sample"]["messages"] == 3


def test_typical_length_is_median():
    profile = voice_profile(["One two.", "One two three four.", "word " * 100])
    assert profile["length"]["median_words"] == 4


def test_contraction_and_punctuation_counts():
    profile = voice_profile(["I'm ready! Aren't you?", "We’re ready!! Can’t wait.", "The draft is ready."])
    assert profile["contractions"] == {"messages": 2, "share": 0.667, "occurrences": 4}
    assert profile["exclamations"] == {"messages": 2, "share": 0.667, "occurrences": 3}
    assert profile["questions"] == {"messages": 1, "share": 0.333, "occurrences": 1}


def test_possessive_names_not_contractions():
    assert voice_profile(["Rowan's draft and Mira’s notes."])["contractions"]["occurrences"] == 0


@pytest.mark.parametrize(
    "text", ["I'm", "you're", "we've", "they'll", "I'd", "it's", "let's", "won't", "can't", "shouldn’t"]
)
def test_supported_contractions(text):
    assert voice_profile([text])["contractions"]["occurrences"] == 1


def test_no_contractions():
    assert voice_profile(["I am ready."])["contractions"]["share"] == 0


def test_fullwidth_punctuation():
    profile = voice_profile(["確認できますか？ よろしく！"])
    assert profile["questions"]["occurrences"] == 1
    assert profile["exclamations"]["occurrences"] == 1


def test_formal_markers():
    profile = voice_profile(["Dear Mira,\nI would appreciate your reply.\nSincerely,\nRowan"])
    assert profile["formality"]["score"] == 100
    assert {item["marker"] for item in profile["formality"]["markers"]} == {
        "Dear greeting",
        "Formal closing",
        "I would appreciate",
    }


def test_casual_markers():
    profile = voice_profile(["Hey Mira,\nI'm gonna send it!\nCheers,\nRowan"])
    assert profile["formality"]["score"] == 0


def test_no_markers_unknown():
    result = voice_profile(["The draft is attached."])
    assert result["formality"]["score"] is None
    assert result["formality"]["status"] == "unknown"


def test_marker_counts_once_per_message():
    result = voice_profile(["Could you review this? Could you send it?"])
    marker = next(item for item in result["formality"]["markers"] if item["marker"] == "Could you")
    assert marker["messages"] == 1


def test_greeting_names_not_retained():
    profile = voice_profile(["Hi Mira,\nReady.\nBest,\nRowan"])
    serialized = json.dumps(profile)
    assert "Mira" not in serialized and "Rowan" not in serialized


def test_thanks_in_body_not_closing():
    assert voice_profile(["Thanks for sending the outline."])["signoffs"]["usual"] == []


def test_greeting_only_at_start():
    profile = voice_profile(["The note says hi to everyone."])
    assert profile["greetings"]["usual"] == []


def test_signoff_only_near_end():
    text = "Thanks,\nFirst paragraph.\nSecond paragraph.\nThird paragraph."
    assert voice_profile([text])["signoffs"]["usual"] == []


def test_blank_messages_excluded():
    profile = voice_profile(["", " \n", "Hi Mira,\nReady."])
    assert profile["sample"] == {"messages": 1, "ignored_empty": 2}
    assert profile["greetings"]["usual"][0]["share"] == 1


@pytest.mark.parametrize("bodies", [[], ["", "  "], "Hi Mira", b"Hi Mira", None, ["Hello", None]])
def test_unknown_input(bodies):
    result = voice_profile(bodies)
    assert result["status"] == "unknown" and result["reason"]


def test_generator_input():
    assert voice_profile(iter(["Ready."]))["sample"]["messages"] == 1


def test_larger_sample_label():
    assert voice_profile(["Ready."] * 5)["status"] == "observed"


def test_frequency_ties_alphabetical():
    result = voice_profile(["Hi Mira", "Hello Oren"])
    assert [item["text"] for item in result["greetings"]["usual"]] == ["hello", "hi"]


def test_top_five_and_other_count():
    greetings = ["Hi", "Hello", "Hey", "Dear", "Good morning", "Good afternoon", "Good evening"]
    result = voice_profile([greeting + " Mira," for greeting in greetings])
    assert len(result["greetings"]["usual"]) == 5
    assert result["greetings"]["other_detected"] == 2


def test_json_compatible_and_independent_outputs():
    bodies = ["Hi Mira,\nI'm ready!\nBest,"]
    result = voice_profile(bodies)
    assert json.loads(json.dumps(result)) == result
    result["greetings"]["usual"].clear()
    assert voice_profile(bodies)["greetings"]["usual"]
    assert bodies == ["Hi Mira,\nI'm ready!\nBest,"]


def test_return_is_compact():
    result = voice_profile(["Dear Mira,\nCould you reply?\nKind regards,\nRowan"] * 1000)
    assert len(json.dumps(result)) < 2500
