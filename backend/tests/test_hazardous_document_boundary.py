"""Synthetic originals verify only the new hazardous_evidence ownership boundary."""
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_hazardous_register import hazardous_env, learning_environment, install, record, revoke


@pytest.fixture
def boundary_env(hazardous_env):
    from app.routers import inquiries, intake, search
    client, engine, refs = hazardous_env
    for router in (inquiries.router, intake.router, search.router):
        client.app.include_router(router)
    return client, engine, refs


def upload(client, refs, label, kind='hazardous_evidence'):
    raw = (label + ' synthetic original evidence only.').encode()
    data = {'building_id': refs['building_id']}
    if kind is not None:
        data['document_type'] = kind
    response = client.post('/documents/upload', data=data, files={'file': (label + '.txt', raw, 'text/plain')})
    assert response.status_code == 201, response.text
    return response.json(), raw


def analyze(client, doc):
    response = client.post('/document-analyses', json={'document_id': doc['document_id']})
    assert response.status_code == 201, response.text
    return response.json()


def assert_original_unchanged(engine, identity, raw):
    from app.models import Document, User
    from app.settings import settings
    with Session(engine) as db:
        doc = db.get(Document, identity)
        assert doc.sha256 == sha256(raw).hexdigest()
        assert (Path(settings.storage_root) / doc.storage_path).read_bytes() == raw
        assert doc.created_by == db.scalar(select(User.user_id).where(User.username == 'learning-admin'))


@pytest.mark.parametrize('linked', [False, True])
def test_typed_original_denied_everywhere_after_hazardous_read_revocation(boundary_env, linked):
    client, engine, refs = boundary_env
    doc, raw = upload(client, refs, 'TypedBoundaryOriginal')
    parent = install(client, refs)
    if linked:
        record(client, parent, refs, document_ids=[doc['document_id']], legal_source_version_ids=[], inspection_ids=[])
    analysis = analyze(client, doc)
    revoke(engine, 'hazardous.read')
    identity = doc['document_id']
    assert client.get('/hazardous/installations/' + parent['installation_id']).status_code == 403
    for path in ('/documents/' + identity, '/documents/' + identity + '/download',
                 '/document-analyses/' + analysis['document_analysis_id']):
        response = client.get(path)
        assert response.status_code == 403, (path, response.text)
        assert identity not in response.text and 'TypedBoundaryOriginal' not in response.text
    found = client.get('/search', params={'q': 'TypedBoundaryOriginal', 'modules': 'documents'})
    assert found.status_code == 200 and found.json()['hits'] == []
    listed = client.get('/document-analyses')
    assert listed.status_code == 200 and listed.json() == []
    denied_analysis = client.post('/document-analyses', json={'document_id': identity})
    assert denied_analysis.status_code == 403, denied_analysis.text
    assert_original_unchanged(engine, identity, raw)


def test_authorized_typed_original_retains_exact_bytes_hash_and_no_store(boundary_env):
    client, engine, refs = boundary_env
    doc, raw = upload(client, refs, 'AuthorizedBoundaryOriginal')
    identity = doc['document_id']
    metadata = client.get('/documents/' + identity)
    download = client.get('/documents/' + identity + '/download')
    assert metadata.status_code == download.status_code == 200
    assert metadata.json() == doc
    assert download.content == raw
    assert metadata.headers['cache-control'] == download.headers['cache-control'] == 'no-store'
    assert metadata.json()['sha256'] == sha256(raw).hexdigest()
    analysis = analyze(client, doc)
    assert raw.decode() in analysis['extracted_text']
    assert client.get('/document-analyses/' + analysis['document_analysis_id']).status_code == 200
    found = client.get('/search', params={'q': 'AuthorizedBoundaryOriginal', 'modules': 'documents'})
    assert found.status_code == 200
    assert [hit['source_id'] for hit in found.json()['hits']] == [identity]
    assert_original_unchanged(engine, identity, raw)


@pytest.mark.parametrize('kind', [None, 'hazardous_evidence_copy'])
def test_generic_shared_original_keeps_existing_rights_when_linked(boundary_env, kind):
    client, engine, refs = boundary_env
    doc, raw = upload(client, refs, 'GenericBoundaryOriginal', kind)
    parent = install(client, refs)
    record(client, parent, refs, document_ids=[doc['document_id']], legal_source_version_ids=[], inspection_ids=[])
    previous = analyze(client, doc)
    revoke(engine, 'hazardous.read')
    identity = doc['document_id']
    assert client.get('/hazardous/installations/' + parent['installation_id']).status_code == 403
    assert client.get('/documents/' + identity).status_code == 200
    assert client.get('/documents/' + identity + '/download').content == raw
    assert client.get('/document-analyses/' + previous['document_analysis_id']).status_code == 200
    assert raw.decode() in analyze(client, doc)['extracted_text']
    found = client.get('/search', params={'q': 'GenericBoundaryOriginal', 'modules': 'documents'})
    assert found.status_code == 200 and [hit['source_id'] for hit in found.json()['hits']] == [identity]
    assert_original_unchanged(engine, identity, raw)


def test_hidden_typed_originals_do_not_consume_search_or_analysis_limit(boundary_env):
    client, engine, refs = boundary_env
    generic, _ = upload(client, refs, 'BoundaryPageVisible', None)
    visible_analysis = analyze(client, generic)
    hidden_ids = []
    for suffix in ('First', 'Second'):
        hidden, _ = upload(client, refs, 'BoundaryPageHidden' + suffix)
        hidden_ids.append(hidden['document_id'])
        analyze(client, hidden)
    # Both newer hidden rows sort ahead of the older visible row before revocation.
    authorized = client.get('/search', params={'q': 'BoundaryPage', 'modules': 'documents', 'per_module_limit': 1})
    assert authorized.json()['hits'][0]['source_id'] in hidden_ids
    revoke(engine, 'hazardous.read')
    found = client.get('/search', params={'q': 'BoundaryPage', 'modules': 'documents', 'per_module_limit': 1})
    assert found.status_code == 200
    assert [hit['source_id'] for hit in found.json()['hits']] == [generic['document_id']]
    listed = client.get('/document-analyses', params={'limit': 1})
    assert listed.status_code == 200
    assert [item['document_analysis_id'] for item in listed.json()] == [visible_analysis['document_analysis_id']]
    assert not any(identity in found.text + listed.text for identity in hidden_ids)


def test_hazardous_type_permission_flows_through_existing_inquiry_closure(boundary_env):
    from app.inquiries_models import Inquiry
    from app.inquiries_service import document_permissions
    from app.models import Document, User
    client, engine, refs = boundary_env
    doc, raw = upload(client, refs, 'TransitiveBoundaryOriginal')
    inquiry = client.post('/inquiries', json={'year': 2026, 'question': 'Synthetic hazardous source question'})
    assert inquiry.status_code == 201, inquiry.text
    inquiry_id = inquiry.json()['inquiry_id']
    evidence = client.post('/inquiries/' + inquiry_id + '/evidence', json={
        'expected_version': 1, 'source_type': 'document', 'source_id': doc['document_id'],
        'query_parameters': {}, 'excerpt': raw.decode()})
    assert evidence.status_code == 201, evidence.text
    # Synthetic import provenance exercises the existing derived-original graph.
    derived, derived_raw = upload(client, refs, 'DerivedBoundaryOriginal', 'inquiry_import_original')
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.username == 'learning-admin'))
        db.add(Inquiry(year=2026, question='Synthetic derived inquiry', created_by=user.user_id,
                       provenance={'source_document_id': derived['document_id'],
                                   'security_sources': [{'source_type': 'document', 'source_id': doc['document_id']}]}))
        db.commit()
        assert 'hazardous.read' in document_permissions(db, db.get(Document, derived['document_id']))
    assert client.get('/documents/' + derived['document_id']).status_code == 200
    revoke(engine, 'hazardous.read')
    assert client.get('/inquiries/' + inquiry_id).status_code == 403
    assert client.get('/inquiries/source/document/' + doc['document_id']).status_code == 403
    for suffix in ('', '/download'):
        assert client.get('/documents/' + derived['document_id'] + suffix).status_code == 403
    assert_original_unchanged(engine, doc['document_id'], raw)
    assert_original_unchanged(engine, derived['document_id'], derived_raw)


def test_audit_permission_retains_metadata_trace_without_original_content(boundary_env):
    # Specification §7 permits internal identifiers for audit/management rights.
    # This trace is intentionally distinct from document and Dashboard/Search access.
    from app.routers import administration
    client, engine, refs = boundary_env
    client.app.include_router(administration.router)
    doc, raw = upload(client, refs, 'PrivateAuditBoundaryFilename')
    revoke(engine, 'hazardous.read')
    assert client.get('/documents/' + doc['document_id']).status_code == 403
    response = client.get('/administration/audit', params={'action': 'document.upload'})
    assert response.status_code == 200
    assert doc['document_id'] in response.text and doc['sha256'] in response.text
    assert refs['building_id'] in response.text
    assert doc['original_filename'] not in response.text and raw.decode() not in response.text
    revoke(engine, 'audit.read')
    assert client.get('/administration/audit', params={'action': 'document.upload'}).status_code == 403
