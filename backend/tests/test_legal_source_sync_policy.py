"""Synthetic source-policy dispatch tests; no collector or network is executed."""
import importlib.util
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def sync_fixture(tmp_path, monkeypatch):
    from app.db import Base
    from app.models import LegalJurisdiction, LegalSource, LegalSyncRun

    script = Path(__file__).resolve().parents[2] / 'scripts/run_legal_source_sync.py'
    spec = importlib.util.spec_from_file_location('synthetic_legal_source_sync', script)
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    engine = create_engine('sqlite+pysqlite:///' + str(tmp_path / 'synthetic.db'))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(sync, 'SessionLocal', sessions)
    calls = []
    workspaces = []
    processes = []

    def collector(source, work, **kwargs):
        calls.append((source.legal_source_id, source.adapter_type, kwargs))
        return {'importer': {'inserted_versions': 0, 'unchanged_documents': 0, 'failure_count': 0}}

    monkeypatch.setattr(sync, 'sync_egov', collector)
    monkeypatch.setattr(sync, 'sync_official_html', collector)
    # Any accidental subprocess bypass is a failure, not a real acquisition.
    def refuse_subprocess(*args, **kwargs):
        processes.append(args)
        raise AssertionError('synthetic test must not execute a subprocess')
    monkeypatch.setattr(sync.subprocess, 'run', refuse_subprocess)

    def synthetic_workspace(**kwargs):
        workspaces.append(kwargs)
        return nullcontext(str(tmp_path / 'unused-collector-workspace'))

    monkeypatch.setattr(sync.tempfile, 'TemporaryDirectory', synthetic_workspace)
    stamp = datetime.now(timezone.utc)

    def source(enabled, mode, adapter='egov_v2'):
        with sessions() as db:
            jurisdiction = LegalJurisdiction(code='SYN', name='Synthetic jurisdiction', jurisdiction_type='national')
            db.add(jurisdiction)
            db.flush()
            row = LegalSource(jurisdiction_id=jurisdiction.jurisdiction_id, source_code='SYN',
                              name='Synthetic source', source_type='national_law', adapter_type=adapter,
                              base_url='https://synthetic.invalid/', enabled=enabled, update_mode=mode,
                              last_checked_at=stamp, last_success_at=stamp, last_full_sync_at=stamp,
                              coverage_status='complete', expected_document_count=3, captured_document_count=3)
            db.add(row)
            db.commit()
            identity = row.legal_source_id
        with sessions() as db:
            row = db.get(LegalSource, identity)
            before = {column.key: getattr(row, column.key) for column in LegalSource.__table__.columns}
        return identity, before

    yield SimpleNamespace(sync=sync, sessions=sessions, calls=calls, source=source,
                          source_model=LegalSource, run_model=LegalSyncRun,
                          workspaces=workspaces, processes=processes)
    engine.dispose()


DENIED = [(False, 'online'), (True, 'bundle'), (True, 'manual'), (True, 'unknown')]


@pytest.mark.parametrize('enabled,mode', DENIED)
def test_denied_source_never_dispatches_collector(sync_fixture, enabled, mode):
    fixture = sync_fixture
    identity, _ = fixture.source(enabled, mode)
    rejection = None
    try:
        fixture.sync.sync_source(identity, allow_bootstrap=True)
    except RuntimeError as exc:
        rejection = exc
    assert fixture.calls == [], 'source policy was bypassed before collector dispatch'
    assert rejection is not None, 'disabled/non-online source must be rejected'


@pytest.mark.parametrize('enabled,mode', DENIED)
def test_denied_source_retains_sync_state(sync_fixture, enabled, mode):
    fixture = sync_fixture
    identity, before = fixture.source(enabled, mode)
    try:
        fixture.sync.sync_source(identity, allow_bootstrap=True)
    except RuntimeError:
        pass
    with fixture.sessions() as db:
        count = db.scalar(select(func.count()).select_from(fixture.run_model))
        row = db.get(fixture.source_model, identity)
        after = {column.key: getattr(row, column.key) for column in fixture.source_model.__table__.columns}
        assert (after, count) == (before, 0), 'rejected source state and run inventory must remain unchanged'


@pytest.mark.parametrize('enabled,mode', DENIED)
@pytest.mark.parametrize('adapter', ['egov_v2', 'official_html_crawl'])
@pytest.mark.parametrize('allow_bootstrap', [False, True])
def test_denied_source_rejects_before_workspace_or_process(sync_fixture, enabled, mode, adapter, allow_bootstrap):
    fixture = sync_fixture
    identity, _ = fixture.source(enabled, mode, adapter)
    rejection = None
    try:
        fixture.sync.sync_source(identity, allow_bootstrap=allow_bootstrap)
    except RuntimeError as exc:
        rejection = exc
    assert (fixture.workspaces, fixture.processes, fixture.calls) == ([], [], []), 'policy rejection must precede resource dispatch'
    assert rejection is not None


def test_missing_source_retains_existing_error_without_resources_or_runs(sync_fixture):
    fixture = sync_fixture
    with pytest.raises(RuntimeError, match='^legal source not found$'):
        fixture.sync.sync_source('00000000-0000-0000-0000-000000000000', allow_bootstrap=True)
    assert (fixture.workspaces, fixture.processes, fixture.calls) == ([], [], [])
    with fixture.sessions() as db:
        assert db.scalar(select(func.count()).select_from(fixture.run_model)) == 0


@pytest.mark.parametrize('adapter', ['egov_v2', 'official_html_crawl'])
@pytest.mark.parametrize('allow_bootstrap', [False, True])
def test_enabled_online_explicit_sync_bypasses_frequency_only(sync_fixture, adapter, allow_bootstrap):
    fixture = sync_fixture
    identity, _ = fixture.source(True, 'online', adapter)
    with fixture.sessions() as db:
        assert not fixture.sync.is_due(db.get(fixture.source_model, identity), datetime.now(timezone.utc))
    result = fixture.sync.sync_source(identity, allow_bootstrap=allow_bootstrap)
    assert result['source_id'] == identity and result['status'] == 'completed'
    expected_options = {'allow_bootstrap': allow_bootstrap} if adapter == 'egov_v2' else {}
    assert fixture.calls == [(identity, adapter, expected_options)]
    assert len(fixture.workspaces) == 1 and fixture.processes == []
    with fixture.sessions() as db:
        run = db.scalar(select(fixture.run_model))
        assert run.status == 'completed' and run.error_count == 0
        assert db.scalar(select(func.count()).select_from(fixture.run_model)) == 1
        row = db.get(fixture.source_model, identity)
        assert row.last_success_at is not None and row.coverage_status == 'complete'
