"""Private authenticated envelopes. Keys never live in the storage/backup tree."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .settings import settings

MAGIC = b'FREA1'
MAX_ENVELOPE = 32 * 1024 * 1024
KINDS = {'revision', 'source', 'reading', 'fields', 'ai', 'run', 'config', 'training_truth', 'training_dataset'}


class VaultError(RuntimeError):
    def __init__(self, code='PRIVATE_STORAGE_UNAVAILABLE'):
        self.code = code
        super().__init__(code)


def _identity(kind, identity):
    try:
        if kind not in KINDS:
            raise ValueError
        return str(UUID(str(identity)))
    except (ValueError, TypeError, AttributeError):
        raise VaultError() from None


def _key():
    try:
        if not settings.emergency_audit_key_file:
            raise VaultError('KEY_NOT_CONFIGURED')
        path = Path(settings.emergency_audit_key_file)
        if path.is_symlink():
            raise VaultError()
        path = path.resolve(strict=True)
        if path.is_relative_to(Path(settings.storage_root).resolve()):
            raise VaultError('KEY_LOCATION_INVALID')
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != 32:
            raise VaultError('KEY_INVALID')
        if os.name != 'nt' and info.st_mode & 0o077:
            raise VaultError('KEY_PERMISSIONS_INVALID')
        value = path.read_bytes()
        if len(value) != 32:
            raise VaultError('KEY_INVALID')
        return value
    except (OSError, ValueError):
        raise VaultError() from None


def ready():
    try:
        _key()
        return True
    except VaultError:
        return False


def _aad(kind, identity):
    identity = _identity(kind, identity)
    tenant = settings.tenant_id or 'unbound-synthetic'
    return f'fire-ai-emergency-audit-v1\0{tenant}\0{kind}\0{identity}'.encode('ascii')


def seal(kind, identity, data: bytes):
    if not isinstance(data, bytes) or len(data) > MAX_ENVELOPE - 64:
        raise VaultError('PRIVATE_CONTENT_TOO_LARGE')
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(_key()).encrypt(nonce, data, _aad(kind, identity))


def open_sealed(kind, identity, data: bytes):
    if not isinstance(data, bytes) or not 33 <= len(data) <= MAX_ENVELOPE or not data.startswith(MAGIC):
        raise VaultError('PRIVATE_CONTENT_INVALID')
    try:
        return AESGCM(_key()).decrypt(data[5:17], data[17:], _aad(kind, identity))
    except (InvalidTag, ValueError):
        raise VaultError('PRIVATE_CONTENT_INTEGRITY') from None


def seal_json(kind, identity, value):
    try:
        data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError, RecursionError):
        raise VaultError('PRIVATE_CONTENT_INVALID') from None
    return seal(kind, identity, data)


def open_json(kind, identity, data, default=None):
    if data is None:
        return default
    try:
        return json.loads(open_sealed(kind, identity, data))
    except (ValueError, UnicodeError, RecursionError):
        raise VaultError('PRIVATE_CONTENT_INVALID') from None


def _path(kind, identity, *, create=False):
    identity = _identity(kind, identity)
    if kind not in {'revision', 'source'}:
        raise VaultError()
    try:
        root = Path(settings.storage_root).resolve()
        folder = root / 'emergency-audit' / kind
        for part in (root / 'emergency-audit', folder):
            if part.is_symlink():
                raise VaultError()
            if create:
                part.mkdir(mode=0o700, parents=True, exist_ok=True)
        result = folder / (identity + '.bin')
        if result.is_symlink() or not result.resolve().is_relative_to(root):
            raise VaultError()
        return result
    except (OSError, ValueError):
        raise VaultError() from None


def store_original(kind, identity, data):
    encrypted = seal(kind, identity, data)
    path = _path(kind, identity, create=True)
    created = False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        created = True
        with os.fdopen(fd, 'wb') as handle:
            handle.write(encrypted)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        if created:
            path.unlink(missing_ok=True)
        raise VaultError() from None


def read_original(kind, identity):
    path = _path(kind, identity)
    try:
        with path.open('rb') as handle:
            data = handle.read(MAX_ENVELOPE + 1)
        return open_sealed(kind, identity, data)
    except OSError:
        raise VaultError() from None


def discard_uncommitted(kind, identity):
    """Only for a failed new DB transaction, never ordinary historical deletion."""
    try:
        _path(kind, identity).unlink(missing_ok=True)
    except OSError:
        raise VaultError() from None
