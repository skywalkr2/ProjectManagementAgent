"""Encrypted backups (design 4.15, 12.1): every file of every copy is sealed when a key is set, restoring needs the key
and refuses a wrong one, and a backup made without a key is as it was."""

import hashlib
from pathlib import Path

import pytest

from engine import backup_crypto
from engine.backup import KeyNeeded, RestoreError, restore_backup, run_backup, state
from engine.cli import main
from engine.storage import Store
from engine.workspace import init_workspace, resolve
from tests.conftest import DEMO_A
from tests.test_update_restore import NOW, counts

SECRET = "a long phrase only the person knows"
SQLITE_HEADER = b"SQLite format 3\x00"


@pytest.fixture(autouse=True)
def cheap_key_derivation(monkeypatch):
    """The key derivation is made deliberately slow; tests use the smallest cost it accepts."""
    monkeypatch.setattr(backup_crypto, "KDF", {"n": 2**4, "r": 1, "p": 1})


def make_backup(tmp_path, key_reference=None):
    ws = init_workspace(tmp_path / "ws", template=DEMO_A, git=False)
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    flags = {"storage.backups.targets": [{"path": str(offsite), "label": "test"}]}
    if key_reference:
        flags["storage.backups.encrypt"] = key_reference
    cfg = ws.config(env={}, flags=flags)
    (ws.root / "texts").mkdir()
    (ws.root / "texts" / "note.md").write_text("kept text\n", encoding="utf-8")
    run_backup(ws, cfg, NOW)
    made = list(offsite.iterdir())
    return ws, cfg, (made[0] if made else None)


@pytest.fixture
def key_file(tmp_path):
    path = tmp_path / "keys" / "backup.key"
    path.parent.mkdir()
    path.write_text(SECRET + "\n", encoding="utf-8")
    return path


@pytest.fixture
def encrypted(tmp_path, key_file):
    return make_backup(tmp_path, f"file:{key_file}")


def digest(folder: Path):
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()
    }


def test_every_file_of_an_encrypted_copy_is_sealed(encrypted):
    ws, cfg, folder = encrypted
    assert backup_crypto.encrypted(folder)
    held = [p for p in folder.rglob("*") if p.is_file() and p.name != backup_crypto.MANIFEST]
    assert {p.relative_to(folder).as_posix() for p in held} >= {"cockpit.db", "texts/note.md"}
    for path in held:
        assert path.read_bytes().startswith(backup_crypto.MAGIC)
    everything = b"".join(p.read_bytes() for p in folder.rglob("*") if p.is_file())
    assert b"kept text" not in everything and SQLITE_HEADER not in everything and SECRET.encode() not in everything
    assert not list(ws.private_dir.glob("backup-*"))  # the plain copy of the database is gone


def test_restoring_with_the_key_gives_the_same_workspace(encrypted, tmp_path):
    ws, cfg, folder = encrypted
    before = digest(folder)
    target = tmp_path / "restored"
    restored = restore_backup(folder, target, SECRET)
    assert counts(target / "cockpit.db") == counts(ws.db_path)
    assert restored.ledger > 0 and (target / "texts" / "note.md").read_text() == "kept text\n"
    assert not (target / backup_crypto.MANIFEST).exists()
    opened = resolve(target)
    store = Store(opened.db_path, cfg=opened.config())
    try:
        assert len(store.read().list("person")) == counts(ws.db_path)[0]["person"]
    finally:
        store.close()
    assert digest(folder) == before  # the backup was only read
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".restore-")]


def test_a_wrong_key_is_refused_plainly_and_nothing_is_written(encrypted, tmp_path):
    _, _, folder = encrypted
    target = tmp_path / "restored"
    with pytest.raises(RestoreError, match="doesn't open this backup") as refused:
        restore_backup(folder, target, "some other phrase")
    assert not isinstance(refused.value, KeyNeeded) and not target.exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".restore-")]


def test_an_encrypted_backup_needs_a_key(encrypted, tmp_path):
    _, _, folder = encrypted
    with pytest.raises(KeyNeeded, match="needs the key"):
        restore_backup(folder, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_a_copy_that_was_changed_or_cut_short_is_refused(encrypted, tmp_path):
    _, _, folder = encrypted
    note = folder / "texts" / "note.md"
    sealed = note.read_bytes()
    note.write_bytes(sealed[:-3])
    with pytest.raises(RestoreError, match="note.md is damaged"):
        restore_backup(folder, tmp_path / "one", SECRET)
    note.write_bytes(sealed[:-1] + bytes([sealed[-1] ^ 1]))
    with pytest.raises(RestoreError, match="note.md is damaged"):
        restore_backup(folder, tmp_path / "two", SECRET)
    note.write_bytes(sealed)
    (folder / "texts" / "moved.md").write_bytes(sealed)  # sealed for another place
    with pytest.raises(RestoreError, match="moved.md is damaged"):
        restore_backup(folder, tmp_path / "three", SECRET)
    assert not (tmp_path / "one").exists() and not (tmp_path / "two").exists() and not (tmp_path / "three").exists()


def test_large_and_empty_files_survive_the_round_trip(tmp_path):
    sealer, _ = backup_crypto.create(SECRET)
    for size in (0, 1, backup_crypto.CHUNK - 1, backup_crypto.CHUNK, backup_crypto.CHUNK + 1, 2 * backup_crypto.CHUNK):
        source = tmp_path / f"plain-{size}"
        source.write_bytes(bytes(range(256)) * (size // 256) + bytes(size % 256))
        sealed, opened = tmp_path / f"sealed-{size}", tmp_path / f"opened-{size}"
        sealer.seal(source, sealed, "a/file")
        sealer.open(sealed, opened, "a/file")
        assert opened.read_bytes() == source.read_bytes()


def test_a_backup_made_without_a_key_is_unchanged(tmp_path):
    ws, cfg, folder = make_backup(tmp_path)
    assert not backup_crypto.encrypted(folder)
    assert (folder / "cockpit.db").read_bytes().startswith(SQLITE_HEADER)
    assert (folder / "texts" / "note.md").read_text() == "kept text\n"
    restored = restore_backup(folder, tmp_path / "restored")
    assert counts(restored.workspace.db_path) == counts(ws.db_path)
    assert state(ws, cfg, NOW).encrypted is False and "Encrypted" not in state(ws, cfg, NOW).message


def test_the_status_says_the_backup_is_encrypted(encrypted):
    ws, cfg, _ = encrypted
    now = state(ws, cfg, NOW)
    assert now.encrypted and now.message.endswith("Encrypted.")


def test_a_key_that_cant_be_read_fails_the_backup_and_makes_no_plain_copy(tmp_path):
    ws, cfg, folder = make_backup(tmp_path, f"file:{tmp_path / 'not-there'}")
    assert folder is None and list((tmp_path / "offsite").iterdir()) == []
    result = state(ws, cfg, NOW)
    assert "key for encrypting backups can't be read" in (result.last_error or "") and result.needs_attention


def test_the_key_is_named_by_a_reference_never_given_itself(tmp_path):
    ws = init_workspace(tmp_path / "ws", template=DEMO_A, git=False)
    with pytest.raises(Exception, match="reference to where it is kept"):
        ws.config(env={}, flags={"storage.backups.encrypt": SECRET})
    assert ws.config(env={}).storage.backups.encrypt == ""


def test_the_command_restores_with_a_key_reference_and_refuses_without_or_with_a_wrong_one(
    encrypted, tmp_path, key_file, capsys, monkeypatch
):
    _, _, folder = encrypted
    assert main(["restore", "--backup", str(folder), str(tmp_path / "none")]) == 1
    assert "needs the key it was made with" in capsys.readouterr().err
    wrong = tmp_path / "wrong.key"
    wrong.write_text("not the key")
    assert main(["restore", "--backup", str(folder), str(tmp_path / "bad"), "--key", f"file:{wrong}"]) == 1
    assert "doesn't open this backup" in capsys.readouterr().err
    assert main(["restore", "--backup", str(folder), str(tmp_path / "gone"), "--key", "file:/no/such/key"]) == 1
    assert "key can't be read" in capsys.readouterr().err
    monkeypatch.setenv("TEST_BACKUP_KEY", SECRET)
    assert main(["restore", "--backup", str(folder), str(tmp_path / "good"), "--key", "env:TEST_BACKUP_KEY"]) == 0
    assert (tmp_path / "good" / "cockpit.db").is_file()
    assert not (tmp_path / "none").exists() and not (tmp_path / "bad").exists()
