"""Synthetic-only ciphertext and integrity tests for audit originals."""
import os
from uuid import uuid4

import pytest

from app import emergency_vault as vault
from app.settings import settings


@pytest.fixture
def configured(tmp_path, monkeypatch):
    key = tmp_path / 'external-key'
    key.write_bytes(os.urandom(32)); key.chmod(0o600)
    monkeypatch.setattr(settings, 'emergency_audit_key_file', str(key))
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path / 'storage'))
    monkeypatch.setattr(settings, 'tenant_id', None)
    return tmp_path


def test_private_bytes_and_json_roundtrip_without_plaintext(configured):
    identity = str(uuid4()); payload = b'SYNTHETIC_PRIVATE_ORIGINAL'
    vault.store_original('revision', identity, payload)
    stored = list((configured / 'storage').rglob('*.bin'))
    assert len(stored) == 1 and payload not in stored[0].read_bytes()
    assert vault.read_original('revision', identity) == payload
    encrypted = vault.seal_json('fields', identity, {'text': payload.decode()})
    assert payload not in encrypted
    assert vault.open_json('fields', identity, encrypted)['text'] == payload.decode()


def test_wrong_identity_tenant_tampering_and_missing_key_fail_closed(configured, monkeypatch):
    identity = str(uuid4()); data = vault.seal('reading', identity, b'synthetic')
    with pytest.raises(vault.VaultError):
        vault.open_sealed('reading', str(uuid4()), data)
    with pytest.raises(vault.VaultError):
        vault.open_sealed('reading', identity, data[:-1] + bytes([data[-1] ^ 1]))
    monkeypatch.setattr(settings, 'tenant_id', str(uuid4()))
    with pytest.raises(vault.VaultError):
        vault.open_sealed('reading', identity, data)
    monkeypatch.setattr(settings, 'emergency_audit_key_file', None)
    with pytest.raises(vault.VaultError):
        vault.seal('reading', identity, b'synthetic')


def test_storage_is_immutable_and_rejects_paths_symlinks_insecure_keys(configured, monkeypatch):
    identity = str(uuid4()); vault.store_original('revision', identity, b'one')
    with pytest.raises(vault.VaultError):
        vault.store_original('revision', identity, b'two')
    with pytest.raises(vault.VaultError):
        vault.store_original('../escape', identity, b'two')
    target = configured / 'outside'; target.mkdir()
    (configured / 'storage' / 'emergency-audit' / 'source').symlink_to(target)
    with pytest.raises(vault.VaultError):
        vault.store_original('source', str(uuid4()), b'three')
    if os.name != 'nt':
        (configured / 'external-key').chmod(0o644)
        with pytest.raises(vault.VaultError):
            vault.seal('reading', identity, b'synthetic')
