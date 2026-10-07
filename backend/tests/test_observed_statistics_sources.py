"""Synthetic selectors: one source population defines value and private evidence."""
from datetime import date, datetime, timezone
from decimal import Decimal
import importlib
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.main import app  # register the existing domain models
from app.db import Base
from app.models import EmergencyCase, EmergencyPatient, FireInvestigationCase, User
from app.operations_models import Incident, Dispatch, Vehicle, VehicleTrip
from app.audit import write_audit


@pytest.fixture
def source_db(tmp_path):
    engine = create_engine('sqlite+pysqlite:///' + str(tmp_path / 'statistics.db'))
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(username='synthetic', password_hash='not-a-real-password')
        db.add(user); db.commit()
        db.info['synthetic_user_id'] = user.user_id
        yield db
    engine.dispose()


def capture(db, keys, start='2026-01-01', end='2026-01-31'):
    schemas = importlib.import_module('app.statistics_schemas')
    sources = importlib.import_module('app.statistics_sources')
    query = schemas.StatisticsQuery(start_date=start, end_date=end, metric_keys=keys)
    return sources.capture_sources(db, sources.pin_period(query, 'Asia/Tokyo'), query.metric_keys)


def observed(result, key):
    return next(row for row in result.public['metrics'] if row['key'] == key)


def audited(db, row, action):
    db.add(row); db.flush()
    primary = list(row.__table__.primary_key)[0].name
    write_audit(db, user_id=db.info['synthetic_user_id'], action=action,
                entity_type=row.__tablename__, entity_id=getattr(row, primary), after={'version': getattr(row, 'version', None)})
    db.flush()
    return row


def test_empty_observed_zero_is_not_complete_history(source_db):
    result = capture(source_db, ['emergency.cases', 'fleet.distance_km'])
    assert observed(result, 'emergency.cases')['value'] == '0'
    assert observed(result, 'fleet.distance_km')['value'] == '0.0'
    assert result.public['coverage_status'] == 'unknown'
    assert all(m['coverage_status'] == 'unknown' for m in result.public['metrics'])


def test_patient_grain_empty_cases_and_department_wide_unknown_exclusions(source_db):
    db = source_db
    cases = [EmergencyCase(source_case_key=str(n), call_date=d) for n, d in enumerate([date(2026,1,1),date(2026,1,31),None,date(2025,1,1)])]
    db.add_all(cases); db.flush()
    patients = [EmergencyPatient(emergency_case_id=cases[i].emergency_case_id, patient_number=n, diagnosis_text='PRIVATE') for i,n in [(0,1),(0,2),(2,1),(2,2),(3,1)]]
    db.add_all(patients); db.commit()
    keys = ['emergency.cases','emergency.patient_records']
    result = capture(db, keys)
    assert [observed(result,k)['value'] for k in keys] == ['2','2']
    assert observed(result,keys[0])['exclusions'] == [{'reason':'unknown_date','count':1,'grain':'case','scope':'department_all_dates'}]
    assert observed(result,keys[1])['exclusions'] == [{'reason':'unknown_date','count':2,'grain':'patient_record','scope':'department_all_dates'}]
    assert set(result.evidence['metrics'][keys[1]]['selected']) == {p.emergency_patient_id for p in patients[:2]}
    assert 'PRIVATE' not in str(result.public) and patients[0].emergency_patient_id not in str(result.public)
    db.add(EmergencyPatient(emergency_case_id=cases[1].emergency_case_id,patient_number=1)); db.commit()
    assert capture(db,keys).fingerprint != result.fingerprint


def test_operations_dispatch_population_independent_of_active_incidents(source_db):
    db = source_db
    parents = [audited(db, Incident(kind='rescue', title='Synthetic', status=status, occurred_at=datetime(2026,1,10,tzinfo=timezone.utc)), 'incident.create') for status in ['active','cancelled']]
    db.add_all([Dispatch(incident_id=parents[0].incident_id, unit='S', status='draft'),
        Dispatch(incident_id=parents[1].incident_id, unit='S',status='approved',approved_by=db.info['synthetic_user_id'],reviewed_by=db.info['synthetic_user_id'],approved_at=datetime.now(timezone.utc)),
        Dispatch(incident_id=parents[0].incident_id, unit='S',status='cancelled')]); db.commit()
    keys = ['operations.incidents','operations.dispatches','operations.approved_dispatches']
    result = capture(db, keys)
    assert [observed(result,k)['value'] for k in keys] == ['1','2','1']
    assert len(result.evidence['metrics'][keys[0]]['selected']) == 1
    assert len(result.evidence['metrics'][keys[1]]['selected']) == 2


def test_utc_admission_midnight_end_exclusion_and_retired_vehicle_distance(source_db):
    db = source_db
    vehicle = Vehicle(code='S',name='Synthetic',active=False);db.add(vehicle);db.flush()
    # Current API schema normalizes these exact instants before SQLite strips tzinfo.
    from app.operations_schemas import TripInput
    for n, when in enumerate(['2025-12-31T23:59:59+09:00','2026-01-01T00:00:00+09:00','2026-01-31T23:59:59+09:00','2026-02-01T00:00:00+09:00']):
        payload=TripInput(expected_version=1,started_at=when,ended_at=when,start_odometer=str(n*10),end_odometer=str(n*10+2.3),purpose='Synthetic')
        audited(db,VehicleTrip(vehicle_id=vehicle.vehicle_id,created_by=db.info['synthetic_user_id'],**payload.model_dump(exclude={'expected_version'})), 'fleet.trip.create')
    db.commit()
    result=capture(db,['fleet.trips','fleet.distance_km'])
    assert observed(result,'fleet.trips')['value']=='2'
    assert observed(result,'fleet.distance_km')['value']=='4.6'
    assert set(result.evidence['metrics']['fleet.trips']['selected'])==set(result.evidence['metrics']['fleet.distance_km']['selected'])
    assert result.public['period']['start_at_utc']=='2025-12-31T15:00:00+00:00'
    assert result.public['period']['end_before_utc']=='2026-01-31T15:00:00+00:00'


def test_sqlite_fire_and_unaudited_legacy_dates_are_excluded_and_fingerprinted(source_db):
    db=source_db
    fire=FireInvestigationCase(title='Synthetic',occurred_at=datetime.fromisoformat('2026-01-10T09:00:00+09:00'));db.add(fire);db.flush()
    db.add_all([Incident(kind='fire',title='Linked',fire_investigation_case_id=fire.fire_investigation_case_id),Incident(kind='rescue',title='Legacy',occurred_at=datetime(2026,1,1))]);db.commit()
    result=capture(db,['operations.incidents'])
    metric=observed(result,'operations.incidents')
    assert metric['value']=='0'
    assert sum(e['count'] for e in metric['exclusions'])==2
    assert {e['reason'] for e in metric['exclusions']}=={'legacy_timestamp_ambiguous','sqlite_fire_timestamp_ambiguous'}
    db.add(Incident(kind='rescue',title='Unknown',occurred_at=None));db.commit()
    assert capture(db,['operations.incidents']).fingerprint!=result.fingerprint


def test_date_fields_stay_dates_and_parent_date_changes_stale_dispatch(source_db):
    db=source_db
    case=EmergencyCase(source_case_key='date-only',call_date=date(2026,1,1));db.add(case);db.flush()
    parent=Incident(kind='emergency_support',title='Synthetic',emergency_case_id=case.emergency_case_id);db.add(parent);db.flush()
    db.add(Dispatch(incident_id=parent.incident_id,unit='S'));db.commit()
    first=capture(db,['operations.dispatches'])
    assert observed(first,'operations.dispatches')['value']=='1'
    case.call_date=date(2025,12,31);db.commit()
    assert capture(db,['operations.dispatches']).fingerprint!=first.fingerprint


def test_query_rejects_overrides_bad_ranges_duplicate_metrics_and_overflow():
    from pydantic import ValidationError
    schema=importlib.import_module('app.statistics_schemas').StatisticsQuery
    for extra in [{'business_timezone':'UTC'},{'values':{}},{'start_at_utc':'2026-01-01'},{'metric_keys':['emergency.cases','emergency.cases']},{'end_date':'9999-12-31'},{'start_date':'2027-01-01'},{'start_date':20260101}]:
        with pytest.raises(ValidationError):schema.model_validate({'start_date':'2026-01-01','end_date':'2026-01-31','metric_keys':['emergency.cases'],**extra})


def test_leap_day_equivalent_instants_and_pinned_zone_survive_configuration_change(source_db):
    from app.operations_schemas import IncidentInput
    db=source_db
    for when in ['2024-02-29T00:00:00+09:00','2024-02-28T15:00:00Z']:
        payload=IncidentInput(kind='rescue',title='Synthetic',occurred_at=when)
        audited(db,Incident(**payload.model_dump()),'incident.create')
    db.commit()
    result=capture(db,['operations.incidents'],'2024-02-29','2024-02-29')
    assert observed(result,'operations.incidents')['value']=='2'
    sources=importlib.import_module('app.statistics_sources')
    assert sources.capture_sources(db,result.public['period'],['operations.incidents']).fingerprint==result.fingerprint


def test_sqlite_admission_requires_exact_successful_action_table_actor_and_trip_creator(source_db):
    db=source_db
    incident=Incident(kind='rescue',title='Wrong audit',occurred_at=datetime(2026,1,2));db.add(incident);db.flush()
    write_audit(db,user_id=db.info['synthetic_user_id'],action='fleet.trip.create',entity_type='operation_incidents',entity_id=incident.incident_id)
    unowned=Incident(kind='rescue',title='Unowned audit',occurred_at=datetime(2026,1,2));db.add(unowned);db.flush()
    write_audit(db,user_id=None,action='incident.create',entity_type='operation_incidents',entity_id=unowned.incident_id)
    other=User(username='other',password_hash='synthetic');db.add(other);db.flush()
    vehicle=Vehicle(code='actor',name='Synthetic');db.add(vehicle);db.flush()
    trip=VehicleTrip(vehicle_id=vehicle.vehicle_id,created_by=other.user_id,started_at=datetime(2026,1,2),ended_at=datetime(2026,1,2),start_odometer=0,end_odometer=2,purpose='Synthetic');db.add(trip);db.flush()
    write_audit(db,user_id=db.info['synthetic_user_id'],action='fleet.trip.create',entity_type='operation_vehicle_trips',entity_id=trip.trip_id)
    db.commit()
    result=capture(db,['operations.incidents','fleet.trips'])
    assert [metric['value'] for metric in result.public['metrics']]==['0','0']
    assert [sum(e['count'] for e in metric['exclusions']) for metric in result.public['metrics']]==[2,1]


def test_validated_timezone_configuration_and_explicit_confirmation_boolean():
    from app.settings import Settings
    from app.statistics_schemas import ConfirmStatistics
    from pydantic import ValidationError
    assert Settings(_env_file=None).statistics_business_timezone=='Asia/Tokyo'
    with pytest.raises(ValidationError):Settings(_env_file=None,statistics_business_timezone='Invalid/Zone')
    with pytest.raises(ValidationError):ConfirmStatistics(expected_version=1,acknowledged=1,review_note='Synthetic')
