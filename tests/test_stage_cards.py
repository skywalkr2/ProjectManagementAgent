"""What a card on the stages board shows beside the title (design 7.13): the first project's name, the owners in the
owner format and the due date, taken from the fields a record has, whatever its kind; a record without them has none."""

from engine.names import People
from engine.stages import card_details
from engine.storage.store import Stored


def stored(**data):
    return Stored(kind="k/x", id="X-1", version=1, deleted=False, data=data)


PEOPLE = People.from_records(
    {"PER-1": {"full_name": "Ada Example", "team": "TEAM-1"}, "PER-2": {"full_name": "Bo Example"}},
    "PER-1",
    owner_format="{full_name} ({team})",
    team_names={"TEAM-1": "Harbor"},
)
PROJECTS = {"P-1": "Harbor refit", "P-2": "Lighthouse"}


def test_a_record_with_the_fields_shows_them_the_way_the_workspace_writes_them():
    card = card_details(
        stored(projects=["P-2", "P-1"], owners=[{"person": "PER-1"}, {"person": "PER-2"}], due="2026-11-02"),
        PEOPLE,
        PROJECTS,
    )
    assert card == {"project": "Lighthouse", "owners": ["Ada Example (Harbor)", "Bo Example"], "due": "2026-11-02"}


def test_a_single_project_or_owner_field_is_read_too():
    card = card_details(stored(project="P-1", owner="PER-2"), PEOPLE, PROJECTS)
    assert card == {"project": "Harbor refit", "owners": ["Bo Example"], "due": None}


def test_a_record_without_the_fields_has_none_and_a_missing_project_is_left_out():
    assert card_details(stored(), PEOPLE, PROJECTS) == {"project": None, "owners": [], "due": None}
    assert card_details(stored(projects=["P-9"]), PEOPLE, PROJECTS)["project"] is None
    assert card_details(stored(due=""), PEOPLE, PROJECTS)["due"] is None
