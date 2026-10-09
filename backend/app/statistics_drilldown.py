"""Only explicit, separately authorized source-navigation pointers cross this boundary."""
from fastapi import HTTPException
from .models import EmergencyCase, EmergencyPatient
from .operations_models import Incident, Dispatch, VehicleTrip
from .operations_service import source_permission
from .workforce_models import WorkforceRosterEntry, WorkforceAttendance, WorkforceTimeEntry
from .workforce_source import original_rights


def drilldown(db, row, evidence, key, permissions, limit, offset):
    if key not in row.metric_keys:
        raise HTTPException(422, 'Metric is not part of this report')
    models = {'emergency.cases': EmergencyCase, 'emergency.patient_records': EmergencyPatient,
              'operations.incidents': Incident, 'operations.dispatches': Dispatch,
              'operations.approved_dispatches': Dispatch, 'fleet.trips': VehicleTrip, 'fleet.distance_km': VehicleTrip,
              'workforce.approved_rosters': WorkforceRosterEntry, 'workforce.approved_worked_minutes': WorkforceAttendance,
              'workforce.approved_overtime_minutes': WorkforceTimeEntry}
    needed = {'workforce.read', 'personnel.read'} if key.startswith('workforce.') else ({'emergency.case.read'} if key.startswith('emergency.') else ({'incident.read'} if key.startswith('operations.') else {'fleet.read'}))
    if key == 'emergency.patient_records': needed.add('emergency.patient.read')
    if not needed.issubset(permissions):
        raise HTTPException(403, 'Original source detail permissions are required')
    items = []
    for identity in sorted(evidence.evidence['metrics'][key]['selected']):
        source = db.get(models[key], identity)
        if source is None:
            continue
        item = {'source_module': key.split('.')[0], 'record_type': 'case', 'record_id': identity}
        if isinstance(source, (WorkforceRosterEntry, WorkforceAttendance, WorkforceTimeEntry)):
            if not original_rights(db, source).issubset(permissions):
                raise HTTPException(403, 'Original workforce document permissions are required')
            kind = 'roster' if isinstance(source, WorkforceRosterEntry) else ('attendance' if isinstance(source, WorkforceAttendance) else 'time')
            item.update(record_type=kind, navigation={'surface':'workforce_'+kind,'id':identity})
        elif isinstance(source, EmergencyPatient):
            item.update(record_type='patient_record', parent_id=source.emergency_case_id, navigation={'surface':'emergency_case','id':source.emergency_case_id})
        elif isinstance(source, EmergencyCase):
            item['navigation'] = {'surface':'emergency_case','id':source.emergency_case_id}
        elif isinstance(source, VehicleTrip):
            item.update(record_type='trip', parent_id=source.vehicle_id, navigation={'surface':'vehicle','id':source.vehicle_id})
        else:
            parent = source if isinstance(source, Incident) else db.get(Incident, source.incident_id)
            required = source_permission(parent) if parent else None
            if parent is None or (required and required not in permissions):
                raise HTTPException(403, 'Original linked source detail permissions are required')
            if isinstance(source, Dispatch):
                item.update(record_type='dispatch', parent_id=source.incident_id, navigation={'surface':'dispatch','id':source.dispatch_id})
            else:
                item.update(record_type='incident', navigation={'surface':'incident','id':source.incident_id})
        items.append(item)
    return {'items':items[offset:offset+limit], 'total':len(items), 'limit':limit, 'offset':offset}
