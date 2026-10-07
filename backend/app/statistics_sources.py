"""Code-owned source selectors; private evidence never doubles as a public projection."""
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from .models import AuditLog, EmergencyCase, EmergencyPatient, FireInvestigationCase, now_utc
from .operations_models import Incident, Dispatch, VehicleTrip

QUERY_VERSION = 'observed-statistics-v1'
DATE_BASIS_VERSION = 'local-inclusive-date-v1'
SOURCE_PERMISSIONS = {'emergency': 'emergency.report.read', 'operations': 'incident.aggregate', 'fleet': 'fleet.aggregate'}
EXPORT_PERMISSIONS = {'emergency': 'emergency.report.export', 'operations': 'incident.export', 'fleet': 'fleet.export'}


def definition(key, label, module, unit, grain, basis, description):
    return {'key': key, 'label': label, 'source_module': module, 'unit': unit, 'grain': grain,
            'denominator': None, 'date_basis': basis, 'definition': description, 'definition_version': QUERY_VERSION}


DEFINITIONS = {row['key']: row for row in [
    definition('emergency.cases', '救急事案件数', 'emergency', '件', 'case', 'emergency_cases.call_date (DATE)', '選択日付に該当する救急事案。傷病者のない事案を含みます。'),
    definition('emergency.patient_records', '救急傷病者記録数', 'emergency', '記録', 'patient_record', 'parent emergency_cases.call_date (DATE)', '選択日付の事案に属する重複のない傷病者記録。実人数とは異なります。'),
    definition('operations.incidents', '活動事案件数', 'operations', '件', 'incident', 'incident occurrence or linked source occurrence', '選択日付の有効な活動事案。連携救急のDATE、連携火災または活動事案の記録時刻を使用します。'),
    definition('operations.dispatches', '出動記録数', 'operations', '記録', 'dispatch', 'parent incident occurrence or linked source occurrence', '選択日付の全親事案に属する取消以外の出動記録。親事案の現在の有効状態とは独立です。'),
    definition('operations.approved_dispatches', '承認済出動記録数', 'operations', '記録', 'dispatch', 'parent incident occurrence or linked source occurrence', '選択日付の全親事案に属する承認済出動記録。'),
    definition('fleet.trips', '車両運行記録数', 'fleet', '記録', 'trip', 'operation_vehicle_trips.started_at (timestamp)', '選択日付に開始した運行記録。現在の車両の有効状態にかかわらず含みます。'),
    definition('fleet.distance_km', '車両運行距離', 'fleet', 'km', 'trip', 'operation_vehicle_trips.started_at (timestamp)', '同じ選択運行記録の終了距離計と開始距離計の差をDecimalで合計します。'),
]}


def required_permissions(keys, *, export=False):
    modules = {DEFINITIONS[key]['source_module'] for key in keys}
    return {SOURCE_PERMISSIONS[module] for module in modules} | ({EXPORT_PERMISSIONS[module] for module in modules} if export else set())


def canonical(value):
    def scalar(value):
        if isinstance(value, datetime) and value.tzinfo is not None:
            return value.astimezone(timezone.utc).isoformat()
        return value.isoformat() if isinstance(value, (date, datetime, time)) else str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=scalar)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def row_evidence(row, contribution=None):
    data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    result = {'table': row.__tablename__, 'version': getattr(row, 'version', None), 'content_hash': digest(data)}
    if contribution is not None:
        result['contribution'] = str(contribution)
    return result


def row_id(row):
    return str(getattr(row, list(row.__table__.primary_key)[0].name))


def pin_period(query, zone):
    try:
        local_zone = ZoneInfo(zone)
        start = datetime.combine(query.start_date, time.min, local_zone).astimezone(timezone.utc)
        end = datetime.combine(query.end_date + timedelta(days=1), time.min, local_zone).astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise HTTPException(422, 'Date range cannot be represented in the business timezone') from exc
    return {'start_date': query.start_date.isoformat(), 'end_date': query.end_date.isoformat(),
            'business_timezone': zone, 'start_at_utc': start.isoformat(), 'end_before_utc': end.isoformat(),
            'date_basis_version': DATE_BASIS_VERSION}


@dataclass(frozen=True)
class Capture:
    public: dict
    evidence: dict
    fingerprint: str


class Selection:
    """One population holds both contributions and private lineage."""
    def __init__(self, key):
        self.key = key
        self.selected = {}
        self.dependencies = {}
        self.excluded = {}
        self.limitations = set()

    def depend(self, row):
        if row is not None:
            self.dependencies[row.__tablename__ + ':' + row_id(row)] = row_evidence(row)

    def add(self, row, contribution=1):
        self.selected[row_id(row)] = row_evidence(row, contribution)

    def exclude(self, row, reason):
        self.excluded[row_id(row)] = {**row_evidence(row), 'reason': reason}

    def projections(self):
        spec = DEFINITIONS[self.key]
        total = sum((Decimal(row['contribution']) for row in self.selected.values()), Decimal('0'))
        value = str(total.quantize(Decimal('0.1'))) if self.key == 'fleet.distance_km' else str(int(total))
        counts = Counter(row['reason'] for row in self.excluded.values())
        public = {**spec, 'status': 'observed', 'value': value, 'coverage_status': 'unknown',
                  'exclusions': [{'reason': reason, 'count': count, 'grain': spec['grain'], 'scope': 'department_all_dates'} for reason, count in sorted(counts.items())],
                  'limitations': ['記録された観測値です。対象期間の記録が完全であることは確認していません。', *sorted(self.limitations)]}
        evidence = {'selected': self.selected, 'dependencies': self.dependencies, 'excluded': self.excluded}
        return public, evidence


class Selector:
    def __init__(self, db, period):
        self.db, self.period = db, period
        self.dialect = db.get_bind().dialect.name
        self.start, self.end = (date.fromisoformat(period[k]) for k in ['start_date', 'end_date'])
        self.start_at, self.end_at = (datetime.fromisoformat(period[k]) for k in ['start_at_utc', 'end_before_utc'])
        self.admissions = {}

    def admitted_audit(self, row):
        if self.dialect != 'sqlite':
            return None
        table = row.__tablename__
        if table not in self.admissions:
            action = {'operation_incidents': 'incident.create', 'operation_vehicle_trips': 'fleet.trip.create'}[table]
            self.admissions[table] = {audit.entity_id: audit for audit in self.db.scalars(
                select(AuditLog).where(AuditLog.action == action, AuditLog.entity_type == table,
                                      AuditLog.success.is_(True), AuditLog.user_id.is_not(None)).order_by(AuditLog.audit_id))}
        audit = self.admissions[table].get(row_id(row))
        if isinstance(row, VehicleTrip) and audit and audit.user_id != row.created_by:
            return None
        return audit

    def dated(self, value):
        return ('unknown_date', False) if value is None else (None, self.start <= value <= self.end)

    def timestamp(self, value, row, *, fire=False):
        if value is None:
            return 'unknown_date', False
        if self.dialect == 'sqlite':
            if fire:
                return 'sqlite_fire_timestamp_ambiguous', False
            # This is source-specific admission evidence, never a global naive→UTC rule.
            if self.admitted_audit(row) is None:
                return 'legacy_timestamp_ambiguous', False
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
        elif value.tzinfo is None:
            return 'legacy_timestamp_ambiguous', False
        return None, self.start_at <= value.astimezone(timezone.utc) < self.end_at

    def admission(self, selection, row):
        if self.dialect == 'sqlite':
            selection.depend(self.admitted_audit(row))

    def emergency(self, selections):
        cases = {row.emergency_case_id: row for row in self.db.scalars(select(EmergencyCase))}
        if 'emergency.cases' in selections:
            chosen = selections['emergency.cases']
            for case in cases.values():
                reason, match = self.dated(case.call_date)
                if reason: chosen.exclude(case, reason)
                elif match: chosen.add(case)
        if 'emergency.patient_records' in selections:
            chosen = selections['emergency.patient_records']
            # Case dependencies also preserve empty matching and undated cases.
            for case in cases.values():
                reason, match = self.dated(case.call_date)
                if reason or match: chosen.depend(case)
            for patient in self.db.scalars(select(EmergencyPatient)):
                case = cases.get(patient.emergency_case_id)
                reason, match = self.dated(case.call_date if case else None)
                if reason: chosen.exclude(patient, reason)
                elif match: chosen.add(patient)

    def operations(self, selections):
        parents = {}
        for row in self.db.scalars(select(Incident)):
            source = None
            if row.emergency_case_id:
                source = self.db.get(EmergencyCase, row.emergency_case_id)
                reason, match = self.dated(source.call_date if source else None)
            elif row.fire_investigation_case_id:
                source = self.db.get(FireInvestigationCase, row.fire_investigation_case_id)
                reason, match = self.timestamp(source.occurred_at if source else None, source, fire=True)
            else:
                reason, match = self.timestamp(row.occurred_at, row)
            parents[row.incident_id] = row, source, reason, match
            for key, chosen in selections.items():
                if reason or match:
                    chosen.depend(row); chosen.depend(source); self.admission(chosen, row)
                if key == 'operations.incidents' and row.status == 'active':
                    if reason: chosen.exclude(row, reason)
                    elif match: chosen.add(row)
        for dispatch in self.db.scalars(select(Dispatch)):
            parent = parents.get(dispatch.incident_id)
            reason, match = (parent[2], parent[3]) if parent else ('unknown_date', False)
            for key, chosen in selections.items():
                qualifies = (key == 'operations.dispatches' and dispatch.status != 'cancelled') or (key == 'operations.approved_dispatches' and dispatch.status == 'approved')
                if qualifies:
                    if reason: chosen.exclude(dispatch, reason)
                    elif match: chosen.add(dispatch)
        for chosen in selections.values():
            chosen.limitations.add('時刻は記録された瞬間を使用します。元の入力者が意図したタイムゾーンは検証できません。')
            if self.dialect == 'sqlite':
                chosen.limitations.add('SQLiteではUTC正規化を行う活動API・取込の作成監査がある時刻のみ使用します。直接・旧方式の登録や連携火災時刻は曖昧なため除外します。作成監査の欠けた復元・旧記録は過少集計になり得ます。監査は元の正規化や後の直接SQL変更を証明しません。')

    def fleet(self, selections):
        for trip in self.db.scalars(select(VehicleTrip)):
            reason, match = self.timestamp(trip.started_at, trip)
            for key, chosen in selections.items():
                if reason:
                    chosen.exclude(trip, reason)
                elif match:
                    chosen.add(trip, trip.end_odometer - trip.start_odometer if key == 'fleet.distance_km' else 1)
                if reason or match: self.admission(chosen, trip)
        for chosen in selections.values():
            chosen.limitations.add('運行開始の記録時刻で集計します。元の入力者が意図したタイムゾーンは検証できません。')
            if self.dialect == 'sqlite':
                chosen.limitations.add('SQLiteではUTC正規化を行う車両API・取込の作成監査がある時刻のみ使用します。直接・旧方式の登録は曖昧なため除外します。作成監査の欠けた復元・旧記録は過少集計になり得ます。監査は元の正規化や後の直接SQL変更を証明しません。')


def capture_sources(db, period, keys):
    selector = Selector(db, period)
    selections = {key: Selection(key) for key in keys}
    for module in ['emergency', 'operations', 'fleet']:
        group = {key: chosen for key, chosen in selections.items() if DEFINITIONS[key]['source_module'] == module}
        if group:
            getattr(selector, module)(group)
    projected = {key: selection.projections() for key, selection in selections.items()}
    public = {'query_version': QUERY_VERSION, 'period': period, 'captured_at': now_utc().isoformat(),
              'coverage_status': 'unknown', 'metrics': [projected[key][0] for key in keys]}
    public['public_checksum'] = digest(public)
    evidence = {'query_version': QUERY_VERSION, 'period': period, 'metrics': {key: projected[key][1] for key in keys}}
    return Capture(public, evidence, digest(evidence))
