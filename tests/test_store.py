import pytest

from engine.storage import ConflictError, InvalidRecord, StoreError, WriteContext

PM = WriteContext(actor="pm", trust="trusted", op="test")
EVIDENCE = {"source": "SRC-1", "quote": "done"}
AI = WriteContext(actor="assistant", trust="untrusted", op="action.close", evidence=EVIDENCE)


def person(tx, name="A Person"):
    return tx.create("person", {"full_name": name}, PM)


def test_ids_come_from_a_sequence(store):
    with store.transaction() as tx:
        assert person(tx).id == "PER-1"
        assert person(tx).id == "PER-2"


def test_deleted_ids_are_never_reused(store):
    with store.transaction() as tx:
        p = person(tx)
        tx.delete("person", p.id, PM, read_version=p.version)
        assert tx.get("person", p.id) is None
        assert tx.get("person", p.id, include_deleted=True).deleted
        assert person(tx).id == "PER-2"


def test_explicit_ids_reserve_the_sequence(store):
    with store.transaction() as tx:
        tx.create("person", {"full_name": "X"}, PM, record_id="PER-7")
        assert person(tx).id == "PER-8"
        with pytest.raises(StoreError, match="already exists"):
            tx.create("person", {"full_name": "Y"}, PM, record_id="PER-7")


def test_wrong_prefix_is_refused(store):
    with store.transaction() as tx, pytest.raises(InvalidRecord, match="not a person id"):
        tx.create("person", {"full_name": "X"}, PM, record_id="Q-1")


def test_every_changed_field_is_in_the_ledger_with_who_and_why(store):
    with store.transaction() as tx:
        p = person(tx)
        tx.update("person", p.id, {"role": "Editor", "full_name": "B Person"}, AI, read_version=1)
    entries = store.read().ledger(kind="person", record_id="PER-1")
    updates = [e for e in entries if e["version"] == 2]
    assert {e["field"] for e in updates} == {"role", "full_name"}
    role = next(e for e in updates if e["field"] == "role")
    assert role["before"] is None and role["after"] == "Editor"
    assert role["actor"] == "assistant" and role["trust"] == "untrusted"
    assert role["evidence"] == {"source": "SRC-1", "quote": "done"}


def test_a_failed_transaction_leaves_no_record_and_no_ledger(store):
    with pytest.raises(RuntimeError), store.transaction() as tx:
        person(tx)
        raise RuntimeError("boom")
    assert store.read().list("person") == []
    assert store.read().ledger() == []
    assert store.read().sequences() == {}


def test_a_stale_write_to_other_fields_merges(store):
    with store.transaction() as tx:
        p = person(tx)
        tx.update("person", p.id, {"role": "Editor"}, PM, read_version=1)
        merged = tx.update("person", p.id, {"org": "Somewhere"}, PM, read_version=1)
    assert merged.version == 3
    assert merged.data["role"] == "Editor" and merged.data["org"] == "Somewhere"


def test_a_stale_write_to_the_same_field_is_refused(store):
    with store.transaction() as tx:
        p = person(tx)
        tx.update("person", p.id, {"role": "Editor"}, PM, read_version=1)
    with store.transaction() as tx, pytest.raises(ConflictError) as err:
        tx.update("person", p.id, {"role": "Publicist"}, PM, read_version=1)
    assert err.value.fields == ["role"]


def test_no_change_writes_nothing(store):
    with store.transaction() as tx:
        p = person(tx)
        same = tx.update("person", p.id, {"full_name": "A Person"}, PM, read_version=1)
    assert same.version == 1
    assert all(e["version"] == 1 for e in store.read().ledger())


def test_records_are_validated(store):
    with store.transaction() as tx:
        with pytest.raises(InvalidRecord, match="at least one owner"):
            tx.create("action", {"text": "Do a thing"}, PM)
        held = tx.create("action", {"text": "Do a thing", "status": "held"}, PM)
        assert held.data["owners"] == []
        with pytest.raises(InvalidRecord):
            tx.create("person", {"full_name": "X", "nickname": "Y"}, PM)


def test_id_cannot_change(store):
    with store.transaction() as tx:
        p = person(tx)
        with pytest.raises(StoreError, match="id can't change"):
            tx.update("person", p.id, {"id": "PER-9"}, PM, read_version=1)
