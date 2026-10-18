import copy
import json
from dataclasses import FrozenInstanceError

import pytest

from engine.release_check import newer_release


def release(version="1.1", **changes):
    result = {
        "version": version,
        "date": "2027-01-05",
        "notes": "Fictional reminder improvements.",
        "download_url": "https" + "://downloads.example.com/fictional-build.zip",
        "sha256": "a" * 64,
    }
    result.update(changes)
    return result


def test_newest_version_not_feed_order():
    feed = [release("1.3"), release("1.2"), release("1.10"), release("1.9")]
    assert newer_release("1.0", feed).version == "1.10"


def test_date_does_not_override_version():
    feed = [release("1.2", date="2028-01-01"), release("1.3", date="2027-01-01")]
    assert newer_release("1.0", feed).version == "1.3"


@pytest.mark.parametrize("feed", [[], [release("0.9")], [release("1.0")], [release("1.0.0")]])
def test_none_when_no_newer_release(feed):
    assert newer_release("1.0", feed) is None


@pytest.mark.parametrize("version", ["2.0a1", "2.0b2", "2.0rc1", "2.0.dev1"])
def test_prereleases_excluded_by_default(version):
    assert newer_release("1.0", [release(version)]) is None
    assert newer_release("1.0", [release(version)], True).version == version


def test_stable_selected_when_prerelease_hidden():
    assert newer_release("1.0", [release("1.2"), release("2.0rc1")]).version == "1.2"


def test_final_newer_than_installed_candidate():
    assert newer_release("2.0rc1", [release("2.0")]).version == "2.0"


def test_post_release():
    assert newer_release("1.0", [release("1.0.post1")]).version == "1.0.post1"


def test_local_version_uses_library_ordering():
    assert newer_release("1.0", [release("1.0+fictional.1")]).version == "1.0+fictional.1"


def test_epoch_uses_library_ordering():
    assert newer_release("99.0", [release("1!1.0")]).version == "1!1.0"


@pytest.mark.parametrize("checksum", [None, "", "a" * 63, "a" * 65, "g" * 64, " a" * 32, 123])
def test_bad_checksum_refused(checksum):
    assert newer_release("1.0", [release(sha256=checksum)]) is None


def test_missing_checksum_refused():
    item = release()
    del item["sha256"]
    assert newer_release("1.0", [item]) is None


def test_bad_newest_does_not_hide_valid_older_update():
    assert newer_release("1.0", [release("2.0", sha256=""), release("1.2")]).version == "1.2"


def test_uppercase_checksum_normalized():
    assert newer_release("1.0", [release(sha256="A" * 64)]).sha256 == "a" * 64


@pytest.mark.parametrize("serialized", [str, bytes])
def test_json_feed(serialized):
    text = json.dumps([release()])
    feed = text if serialized is str else text.encode("utf-8")
    assert newer_release("1.0", feed).version == "1.1"


@pytest.mark.parametrize("feed", ["not JSON", "{}", {}, None, 42])
def test_bad_envelope_raises(feed):
    with pytest.raises(ValueError):
        newer_release("1.0", feed)


def test_duplicate_json_fields_raise():
    with pytest.raises(ValueError):
        newer_release("1.0", '[{"version":"1.1","version":"1.2"}]')


@pytest.mark.parametrize("current", ["", "version next", None])
def test_unknown_current_raises(current):
    with pytest.raises(ValueError):
        newer_release(current, [])


def test_invalid_release_version_skipped():
    assert newer_release("1.0", [release("next"), release("1.2")]).version == "1.2"


@pytest.mark.parametrize("published", ["2027-02-30", "tomorrow", "2027-01-05T10:00:00", ""])
def test_bad_dates_skipped(published):
    assert newer_release("1.0", [release(date=published)]) is None


def test_aware_timestamp_accepted():
    assert newer_release("1.0", [release(date="2027-01-05T10:00:00Z")]).date == "2027-01-05T10:00:00Z"


@pytest.mark.parametrize(
    "address",
    [
        "",
        "relative.zip",
        "file:/tmp/fictional.zip",
        "http" + "://downloads.example.com/fictional-build.zip",
        "https" + "://",
        "https" + "://example.com:99999/a",
        "https" + "://rowan:fictional@example.com/a",
        "https" + "://example.com/a\n",
    ],
)
def test_bad_address_skipped(address):
    assert newer_release("1.0", [release(download_url=address)]) is None


def test_conflicting_newest_duplicate_raises():
    with pytest.raises(ValueError):
        newer_release("1.0", [release("1.1"), release("1.1.0", sha256="b" * 64)])


def test_equivalent_spelling_duplicates_are_stable():
    a, b = release("1.1"), release("1.1.0")
    assert newer_release("1.0", [a, b]) == newer_release("1.0", [b, a])


def test_identical_duplicates():
    assert newer_release("1.0", [release(), release()]).version == "1.1"


def test_empty_notes_allowed():
    assert newer_release("1.0", [release(notes="")]).notes == ""


def test_invalid_entries_do_not_block_valid_ones():
    assert newer_release("1.0", [None, "fictional", {}, release()]).version == "1.1"


def test_inputs_unchanged_output_frozen():
    feed = [release()]
    before = copy.deepcopy(feed)
    result = newer_release("1.0", feed)
    assert feed == before
    with pytest.raises(FrozenInstanceError):
        result.version = "9.0"


def test_prerelease_flag_must_be_boolean():
    with pytest.raises(ValueError):
        newer_release("1.0", [], "yes")
