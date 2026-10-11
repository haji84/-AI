"""Authenticated envelope for one complete department-bound format2 backup pair.

Real recipient enrollment and private-key custody remain operational Human Gates.
This module never generates or persists a recipient private key.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import stat
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Collection, Iterator
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


ENVELOPE_VERSION = 1
ALGORITHM = "X25519-HKDF-SHA256-AES-256-GCM"
PAYLOAD_NAME = "backup.enc"
ENVELOPE_NAME = "envelope.json"
_AAD_FIELDS = (
    "version",
    "algorithm",
    "tenant_id",
    "key_id",
    "backup_id",
    "ephemeral_public_key",
    "nonce",
    "ciphertext_file",
)
_OUTER_FIELDS = frozenset((*_AAD_FIELDS, "tag"))
_ALLOWED_PAYLOAD_MEMBERS = frozenset(
    {"manifest.json", "database.dump", "database.sqlite3", "storage.tar.gz"}
)


class EncryptedBackupError(ValueError):
    """Fail-closed encrypted backup validation error."""


def _canonical_uuid(value: str, label: str) -> str:
    try:
        parsed = str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise EncryptedBackupError(f"invalid {label}") from None
    if parsed != value:
        raise EncryptedBackupError(f"non-canonical {label}")
    return parsed


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: object, label: str, length: int) -> bytes:
    if not isinstance(value, str):
        raise EncryptedBackupError(f"invalid envelope {label}")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise EncryptedBackupError(f"invalid envelope {label}") from None
    if len(decoded) != length:
        raise EncryptedBackupError(f"invalid envelope {label}")
    return decoded


def _canonical_json(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _key_id(public_key: X25519PublicKey) -> str:
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return "x25519-sha256:" + hashlib.sha256(raw).hexdigest()


def _regular_key_file(path: Path, *, private: bool) -> Path:
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as exc:
        raise EncryptedBackupError("key file unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise EncryptedBackupError("key must be a regular file, not a link")
    if private and info.st_mode & 0o077:
        raise EncryptedBackupError("private key permissions must deny group and other access")
    return path.resolve()


def _load_public_key(path: Path) -> X25519PublicKey:
    path = _regular_key_file(path, private=False)
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (OSError, ValueError, TypeError):
        raise EncryptedBackupError("invalid recipient public key") from None
    if not isinstance(key, X25519PublicKey):
        raise EncryptedBackupError("recipient key must be X25519")
    return key


def _load_private_key(path: Path) -> X25519PrivateKey:
    path = _regular_key_file(path, private=True)
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, ValueError, TypeError):
        raise EncryptedBackupError("invalid decryption private key") from None
    if not isinstance(key, X25519PrivateKey):
        raise EncryptedBackupError("decryption key must be X25519")
    return key


def key_id_for_private_key(path: Path) -> str:
    return _key_id(_load_private_key(path).public_key())


def _is_within(path: Path, parent: Path) -> bool:
    return path == parent or path.is_relative_to(parent)


def _derive_key(shared_secret: bytes, tenant_id: str, backup_id: str) -> bytes:
    context = f"fire-ai-encrypted-backup-v1\0{tenant_id}\0{backup_id}".encode("ascii")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=context).derive(shared_secret)


def _write_payload_archive(source: Path, target: Path) -> None:
    manifest_path = source / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        raise EncryptedBackupError("format2 manifest unavailable") from None
    if manifest.get("format_version") != 2:
        raise EncryptedBackupError("encrypted backup requires format2")
    database_file = manifest.get("database_file")
    if database_file not in {"database.dump", "database.sqlite3"}:
        raise EncryptedBackupError("invalid format2 database file")
    names = ("manifest.json", database_file, "storage.tar.gz")
    if set(path.name for path in source.iterdir()) != set(names):
        raise EncryptedBackupError("format2 folder contains unexpected or missing entries")
    for name in names:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise EncryptedBackupError("format2 files must be regular files")
    with tarfile.open(target, "w", format=tarfile.PAX_FORMAT) as archive:
        for name in names:
            archive.add(source / name, arcname=name, recursive=False)


def _encrypt_payload(source: Path, target: Path, key: bytes, nonce: bytes, aad: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(aad)
    with source.open("rb") as input_file, target.open("xb") as output_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            output_file.write(encryptor.update(chunk))
        output_file.write(encryptor.finalize())
    return encryptor.tag


def encrypt_format2_backup(
    source: Path,
    destination: Path,
    *,
    tenant_id: str,
    recipient_public_key: Path,
    backup_id: str,
    forbidden_key_roots: Collection[Path] = (),
) -> Path:
    """Atomically publish an authenticated encrypted envelope under destination."""
    tenant_id = _canonical_uuid(tenant_id, "tenant UUID")
    backup_id = _canonical_uuid(backup_id, "backup identity")
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    public_path = _regular_key_file(recipient_public_key, private=False)
    forbidden_roots = (source, destination, *(Path(root).resolve() for root in forbidden_key_roots))
    if any(_is_within(public_path, root) for root in forbidden_roots):
        raise EncryptedBackupError("recipient key must remain separate from backup data and destination")
    public_key = _load_public_key(public_path)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("tenant_id") != tenant_id:
        raise EncryptedBackupError("format2 backup belongs to another department")

    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    final = destination / f"fire-ai-backup-{backup_id}"
    partial = destination / f".fire-ai-backup-{backup_id}.partial"
    if final.exists() or partial.exists():
        raise EncryptedBackupError("backup identity already exists")
    partial.mkdir(mode=0o700)
    try:
        with tempfile.TemporaryDirectory(prefix=".fire-ai-encrypt-") as temporary:
            payload = Path(temporary) / "payload.tar"
            _write_payload_archive(source, payload)
            ephemeral = X25519PrivateKey.generate()
            nonce = os.urandom(12)
            metadata = {
                "version": ENVELOPE_VERSION,
                "algorithm": ALGORITHM,
                "tenant_id": tenant_id,
                "key_id": _key_id(public_key),
                "backup_id": backup_id,
                "ephemeral_public_key": _b64encode(
                    ephemeral.public_key().public_bytes(
                        serialization.Encoding.Raw, serialization.PublicFormat.Raw
                    )
                ),
                "nonce": _b64encode(nonce),
                "ciphertext_file": PAYLOAD_NAME,
            }
            shared = ephemeral.exchange(public_key)
            key = _derive_key(shared, tenant_id, backup_id)
            tag = _encrypt_payload(payload, partial / PAYLOAD_NAME, key, nonce, _canonical_json(metadata))
            (partial / ENVELOPE_NAME).write_text(
                json.dumps({**metadata, "tag": _b64encode(tag)}, sort_keys=True, indent=2),
                encoding="ascii",
            )
            for path in partial.iterdir():
                path.chmod(0o600)
        partial.rename(final)
        return final
    except BaseException as exc:
        shutil.rmtree(partial, ignore_errors=True)
        if isinstance(exc, EncryptedBackupError):
            raise
        if isinstance(exc, (SystemExit, KeyboardInterrupt)):
            raise
        raise EncryptedBackupError("encrypted backup publication failed") from exc


def _load_envelope(folder: Path) -> tuple[dict, bytes]:
    try:
        entries = {path.name for path in folder.iterdir()}
    except OSError as exc:
        raise EncryptedBackupError("encrypted envelope files unavailable") from exc
    if entries != {ENVELOPE_NAME, PAYLOAD_NAME}:
        raise EncryptedBackupError("encrypted envelope files are incomplete or unexpected")
    envelope_path = folder / ENVELOPE_NAME
    if envelope_path.is_symlink() or not envelope_path.is_file():
        raise EncryptedBackupError("encrypted envelope metadata must be a regular file")
    try:
        envelope = json.loads(envelope_path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, ValueError, TypeError):
        raise EncryptedBackupError("encrypted envelope metadata unavailable") from None
    if not isinstance(envelope, dict) or set(envelope) != _OUTER_FIELDS:
        raise EncryptedBackupError("invalid encrypted envelope fields")
    if envelope.get("version") != ENVELOPE_VERSION or envelope.get("algorithm") != ALGORITHM:
        raise EncryptedBackupError("unsupported encrypted envelope")
    if envelope.get("ciphertext_file") != PAYLOAD_NAME:
        raise EncryptedBackupError("invalid encrypted payload name")
    metadata = {field: envelope[field] for field in _AAD_FIELDS}
    return metadata, _b64decode(envelope["tag"], "tag", 16)


def _extract_payload(payload: Path, output: Path) -> None:
    seen: set[str] = set()
    total = 0
    try:
        with tarfile.open(payload, "r:") as archive:
            members = archive.getmembers()
            for member in members:
                if (
                    member.name not in _ALLOWED_PAYLOAD_MEMBERS
                    or member.name in seen
                    or not member.isfile()
                    or member.issparse()
                ):
                    raise EncryptedBackupError("unsafe encrypted backup payload")
                seen.add(member.name)
                total += member.size
                if total > payload.stat().st_size:
                    raise EncryptedBackupError("encrypted backup payload exceeds authenticated bounds")
            if "manifest.json" not in seen or "storage.tar.gz" not in seen:
                raise EncryptedBackupError("encrypted format2 payload is incomplete")
            if not seen.intersection({"database.dump", "database.sqlite3"}):
                raise EncryptedBackupError("encrypted format2 database is missing")
            output.mkdir(mode=0o700)
            for member in members:
                source = archive.extractfile(member)
                if source is None:
                    raise EncryptedBackupError("encrypted payload member unavailable")
                target = output / member.name
                with source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination)
                target.chmod(0o600)
    except (OSError, tarfile.TarError) as exc:
        raise EncryptedBackupError("invalid encrypted backup payload") from exc


@contextmanager
def decrypt_encrypted_backup(
    folder: Path,
    private_key: Path,
    *,
    expected_tenant_id: str,
    staging_parent: Path,
    revoked_key_ids: Collection[str] = (),
    forbidden_key_roots: Collection[Path] = (),
) -> Iterator[Path]:
    """Yield a private format2 staging folder and erase it on every exit path."""
    expected_tenant_id = _canonical_uuid(expected_tenant_id, "tenant UUID")
    folder = Path(folder).resolve()
    staging_parent = Path(staging_parent)
    if staging_parent.is_symlink() or not staging_parent.is_dir() or staging_parent.stat().st_mode & 0o077:
        raise EncryptedBackupError("private staging parent must be a private regular directory")
    staging_parent = staging_parent.resolve()
    private_path = _regular_key_file(private_key, private=True)
    forbidden_roots = (folder.parent, staging_parent, *(Path(root).resolve() for root in forbidden_key_roots))
    if any(_is_within(private_path, root) for root in forbidden_roots):
        raise EncryptedBackupError("private key must remain separate from protected data and runtime trees")
    key = _load_private_key(private_path)
    key_id = _key_id(key.public_key())
    if key_id in set(revoked_key_ids):
        raise EncryptedBackupError("decryption key is revoked")

    temporary = Path(tempfile.mkdtemp(prefix=".fire-ai-decrypt-", dir=staging_parent))
    temporary.chmod(0o700)
    try:
        metadata, tag = _load_envelope(folder)
        tenant_id = _canonical_uuid(metadata["tenant_id"], "envelope tenant UUID")
        backup_id = _canonical_uuid(metadata["backup_id"], "backup identity")
        if folder.name != f"fire-ai-backup-{backup_id}":
            raise EncryptedBackupError("encrypted backup identity does not match its folder")
        if tenant_id != expected_tenant_id:
            raise EncryptedBackupError("encrypted backup belongs to another department")
        if metadata["key_id"] != key_id:
            raise EncryptedBackupError("encrypted backup requires another key")
        ephemeral_raw = _b64decode(metadata["ephemeral_public_key"], "ephemeral public key", 32)
        nonce = _b64decode(metadata["nonce"], "nonce", 12)
        ciphertext = folder / PAYLOAD_NAME
        if ciphertext.is_symlink() or not ciphertext.is_file():
            raise EncryptedBackupError("encrypted payload must be a regular file")
        payload = temporary / "payload.tar"
        decryptor = Cipher(
            algorithms.AES(_derive_key(key.exchange(X25519PublicKey.from_public_bytes(ephemeral_raw)), tenant_id, backup_id)),
            modes.GCM(nonce, tag),
        ).decryptor()
        decryptor.authenticate_additional_data(_canonical_json(metadata))
        try:
            with ciphertext.open("rb") as input_file, payload.open("xb") as output_file:
                for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                    output_file.write(decryptor.update(chunk))
                output_file.write(decryptor.finalize())
        except InvalidTag:
            raise EncryptedBackupError("encrypted backup authentication failed") from None
        payload.chmod(0o600)
        restored = temporary / "format2"
        _extract_payload(payload, restored)
        manifest = json.loads((restored / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("format_version") != 2 or manifest.get("tenant_id") != expected_tenant_id:
            raise EncryptedBackupError("decrypted format2 identity mismatch")
        yield restored
    except EncryptedBackupError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise EncryptedBackupError("encrypted backup validation failed") from exc
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
