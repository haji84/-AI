"""Saved observations and current-source-authorized Human transitions."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .models import now_utc
from .statistics_models import StatisticsReport, StatisticsEvidence, StatisticsHistory
from .statistics_sources import required_permissions, pin_period
from .settings import settings
from . import statistics_service as service


def get_report(db, key):
    try:
        key = str(UUID(key))
    except (ValueError, TypeError):
        raise HTTPException(404, 'Statistics report not found')
    row = db.get(StatisticsReport, key, populate_existing=True)
    if row is None:
        raise HTTPException(404, 'Statistics report not found')
    return row


def public_lifecycle_time(value: datetime | None):
    """Serialize only statistics lifecycle times produced by server-owned now_utc.

    SQLite drops tzinfo from these known UTC fields. Source/legacy event times
    have separate admission contracts and must never use this serializer.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def public_report(row):
    return {'report_id': row.report_id, 'version': row.version, 'state': row.state,
            'predecessor_id': row.predecessor_id, 'successor_id': row.successor_id,
            'created_at': public_lifecycle_time(row.created_at), 'confirmed_at': public_lifecycle_time(row.confirmed_at),
            'snapshot': deepcopy(row.snapshot)}


def report_codes(row, command='statistics.read', export=False):
    return {'statistics.read', command} | required_permissions(row.metric_keys, export=export)


def append_history(db, identity, row, action, note=None):
    db.add(StatisticsHistory(report_id=row.report_id, version=row.version, action=action, actor_id=identity.user_id, note=note))
    service.audit_statistics(db, identity, action, report_id=row.report_id, version=row.version, metric_keys=row.metric_keys)


def insert_report(db, identity, capture, keys, predecessor_id=None):
    row = StatisticsReport(snapshot=capture.public, metric_keys=list(keys), created_by=identity.user_id, predecessor_id=predecessor_id)
    db.add(row); db.flush()
    db.add(StatisticsEvidence(report_id=row.report_id, evidence=capture.evidence, fingerprint=capture.fingerprint))
    append_history(db, identity, row, 'saved')
    return row


def commit(db):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Statistics lifecycle conflict; reload the report') from exc


def create_report(db, user, query):
    codes = {'statistics.read', 'statistics.record'} | required_permissions(query.metric_keys)
    identity = service.preflight(db, user, codes)
    capture = service.capture_in_snapshot(identity, pin_period(query, settings.statistics_business_timezone), query.metric_keys)
    with service.final_session(identity, codes, mutation=True) as final:
        row = insert_report(final, identity, capture, query.metric_keys)
        commit(final)
        return public_report(row)


def prepare_existing(db, user, key, command):
    identity = service.preflight(db, user, {'statistics.read', command})
    with service.final_session(identity, {'statistics.read', command}) as reader:
        row = get_report(reader, key)
        codes = report_codes(row, command)
        service.authorize(reader, identity, codes)
        frozen = {'keys': list(row.metric_keys), 'period': deepcopy(row.snapshot['period']), 'fingerprint': reader.get(StatisticsEvidence, row.report_id).fingerprint}
    return identity, codes, frozen


def transition(db, user, key, payload, *, replacement=False):
    identity, codes, frozen = prepare_existing(db, user, key, 'statistics.record')
    capture = service.capture_in_snapshot(identity, frozen['period'], frozen['keys'])
    with service.final_session(identity, codes, mutation=True) as final:
        row = get_report(final, key)
        if row.version != payload.expected_version or row.successor_id is not None:
            raise HTTPException(409, 'Statistics lifecycle conflict; reload the report')
        if not replacement:
            if row.state != 'saved':
                raise HTTPException(409, 'Statistics report is already Human-confirmed')
            if capture.fingerprint != frozen['fingerprint']:
                raise HTTPException(409, 'Source observations changed; create a replacement before confirmation')
            changes = {'state': 'confirmed', 'confirmed_by': identity.user_id, 'confirmed_at': now_utc()}
            target = row
        else:
            target = insert_report(final, identity, capture, frozen['keys'], predecessor_id=row.report_id)
            changes = {'successor_id': target.report_id}
        changes['version'] = payload.expected_version + 1
        changed = final.execute(update(StatisticsReport).where(StatisticsReport.report_id == row.report_id, StatisticsReport.version == payload.expected_version, StatisticsReport.successor_id.is_(None)).values(**changes))
        if changed.rowcount != 1:
            raise HTTPException(409, 'Statistics lifecycle conflict; reload the report')
        final.refresh(row)
        append_history(final, identity, row, 'replaced' if replacement else 'confirmed', payload.reason if replacement else payload.review_note)
        commit(final)
        return public_report(target)
