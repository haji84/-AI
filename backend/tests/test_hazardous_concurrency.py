"""Actual PostgreSQL transaction and migration evidence. SQLite is never a substitute."""
import os
from pathlib import Path
import shutil
import threading
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_hazardous_register import hazardous_env, learning_environment, install, record, action, detail
from test_workforce_concurrency import compete


@pytest.fixture
def hazardous_pg(hazardous_env):
    client, engine, refs = hazardous_env
    if engine.dialect.name != 'postgresql':
        pytest.skip('real PostgreSQL row-lock interleaving runs in CI')
    return client, engine, refs


def test_competing_evidence_confirmations_have_one_winner(hazardous_pg):
    client, _, refs = hazardous_pg
    parent = install(client, refs)
    row = record(client, parent, refs)
    request = (f"/hazardous/installations/{parent['installation_id']}/records/{row['record_id']}/confirm",
               {'expected_installation_version': 1, 'expected_version': 1, 'reason': 'Synthetic concurrent review', 'human_acknowledged': True})
    assert sorted(compete(client, [request, request])) == [200, 409]
    shown = detail(client, parent)
    assert shown['evidence_records'][0]['confirmation_current'] is True
    assert len([event for event in shown['history'] if event['action'] == 'record.confirm']) == 1


def test_retirement_and_confirmation_serialize_installation_facts(hazardous_pg):
    client, _, refs = hazardous_pg
    parent = install(client, refs)
    row = record(client, parent, refs)
    confirm = (f"/hazardous/installations/{parent['installation_id']}/records/{row['record_id']}/confirm",
               {'expected_installation_version': 1, 'expected_version': 1, 'reason': 'Synthetic review', 'human_acknowledged': True})
    retire = (f"/hazardous/installations/{parent['installation_id']}/retire",
              {'expected_version': 1, 'reason': 'Synthetic closure', 'human_acknowledged': True})
    results = compete(client, [confirm, retire])
    assert 200 in results and all(status in (200, 409) for status in results), results
    shown = detail(client, parent)
    assert shown['status'] == 'retired'
    assert all(not row['confirmation_current'] for row in shown['evidence_records'])


def test_competing_revisions_leave_one_current_tip(hazardous_pg):
    client, _, refs = hazardous_pg
    parent = install(client, refs)
    old = action(client, parent, record(client, parent, refs), 'confirm')
    revisions = [action(client, parent, old, 'revisions', 201) for _ in range(2)]
    requests = [(f"/hazardous/installations/{parent['installation_id']}/records/{row['record_id']}/confirm",
                 {'expected_installation_version': 1, 'expected_version': 1, 'reason': 'Synthetic correction', 'human_acknowledged': True}) for row in revisions]
    assert sorted(compete(client, requests)) == [200, 409]
    shown = detail(client, parent)
    assert len([row for row in shown['evidence_records'] if row['status'] == 'confirmed']) == 1
    assert len([event for event in shown['history'] if event['action'] == 'record.supersede']) == 1


def test_original_change_while_confirmation_waits_cannot_confirm_old_review(hazardous_pg, monkeypatch):
    from fastapi.testclient import TestClient
    from app import hazardous_service
    from app.models import Document
    from app.settings import settings
    client, engine, refs = hazardous_pg
    parent = install(client, refs)
    row = record(client, parent, refs)
    waiting = threading.Event()
    responses = []
    errors = []
    original_access = hazardous_service.document_access
    def observed_access(db, user, identity, lock=False):
        if identity == refs['proof'] and lock:
            waiting.set()
        return original_access(db, user, identity, lock)
    monkeypatch.setattr(hazardous_service, 'document_access', observed_access)
    def confirm():
        try:
            with TestClient(client.app) as other:
                other.cookies.update(client.cookies)
                response = other.post(f"/hazardous/installations/{parent['installation_id']}/records/{row['record_id']}/confirm", json={'expected_installation_version': 1, 'expected_version': 1, 'reason': 'Synthetic concurrent original review', 'human_acknowledged': True})
                responses.append(response.status_code)
        except BaseException as error:
            errors.append(error)
    worker = threading.Thread(target=confirm)
    with Session(engine) as db:
        source = db.scalar(select(Document).where(Document.document_id == refs['proof']).with_for_update())
        worker.start()
        assert waiting.wait(timeout=15), 'confirmation did not reach the locked original'
        raw = b'Changed synthetic original during queued confirmation'
        (Path(settings.storage_root) / source.storage_path).write_bytes(raw)
        source.sha256 = sha256(raw).hexdigest()
        db.commit()
    worker.join(timeout=20)
    assert not errors and not worker.is_alive(), errors
    assert responses == [409]
    shown = detail(client, parent)
    assert shown['evidence_records'][0]['status'] == 'draft'
    assert not any(event['action'] == 'record.confirm' for event in shown['history'])


def test_database_guards_preserve_history_and_confirmed_evidence(hazardous_pg):
    client, engine, refs = hazardous_pg
    parent = install(client, refs)
    row = action(client, parent, record(client, parent, refs), 'confirm')
    statements = [
        "UPDATE hazardous_history SET reason='tampered'",
        'DELETE FROM hazardous_history',
        "UPDATE hazardous_records SET title='tampered', version=version+1",
        'DELETE FROM hazardous_records',
        'DELETE FROM hazardous_installations',
        "UPDATE hazardous_installations SET materials='[{\"quantity\":\"1.0000001\",\"quantity_unit\":\"L\",\"name\":\"Synthetic\"}]', version=version+1",
    ]
    for statement in statements:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(statement))
    assert detail(client, parent)['evidence_records'][0]['source_snapshot'] == row['source_snapshot']


def test_migration052_upgrades_existing_rows_and_reruns_cleanly(tmp_path):
    base = os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not base:
        pytest.skip('real PostgreSQL upgrade/rerun runs in CI')
    from app.migrations import apply_migrations
    migrations = Path(__file__).resolve().parents[2] / 'db/migrations'
    historical = tmp_path / 'historical'; historical.mkdir()
    for source in migrations.glob('*.sql'):
        if source.name < '052': shutil.copy(source, historical / source.name)
    database = 'fi_hazardous_' + uuid4().hex[:16]
    cluster = create_engine(make_url(base).set(database='postgres'), isolation_level='AUTOCOMMIT')
    target = make_url(base).set(database=database).render_as_string(hide_password=False)
    engine = None
    with cluster.connect() as connection:
        connection.exec_driver_sql('CREATE DATABASE ' + database)
    try:
        apply_migrations(target, historical)
        engine = create_engine(target)
        identity = str(uuid4())
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO facilities(building_id,name,status,version) VALUES (:id,'Synthetic pre-052 facility','active',7)"), {'id': identity})
        assert apply_migrations(target, migrations) == ['052_hazardous_materials_register.sql']
        assert apply_migrations(target, migrations) == []
        with engine.connect() as connection:
            assert connection.execute(text('SELECT version FROM facilities WHERE building_id=:id'), {'id': identity}).scalar_one() == 7
            assert connection.execute(text('SELECT COUNT(*) FROM hazardous_history')).scalar_one() == 0
    finally:
        if engine: engine.dispose()
        with cluster.connect() as connection:
            connection.exec_driver_sql('DROP DATABASE ' + database + ' WITH (FORCE)')
        cluster.dispose()
