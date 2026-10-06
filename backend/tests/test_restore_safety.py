import hashlib
import importlib.util
import io
import json
import sqlite3
import sys
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'restore_phase1.py'
spec = importlib.util.spec_from_file_location('restore_tool', SCRIPT)
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


def bundle(tmp_path, member='storage/originals/example.txt', data=b'original'):
    folder = tmp_path / 'backup'
    folder.mkdir()
    with sqlite3.connect(folder / 'database.sqlite3') as db:
        db.execute('CREATE TABLE evidence(value TEXT)')
        db.execute("INSERT INTO evidence VALUES ('backup')")
    with tarfile.open(folder / 'storage.tar.gz', 'w:gz') as tf:
        item = tarfile.TarInfo(member)
        item.size = len(data)
        tf.addfile(item, io.BytesIO(data))
    manifest = {'database_kind': 'sqlite-test-only', 'database_file': 'database.sqlite3',
                'storage_file': 'storage.tar.gz'}
    for kind in ('database', 'storage'):
        manifest[kind + '_sha256'] = hashlib.sha256((folder / manifest[kind + '_file']).read_bytes()).hexdigest()
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    return folder


def run(monkeypatch, folder, target_db, target_storage):
    monkeypatch.setattr(sys, 'argv', ['restore', str(folder), '--target-database-url',
        'sqlite+pysqlite:///' + str(target_db), '--target-storage-root', str(target_storage), '--confirm-restore'])
    restore.main()


def test_restore_keeps_neighbor_storage_untouched(tmp_path, monkeypatch):
    folder = bundle(tmp_path)
    neighbor = tmp_path / 'storage'
    neighbor.mkdir()
    (neighbor / 'important.txt').write_text('unrelated tenant')
    target = tmp_path / 'restore-storage'
    run(monkeypatch, folder, tmp_path / 'target.db', target)
    assert (neighbor / 'important.txt').read_text() == 'unrelated tenant'
    assert (target / 'originals/example.txt').read_bytes() == b'original'
    assert not (target / 'important.txt').exists()


@pytest.mark.parametrize('member', ['storage/../../escape', '/absolute', 'wrong-root/file'])
def test_invalid_archive_does_not_touch_db_or_storage(tmp_path, monkeypatch, member):
    folder = bundle(tmp_path, member=member)
    target = tmp_path / 'restore-storage'
    target.mkdir()
    (target / 'kept').write_text('existing')
    target_db = tmp_path / 'target.db'
    with sqlite3.connect(target_db) as db:
        db.execute('CREATE TABLE existing(value TEXT)')
    before = target_db.read_bytes()
    with pytest.raises(SystemExit):
        run(monkeypatch, folder, target_db, target)
    assert target_db.read_bytes() == before
    assert (target / 'kept').read_text() == 'existing'


def test_manifest_cannot_point_outside_backup(tmp_path):
    folder = bundle(tmp_path)
    outside = tmp_path / 'other.sqlite3'
    outside.write_bytes((folder / 'database.sqlite3').read_bytes())
    path = folder / 'manifest.json'
    m = json.loads(path.read_text())
    m['database_file'] = '../other.sqlite3'
    path.write_text(json.dumps(m))
    with pytest.raises(SystemExit):
        restore.verify_manifest(folder)


def test_backup_cannot_be_restore_storage_target(tmp_path, monkeypatch):
    folder = bundle(tmp_path)
    before = (folder / 'manifest.json').read_bytes()
    with pytest.raises(SystemExit):
        run(monkeypatch, folder, tmp_path / 'target.db', folder)
    assert (folder / 'manifest.json').read_bytes() == before


def test_target_db_must_not_be_under_replaced_storage(tmp_path, monkeypatch):
    folder = bundle(tmp_path)
    target = tmp_path / 'restore-storage'
    target.mkdir()
    with pytest.raises(SystemExit):
        run(monkeypatch, folder, target / 'database.sqlite3', target)
    assert not (target / 'database.sqlite3').exists()
