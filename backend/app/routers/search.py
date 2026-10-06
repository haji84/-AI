from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import current_user, permission_codes
from ..db import get_db
from ..models import (
    ChangeRequest,
    EmergencyCase,
    ContractCase,
    ContractCounterparty,
    Document,
    DrawingAnalysis,
    DrawingElement,
    EquipmentType,
    Facility,
    FacilityEquipment,
    FireInvestigationCase,
    FireInvestigationMedia,
    FirePhotoAnnotation,
    FireStatementDraft,
    FireTranscriptSegment,
    FormTemplate,
    Inspection,
    InspectionFinding,
    LegalRule,
    LegalSourceDocument,
    Submission,
    SubmissionType,
    User,
    Employee,
)
from ..schemas import UnifiedSearchHitOut, UnifiedSearchResponse
from ..unified_search import SEARCH_VERSION, lexical_score, make_snippet, query_sha256, query_terms

router = APIRouter(prefix="/search", tags=["search"])

from ..assets_models import OperationalAsset, AssetLot
from ..operations_models import Incident, Vehicle
from ..operations_service import incident_dict
from ..personnel import OrganizationUnit
from ..workforce_models import WorkforceRosterEntry, WorkforceShiftType

MODULE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "facilities": ("facility.read",),
    "emergency": ("emergency.case.read",),
    "operations": ("incident.read",),
    "fleet": ("fleet.read",),
    "operational_assets": ("asset.read",),
    "workforce": ("workforce.read",),
    "inspections": ("inspection.read",),
    "submissions": ("submission.read",),
    "equipment": ("equipment.read",),
    "drawings": ("drawing.read",),
    "fire": ("fire_investigation.read",),
    "legal": ("legal_source.read", "legal_rule.read"),
    "documents": ("document.read",),
    "contracts": ("contract.read",),
    "templates": ("template.read",),
    "extensions": ("extension.read",),
}

DEFAULT_MODULE_ORDER = list(MODULE_PERMISSIONS)


def _authorized_modules(perms: set[str]) -> list[str]:
    return [
        module
        for module in DEFAULT_MODULE_ORDER
        if any(permission in perms for permission in MODULE_PERMISSIONS[module])
    ]


def _requested_modules(raw: str | None) -> list[str] | None:
    if raw is None or not raw.strip():
        return None
    values: list[str] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        if value not in MODULE_PERMISSIONS:
            raise HTTPException(status_code=422, detail=f"unknown search module: {value}")
        if value not in values:
            values.append(value)
    return values


def _like_condition(query: str, *columns):
    terms = query_terms(query)
    expressions = []
    for term in terms:
        pattern = f"%{term}%"
        for column in columns:
            expressions.append(column.ilike(pattern))
    return or_(*expressions)


def _date_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _hit(
    query: str,
    *,
    module: str,
    source_type: str,
    source_id: str,
    title: str,
    body: str,
    required_permission: str,
    building_id: str | None = None,
    parent_id: str | None = None,
    occurred_at=None,
    navigation: dict | None = None,
    evidence: dict | None = None,
) -> UnifiedSearchHitOut:
    score = lexical_score(query, title=title, body=body)
    if score <= 0:
        score = 0.25
    return UnifiedSearchHitOut(
        module=module,
        source_type=source_type,
        source_id=source_id,
        title=title or source_type,
        snippet=make_snippet(query, body or title),
        score=score,
        building_id=building_id,
        parent_id=parent_id,
        occurred_at=_date_text(occurred_at),
        required_permission=required_permission,
        navigation=navigation or {},
        evidence={"search_version": SEARCH_VERSION, **(evidence or {})},
    )


def _search_facilities(db: Session, q: str, limit: int) -> list[UnifiedSearchHitOut]:
    rows = db.scalars(
        select(Facility)
        .where(
            _like_condition(
                q,
                Facility.name,
                Facility.address,
                Facility.legacy_serial_no,
                Facility.legacy_internal_key,
            )
        )
        .order_by(Facility.updated_at.desc())
        .limit(limit)
    ).all()
    return [
        _hit(
            q,
            module="facilities",
            source_type="facility",
            source_id=row.building_id,
            title=row.name,
            body=" / ".join(
                x for x in [row.address, row.phone, row.legacy_serial_no, row.status] if x
            ),
            building_id=row.building_id,
            required_permission="facility.read",
            navigation={"surface": "facility", "building_id": row.building_id},
            evidence={"record_version": row.version, "status": row.status},
        )
        for row in rows
    ]


def _search_inspections(db: Session, q: str, limit: int) -> list[UnifiedSearchHitOut]:
    rows = db.execute(
        select(InspectionFinding, Inspection, Facility)
        .join(Inspection, Inspection.inspection_id == InspectionFinding.inspection_id)
        .join(Facility, Facility.building_id == Inspection.building_id)
        .where(
            _like_condition(
                q,
                InspectionFinding.finding_text,
                InspectionFinding.category,
                InspectionFinding.notes,
                Inspection.inspection_type,
                Inspection.notes,
                Facility.name,
            )
        )
        .order_by(Inspection.inspected_at.desc(), InspectionFinding.created_at.desc())
        .limit(limit)
    ).all()
    return [
        _hit(
            q,
            module="inspections",
            source_type="inspection_finding",
            source_id=finding.finding_id,
            title=f"{facility.name} ・ {finding.category or '指摘事項'}",
            body=" / ".join(
                x
                for x in [
                    finding.finding_text,
                    finding.notes,
                    f"是正:{finding.corrective_status}",
                    f"査察:{inspection.inspection_type}",
                ]
                if x
            ),
            building_id=facility.building_id,
            parent_id=inspection.inspection_id,
            occurred_at=inspection.inspected_at,
            required_permission="inspection.read",
            navigation={
                "surface": "inspection",
                "building_id": facility.building_id,
                "inspection_id": inspection.inspection_id,
                "finding_id": finding.finding_id,
            },
            evidence={
                "corrective_status": finding.corrective_status,
                "inspection_status": inspection.status,
            },
        )
        for finding, inspection, facility in rows
    ]


def _search_submissions(db: Session, q: str, limit: int) -> list[UnifiedSearchHitOut]:
    rows = db.execute(
        select(Submission, SubmissionType, Facility)
        .join(SubmissionType, SubmissionType.submission_type_id == Submission.submission_type_id)
        .join(Facility, Facility.building_id == Submission.building_id)
        .where(
            _like_condition(
                q,
                SubmissionType.name,
                SubmissionType.code,
                Submission.official_number,
                Submission.notes,
                Submission.status,
                Facility.name,
            )
        )
        .order_by(Submission.received_at.desc())
        .limit(limit)
    ).all()
    return [
        _hit(
            q,
            module="submissions",
            source_type="submission",
            source_id=row.submission_id,
            title=f"{facility.name} ・ {stype.name}",
            body=" / ".join(
                x
                for x in [
                    f"受付番号:{row.official_number}" if row.official_number else None,
                    row.notes,
                    f"状態:{row.status}",
                ]
                if x
            ),
            building_id=facility.building_id,
            occurred_at=row.submitted_at or row.received_at,
            required_permission="submission.read",
            navigation={
                "surface": "submission",
                "building_id": facility.building_id,
                "submission_id": row.submission_id,
            },
            evidence={"submission_type_code": stype.code, "status": row.status},
        )
        for row, stype, facility in rows
    ]


def _search_equipment(db: Session, q: str, limit: int) -> list[UnifiedSearchHitOut]:
    rows = db.execute(
        select(FacilityEquipment, EquipmentType, Facility)
        .join(EquipmentType, EquipmentType.equipment_type_id == FacilityEquipment.equipment_type_id)
        .join(Facility, Facility.building_id == FacilityEquipment.building_id)
        .where(
            _like_condition(
                q,
                EquipmentType.name,
                EquipmentType.code,
                EquipmentType.category,
                FacilityEquipment.location_text,
                FacilityEquipment.notes,
                Facility.name,
            )
        )
        .order_by(FacilityEquipment.updated_at.desc())
        .limit(limit)
    ).all()
    return [
        _hit(
            q,
            module="equipment",
            source_type="facility_equipment",
            source_id=row.facility_equipment_id,
            title=f"{facility.name} ・ {etype.name}",
            body=" / ".join(
                x
                for x in [
                    row.location_text,
                    row.notes,
                    f"確認:{row.verification_status}",
                    f"由来:{row.source_kind}",
                ]
                if x
            ),
            building_id=facility.building_id,
            required_permission="equipment.read",
            navigation={
                "surface": "equipment",
                "building_id": facility.building_id,
                "facility_equipment_id": row.facility_equipment_id,
            },
            evidence={
                "equipment_type_code": etype.code,
                "verification_status": row.verification_status,
                "source_kind": row.source_kind,
            },
        )
        for row, etype, facility in rows
    ]


def _search_drawings(db: Session, q: str, limit: int) -> list[UnifiedSearchHitOut]:
    rows = db.execute(
        select(DrawingElement, DrawingAnalysis, Facility)
        .join(DrawingAnalysis, DrawingAnalysis.drawing_analysis_id == DrawingElement.drawing_analysis_id)
        .join(Facility, Facility.building_id == DrawingAnalysis.building_id)
        .where(
            _like_condition(
                q,
                DrawingElement.label,
                DrawingElement.element_type,
                Facility.name,
            )
        )
        .order_by(DrawingAnalysis.updated_at.desc(), DrawingElement.page_no)
        .limit(limit)
    ).all()
    return [
        _hit(
            q,
            module="drawings",
            source_type="drawing_element",
            source_id=element.drawing_element_id,
            title=f"{facility.name} ・ {element.label or element.element_type}",
            body=f"{element.element_type} / page {element.page_no} / review {element.review_status}",
            building_id=facility.building_id,
            parent_id=analysis.drawing_analysis_id,
            required_permission="drawing.read",
            navigation={
                "surface": "drawing",
                "building_id": facility.building_id,
                "drawing_analysis_id": analysis.drawing_analysis_id,
                "drawing_element_id": element.drawing_element_id,
            },
            evidence={
                "review_status": element.review_status,
                "source_kind": element.source_kind,
                "page_no": element.page_no,
            },
        )
        for element, analysis, facility in rows
    ]


def _search_fire(db: Session, q: str, limit: int) -> list[UnifiedSearchHitOut]:
    hits: list[UnifiedSearchHitOut] = []
    case_limit = max(1, limit // 4)
    cases = db.scalars(
        select(FireInvestigationCase)
        .where(
            _like_condition(
                q,
                FireInvestigationCase.case_number,
                FireInvestigationCase.title,
                FireInvestigationCase.location_text,
                FireInvestigationCase.official_cause_text,
            )
        )
        .order_by(FireInvestigationCase.updated_at.desc())
        .limit(case_limit)
    ).all()
    for row in cases:
        hits.append(
            _hit(
                q,
                module="fire",
                source_type="fire_case",
                source_id=row.fire_investigation_case_id,
                title=f"{row.case_number or '番号未設定'} ・ {row.title}",
                body=" / ".join(x for x in [row.location_text, row.official_cause_text, row.status] if x),
                building_id=row.building_id,
                occurred_at=row.occurred_at,
                required_permission="fire_investigation.read",
                navigation={"surface": "fire_case", "case_id": row.fire_investigation_case_id},
                evidence={"status": row.status, "official_cause": bool(row.official_cause_text)},
            )
        )

    transcript_rows = db.execute(
        select(FireTranscriptSegment, FireInvestigationMedia, FireInvestigationCase)
        .join(
            FireInvestigationMedia,
            FireInvestigationMedia.fire_investigation_media_id
            == FireTranscriptSegment.fire_investigation_media_id,
        )
        .join(
            FireInvestigationCase,
            FireInvestigationCase.fire_investigation_case_id
            == FireInvestigationMedia.fire_investigation_case_id,
        )
        .where(
            FireTranscriptSegment.review_status == "accepted",
            _like_condition(
                q,
                FireTranscriptSegment.text,
                FireTranscriptSegment.speaker_label,
                FireInvestigationCase.title,
                FireInvestigationCase.case_number,
            ),
        )
        .order_by(FireTranscriptSegment.created_at.desc())
        .limit(case_limit)
    ).all()
    for segment, media, case in transcript_rows:
        hits.append(
            _hit(
                q,
                module="fire",
                source_type="accepted_transcript",
                source_id=segment.fire_transcript_segment_id,
                title=f"{case.case_number or '火災調査'} ・ {segment.speaker_label or '話者未設定'}",
                body=segment.text,
                building_id=case.building_id,
                parent_id=case.fire_investigation_case_id,
                required_permission="fire_investigation.read",
                navigation={
                    "surface": "fire_transcript",
                    "case_id": case.fire_investigation_case_id,
                    "media_id": media.fire_investigation_media_id,
                    "segment_id": segment.fire_transcript_segment_id,
                    "start_ms": segment.start_ms,
                },
                evidence={
                    "review_status": segment.review_status,
                    "uncertainty_markers": segment.uncertainty_markers or [],
                },
            )
        )

    statements = db.execute(
        select(FireStatementDraft, FireInvestigationCase)
        .join(
            FireInvestigationCase,
            FireInvestigationCase.fire_investigation_case_id
            == FireStatementDraft.fire_investigation_case_id,
        )
        .where(
            FireStatementDraft.status == "reviewed",
            _like_condition(
                q,
                FireStatementDraft.person_label,
                FireStatementDraft.draft_text,
                FireInvestigationCase.title,
            ),
        )
        .order_by(FireStatementDraft.updated_at.desc())
        .limit(case_limit)
    ).all()
    for statement, case in statements:
        hits.append(
            _hit(
                q,
                module="fire",
                source_type="reviewed_statement",
                source_id=statement.fire_statement_draft_id,
                title=f"{case.case_number or '火災調査'} ・ {statement.person_label or '人物未設定'}",
                body=statement.draft_text,
                building_id=case.building_id,
                parent_id=case.fire_investigation_case_id,
                required_permission="fire_investigation.read",
                navigation={
                    "surface": "fire_statement",
                    "case_id": case.fire_investigation_case_id,
                    "statement_id": statement.fire_statement_draft_id,
                },
                evidence={
                    "status": statement.status,
                    "uncertainty_reviewed": statement.uncertainty_reviewed,
                    "source_uncertainty_markers": statement.source_uncertainty_markers or [],
                },
            )
        )

    annotations = db.execute(
        select(FirePhotoAnnotation, FireInvestigationMedia, FireInvestigationCase)
        .join(
            FireInvestigationMedia,
            FireInvestigationMedia.fire_investigation_media_id
            == FirePhotoAnnotation.fire_investigation_media_id,
        )
        .join(
            FireInvestigationCase,
            FireInvestigationCase.fire_investigation_case_id
            == FireInvestigationMedia.fire_investigation_case_id,
        )
        .where(
            FirePhotoAnnotation.status == "accepted",
            _like_condition(
                q,
                FirePhotoAnnotation.description,
                FireInvestigationCase.title,
            ),
        )
        .order_by(FirePhotoAnnotation.created_at.desc())
        .limit(case_limit)
    ).all()
    for annotation, media, case in annotations:
        hits.append(
            _hit(
                q,
                module="fire",
                source_type="accepted_photo_annotation",
                source_id=annotation.fire_photo_annotation_id,
                title=f"{case.case_number or '火災調査'} ・ 写真注釈",
                body=annotation.description or "",
                building_id=case.building_id,
                parent_id=case.fire_investigation_case_id,
                required_permission="fire_investigation.read",
                navigation={
                    "surface": "fire_photo",
                    "case_id": case.fire_investigation_case_id,
                    "media_id": media.fire_investigation_media_id,
                    "annotation_id": annotation.fire_photo_annotation_id,
                },
                evidence={"status": annotation.status, "source_kind": annotation.source_kind},
            )
        )
    return hits[:limit]


def _search_legal(db: Session, q: str, limit: int, perms: set[str]) -> list[UnifiedSearchHitOut]:
    hits: list[UnifiedSearchHitOut] = []
    half = max(1, limit // 2)
    if "legal_source.read" in perms:
        docs = db.scalars(
            select(LegalSourceDocument)
            .where(
                _like_condition(
                    q,
                    LegalSourceDocument.title,
                    LegalSourceDocument.document_number,
                    LegalSourceDocument.external_id,
                )
            )
            .order_by(LegalSourceDocument.updated_at.desc())
            .limit(half)
        ).all()
        for doc in docs:
            hits.append(
                _hit(
                    q,
                    module="legal",
                    source_type="legal_document",
                    source_id=doc.legal_source_document_id,
                    title=doc.title,
                    body=" / ".join(
                        x for x in [doc.document_number, doc.document_type, doc.current_status] if x
                    ),
                    occurred_at=doc.promulgation_date,
                    required_permission="legal_source.read",
                    navigation={
                        "surface": "legal_document",
                        "legal_source_document_id": doc.legal_source_document_id,
                    },
                    evidence={"source_url": doc.source_url, "external_id": doc.external_id},
                )
            )

    if "legal_rule.read" in perms:
        rules = db.scalars(
            select(LegalRule)
            .where(
                _like_condition(
                    q,
                    LegalRule.rule_code,
                    LegalRule.name,
                    LegalRule.description,
                    LegalRule.domain,
                )
            )
            .order_by(LegalRule.rule_code)
            .limit(half)
        ).all()
        for rule in rules:
            hits.append(
                _hit(
                    q,
                    module="legal",
                    source_type="legal_rule",
                    source_id=rule.rule_id,
                    title=f"{rule.rule_code} ・ {rule.name}",
                    body=" / ".join(x for x in [rule.domain, rule.description] if x),
                    required_permission="legal_rule.read",
                    navigation={"surface": "legal_rule", "rule_id": rule.rule_id},
                    evidence={"domain": rule.domain, "active": rule.active},
                )
            )
    return hits[:limit]


def _search_documents(db: Session, q: str, limit: int) -> list[UnifiedSearchHitOut]:
    rows = db.scalars(
        select(Document)
        .where(
            _like_condition(
                q,
                Document.original_filename,
                Document.document_type,
                Document.mime_type,
                Document.sha256,
            )
        )
        .order_by(Document.created_at.desc())
        .limit(limit)
    ).all()
    return [
        _hit(
            q,
            module="documents",
            source_type="document",
            source_id=row.document_id,
            title=row.original_filename,
            body=" / ".join(x for x in [row.document_type, row.mime_type, row.sha256] if x),
            building_id=row.building_id,
            occurred_at=row.created_at,
            required_permission="document.read",
            navigation={"surface": "document", "document_id": row.document_id},
            evidence={"sha256": row.sha256, "document_type": row.document_type},
        )
        for row in rows
    ]


def _search_contracts(db: Session, q: str, limit: int) -> list[UnifiedSearchHitOut]:
    rows = db.execute(
        select(ContractCase, ContractCounterparty)
        .outerjoin(
            ContractCounterparty,
            ContractCounterparty.counterparty_id == ContractCase.counterparty_id,
        )
        .where(
            _like_condition(
                q,
                ContractCase.contract_no,
                ContractCase.title,
                ContractCase.contract_method,
                ContractCase.status,
                ContractCounterparty.name,
            )
        )
        .order_by(ContractCase.updated_at.desc())
        .limit(limit)
    ).all()
    return [
        _hit(
            q,
            module="contracts",
            source_type="contract_case",
            source_id=case.contract_case_id,
            title=f"{case.contract_no or '番号未設定'} ・ {case.title}",
            body=" / ".join(
                x
                for x in [
                    counterparty.name if counterparty else None,
                    case.contract_method,
                    case.status,
                ]
                if x
            ),
            occurred_at=case.start_date,
            required_permission="contract.read",
            navigation={"surface": "contract", "contract_case_id": case.contract_case_id},
            evidence={"status": case.status},
        )
        for case, counterparty in rows
    ]


def _search_templates(db: Session, q: str, limit: int) -> list[UnifiedSearchHitOut]:
    rows = db.scalars(
        select(FormTemplate)
        .where(
            _like_condition(
                q,
                FormTemplate.template_code,
                FormTemplate.name,
                FormTemplate.module_code,
                FormTemplate.issuer,
                FormTemplate.version_label,
            )
        )
        .order_by(FormTemplate.created_at.desc())
        .limit(limit)
    ).all()
    return [
        _hit(
            q,
            module="templates",
            source_type="form_template",
            source_id=row.form_template_id,
            title=f"{row.name} ・ {row.version_label}",
            body=" / ".join(x for x in [row.template_code, row.module_code, row.issuer, row.status] if x),
            required_permission="template.read",
            navigation={"surface": "form_template", "form_template_id": row.form_template_id},
            evidence={"status": row.status, "module_code": row.module_code},
        )
        for row in rows
    ]


def _search_extensions(db: Session, q: str, limit: int) -> list[UnifiedSearchHitOut]:
    rows = db.scalars(
        select(ChangeRequest)
        .where(
            _like_condition(
                q,
                ChangeRequest.title,
                ChangeRequest.request_text,
                ChangeRequest.target_module,
                ChangeRequest.target_surface,
                ChangeRequest.status,
            )
        )
        .order_by(ChangeRequest.updated_at.desc())
        .limit(limit)
    ).all()
    return [
        _hit(
            q,
            module="extensions",
            source_type="change_request",
            source_id=row.change_request_id,
            title=row.title,
            body=" / ".join(
                x for x in [row.request_text, row.target_module, row.target_surface, row.status] if x
            ),
            occurred_at=row.created_at,
            required_permission="extension.read",
            navigation={"surface": "change_request", "change_request_id": row.change_request_id},
            evidence={"status": row.status, "risk_level": row.risk_level},
        )
        for row in rows
    ]


def _search_emergency(db, q, limit):
    rows = db.scalars(select(EmergencyCase).where(
        _like_condition(q, EmergencyCase.dispatch_number, EmergencyCase.incident_address,
                        EmergencyCase.command_text)).limit(limit)).all()
    return [_hit(q, module="emergency", source_type="emergency_case",
        source_id=r.emergency_case_id, title=f"{r.station_code or ''} / {r.dispatch_number or ''}",
        body=" / ".join(x for x in [r.incident_address, r.command_text] if x),
        occurred_at=r.call_date, required_permission="emergency.case.read",
        navigation={"surface": "emergency", "emergency_case_id": r.emergency_case_id},
        evidence={"record_version": r.version}) for r in rows]


def _search_operations(db, q, limit, perms):
    hits=[]
    for row in db.scalars(select(Incident).order_by(Incident.updated_at.desc())):
        data=incident_dict(db,row,perms)
        source=data.get('source',{})
        title=row.title
        body=" / ".join(str(x) for x in [row.kind,row.address,row.number,row.notes,source.get('address'),source.get('number')] if x)
        if lexical_score(q,title=title,body=body)<=0:continue
        evidence={'record_version':row.version}
        if source:evidence['linked_source_id']=source['source_id']
        hits.append(_hit(q,module='operations',source_type='incident',source_id=row.incident_id,title=title,body=body,required_permission='incident.read',navigation={'surface':'operations','incident_id':row.incident_id},evidence=evidence))
        if len(hits)>=limit:break
    return hits


def _search_fleet(db,q,limit):
    rows=db.scalars(select(Vehicle).where(_like_condition(q,Vehicle.code,Vehicle.name,Vehicle.registration,Vehicle.notes)).order_by(Vehicle.updated_at.desc()).limit(limit))
    return [_hit(q,module='fleet',source_type='vehicle',source_id=r.vehicle_id,title=f'{r.code} / {r.name}',body=' / '.join(x for x in [r.registration,r.notes] if x),required_permission='fleet.read',navigation={'surface':'operations','vehicle_id':r.vehicle_id},evidence={'record_version':r.version}) for r in rows]


def _search_assets(db,q,limit):
    rows=db.scalars(select(OperationalAsset).where(_like_condition(q,OperationalAsset.code,OperationalAsset.name,OperationalAsset.category)).order_by(OperationalAsset.updated_at.desc()).limit(limit))
    hits=[_hit(q,module='operational_assets',source_type='operational_asset',source_id=r.asset_id,title=f'{r.code} / {r.name}',body=' / '.join([r.category,r.unit]),required_permission='asset.read',navigation={'surface':'operational_assets','asset_id':r.asset_id},evidence={'record_version':r.version,'active':r.active}) for r in rows]
    remaining=limit-len(hits)
    if remaining:
        lots=db.execute(select(AssetLot,OperationalAsset).join(OperationalAsset,OperationalAsset.asset_id==AssetLot.asset_id).where(_like_condition(q,AssetLot.batch_code,AssetLot.provenance)).order_by(AssetLot.updated_at.desc(),AssetLot.lot_id).limit(remaining))
        hits.extend(_hit(q,module='operational_assets',source_type='asset_lot',source_id=lot.lot_id,parent_id=asset.asset_id,title=f'{asset.code} / {asset.name} / {lot.batch_code}',body=' / '.join(x for x in [lot.provenance,str(lot.expires_on) if lot.expires_on else None,asset.unit] if x),required_permission='asset.read',navigation={'surface':'operational_assets','asset_id':asset.asset_id,'lot_id':lot.lot_id},evidence={'record_version':lot.version,'active':lot.active}) for lot,asset in lots)
    return hits


def _search_workforce(db: Session, q: str, limit: int) -> list[UnifiedSearchHitOut]:
    rows = db.execute(
        select(WorkforceRosterEntry, Employee, OrganizationUnit, WorkforceShiftType)
        .join(Employee, Employee.employee_id == WorkforceRosterEntry.employee_id)
        .join(OrganizationUnit, OrganizationUnit.organization_id == WorkforceRosterEntry.organization_id)
        .join(WorkforceShiftType, WorkforceShiftType.shift_type_id == WorkforceRosterEntry.shift_type_id)
        .where(
            _like_condition(
                q,
                Employee.display_name,
                Employee.employee_code,
                OrganizationUnit.name,
                OrganizationUnit.code,
                WorkforceShiftType.name,
                WorkforceShiftType.code,
                WorkforceRosterEntry.note,
                WorkforceRosterEntry.status,
            )
        )
        .order_by(WorkforceRosterEntry.work_date.desc())
        .limit(limit)
    ).all()
    return [
        _hit(
            q,
            module="workforce",
            source_type="workforce_roster",
            source_id=roster.roster_entry_id,
            title=f"{employee.display_name} ・ {organization.name} ・ {shift.name}",
            body=" / ".join(
                x for x in [
                    employee.employee_code,
                    roster.work_date.isoformat(),
                    roster.status,
                    "応援配置" if roster.support_placement else "通常配置",
                    roster.note,
                ] if x
            ),
            parent_id=employee.employee_id,
            occurred_at=roster.work_date,
            required_permission="workforce.read",
            navigation={"surface":"workforce","roster_entry_id":roster.roster_entry_id,"employee_id":employee.employee_id},
            evidence={"record_version":roster.version,"status":roster.status,"assignment_id":roster.assignment_id,"assignment_version":roster.assignment_version},
        )
        for roster,employee,organization,shift in rows
    ]


SEARCHERS = {
    "operational_assets": lambda db,q,limit,perms: _search_assets(db,q,limit),
    "workforce": lambda db,q,limit,perms: _search_workforce(db,q,limit),
    "operations": _search_operations,
    "fleet": lambda db,q,limit,perms: _search_fleet(db,q,limit),
    "emergency": lambda db, q, limit, perms: _search_emergency(db, q, limit),
    "facilities": lambda db, q, limit, perms: _search_facilities(db, q, limit),
    "inspections": lambda db, q, limit, perms: _search_inspections(db, q, limit),
    "submissions": lambda db, q, limit, perms: _search_submissions(db, q, limit),
    "equipment": lambda db, q, limit, perms: _search_equipment(db, q, limit),
    "drawings": lambda db, q, limit, perms: _search_drawings(db, q, limit),
    "fire": lambda db, q, limit, perms: _search_fire(db, q, limit),
    "legal": lambda db, q, limit, perms: _search_legal(db, q, limit, perms),
    "documents": lambda db, q, limit, perms: _search_documents(db, q, limit),
    "contracts": lambda db, q, limit, perms: _search_contracts(db, q, limit),
    "templates": lambda db, q, limit, perms: _search_templates(db, q, limit),
    "extensions": lambda db, q, limit, perms: _search_extensions(db, q, limit),
}


@router.get("", response_model=UnifiedSearchResponse)
def unified_search(
    q: str,
    modules: str | None = None,
    limit: int = 100,
    per_module_limit: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    perms = permission_codes(db, user.user_id)
    if "search.use" not in perms:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing permission: search.use")

    query = (q or "").strip()
    if len(query) < 1:
        raise HTTPException(status_code=422, detail="search query is required")
    if len(query) > 300:
        raise HTTPException(status_code=422, detail="search query is too long")

    authorized = _authorized_modules(perms)
    requested = _requested_modules(modules)
    if requested is not None:
        forbidden = [module for module in requested if module not in authorized]
        if forbidden:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "requested search module is not authorized", "modules": forbidden},
            )
        selected = requested
    else:
        selected = authorized

    overall_limit = max(1, min(limit, 300))
    source_limit = max(1, min(per_module_limit, 100))
    hits: list[UnifiedSearchHitOut] = []
    for module in selected:
        hits.extend(SEARCHERS[module](db, query, source_limit, perms))

    hits.sort(
        key=lambda x: (
            -x.score,
            x.module,
            x.title,
            x.source_id,
        )
    )
    hits = hits[:overall_limit]

    skipped = [module for module in DEFAULT_MODULE_ORDER if module not in selected]
    write_audit(
        db,
        user_id=user.user_id,
        action="unified_search.query",
        entity_type="unified_search",
        entity_id=None,
        after={
            "query_sha256": query_sha256(query),
            "query_length": len(query),
            "searched_modules": selected,
            "result_count": len(hits),
            "search_version": SEARCH_VERSION,
        },
    )
    db.commit()

    return UnifiedSearchResponse(
        query=query,
        hits=hits,
        searched_modules=selected,
        skipped_modules=skipped,
        total_hits=len(hits),
        note=(
            "Search results are permission-filtered and provenance-linked. "
            "The raw query is not written to the audit log. "
            "Emergency case search uses separate case-read permission; patient text is excluded."
        ),
    )

