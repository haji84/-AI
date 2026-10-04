from typing import Literal
from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    user_id: str
    username: str

class FacilityFloorInput(BaseModel):
    floor_number: int = Field(ge=-20, le=200)
    floor_label: str | None = None
    floor_area: float | None = Field(default=None, ge=0)
    use_name: str | None = None
    occupancy_count: int | None = Field(default=None, ge=0)
    employee_count: int | None = Field(default=None, ge=0)
    windowless_status: str | None = None
    curtain_status: str | None = None
    carpet_status: str | None = None
    plywood_status: str | None = None

class FacilityDetailInput(BaseModel):
    legacy_book_type: str | None = None
    content_as_of: str | None = None
    classification_code: str | None = None
    classification_detail_1: str | None = None
    classification_detail_2: str | None = None
    zoning: str | None = None
    article8_partition: str | None = None
    structure: str | None = None
    above_ground_floors: int | None = Field(default=None, ge=0)
    basement_floors: int | None = Field(default=None, ge=0)
    building_area: float | None = Field(default=None, ge=0)
    total_floor_area: float | None = Field(default=None, ge=0)
    occupancy_total: int | None = Field(default=None, ge=0)
    employee_total: int | None = Field(default=None, ge=0)

class FacilityContactInput(BaseModel):
    representative_name: str | None = None
    representative_title: str | None = None
    representative_address: str | None = None
    representative_phone: str | None = None

class FacilityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    phone: str | None = None
    address: str | None = None
    legacy_internal_key: str | None = None
    legacy_serial_no: str | None = None
    detail: FacilityDetailInput | None = None
    contact: FacilityContactInput | None = None
    floors: list[FacilityFloorInput] = Field(default_factory=list)

class FacilityPatch(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=500)
    phone: str | None = None
    address: str | None = None
    legacy_serial_no: str | None = None
    detail: FacilityDetailInput | None = None
    contact: FacilityContactInput | None = None
    floors: list[FacilityFloorInput] | None = None

class FacilityStateChange(BaseModel):
    expected_version: int = Field(ge=1)

class FacilityOut(BaseModel):
    building_id: str
    legacy_internal_key: str | None
    legacy_serial_no: str | None = None
    name: str
    phone: str | None = None
    address: str | None
    status: str
    version: int

class FacilityFloorOut(FacilityFloorInput):
    facility_floor_id: str

class FacilityDetailOut(BaseModel):
    facility: FacilityOut
    detail: FacilityDetailInput
    contact: FacilityContactInput
    floors: list[FacilityFloorOut]

class FacilityHistoryItem(BaseModel):
    audit_id: int
    occurred_at: str
    action: str
    user_id: str | None
    before_data: dict | list | str | None
    after_data: dict | list | str | None

class LegacyReviewField(BaseModel):
    excel_col: str
    legacy_header: str
    value: str | None
    mapping_note: str | None = None


class DocumentOut(BaseModel):
    document_id: str
    building_id: str | None
    original_filename: str
    sha256: str
    size_bytes: int | None
    mime_type: str | None
    document_type: str | None

class ModuleOut(BaseModel):
    module_id: str
    code: str
    name: str
    version: str
    status: str
    manifest: dict

class ExtensionIntakeCreate(BaseModel):
    source_document_id: str
    requested_goal: str | None = None
    target_module: str | None = None

class ExtensionIntakeOut(BaseModel):
    extension_intake_id: str
    source_document_id: str
    requested_goal: str | None
    target_module: str | None
    detected_kind: str | None
    status: str
    analysis: dict
    diff: dict
    proposed_manifest: dict
    sandbox_result: dict

class ChangeRequestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    request_text: str = Field(min_length=1)
    target_module: str | None = None
    target_surface: str | None = None

class ChangeRequestReview(BaseModel):
    expected_version: int = Field(ge=1)
    risk_level: str = "unassessed"
    analysis: dict = Field(default_factory=dict)
    proposed_changes: dict = Field(default_factory=dict)
    acceptance_criteria: list[str] = Field(default_factory=list)
    sandbox_result: dict = Field(default_factory=dict)

class ChangeRequestApprove(BaseModel):
    expected_version: int = Field(ge=1)

class ChangeRequestOut(BaseModel):
    change_request_id: str
    title: str
    request_text: str
    target_module: str | None
    target_surface: str | None
    status: str
    risk_level: str
    analysis: dict
    proposed_changes: dict
    acceptance_criteria: list
    sandbox_result: dict
    version: int

class FormTemplateCreate(BaseModel):
    template_code: str = Field(min_length=1, max_length=150)
    name: str = Field(min_length=1, max_length=300)
    module_code: str = Field(min_length=1, max_length=100)
    document_id: str
    version_label: str = Field(min_length=1, max_length=80)
    issuer: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    field_mapping: dict = Field(default_factory=dict)
    print_settings: dict = Field(default_factory=dict)
    modification_policy: str = "fill_only"

class FormTemplateOut(BaseModel):
    form_template_id: str
    template_code: str
    name: str
    module_code: str
    document_id: str
    version_label: str
    issuer: str | None
    effective_from: str | None
    effective_to: str | None
    field_mapping: dict
    print_settings: dict
    modification_policy: str
    status: str

class ContractCounterpartyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    registration_no: str | None = None
    address: str | None = None
    contact: str | None = None

class ContractCounterpartyOut(BaseModel):
    counterparty_id: str
    name: str
    registration_no: str | None
    address: str | None
    contact: str | None
    active: bool
    version: int

class ContractCreate(BaseModel):
    contract_no: str | None = None
    title: str = Field(min_length=1, max_length=500)
    counterparty_id: str | None = None
    contract_method: str | None = None
    amount: float | None = None
    currency: str = "JPY"
    start_date: str | None = None
    end_date: str | None = None

class ContractPatch(BaseModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    counterparty_id: str | None = None
    contract_method: str | None = None
    amount: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = None

class ContractStateChange(BaseModel):
    expected_version: int = Field(ge=1)

class ContractOut(BaseModel):
    contract_case_id: str
    contract_no: str | None
    title: str
    counterparty_id: str | None
    contract_method: str | None
    amount: float | None
    currency: str
    start_date: str | None
    end_date: str | None
    status: str
    version: int

class FacilityListOut(BaseModel):
    items: list[FacilityOut]
    total: int

class FeatureFlagOut(BaseModel):
    feature_flag_id: str
    key: str
    module_code: str | None
    enabled: bool
    config: dict
    version: int

class FeatureFlagPatch(BaseModel):
    expected_version: int = Field(ge=1)
    enabled: bool
    config: dict | None = None

class ExtensionDeploymentCreate(BaseModel):
    module_code: str
    release_version: str
    previous_version: str | None = None
    migration_version: str | None = None
    feature_flag_key: str | None = None
    evidence: dict = Field(default_factory=dict)

class ExtensionDeploymentOut(BaseModel):
    extension_deployment_id: str
    change_request_id: str
    module_code: str
    release_version: str
    previous_version: str | None
    migration_version: str | None
    feature_flag_key: str | None
    status: str
    rollback_of: str | None
    evidence: dict

class InspectionFindingCreate(BaseModel):
    category: str | None = None
    finding_text: str = Field(min_length=1)
    severity: str | None = None
    corrective_status: str = "open"
    due_date: str | None = None
    notes: str | None = None

class InspectionFindingPatch(BaseModel):
    expected_version: int = Field(ge=1)
    category: str | None = None
    finding_text: str | None = Field(default=None, min_length=1)
    severity: str | None = None
    corrective_status: str | None = None
    due_date: str | None = None
    completed_at: str | None = None
    notes: str | None = None

class InspectionFindingOut(BaseModel):
    finding_id: str
    inspection_id: str
    category: str | None
    finding_text: str
    severity: str | None
    corrective_status: str
    due_date: str | None
    completed_at: str | None
    notes: str | None
    version: int

class InspectionCreate(BaseModel):
    building_id: str
    inspected_at: str
    inspection_type: str = "general"
    status: str = "open"
    notes: str | None = None
    findings: list[InspectionFindingCreate] = Field(default_factory=list)

class InspectionPatch(BaseModel):
    expected_version: int = Field(ge=1)
    inspected_at: str | None = None
    inspection_type: str | None = None
    status: str | None = None
    notes: str | None = None

class InspectionOut(BaseModel):
    inspection_id: str
    building_id: str
    inspected_at: str
    inspection_type: str
    status: str
    notes: str | None
    version: int
    findings: list[InspectionFindingOut] = Field(default_factory=list)

class SubmissionTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    category: str | None = None
    requires_document: bool = True
    rules: dict = Field(default_factory=dict)

class SubmissionTypeOut(BaseModel):
    submission_type_id: str
    code: str
    name: str
    category: str | None
    active: bool
    requires_document: bool
    rules: dict

class SubmissionCreate(BaseModel):
    building_id: str
    submission_type_code: str
    official_number: str | None = None
    submitted_at: str | None = None
    submitted_by: str | None = None
    notes: str | None = None
    payload_data: dict = Field(default_factory=dict)
    document_ids: list[str] = Field(default_factory=list)

class SubmissionPatch(BaseModel):
    expected_version: int = Field(ge=1)
    official_number: str | None = None
    submitted_at: str | None = None
    status: str | None = None
    submitted_by: str | None = None
    notes: str | None = None
    payload_data: dict | None = None

class SubmissionOut(BaseModel):
    submission_id: str
    building_id: str
    submission_type_id: str
    submission_type_code: str
    submission_type_name: str
    official_number: str | None
    received_at: str
    submitted_at: str | None
    status: str
    submitted_by: str | None
    notes: str | None
    payload_data: dict
    version: int
    document_ids: list[str] = Field(default_factory=list)

class FacilityComplianceStatusOut(BaseModel):
    code: str
    name: str
    state: str
    latest_submission_id: str | None = None
    latest_submitted_at: str | None = None
    detail: dict = Field(default_factory=dict)

class FacilityDashboardOut(BaseModel):
    building_id: str
    inspections_total: int
    open_findings: int
    latest_inspection_at: str | None
    submission_statuses: list[FacilityComplianceStatusOut]

class DocumentAnalysisCreate(BaseModel):
    document_id: str
    force_ocr: bool = False

class DocumentAnalysisReview(BaseModel):
    expected_version: int = Field(ge=1)
    building_id: str
    submission_type_code: str | None = None

class DocumentAnalysisOut(BaseModel):
    document_analysis_id: str
    document_id: str
    status: str
    extraction_method: str
    extracted_text: str
    page_count: int | None
    detected_submission_type_code: str | None
    detected_fields: dict
    facility_candidates: list
    difference_candidates: dict
    confidence: float | None
    evidence: dict
    selected_building_id: str | None
    selected_submission_type_code: str | None
    version: int

class IntakeConfirmReceipt(BaseModel):
    expected_version: int = Field(ge=1)
    official_number: str | None = None
    submitted_at: str | None = None
    submitted_by: str | None = None
    notes: str | None = None
    payload_data: dict = Field(default_factory=dict)

class FacilityChangeProposalOut(BaseModel):
    facility_change_proposal_id: str
    document_analysis_id: str
    building_id: str
    expected_facility_version: int
    changes: dict
    status: str
    version: int

class FacilityChangeProposalApply(BaseModel):
    expected_version: int = Field(ge=1)
    expected_facility_version: int = Field(ge=1)
    accepted_paths: list[str] = Field(default_factory=list)

class LegalRuleCreate(BaseModel):
    rule_code: str = Field(min_length=1, max_length=150)
    name: str = Field(min_length=1, max_length=300)
    domain: Literal["submission_requirement", "equipment_requirement"]
    description: str | None = None

class LegalRuleOut(BaseModel):
    rule_id: str
    rule_code: str
    name: str
    domain: str
    description: str | None = None
    active: bool

class LegalRuleVersionCreate(BaseModel):
    version_no: int = Field(ge=1)
    effective_from: str
    effective_to: str | None = None
    conditions: dict
    outcome: dict
    source_document_id: str | None = None
    source_reference: str | None = None
    source_legal_document_version_id: str | None = None

class LegalRuleVersionApprove(BaseModel):
    expected_version: int = Field(ge=1)

class LegalRuleVersionOut(BaseModel):
    legal_rule_version_id: str
    rule_id: str
    version_no: int
    effective_from: str
    effective_to: str | None = None
    conditions: dict
    outcome: dict
    source_document_id: str | None = None
    source_reference: str | None = None
    source_legal_document_version_id: str | None = None
    status: str
    version: int

class RequirementEvaluationCreate(BaseModel):
    domain: Literal["submission_requirement", "equipment_requirement"]
    evaluation_date: str | None = None

class RequirementEvaluationOut(BaseModel):
    evaluation_id: str
    building_id: str
    domain: str
    evaluation_date: str
    facility_version: int
    engine_version: str
    input_snapshot: dict
    results: list
    status: str

class LegalJurisdictionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=150)
    name: str = Field(min_length=1, max_length=300)
    jurisdiction_type: Literal["national","prefecture","municipality","fire_union","fire_department","other"]
    parent_jurisdiction_id: str | None = None
    official_base_url: str | None = None

class LegalJurisdictionOut(BaseModel):
    jurisdiction_id: str
    code: str
    name: str
    jurisdiction_type: str
    parent_jurisdiction_id: str | None = None
    official_base_url: str | None = None
    active: bool

class LegalProfileCreate(BaseModel):
    code: str = Field(min_length=1, max_length=150)
    name: str = Field(min_length=1, max_length=300)
    fire_department_name: str | None = None

class LegalProfileOut(BaseModel):
    legal_profile_id: str
    code: str
    name: str
    fire_department_name: str | None = None
    active: bool

class LegalProfileJurisdictionCreate(BaseModel):
    jurisdiction_id: str
    applicability: str = "applicable"
    priority: int = 100

class LegalSourceCreate(BaseModel):
    legal_profile_id: str | None = None
    jurisdiction_id: str
    source_code: str = Field(min_length=1, max_length=180)
    name: str = Field(min_length=1, max_length=300)
    source_type: str
    adapter_type: str
    base_url: str
    index_url: str | None = None
    update_mode: Literal["online","bundle","manual"] = "online"
    content_scope: str = "all"
    sync_frequency: str = "daily"
    trust_level: str = "official"
    parser_config: dict = Field(default_factory=dict)

class LegalSourceOut(BaseModel):
    legal_source_id: str
    legal_profile_id: str | None = None
    jurisdiction_id: str
    source_code: str
    name: str
    source_type: str
    adapter_type: str
    base_url: str
    index_url: str | None = None
    update_mode: str
    content_scope: str
    sync_frequency: str
    trust_level: str
    enabled: bool
    coverage_status: str = "unverified"
    expected_document_count: int | None = None
    captured_document_count: int | None = None
    stale_after_hours: int = 168



class LegalProvisionOut(BaseModel):
    legal_provision_id: str
    legal_source_document_version_id: str
    parent_provision_id: str | None = None
    provision_type: str
    provision_key: str
    sequence_no: int
    display_label: str | None = None
    heading_text: str | None = None
    body_text: str
    source_anchor: str | None = None
    source_path: str | None = None
    present_in_source: bool

class LegalRuleCitationCreate(BaseModel):
    legal_provision_id: str
    citation_role: Literal["primary","definition","exception","reference","supplementary"] = "primary"

class LegalRuleCitationOut(BaseModel):
    legal_rule_version_id: str
    legal_provision_id: str
    citation_role: str
    cited_text_snapshot: str
    provision: LegalProvisionOut


class LegalSourceDocumentOut(BaseModel):
    legal_source_document_id: str
    legal_source_id: str
    external_id: str
    document_type: str
    title: str
    document_number: str | None = None
    current_status: str
    source_url: str | None = None

class LegalSourceDocumentVersionOut(BaseModel):
    legal_source_document_version_id: str
    legal_source_document_id: str
    version_label: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    source_current_date: str | None = None
    source_url: str | None = None
    sha256: str
    structure_status: str
    structure_parser_version: str | None = None
    provision_count: int | None = None
