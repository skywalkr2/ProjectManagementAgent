"""Encrypting a backup copy (design 4.15, 12.1): every file in a dated backup folder is sealed with a key made from the
secret the person keeps, so a backup that leaves their control can't be read without it.

- The key is derived once per backup from the secret with scrypt and a random salt. The folder's `encryption.json`
  holds what is needed to derive it again (the method, its cost and the salt) and a small sealed check value, so a wrong
  secret is told apart from a damaged file before anything is decrypted. It holds no secret.
- Each file is sealed in chunks with AES-GCM. A chunk's nonce is a random per-file prefix and a counter, and what each
  chunk is bound to (the file's path in the backup, its place and whether it is the last) is authenticated, so a file
  that is cut short, reordered, moved or changed fails to open.
- File names and folders are not hidden; the files' contents are.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

#: The file in a backup folder that says it is encrypted and how to derive its key.
MANIFEST = "encryption.json"
FORMAT = 1
MAGIC = b"CKBK1\n"
CHUNK = 1024 * 1024
TAG = 16
PREFIX = 8
#: The scrypt cost used for new backups; a backup records its own, and a larger one than this limit is refused.
KDF = {"n": 2**15, "r": 8, "p": 1}
MAX_COST_N = 2**20
_CHECK = b"cockpit backup key check"


class BackupKeyError(Exception):
    """The key doesn't open this backup."""


class BackupDamaged(Exception):
    """A file in an encrypted backup is cut short, changed or isn't one this backup made."""


def encrypted(folder: Path) -> bool:
    return (Path(folder) / MANIFEST).is_file()


class Sealer:
    """A key for one backup: seals files into it and opens them again."""

    def __init__(self, key: bytes):
        self._aes = AESGCM(key)

    def seal(self, source: Path, target: Path, name: str) -> None:
        """Write `source` sealed to `target`; `name` is its path in the backup, which the seal is bound to."""
        prefix = os.urandom(PREFIX)
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as reading, target.open("wb") as writing:
            writing.write(MAGIC + prefix)
            chunk, number = reading.read(CHUNK), 0
            while True:
                following = reading.read(CHUNK)
                writing.write(self._aes.encrypt(_nonce(prefix, number), chunk, _bound(name, number, not following)))
                if not following:
                    break
                chunk, number = following, number + 1

    def open(self, source: Path, target: Path, name: str) -> None:
        """Write the sealed file `source` opened to `target`. Raises `BackupDamaged` when it doesn't open."""
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as reading, target.open("wb") as writing:
            header = reading.read(len(MAGIC) + PREFIX)
            if len(header) != len(MAGIC) + PREFIX or not header.startswith(MAGIC):
                raise BackupDamaged(f"{name} isn't a file this backup made")
            prefix = header[len(MAGIC) :]
            block, number = reading.read(CHUNK + TAG), 0
            if not block:
                raise BackupDamaged(f"{name} is cut short")
            while block:
                following = reading.read(CHUNK + TAG)
                try:
                    writing.write(self._aes.decrypt(_nonce(prefix, number), block, _bound(name, number, not following)))
                except InvalidTag:
                    raise BackupDamaged(f"{name} is damaged, cut short or changed") from None
                block, number = following, number + 1

    def check_value(self) -> str:
        nonce = os.urandom(12)
        return base64.b64encode(nonce + self._aes.encrypt(nonce, _CHECK, b"check")).decode()

    def accepts(self, value: str) -> bool:
        try:
            raw = base64.b64decode(value)
            return self._aes.decrypt(raw[:12], raw[12:], b"check") == _CHECK
        except (InvalidTag, ValueError):
            return False


def _nonce(prefix: bytes, number: int) -> bytes:
    return prefix + number.to_bytes(4, "big")


def _bound(name: str, number: int, last: bool) -> bytes:
    return name.encode("utf-8") + b"\0" + number.to_bytes(4, "big") + (b"\1" if last else b"\0")


def _derive(secret: str, salt: bytes, cost: dict[str, int]) -> bytes:
    return Scrypt(salt=salt, length=32, n=cost["n"], r=cost["r"], p=cost["p"]).derive(secret.encode("utf-8"))


def create(secret: str) -> tuple[Sealer, dict[str, Any]]:
    """A key for a new backup from the person's secret, and the manifest to keep in the backup's folder."""
    salt = os.urandom(16)
    sealer = Sealer(_derive(secret, salt, KDF))
    manifest = {
        "format": FORMAT,
        "method": "scrypt+aes-256-gcm",
        **KDF,
        "salt": base64.b64encode(salt).decode(),
        "check": sealer.check_value(),
    }
    return sealer, manifest


def write_manifest(folder: Path, manifest: dict[str, Any]) -> None:
    (Path(folder) / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def open_backup(folder: Path, secret: str) -> Sealer:
    """The key for an encrypted backup folder. Raises `BackupKeyError` when the secret isn't the one it was made with
    and `BackupDamaged` when the folder's manifest can't be read."""
    try:
        manifest = json.loads((Path(folder) / MANIFEST).read_text(encoding="utf-8"))
        cost = {k: int(manifest[k]) for k in ("n", "r", "p")}
        salt = base64.b64decode(manifest["salt"])
        check = str(manifest["check"])
        if (
            manifest.get("format") != FORMAT
            or cost["n"] > MAX_COST_N
            or cost["n"] < 2
            or cost["r"] < 1
            or cost["p"] < 1
        ):
            raise ValueError("unknown format")
        sealer = Sealer(_derive(secret, salt, cost))
    except (OSError, ValueError, KeyError, TypeError):
        raise BackupDamaged("the backup's encryption notes can't be read") from None
    if not sealer.accepts(check):
        raise BackupKeyError("that key doesn't open this backup")
    return sealer


def seal_tree(sealer: Sealer, root: Path, target: Path, prefix: str) -> None:
    """Seal every file under `root` into `target`, each at the same relative path. `prefix` is the folder's name in the
    backup, so a file keeps its place in what the seal is bound to."""
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = f"{prefix}/{path.relative_to(root).as_posix()}"
            sealer.seal(path, target / path.relative_to(root), relative)


def open_tree(sealer: Sealer, folder: Path, target: Path) -> None:
    """Open every sealed file in a backup folder into `target` at the same relative paths."""
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file() and path.name != MANIFEST:
            relative = path.relative_to(folder).as_posix()
            sealer.open(path, target / relative, relative)
