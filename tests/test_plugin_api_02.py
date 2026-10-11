"""Plugin API 0.2: declared rules on record types, lookups, validators that see the changeset, origin, delete with
Undo, event kind filters and data levels, through a small fictional plugin."""

import pytest
import yaml

from engine.config import load_config
from tests.conftest import DEMO_B, fixture_records

FIXTURE = """
from typing import Annotated, ClassVar, Literal
from engine.plugin_api import OpModel, Record, RefTo, Settings

SEEN = {"origins": [], "events": []}

class Config(Settings):
    pass

class Entry(Record):
    record_kind: ClassVar[str] = "p02/entry"
    prefix: ClassVar[str] = "ENT"
    person_only: ClassVar[dict] = {"status": ("decided",)}
    unique: ClassVar[tuple] = (("project", "slug"),)
    slug: str
    project: Annotated[str | None, RefTo("project")] = None
    people: list[Annotated[str, RefTo("person")]] = []
    follows: Annotated[str | None, RefTo("p02/entry")] = None
    status: Literal["draft", "decided"] = "draft"

class Add(OpModel):
    op: Literal["p02/add"] = "p02/add"
    writes: ClassVar[dict] = {"p02/entry": ("*",)}
    slug: str
    project: str | None = None
    people: list[str] = []
    follows: str | None = None

    def describe(self):
        return "Add the entry " + self.slug

class Decide(OpModel):
    op: Literal["p02/decide"] = "p02/decide"
    writes: ClassVar[dict] = {"p02/entry": ("status",)}
    slug: str

class Remove(OpModel):
    op: Literal["p02/remove"] = "p02/remove"
    writes: ClassVar[dict] = {"p02/entry": ("*",)}
    slug: str

def add(op, writer, cfg):
    writer.create(
        "p02/entry", {"slug": op.slug, "project": op.project, "people": op.people, "follows": op.follows}
    )

def decide(op, writer, cfg):
    entry = writer.find("p02/entry", slug=op.slug)
    writer.update("p02/entry", entry.id, {"status": "decided"}, read_version=entry.version)

def remove(op, writer, cfg):
    entry = writer.find("p02/entry", slug=op.slug)
    writer.delete("p02/entry", entry.id, read_version=entry.version)

def decide_needs_entry(op, view, origin):
    SEEN["origins"].append(origin)
    return [] if view.find("p02/entry", slug=op.slug) else ["no entry called " + op.slug]

def remove_by_keyword(op, view, *, origin):
    SEEN["origins"].append(origin)
    return []

def on_change(payload, context):
    SEEN["events"].append(payload["kind"])

def register(registrar):
    registrar.record_type(Entry)
    registrar.op(Add, "data", add)
    registrar.op(Decide, "data", decide)
    registrar.op(Remove, "data", remove)
    registrar.op_validator("p02/decide", decide_needs_entry)
    registrar.op_validator("p02/remove", remove_by_keyword)
    registrar.subscribe("record.changed", on_change)
"""


@pytest.fixture
def env(tmp_path):
    from engine.storage import Store
    from engine.workspace import init_workspace

    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    plugin = ws.root / "plugins" / "p02"
    plugin.mkdir(parents=True)
    manifest = {
        "name": "p02",
        "version": "0.1.0",
        "plugin_api": ">=0.3,<0.4",
        "description": "Plugin API 0.2 fixture",
        "entry": "fixture:register",
        "config_schema": "fixture:Config",
        "subscribes": [{"event": "record.changed", "kinds": ["p02/entry"]}],
        "provides": {
            "record_types": ["p02/entry"],
            "ops": ["p02/add", "p02/decide", "p02/remove"],
            "op_validators": ["p02/decide", "p02/remove"],
        },
    }
    (plugin / "plugin.yaml").write_text(yaml.safe_dump(manifest))
    (plugin / "fixture.py").write_text(FIXTURE)
    enabled = yaml.safe_load((ws.config_dir / "workspace.yaml").read_text())
    enabled.setdefault("plugins", {})["enabled"] = [*enabled["plugins"].get("enabled", []), "p02"]
    (ws.config_dir / "workspace.yaml").write_text(yaml.safe_dump(enabled))
    cfg = load_config(ws.config_dir, env={})
    store = Store(ws.db_path, cfg=cfg)
    assert store.plugins.active("p02"), store.plugins.status.get("p02")
    yield ws, cfg, store
    store.close()


def apply(env, ops, *, trust="trusted", pm=False):
    from engine.applier import Context, Inputs, apply_changeset
    from engine.names import People
    from engine.ops import CHANGESET

    _, cfg, store = env
    cs = CHANGESET.validate_python({"ops": ops}, context={"op_models": store.plugins.ops})
    allowed = tuple(store.plugins.ops)
    ctx = Context(store, cfg, People(store, cfg), allowed, Inputs("REQ-1", None, "", "", trust), confirmed_by_pm=pm)
    cs_id = apply_changeset(cs, [], ctx, run=None)
    return cs_id, [o["status"] for o in store.read().get("changeset", cs_id).data["ops"]]


def module(store):
    import sys

    return next(m for name, m in sys.modules.items() if name.endswith(".fixture") and hasattr(m, "SEEN"))


def project_id():
    return fixture_records(DEMO_B, "project")[0]["id"]


def test_unique_fields_and_references_are_enforced(env):
    _, _, store = env
    assert apply(env, [{"op": "p02/add", "slug": "one", "project": project_id()}])[1] == ["applied"]
    assert apply(env, [{"op": "p02/add", "slug": "one", "project": project_id()}])[1] == ["refused"]
    assert apply(env, [{"op": "p02/add", "slug": "two", "project": "PRJ-999"}])[1] == ["refused"]
    assert len(store.read().list("p02/entry")) == 1


def test_lookups_filter_in_the_database(env):
    from engine.plugin_api import ReadView

    _, _, store = env
    apply(env, [{"op": "p02/add", "slug": "a", "project": project_id()}, {"op": "p02/add", "slug": "b"}])
    view = ReadView(store.read(), "p02")
    assert [e.data["slug"] for e in view.list("p02/entry", project=project_id())] == ["a"]
    assert view.find("p02/entry", slug="b").data["project"] is None
    assert view.find("p02/entry", slug="missing") is None


def test_a_validator_sees_what_earlier_ops_in_the_same_changeset_created(env):
    # Not refused: the validator found the entry op 0 created. (Held, because only the person may decide.)
    _, statuses = apply(env, [{"op": "p02/add", "slug": "x"}, {"op": "p02/decide", "slug": "x"}])
    assert statuses == ["applied", "held"]
    assert apply(env, [{"op": "p02/decide", "slug": "never-added"}], pm=True)[1] == ["refused"]


def test_validators_are_told_who_asked(env):
    _, _, store = env
    apply(env, [{"op": "p02/add", "slug": "y"}])
    apply(env, [{"op": "p02/decide", "slug": "y"}], trust="untrusted")
    origins = module(store).SEEN["origins"]
    assert {"actor": "assistant", "trust": "untrusted", "via": "task"} in origins


def test_a_person_only_value_from_the_assistant_is_held_and_applies_when_released(env):
    from engine.applier import release

    _, cfg, store = env
    apply(env, [{"op": "p02/add", "slug": "z"}])
    cs_id, statuses = apply(env, [{"op": "p02/decide", "slug": "z"}])
    assert statuses == ["held"]
    assert store.read().list("p02/entry")[0].data["status"] == "draft"
    release(store, cfg, cs_id, 0)
    assert store.read().list("p02/entry")[0].data["status"] == "decided"


def test_delete_is_refused_while_referred_to_and_undo_brings_a_record_back(env):
    from engine.applier import undo

    _, _, store = env
    apply(env, [{"op": "p02/add", "slug": "keep", "project": project_id()}])
    project = store.read().get("project", project_id())
    delete_project = {
        "op": "record.delete",
        "record": {"kind": "project", "id": project.id},
        "read_version": project.version,
    }
    assert apply(env, [delete_project], pm=True)[1] == ["refused"]
    cs_id, statuses = apply(env, [{"op": "p02/remove", "slug": "keep"}])
    assert statuses == ["applied"] and store.read().list("p02/entry") == []
    undo(store, cs_id)
    assert [e.data["slug"] for e in store.read().list("p02/entry")] == ["keep"]


def test_record_delete_from_the_assistant_waits_for_the_person(env):
    _, _, store = env
    note = apply(env, [{"op": "note", "text": "A note to remove later."}], pm=True)
    note_id = store.read().list("note")[-1]
    op = {"op": "record.delete", "record": {"kind": "note", "id": note_id.id}, "read_version": note_id.version}
    assert note and apply(env, [op], trust="untrusted")[1] == ["held"]
    assert apply(env, [op], pm=True)[1] == ["applied"]


def test_reading_notes_never_offers_delete():
    from engine.tasks import TASKS

    assert "record.delete" not in TASKS["notes"].ops and "file.add" not in TASKS["notes"].ops


def test_an_event_subscription_can_be_limited_to_kinds(env):
    _, _, store = env
    module(store).SEEN["events"].clear()
    apply(env, [{"op": "p02/add", "slug": "e"}, {"op": "note", "text": "Not for the plugin."}], pm=True)
    assert set(module(store).SEEN["events"]) == {"p02/entry"}


def test_a_record_type_may_be_restricted_only_if_the_manifest_says_so(env):
    from engine.storage import Store

    ws, _, store = env
    fixture = ws.root / "plugins" / "p02" / "fixture.py"
    fixture.write_text(
        FIXTURE.replace("    slug: str\n", '    data_level: ClassVar[str] = "restricted"\n    slug: str\n', 1)
    )
    other = Store(ws.root / "other.db", cfg=load_config(ws.config_dir, env={}))
    assert not other.plugins.active("p02")
    reason = other.plugins.status["p02"].reason
    assert "requires.data_levels" in reason and "p02/entry" in reason
    other.close()


def test_references_inside_lists_are_enforced(env):
    _, _, store = env
    person = fixture_records(DEMO_B, "person")[0]["id"]
    assert apply(env, [{"op": "p02/add", "slug": "l1", "people": ["PER-999"]}])[1] == ["refused"]
    assert apply(env, [{"op": "p02/add", "slug": "l2", "people": [person]}])[1] == ["applied"]
    stored = store.read().get("person", person)
    delete = {"op": "record.delete", "record": {"kind": "person", "id": person}, "read_version": stored.version}
    assert apply(env, [delete], pm=True)[1] == ["refused"]


def test_an_op_names_itself_in_the_review_list(env):
    _, _, store = env
    cs_id, _ = apply(env, [{"op": "p02/add", "slug": "named"}])
    assert store.read().get("changeset", cs_id).data["ops"][0]["label"] == "Add the entry named"


def test_a_stale_delete_is_refused_not_raised(env):
    _, _, store = env
    apply(env, [{"op": "p02/add", "slug": "s"}])
    entry = store.read().list("p02/entry")[0]
    op = {"op": "record.delete", "record": {"kind": "p02/entry", "id": entry.id}, "read_version": entry.version + 1}
    assert apply(env, [op], pm=True)[1] == ["refused"]
    assert store.read().list("p02/entry")


def test_lookups_refuse_unknown_fields_and_lists_and_can_ask_for_no_project(env):
    from engine.plugin_api import ANY, ReadView
    from engine.storage import StoreError

    _, _, store = env
    apply(env, [{"op": "p02/add", "slug": "in", "project": project_id()}, {"op": "p02/add", "slug": "out"}])
    view = ReadView(store.read(), "p02")
    with pytest.raises(StoreError, match="no field 'slgu'"):
        view.list("p02/entry", slgu="in")
    with pytest.raises(StoreError, match="one value"):
        view.list("p02/entry", slug=["in", "out"])
    assert [e.data["slug"] for e in view.list("p02/entry", project=None)] == ["out"]
    assert len(view.list("p02/entry", project=ANY)) == len(view.list("p02/entry")) == 2
    assert view.find("p02/entry", slug="IN") is None


def test_a_validator_may_take_origin_as_a_keyword(env):
    _, _, store = env
    apply(env, [{"op": "p02/add", "slug": "k"}])
    assert apply(env, [{"op": "p02/remove", "slug": "k"}], pm=True)[1] == ["applied"]
    assert store.plugins.active("p02")
    assert any(o["actor"] == "pm" for o in module(store).SEEN["origins"])


def test_undo_skips_what_would_break_a_unique_or_reference_rule(env):
    from engine.applier import undo

    _, _, store = env
    apply(env, [{"op": "p02/add", "slug": "u"}])
    removed, _ = apply(env, [{"op": "p02/remove", "slug": "u"}])
    apply(env, [{"op": "p02/add", "slug": "u"}])
    report = undo(store, removed)
    assert report.skipped and "slug=u" in report.skipped[0]["reason"]
    assert len(store.read().list("p02/entry")) == 1

    created, _ = apply(env, [{"op": "p02/add", "slug": "first"}])
    first = store.read().find("p02/entry", {"slug": "first"})[0]
    apply(env, [{"op": "p02/add", "slug": "second", "follows": first.id}])
    report = undo(store, created)
    assert report.skipped and "referred to" in report.skipped[0]["reason"]
    assert store.read().get("p02/entry", first.id) is not None


@pytest.mark.parametrize(
    "subscription, reason",
    [
        ({"event": "question.answered", "kinds": ["note"]}, "carries no kind"),
        ({"event": "record.changed", "kinds": ["p02/entyr"]}, "p02/entyr"),
        ({"event": "record.changed", "kinds": ["other/thing"]}, "other/thing"),
        ({"event": "file.added", "kinds": ["note"]}, "note"),
    ],
)
def test_event_filters_are_checked_when_the_plugin_loads(env, subscription, reason):
    from engine.storage import Store

    ws, _, _ = env
    path = ws.root / "plugins" / "p02" / "plugin.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["subscribes"] = [subscription]
    path.write_text(yaml.safe_dump(manifest))
    fixture = ws.root / "plugins" / "p02" / "fixture.py"
    fixture.write_text(FIXTURE.replace('"record.changed", on_change', f'"{subscription["event"]}", on_change'))
    other = Store(ws.root / "other.db", cfg=load_config(ws.config_dir, env={}))
    assert not other.plugins.active("p02")
    assert reason in other.plugins.status["p02"].reason
    other.close()
