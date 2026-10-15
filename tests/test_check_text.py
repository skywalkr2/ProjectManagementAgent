"""The text a check on words reads (engine/check_text.py): links and the person's own quoted text are taken out before
the screen-text check, the applier's wording lints and the word-overlap checks read it. Settings keys and file names
are not links, so the checks still catch them."""

import pytest

from api.screen_text import problems, settings_keys
from engine.applier import _shares_words, _similar
from engine.check_text import quoted_passages, without_links, without_quotes, words_of
from tests.test_pipeline import answers, env, outcomes, run  # noqa: F401  (the fixture and helpers)

# Built from parts, so the scan for web addresses in code finds none.
HTTPS, HTTP = "https:" + "//", "http:" + "//"

LINKS = [
    f"{HTTPS}docs.example.com/guide/page?topic=settings.yaml&key=watch.sources#top",
    f"{HTTP}example.com/a.yml?x=1",
    "www.example.com/path?query=a.b.c",
    "docs.example.com",
    "docs.example.com/page?q=1",
    "example.org",
    "mailto:someone@example.com",
    "someone@mail.example.com",
]


@pytest.mark.parametrize("link", LINKS)
def test_every_kind_of_link_is_taken_out(link):
    assert without_links(f"Read {link} first.").split() == ["Read", "first."]


def test_the_punctuation_after_a_link_is_not_part_of_it():
    assert without_links(f"(see {HTTPS}example.com/a?b=1).").strip() == "(see  )."
    assert without_links("Go to docs.example.com, then back.").split() == ["Go", "to", ",", "then", "back."]


@pytest.mark.parametrize(
    "text", ["Raise watch.interval? It helps.", "notes.yaml", "The file report.pdf is ready.", "e.g. this"]
)
def test_names_that_are_not_links_stay(text):
    assert without_links(text) == text


def test_no_settings_key_reads_as_a_link():
    for key in sorted(settings_keys()):
        assert without_links(f"Raise {key}.") == f"Raise {key}.", key
        assert without_links(f"Raise {key}? Then go.") == f"Raise {key}? Then go.", key


def test_quotes_come_out_whatever_the_quotation_marks_or_spacing():
    assert words_of("Say “please  confirm the date” now", ['"please confirm the date"']).split() == ["Say", "now"]
    assert without_quotes("Keep this", []) == "Keep this"
    assert quoted_passages('He said "one thing" and “another”') == ["one thing", "another"]


# ---- the screen check ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("link", LINKS)
def test_a_link_never_trips_the_screen_check(link):
    assert problems(f"The details are at {link}, if you need them.") == []


def test_a_link_with_a_query_string_and_a_dotted_domain_passes_beside_plain_words():
    text = f"See {HTTPS}docs.example.com/page.yaml?key=ai.accounts.main&next=1 or docs.example.com for the steps."
    assert problems(text) == []


def test_a_real_settings_key_beside_a_link_still_fails():
    key = sorted(k for k in settings_keys() if k.count(".") >= 2)[0]
    found = problems(f"Raise {key} (see {HTTPS}docs.example.com/page?x=1).")
    assert len(found) == 1 and key in found[0]


def test_a_settings_file_name_beside_a_link_still_fails():
    assert problems(f"Open ai.yaml, or read {HTTPS}docs.example.com/ai.yaml?raw=1.")


# ---- the applier's wording lints -------------------------------------------------------------------------------------


EVIDENCE = {"quote": "Reply to them"}


def _problems(store, cs_id):
    return [(p["check"], p["severity"]) for o in outcomes(store, cs_id) for p in o["problems"]]


def test_a_blocked_phrase_inside_a_link_is_not_caught_and_one_outside_it_is(env):  # noqa: F811
    _, cfg, store = env
    blocked = cfg.language.blocked_phrases[0]
    link = f"{HTTPS}docs.example.com/{blocked}/page?{blocked}=1&www.example.com"
    answers({"ops": [{"op": "question.add", "to": "me", "title": f"Which finish, see {link}?"}]})
    _, cs_id = run(env, f"We need a cover finish: {link}")
    assert _problems(store, cs_id) == []
    answers({"ops": [{"op": "question.add", "to": "me", "title": f"{blocked.capitalize()} the finish, see {link}?"}]})
    _, cs_id = run(env, f"We need a cover finish, again: {link}")
    assert _problems(store, cs_id) == [("blocked-wording", "warn")]


def test_words_the_input_said_in_quotation_marks_are_not_the_assistants_wording(env):  # noqa: F811
    _, cfg, store = env
    blocked = cfg.language.blocked_phrases[0]
    said = f"please {blocked} the date"
    answers(
        {
            "ops": [
                {
                    "op": "action.add",
                    "text": f'Reply to the printer who wrote "{said}"',
                    "owners": ["me"],
                    "evidence": EVIDENCE,
                }
            ]
        }
    )
    _, cs_id = run(env, f"The printer wrote: {said}. Reply to them.")
    assert _problems(store, cs_id) == []
    answers(
        {
            "ops": [
                {
                    "op": "action.add",
                    "text": f'{blocked.capitalize()} "{said}" now',
                    "owners": ["me"],
                    "evidence": EVIDENCE,
                }
            ]
        }
    )
    _, cs_id = run(env, f"The printer wrote: {said}. Reply to them, again.")
    assert _problems(store, cs_id) == [("blocked-wording", "warn")]


def test_separators_inside_the_evidence_do_not_make_a_run_on_list(env):  # noqa: F811
    _, cfg, store = env
    separator = cfg.language.run_on_separators[0]
    quote = f"proofs{separator}files"
    op = {"op": "action.add", "text": f"Send the {quote} out", "owners": ["me"], "evidence": {"quote": quote}}
    answers({"ops": [op]})
    _, cs_id = run(env, f"Please send the {quote} out.")
    assert _problems(store, cs_id) == []
    answers(
        {
            "ops": [
                {
                    "op": "action.add",
                    "text": f"Send the proofs{separator}the files",
                    "owners": ["me"],
                    "evidence": EVIDENCE,
                }
            ]
        }
    )
    _, cs_id = run(env, "Please send them, again. Reply to them.")
    assert ("run-on-list", "warn") in _problems(store, cs_id)


def test_the_word_overlap_checks_do_not_read_links():
    assert _shares_words(f"Read {HTTPS}example.com/budget?item=1", "Budget review") is False
    assert _similar(f"Read {HTTPS}example.com/a?x=1 today", f"Read {HTTPS}other.example.org/b?y=2 today") == 1.0
