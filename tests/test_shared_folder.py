"""A synced folder others can change (`storage.sync.shared`): what is found there is outside content, not the person's
own words, but the person's review is unchanged and nothing applies without them."""

from tests.test_outside import apply, book, env, page, pick_up, write  # noqa: F401  (env is a fixture)


def test_edits_from_a_shared_folder_are_untrusted_content_the_person_still_reviews(env):  # noqa: F811
    from engine import outside
    from engine.applier import release

    ws, cfg, store, folder = env
    _, section = book(env)
    write(env)
    cfg.storage.sync.shared = True
    page(folder).write_text(page(folder).read_text().replace("at dawn", "before dawn").replace("order: 3", "order: 4"))
    assert outside.pick_up(store, ws, cfg)
    view = store.read()
    version = [v for v in view.list("text_version") if v.data["status"] == "pending"][-1]
    assert version.data["note"] == outside.NOTE_SHARED
    changeset = [c for c in view.list("changeset") if c.data["summary"].startswith("Edited in the shared folder")][-1]
    assert changeset.data["trust"] == "untrusted"
    request = view.get("request", changeset.data["request"])
    assert request.data["origin"] == "input" and request.data["state"] == "review"
    [edit] = [o for o in changeset.data["ops"] if o["op"]["op"] == "record.edit"]
    assert edit["status"] == "held" and outside.HELD_SHARED in edit["reason"]
    assert view.get("p15/section", section.id).data["order"] == 3  # nothing applied without the person
    rows = view.sql("SELECT trust FROM ledger WHERE changeset=?", (changeset.id,)).fetchall()
    assert rows and {r["trust"] for r in rows} == {"untrusted"}
    release(store, cfg, changeset.id, edit["index"])
    assert store.read().get("p15/section", section.id).data["order"] == 4


def test_edits_from_a_folder_only_the_person_uses_stay_the_persons_own(env):  # noqa: F811
    from engine import outside

    ws, cfg, store, folder = env
    book(env)
    write(env)
    assert cfg.storage.sync.shared is False
    page(folder).write_text(page(folder).read_text().replace("at dawn", "before dawn"))
    outside.pick_up(store, ws, cfg)
    changeset = [c for c in store.read().list("changeset") if c.data["summary"].startswith("Edited outside")][-1]
    assert changeset.data["trust"] == "trusted"
    assert store.read().get("request", changeset.data["request"]).data["origin"] == "pm"


def test_a_working_copy_from_a_shared_folder_is_untrusted_too(env):  # noqa: F811
    from engine import working

    _, cfg, store, folder = env
    _, section = book(env)
    copy = working.hand_out(store, cfg, "p15/lines", section.kind, section.id, "body")
    write(env)
    cfg.storage.sync.shared = True
    handed = store.read().get("file", copy.data["file"]).data["name"]
    path = folder / "Lake Ferries" / "working" / handed
    path.write_text(path.read_text().replace("at dawn", "at noon"))
    pick_up(env)
    back = store.read().get("working_copy", copy.id)
    assert back.data["status"] == "returned"
    assert store.read().get("text_version", back.data["proposal"]).data["status"] == "pending"
    changeset = [c for c in store.read().list("changeset") if c.data["summary"].startswith("Took back")][-1]
    assert changeset.data["trust"] == "untrusted" and not changeset.data["reviewed"]


def test_the_shared_setting_is_live_and_off_by_default():
    from engine.config import load_config
    from engine.worker import is_live
    from tests.conftest import DEMO_A, DEMO_B

    assert is_live("storage.sync.shared")
    for demo in (DEMO_A, DEMO_B):
        assert load_config(demo / "config", env={}).storage.sync.shared is False
