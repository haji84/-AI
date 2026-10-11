import importlib.util
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from sqlalchemy import create_engine

from app.db import Base
from app import models  # noqa: F401 - register all tables with Base metadata
from app.encrypted_backup import (
    EncryptedBackupError,
    decrypt_encrypted_backup,
    encrypt_format2_backup,
    key_id_for_private_key,
)
from app.settings import Settings
from app.tenant import initialize_tenant


def script(name: str):
    path = Path(__file__).resolve().parents[2] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"encrypted_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def department(root: Path, tenant_id: str | None = None) -> Settings:
    root.mkdir()
    cfg = Settings(
        _env_file=None,
        tenant_id=tenant_id or str(uuid4()),
        trusted_hosts=["synthetic.test"],
        database_url="sqlite+pysqlite:///" + str(root / "database.sqlite3"),
        storage_root=str(root / "originals"),
    )
    engine = create_engine(cfg.database_url)
    Base.metadata.create_all(engine)
    initialize_tenant(engine, cfg, "Synthetic encrypted-backup department")
    (Path(cfg.storage_root) / "evidence.pdf").write_bytes(b"synthetic encrypted original")
    engine.dispose()
    return cfg


def write_keys(root: Path, name: str = "recipient") -> tuple[Path, Path]:
    private = X25519PrivateKey.generate()
    private_path = root / f"{name}.private.pem"
    public_path = root / f"{name}.public.pem"
    private_path.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private_path.chmod(0o600)
    public_path.write_bytes(
        private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return public_path, private_path


def format2_folder(root: Path, tenant_id: str) -> Path:
    folder = root / "format2"
    folder.mkdir(parents=True)
    (folder / "database.sqlite3").write_bytes(b"synthetic database")
    (folder / "storage.tar.gz").write_bytes(b"synthetic originals archive")
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "format_version": 2,
                "tenant_id": tenant_id,
                "database_kind": "sqlite-test-only",
                "database_file": "database.sqlite3",
                "storage_file": "storage.tar.gz",
            }
        ),
        encoding="utf-8",
    )
    return folder


def test_authenticated_envelope_round_trip_hides_complete_format2_pair(tmp_path):
    tenant_id = str(uuid4())
    source = format2_folder(tmp_path, tenant_id)
    public_key, private_key = write_keys(tmp_path)

    encrypted = encrypt_format2_backup(
        source,
        tmp_path / "published",
        tenant_id=tenant_id,
        recipient_public_key=public_key,
        backup_id=str(uuid4()),
    )

    assert sorted(path.name for path in encrypted.iterdir()) == ["backup.enc", "envelope.json"]
    published_bytes = b"".join(path.read_bytes() for path in encrypted.iterdir())
    assert b"synthetic database" not in published_bytes
    assert b"synthetic originals archive" not in published_bytes
    assert b"manifest.json" not in published_bytes
    assert private_key.read_bytes() not in published_bytes

    staging_parent = tmp_path / "private-staging"
    staging_parent.mkdir(mode=0o700)
    with decrypt_encrypted_backup(
        encrypted,
        private_key,
        expected_tenant_id=tenant_id,
        staging_parent=staging_parent,
    ) as restored:
        assert (restored / "database.sqlite3").read_bytes() == b"synthetic database"
        assert (restored / "storage.tar.gz").read_bytes() == b"synthetic originals archive"
        assert json.loads((restored / "manifest.json").read_text())["tenant_id"] == tenant_id
        assert restored.stat().st_mode & 0o077 == 0
    assert list(staging_parent.iterdir()) == []


@pytest.mark.parametrize(
    "mutation",
    ["tenant_id", "backup_id", "key_id", "ephemeral_public_key", "nonce", "tag", "ciphertext"],
)
def test_envelope_tamper_fails_closed_without_plaintext_staging(tmp_path, mutation):
    tenant_id = str(uuid4())
    public_key, private_key = write_keys(tmp_path)
    encrypted = encrypt_format2_backup(
        format2_folder(tmp_path, tenant_id),
        tmp_path / "published",
        tenant_id=tenant_id,
        recipient_public_key=public_key,
        backup_id=str(uuid4()),
    )
    if mutation == "ciphertext":
        path = encrypted / "backup.enc"
        data = bytearray(path.read_bytes())
        data[max(0, len(data) // 2)] ^= 1
        path.write_bytes(data)
    else:
        path = encrypted / "envelope.json"
        envelope = json.loads(path.read_text())
        envelope[mutation] = str(uuid4()) if mutation in {"tenant_id", "backup_id"} else "AAAA"
        path.write_text(json.dumps(envelope))
    staging_parent = tmp_path / "private-staging"
    staging_parent.mkdir(mode=0o700)

    with pytest.raises(EncryptedBackupError):
        with decrypt_encrypted_backup(
            encrypted,
            private_key,
            expected_tenant_id=tenant_id,
            staging_parent=staging_parent,
        ):
            pytest.fail("tampered envelope yielded plaintext")
    assert list(staging_parent.iterdir()) == []


def test_wrong_revoked_or_other_tenant_key_fails_closed(tmp_path):
    tenant_id = str(uuid4())
    public_key, private_key = write_keys(tmp_path, "right")
    _, wrong_private_key = write_keys(tmp_path, "wrong")
    encrypted = encrypt_format2_backup(
        format2_folder(tmp_path, tenant_id),
        tmp_path / "published",
        tenant_id=tenant_id,
        recipient_public_key=public_key,
        backup_id=str(uuid4()),
    )
    key_id = key_id_for_private_key(private_key)

    attempts = [
        (wrong_private_key, tenant_id, set()),
        (private_key, str(uuid4()), set()),
        (private_key, tenant_id, {key_id}),
    ]
    for candidate, expected_tenant, revoked in attempts:
        staging_parent = tmp_path / f"stage-{uuid4().hex}"
        staging_parent.mkdir(mode=0o700)
        with pytest.raises(EncryptedBackupError):
            with decrypt_encrypted_backup(
                encrypted,
                candidate,
                expected_tenant_id=expected_tenant,
                staging_parent=staging_parent,
                revoked_key_ids=revoked,
            ):
                pytest.fail("invalid key policy yielded plaintext")
        assert list(staging_parent.iterdir()) == []


def test_private_key_must_be_private_regular_and_separate(tmp_path):
    tenant_id = str(uuid4())
    public_key, private_key = write_keys(tmp_path)
    encrypted = encrypt_format2_backup(
        format2_folder(tmp_path, tenant_id),
        tmp_path / "published",
        tenant_id=tenant_id,
        recipient_public_key=public_key,
        backup_id=str(uuid4()),
    )
    staging_parent = tmp_path / "private-staging"
    staging_parent.mkdir(mode=0o700)

    private_key.chmod(0o644)
    with pytest.raises(EncryptedBackupError, match="permissions"):
        with decrypt_encrypted_backup(encrypted, private_key, expected_tenant_id=tenant_id, staging_parent=staging_parent):
            pass
    private_key.chmod(0o600)
    linked = tmp_path / "linked-private.pem"
    linked.symlink_to(private_key)
    with pytest.raises(EncryptedBackupError, match="regular"):
        with decrypt_encrypted_backup(encrypted, linked, expected_tenant_id=tenant_id, staging_parent=staging_parent):
            pass
    co_located = encrypted / "private.pem"
    co_located.write_bytes(private_key.read_bytes())
    co_located.chmod(0o600)
    with pytest.raises(EncryptedBackupError, match="separate"):
        with decrypt_encrypted_backup(encrypted, co_located, expected_tenant_id=tenant_id, staging_parent=staging_parent):
            pass


def test_envelope_refuses_extra_or_substituted_published_files(tmp_path):
    tenant_id = str(uuid4())
    public_key, private_key = write_keys(tmp_path)
    encrypted = encrypt_format2_backup(
        format2_folder(tmp_path / "first", tenant_id),
        tmp_path / "published-first",
        tenant_id=tenant_id,
        recipient_public_key=public_key,
        backup_id=str(uuid4()),
    )
    staging_parent = tmp_path / "private-staging"
    staging_parent.mkdir(mode=0o700)
    (encrypted / "unexpected-plaintext").write_text("must not be ignored")
    with pytest.raises(EncryptedBackupError, match="files"):
        with decrypt_encrypted_backup(encrypted, private_key, expected_tenant_id=tenant_id, staging_parent=staging_parent):
            pass
    (encrypted / "unexpected-plaintext").unlink()

    second = encrypt_format2_backup(
        format2_folder(tmp_path / "second", tenant_id),
        tmp_path / "published-second",
        tenant_id=tenant_id,
        recipient_public_key=public_key,
        backup_id=str(uuid4()),
    )
    (encrypted / "backup.enc").write_bytes((second / "backup.enc").read_bytes())
    (encrypted / "envelope.json").write_bytes((second / "envelope.json").read_bytes())
    with pytest.raises(EncryptedBackupError, match="backup identity"):
        with decrypt_encrypted_backup(encrypted, private_key, expected_tenant_id=tenant_id, staging_parent=staging_parent):
            pass
    assert list(staging_parent.iterdir()) == []


def test_truncated_ciphertext_and_public_staging_fail_closed(tmp_path):
    tenant_id = str(uuid4())
    public_key, private_key = write_keys(tmp_path)
    encrypted = encrypt_format2_backup(
        format2_folder(tmp_path, tenant_id),
        tmp_path / "published",
        tenant_id=tenant_id,
        recipient_public_key=public_key,
        backup_id=str(uuid4()),
    )
    ciphertext = encrypted / "backup.enc"
    ciphertext.write_bytes(ciphertext.read_bytes()[:-1])
    staging_parent = tmp_path / "private-staging"
    staging_parent.mkdir(mode=0o700)
    with pytest.raises(EncryptedBackupError, match="authentication"):
        with decrypt_encrypted_backup(encrypted, private_key, expected_tenant_id=tenant_id, staging_parent=staging_parent):
            pass
    staging_parent.chmod(0o755)
    with pytest.raises(EncryptedBackupError, match="private"):
        with decrypt_encrypted_backup(encrypted, private_key, expected_tenant_id=tenant_id, staging_parent=staging_parent):
            pass


def test_interrupted_encryption_never_publishes_completed_folder(tmp_path, monkeypatch):
    tenant_id = str(uuid4())
    public_key, _ = write_keys(tmp_path)
    source = format2_folder(tmp_path, tenant_id)

    def fail_after_partial(*args, **kwargs):
        raise OSError("synthetic write failure")

    monkeypatch.setattr("app.encrypted_backup._encrypt_payload", fail_after_partial)
    destination = tmp_path / "published"
    with pytest.raises(EncryptedBackupError):
        encrypt_format2_backup(
            source,
            destination,
            tenant_id=tenant_id,
            recipient_public_key=public_key,
            backup_id=str(uuid4()),
        )
    assert not destination.exists() or list(destination.iterdir()) == []


def test_signal_interruption_removes_partial_envelope(tmp_path, monkeypatch):
    tenant_id = str(uuid4())
    public_key, _ = write_keys(tmp_path)
    source = format2_folder(tmp_path, tenant_id)

    def terminate(*args, **kwargs):
        raise SystemExit(143)

    monkeypatch.setattr("app.encrypted_backup._encrypt_payload", terminate)
    destination = tmp_path / "published"
    with pytest.raises(SystemExit):
        encrypt_format2_backup(
            source,
            destination,
            tenant_id=tenant_id,
            recipient_public_key=public_key,
            backup_id=str(uuid4()),
        )
    assert not destination.exists() or list(destination.iterdir()) == []


def encrypted_cli_backup(monkeypatch, tmp_path: Path, cfg: Settings, public_key: Path) -> Path:
    backup = script("backup_phase1")
    monkeypatch.setattr(backup, "settings", cfg)
    monkeypatch.setenv("FIRE_AI_BACKUP_RECIPIENT_PUBLIC_KEY", str(public_key))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backup",
            "--destination",
            str(tmp_path / "backups"),
            "--confirm-writers-stopped",
            "--release-id",
            "encrypted-test-release",
            "--recipient-public-key-env",
            "FIRE_AI_BACKUP_RECIPIENT_PUBLIC_KEY",
        ],
    )
    backup.main()
    return next((tmp_path / "backups").iterdir())


def encrypted_cli_restore(
    monkeypatch,
    folder: Path,
    cfg: Settings,
    private_key: Path,
) -> None:
    restore = script("restore_phase1")
    monkeypatch.setattr(restore, "settings", cfg)
    monkeypatch.setenv("FIRE_AI_BACKUP_PRIVATE_KEY", str(private_key))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore",
            str(folder),
            "--target-database-url",
            cfg.database_url,
            "--target-storage-root",
            cfg.storage_root,
            "--confirm-restore",
            "--confirm-writers-stopped",
            "--expected-release-id",
            "encrypted-test-release",
            "--decryption-private-key-env",
            "FIRE_AI_BACKUP_PRIVATE_KEY",
        ],
    )
    restore.main()


def test_cli_encrypted_round_trip_reuses_format2_restore_without_plaintext_publish(
    tmp_path, monkeypatch, capsys
):
    source = department(tmp_path / "source")
    target = department(tmp_path / "target", source.tenant_id)
    (Path(target.storage_root) / "evidence.pdf").write_bytes(b"changed target")
    public_key, private_key = write_keys(tmp_path)

    folder = encrypted_cli_backup(monkeypatch, tmp_path, source, public_key)
    assert sorted(path.name for path in folder.iterdir()) == ["backup.enc", "envelope.json"]
    assert not list((tmp_path / "backups").glob(".*partial*"))
    encrypted_cli_restore(monkeypatch, folder, target, private_key)

    assert (Path(target.storage_root) / "evidence.pdf").read_bytes() == b"synthetic encrypted original"
    with sqlite3.connect(Path(target.database_url.split("///", 1)[1])) as database:
        actions = [row[0] for row in database.execute("SELECT action FROM audit_logs")]
    assert "tenant.backup.started" in actions
    assert "tenant.restore.completed" in actions
    output = capsys.readouterr()
    assert str(public_key) not in output.out + output.err
    assert str(private_key) not in output.out + output.err


def test_cli_wrong_decryption_key_leaves_database_and_originals_unchanged(tmp_path, monkeypatch):
    source = department(tmp_path / "source")
    target = department(tmp_path / "target", source.tenant_id)
    public_key, _ = write_keys(tmp_path, "right")
    _, wrong_private_key = write_keys(tmp_path, "wrong")
    folder = encrypted_cli_backup(monkeypatch, tmp_path, source, public_key)
    target_database = Path(target.database_url.split("///", 1)[1])
    before_database = target_database.read_bytes()
    before_original = (Path(target.storage_root) / "evidence.pdf").read_bytes()

    with pytest.raises(SystemExit, match="encrypted backup"):
        encrypted_cli_restore(monkeypatch, folder, target, wrong_private_key)
    assert target_database.read_bytes() == before_database
    assert (Path(target.storage_root) / "evidence.pdf").read_bytes() == before_original


def test_required_encryption_never_falls_back_when_recipient_env_is_missing(tmp_path, monkeypatch):
    cfg = department(tmp_path / "source")
    backup = script("backup_phase1")
    monkeypatch.setattr(backup, "settings", cfg)
    monkeypatch.delenv("FIRE_AI_MISSING_RECIPIENT", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backup",
            "--destination",
            str(tmp_path / "backups"),
            "--confirm-writers-stopped",
            "--release-id",
            "encrypted-test-release",
            "--recipient-public-key-env",
            "FIRE_AI_MISSING_RECIPIENT",
        ],
    )

    with pytest.raises(SystemExit, match="recipient"):
        backup.main()
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("location", ["originals", "database", "application"])
def test_backup_cli_rejects_public_recipient_in_forbidden_tree(tmp_path, monkeypatch, location):
    cfg = department(tmp_path / "source")
    public_key, _ = write_keys(tmp_path, "external")
    application_root = tmp_path / "installed-release"
    application_root.mkdir()
    roots = {
        "originals": Path(cfg.storage_root),
        "database": Path(cfg.database_url.split("///", 1)[1]).parent,
        "application": application_root,
    }
    forbidden_key = roots[location] / f"{location}.public.pem"
    forbidden_key.write_bytes(public_key.read_bytes())
    backup = script("backup_phase1")
    monkeypatch.setattr(backup, "settings", cfg)
    monkeypatch.setattr(backup, "APPLICATION_ROOT", application_root)
    monkeypatch.setenv("FIRE_AI_BACKUP_RECIPIENT_PUBLIC_KEY", str(forbidden_key))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backup",
            "--destination",
            str(tmp_path / "backups"),
            "--confirm-writers-stopped",
            "--release-id",
            "encrypted-test-release",
            "--recipient-public-key-env",
            "FIRE_AI_BACKUP_RECIPIENT_PUBLIC_KEY",
        ],
    )

    with pytest.raises(SystemExit, match="encrypted backup publication"):
        backup.main()
    assert not (tmp_path / "backups").exists() or not list((tmp_path / "backups").iterdir())


def test_encrypted_marker_without_envelope_never_falls_back_to_plain_restore(tmp_path, monkeypatch):
    source = department(tmp_path / "source")
    target = department(tmp_path / "target", source.tenant_id)
    backup = script("backup_phase1")
    monkeypatch.setattr(backup, "settings", source)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backup",
            "--destination",
            str(tmp_path / "backups"),
            "--confirm-writers-stopped",
            "--release-id",
            "encrypted-test-release",
        ],
    )
    backup.main()
    folder = next((tmp_path / "backups").iterdir())
    (folder / "backup.enc").write_bytes(b"interrupted encrypted output")
    target_database = Path(target.database_url.split("///", 1)[1])
    before_database = target_database.read_bytes()
    restore = script("restore_phase1")
    monkeypatch.setattr(restore, "settings", target)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore",
            str(folder),
            "--target-database-url",
            target.database_url,
            "--target-storage-root",
            target.storage_root,
            "--confirm-restore",
            "--confirm-writers-stopped",
            "--expected-release-id",
            "encrypted-test-release",
        ],
    )

    with pytest.raises(SystemExit, match="incomplete encrypted"):
        restore.main()
    assert target_database.read_bytes() == before_database


def test_encrypted_uuid_folder_without_pair_never_falls_back_to_plain_restore(tmp_path, monkeypatch):
    source = department(tmp_path / "source")
    target = department(tmp_path / "target", source.tenant_id)
    backup = script("backup_phase1")
    monkeypatch.setattr(backup, "settings", source)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backup",
            "--destination",
            str(tmp_path / "backups"),
            "--confirm-writers-stopped",
            "--release-id",
            "encrypted-test-release",
        ],
    )
    backup.main()
    plain = next((tmp_path / "backups").iterdir())
    disguised = plain.with_name(f"fire-ai-backup-{uuid4()}")
    plain.rename(disguised)
    target_database = Path(target.database_url.split("///", 1)[1])
    before_database = target_database.read_bytes()
    restore = script("restore_phase1")
    monkeypatch.setattr(restore, "settings", target)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore",
            str(disguised),
            "--target-database-url",
            target.database_url,
            "--target-storage-root",
            target.storage_root,
            "--confirm-restore",
            "--confirm-writers-stopped",
            "--expected-release-id",
            "encrypted-test-release",
        ],
    )

    with pytest.raises(SystemExit, match="incomplete encrypted"):
        restore.main()
    assert target_database.read_bytes() == before_database


@pytest.mark.parametrize("location", ["originals", "database", "backup", "application"])
def test_restore_cli_rejects_private_key_in_forbidden_tree(tmp_path, monkeypatch, location):
    source = department(tmp_path / "source")
    target = department(tmp_path / "target", source.tenant_id)
    public_key, private_key = write_keys(tmp_path, "separate")
    folder = encrypted_cli_backup(monkeypatch, tmp_path, source, public_key)
    application_root = tmp_path / "installed-release"
    application_root.mkdir()
    roots = {
        "originals": Path(target.storage_root),
        "database": Path(target.database_url.split("///", 1)[1]).parent,
        "backup": folder.parent,
        "application": application_root,
    }
    forbidden_key = roots[location] / f"{location}.private.pem"
    forbidden_key.write_bytes(private_key.read_bytes())
    forbidden_key.chmod(0o600)
    target_database = Path(target.database_url.split("///", 1)[1])
    before_database = target_database.read_bytes()

    restore = script("restore_phase1")
    monkeypatch.setattr(restore, "settings", target)
    monkeypatch.setattr(restore, "APPLICATION_ROOT", application_root)
    monkeypatch.setenv("FIRE_AI_BACKUP_PRIVATE_KEY", str(forbidden_key))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore",
            str(folder),
            "--target-database-url",
            target.database_url,
            "--target-storage-root",
            target.storage_root,
            "--confirm-restore",
            "--confirm-writers-stopped",
            "--expected-release-id",
            "encrypted-test-release",
            "--decryption-private-key-env",
            "FIRE_AI_BACKUP_PRIVATE_KEY",
        ],
    )

    with pytest.raises(SystemExit, match="encrypted backup validation"):
        restore.main()
    assert target_database.read_bytes() == before_database
    assert forbidden_key.is_file()


@pytest.mark.parametrize("name", ["backup_phase1", "restore_phase1"])
def test_backup_and_restore_cli_install_cleanup_signal_handler(monkeypatch, name):
    module = script(name)
    assert module.controlled_termination.__module__ == "app.termination"
    events = []

    @contextmanager
    def signal_guard():
        events.append("guard-enter")
        try:
            yield
        finally:
            events.append("guard-exit")

    monkeypatch.setattr(module, "controlled_termination", signal_guard, raising=False)
    monkeypatch.setattr(module, "_main", lambda: events.append("operation"), raising=False)

    module.main()

    assert events == ["guard-enter", "operation", "guard-exit"]


def test_postgresql_encrypted_pair_restores_separate_same_uuid_target(tmp_path, monkeypatch):
    url = os.environ.get("FIRE_AI_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("PostgreSQL encrypted backup/restore service is exercised in CI")
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from app.migrations import apply_migrations
    from app.tenant import validate_binding

    admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    database_names = ["fi_enc_source_" + uuid4().hex[:12], "fi_enc_target_" + uuid4().hex[:12]]
    engines = []
    try:
        with admin.connect() as connection:
            for name in database_names:
                connection.execute(text(f"CREATE DATABASE {name}"))
        tenant_id = str(uuid4())
        configs = []
        for index, name in enumerate(database_names):
            database_url = make_url(url).set(database=name).render_as_string(hide_password=False)
            apply_migrations(database_url, Path(__file__).resolve().parents[2] / "db" / "migrations")
            cfg = Settings(
                _env_file=None,
                production_mode=True,
                tenant_id=tenant_id,
                database_url=database_url,
                cookie_secure=True,
                trusted_hosts=["synthetic.test"],
                storage_root=str(tmp_path / f"pg-originals-{index}"),
            )
            engine = create_engine(database_url)
            engines.append(engine)
            initialize_tenant(engine, cfg, "Synthetic encrypted PostgreSQL department")
            configs.append(cfg)
        source, target = configs
        (Path(source.storage_root) / "evidence.pdf").write_bytes(b"postgres encrypted original")
        public_key, private_key = write_keys(tmp_path)

        folder = encrypted_cli_backup(monkeypatch, tmp_path, source, public_key)
        encrypted_cli_restore(monkeypatch, folder, target, private_key)

        assert validate_binding(engines[1], target)["tenant_id"] == tenant_id
        assert (Path(target.storage_root) / "evidence.pdf").read_bytes() == b"postgres encrypted original"
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as connection:
            for name in database_names:
                connection.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        admin.dispose()
