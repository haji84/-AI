"""Live work pointers; source services remain authoritative for business state."""
from collections import Counter
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from . import assets_service, inquiries_service, operations_service, violation_corrections
from .assets_models import AssetLoan, AssetLot, OperationalAsset
from .authz import permission_codes
from .models import FeatureFlag
from .operations_models import Vehicle, VehicleService
from .violation_models import CorrectiveAction, ViolationCase
from .work_queue_schemas import Navigation, Provenance, WorkQueueItem, WorkQueueResponse

ASSET_LABELS = {
    'pressure_test': '耐圧試験', 'use': '使用期限', 'calibration': '校正',
    'service': '整備', 'expiry': 'ロット期限', 'loan_return': '貸出返却',
}
FLEET_LABELS = {
    'inspection': '車両点検', 'service': '車両整備',
    'service_mileage': '走行距離による整備', 'unresolved_fault': '未解決の故障',
}


def _personal_relationships(row, user):
    relationships = []
    if getattr(row, 'created_by', None) == user.user_id:
        relationships.append('created_by_me')
    if user.employee_id and getattr(row, 'borrower_employee_id', None) == user.employee_id:
        relationships.append('borrowed_by_me')
    return relationships


def _item(*, module, kind, title, source_type, source, status, as_of,
          permissions, navigation, source_api, due_on=None, relationships=None,
          overdue=None, parent=None):
    source_id = getattr(source, list(source.__table__.primary_key.columns)[0].name)
    provenance = Provenance(source_api=source_api, as_of=as_of, source_version=source.version)
    if parent is not None:
        provenance.parent_source_type, provenance.parent_source_id, provenance.parent_source_version = parent
    return WorkQueueItem(
        key=f'{module}:{kind}:{source_id}', module=module, kind=kind, title=title,
        source_type=source_type, source_id=source_id, source_version=source.version,
        status=status, due_on=due_on,
        overdue=bool(due_on and due_on < as_of) if overdue is None else overdue,
        relationships=relationships or ['shared_deadline'], required_permissions=sorted(permissions),
        navigation=Navigation(**navigation), provenance=provenance,
    )


def _assets(db, user, as_of, days):
    through = as_of + timedelta(days=days)
    for alert in assets_service.alerts(db, user, as_of, days):
        asset = db.get(OperationalAsset, alert['asset_id'])
        # The canonical loan alert also includes inactive parents; a home pointer
        # must not keep retired assets in the user's work list.
        if asset is None or not asset.active:
            continue
        kind = alert['kind']
        source, source_type, parent = asset, 'asset', None
        permissions = {'asset.read'}
        if kind == 'loan_return':
            source = db.get(AssetLoan, alert['loan_id'])
            if source is None or source.outstanding_quantity <= 0:
                continue
            lot = db.get(AssetLot, source.lot_id)
            if lot is None or not lot.active:
                continue
            source_type = 'asset_loan'
            permissions.add('asset.borrower.read')
            status = 'outstanding'
            due_on = source.due_on
        elif kind == 'expiry':
            source = db.get(AssetLot, alert['lot_id'])
            if source is None or not source.active:
                continue
            source_type, status = 'asset_lot', 'active'
            due_on = source.expires_on
        else:
            status = 'active'
            due_on = getattr(asset, f'next_{kind}_on')
        # Source rows can change after the alert query. Keep the deadline and
        # version from the same record read, and reapply the requested horizon.
        if due_on is None or due_on > through:
            continue
        if source is not asset:
            parent = ('asset', asset.asset_id, asset.version)
        yield _item(module='operational_assets', kind=kind,
            title=f'{ASSET_LABELS[kind]}: {asset.name[:100]}', source_type=source_type,
            source=source, status=status, as_of=as_of, permissions=permissions,
            navigation={'surface': 'asset', 'id': asset.asset_id}, source_api='/assets/alerts',
            due_on=due_on, relationships=_personal_relationships(source, user), parent=parent)


def _fleet(db, user, as_of, through):
    for alert in operations_service.alerts(db, as_of):
        vehicle = db.get(Vehicle, alert['vehicle_id'])
        if vehicle is None or not vehicle.active:
            continue
        kind = alert['kind']
        due_on = None
        if kind in ('inspection', 'service'):
            due_on = getattr(vehicle, f'next_{kind}_on')
            if due_on is None or due_on > through:
                continue
        if kind == 'service_mileage' and (vehicle.next_service_odometer is None or vehicle.odometer < vehicle.next_service_odometer):
            continue
        source, source_type, parent, status = vehicle, 'vehicle', None, 'active'
        if kind == 'unresolved_fault':
            source = db.get(VehicleService, alert['service_id'])
            if source is None or source.status == 'cancelled' or source.resolved_by_service_id:
                continue
            source_type, status = 'vehicle_service', source.status
            parent = ('vehicle', vehicle.vehicle_id, vehicle.version)
        relationships = _personal_relationships(source, user)
        if not relationships and due_on is None:
            relationships = ['available_to_my_role']
        yield _item(module='fleet', kind=kind, title=f'{FLEET_LABELS[kind]}: {vehicle.code[:100]}',
            source_type=source_type, source=source, status=status, as_of=as_of,
            permissions={'fleet.read'}, navigation={'surface': 'vehicle', 'id': vehicle.vehicle_id},
            source_api='/operations/alerts', due_on=due_on,
            overdue=True if kind == 'service_mileage' else None,
            relationships=relationships, parent=parent)


def _corrections(db, user, as_of, through):
    statement = select(CorrectiveAction, ViolationCase).join(
        ViolationCase, CorrectiveAction.case_id == ViolationCase.case_id
    ).where(ViolationCase.status.in_(violation_corrections.ACTIVE_CASES),
        CorrectiveAction.status.not_in(('completed', 'cancelled')), CorrectiveAction.due_on <= through)
    for action, case in db.execute(statement):
        visible = violation_corrections.visible(db, user, action)
        yield _item(module='violations', kind='corrective_action', title=f'改善措置: {action.action_id[:8]}',
            source_type='corrective_action', source=action, status=visible['status'], as_of=as_of,
            permissions={'violation.read'}, navigation={'surface': 'violation', 'id': case.case_id},
            source_api='/violations/corrections', due_on=action.due_on,
            relationships=_personal_relationships(action, user), parent=('violation', case.case_id, case.version))


def _inquiries(db, user, permissions, as_of):
    # list_rows applies the full live inquiry/evidence/document permission closure
    # before even reading a title, calculating counts, or choosing a page.
    for inquiry in inquiries_service.list_rows(db, user):
        if inquiry.status == 'approved':
            continue
        relationships = _personal_relationships(inquiry, user)
        required = inquiries_service.permission_closure(db, [('inquiry', inquiry.inquiry_id)])
        kind = 'draft'
        label = '照会下書き'
        actionable = {'draft': 'inquiry.review', 'reviewed': 'inquiry.approve'}.get(inquiry.status)
        if actionable in permissions:
            relationships.append('available_to_my_role')
            required.add(actionable)
            kind = 'review' if inquiry.status == 'draft' else 'approval'
            label = '照会レビュー' if inquiry.status == 'draft' else '照会承認'
        if not relationships:
            continue
        # Evidence can change after list_rows authorizes its result. Recheck the
        # recomputed closure and current role rights before exposing the pointer.
        if not required <= permission_codes(db, user.user_id):
            continue
        yield _item(module='inquiries', kind=kind, title=f'{label}: {inquiry.question[:100]}',
            source_type='inquiry', source=inquiry, status=inquiry.status, as_of=as_of,
            permissions=required, navigation={'surface': 'inquiry', 'id': inquiry.inquiry_id},
            source_api='/inquiries', relationships=relationships)


def list_work_queue(db, user, *, as_of=None, days=30, scope='all', limit=50, offset=0):
    """Filter live source views before counts/page; no cross-source snapshot is claimed.

    Sources are read sequentially under the caller's ordinary transaction isolation.
    Concurrent changes can appear on the next refresh; counts describe the pointers
    selected by this request, not one atomic business-state snapshot.
    """
    flags = dict(db.execute(select(FeatureFlag.key, FeatureFlag.enabled).where(
        FeatureFlag.key.in_([f'module.{code}.enabled' for code in (
            'work_queue', 'operational_assets', 'fleet', 'violations', 'inquiries')]))).all())

    def enabled(module):
        return flags.get(f'module.{module}.enabled', True)

    if not enabled('work_queue'):
        raise HTTPException(404, 'work queue disabled', headers={'Cache-Control': 'no-store'})
    as_of = as_of or assets_service.business_today()
    try:
        through = as_of + timedelta(days=days)
    except OverflowError:
        raise HTTPException(422, 'requested date horizon exceeds supported dates') from None
    permissions = permission_codes(db, user.user_id)
    items = []
    providers = (
        ('operational_assets', 'asset.read', lambda: _assets(db, user, as_of, days)),
        ('fleet', 'fleet.read', lambda: _fleet(db, user, as_of, through)),
        ('violations', 'violation.read', lambda: _corrections(db, user, as_of, through)),
        ('inquiries', 'inquiry.read', lambda: _inquiries(db, user, permissions, as_of)),
    )
    for module, permission, provider in providers:
        if enabled(module) and permission in permissions:
            items.extend(provider())
    if scope == 'related':
        items = [item for item in items if {'created_by_me', 'borrowed_by_me'}.intersection(item.relationships)]
    items.sort(key=lambda item: (not item.overdue, item.due_on or date.max,
        item.module, item.kind, item.source_id, item.key))
    return WorkQueueResponse(as_of=as_of, through=through, business_timezone=str(assets_service.BUSINESS_TIMEZONE),
        scope=scope, limit=limit, offset=offset, total=len(items), counts=dict(sorted(Counter(item.module for item in items).items())),
        items=items[offset:offset+limit])
