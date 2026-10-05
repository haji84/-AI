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
    domain: Literal["submission_requirement", "equipment_requirement", "occupancy_classification", "equipment_placement"]
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


class LegalRuleDraftCandidateCreate(BaseModel):
    source_legal_document_version_id: str | None = None
    domain: Literal["submission_requirement","equipment_requirement","occupancy_classification","equipment_placement"]
    proposed_rule_code: str | None = None
    proposed_name: str = Field(min_length=1, max_length=300)
    proposed_conditions: dict
    proposed_outcome: dict
    extraction_method: Literal["manual","deterministic","ai"]
    model_version: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    rationale: str | None = None
    citations: list[LegalRuleCitationCreate] = Field(default_factory=list)

class LegalRuleDraftCandidatePatch(BaseModel):
    expected_version: int = Field(ge=1)
    proposed_rule_code: str | None = None
    proposed_name: str | None = Field(default=None, min_length=1, max_length=300)
    proposed_conditions: dict | None = None
    proposed_outcome: dict | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    rationale: str | None = None

class LegalRuleDraftCandidateReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["reviewed","rejected"]

class LegalRuleDraftCandidatePromote(BaseModel):
    expected_version: int = Field(ge=1)
    effective_from: str
    effective_to: str | None = None

class LegalRuleDraftCitationOut(BaseModel):
    legal_provision_id: str
    citation_role: str
    provision: LegalProvisionOut

class LegalRuleDraftCandidateOut(BaseModel):
    legal_rule_draft_candidate_id: str
    source_legal_document_version_id: str | None = None
    domain: str
    proposed_rule_code: str | None = None
    proposed_name: str
    proposed_conditions: dict
    proposed_outcome: dict
    extraction_method: str
    model_version: str | None = None
    confidence: float | None = None
    rationale: str | None = None
    status: str
    version: int
    promoted_rule_id: str | None = None
    promoted_rule_version_id: str | None = None
    citations: list[LegalRuleDraftCitationOut] = Field(default_factory=list)


class LegalProvisionReviewCandidateOut(BaseModel):
    legal_provision_review_candidate_id: str
    legal_provision_id: str
    category: str
    relevance_score: float
    priority_lane: str = "normal"
    source_priority_score: float = 0
    provision_context: str = "main"
    context_priority_score: float = 0
    review_priority_score: float = 0
    reasons: list
    extraction_method: str
    model_version: str | None = None
    status: str
    version: int
    legal_rule_draft_candidate_id: str | None = None
    document_title: str
    provision: LegalProvisionOut

class LegalProvisionReviewCandidatePatch(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["reviewed","ignored"]

class LegalProvisionReviewCandidateDraft(BaseModel):
    expected_version: int = Field(ge=1)
    proposed_name: str | None = Field(default=None, min_length=1, max_length=300)


class LegalReviewQueueSummaryOut(BaseModel):
    total: int
    by_status: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_priority_lane: dict[str, int] = Field(default_factory=dict)
    by_provision_context: dict[str, int] = Field(default_factory=dict)


class LegalRuleCoverageOut(BaseModel):
    review_queue_by_domain_status: dict[str, dict[str, int]] = Field(default_factory=dict)
    draft_candidates_by_domain_status: dict[str, dict[str, int]] = Field(default_factory=dict)
    rule_versions_by_domain_status: dict[str, dict[str, int]] = Field(default_factory=dict)
    approved_rule_count_by_domain: dict[str, int] = Field(default_factory=dict)
    exact_citation_count: int = 0
    note: str


class SubmissionRequirementComparisonItemOut(BaseModel):
    submission_type_code: str
    submission_type_name: str | None = None
    state: str
    latest_submission_id: str | None = None
    latest_submitted_at: str | None = None
    rule_evidence: list[dict] = Field(default_factory=list)
    detail: dict = Field(default_factory=dict)

class FacilitySubmissionRequirementComplianceOut(BaseModel):
    building_id: str
    evaluation_id: str
    evaluation_date: str
    facility_version: int
    matched_rule_count: int
    actionable_rule_count: int
    gap_candidate_count: int
    manual_review_count: int
    items: list[SubmissionRequirementComparisonItemOut] = Field(default_factory=list)
    unmapped_rules: list[dict] = Field(default_factory=list)
    note: str


class EquipmentTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=150)
    name: str = Field(min_length=1, max_length=300)
    category: str | None = None
    metadata: dict = Field(default_factory=dict)

class EquipmentTypeOut(BaseModel):
    equipment_type_id: str
    code: str
    name: str
    category: str | None = None
    active: bool
    metadata: dict = Field(default_factory=dict)

class FacilityEquipmentCreate(BaseModel):
    equipment_type_code: str
    floor_number: int | None = None
    location_text: str | None = None
    quantity: int | None = Field(default=None, ge=0)
    operational_status: Literal["installed","removed","unknown"] = "installed"
    verification_status: Literal["verified","unverified","legacy_only","ai_candidate"] = "verified"
    source_kind: Literal["manual","submission","legacy","drawing_ai","import"] = "manual"
    source_document_id: str | None = None
    submission_id: str | None = None
    installed_at: str | None = None
    last_verified_at: str | None = None
    notes: str | None = None

class FacilityEquipmentPatch(BaseModel):
    expected_version: int = Field(ge=1)
    floor_number: int | None = None
    location_text: str | None = None
    quantity: int | None = Field(default=None, ge=0)
    operational_status: Literal["installed","removed","unknown"] | None = None
    verification_status: Literal["verified","unverified","legacy_only","ai_candidate"] | None = None
    source_kind: Literal["manual","submission","legacy","drawing_ai","import"] | None = None
    source_document_id: str | None = None
    submission_id: str | None = None
    installed_at: str | None = None
    last_verified_at: str | None = None
    notes: str | None = None

class FacilityEquipmentOut(BaseModel):
    facility_equipment_id: str
    building_id: str
    equipment_type_id: str
    equipment_type_code: str
    equipment_type_name: str
    floor_number: int | None = None
    location_text: str | None = None
    quantity: int | None = None
    operational_status: str
    verification_status: str
    source_kind: str
    source_document_id: str | None = None
    submission_id: str | None = None
    installed_at: str | None = None
    last_verified_at: str | None = None
    notes: str | None = None
    version: int

class EquipmentRequirementComparisonItemOut(BaseModel):
    equipment_type_code: str
    equipment_type_name: str | None = None
    state: str
    verified_equipment_ids: list[str] = Field(default_factory=list)
    evidence_equipment_ids: list[str] = Field(default_factory=list)
    rule_evidence: list[dict] = Field(default_factory=list)
    detail: dict = Field(default_factory=dict)

class FacilityEquipmentRequirementComplianceOut(BaseModel):
    building_id: str
    evaluation_id: str
    evaluation_date: str
    facility_version: int
    matched_rule_count: int
    actionable_rule_count: int
    gap_candidate_count: int
    manual_review_count: int
    items: list[EquipmentRequirementComparisonItemOut] = Field(default_factory=list)
    unmapped_rules: list[dict] = Field(default_factory=list)
    note: str


class DrawingAnalysisCreate(BaseModel):
    document_id: str
    analysis_method: Literal["ai","manual","import"] = "ai"
    model_version: str | None = None
    page_count: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    summary: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)

class DrawingAnalysisOut(BaseModel):
    drawing_analysis_id: str
    building_id: str
    document_id: str
    status: str
    analysis_method: str
    model_version: str | None = None
    page_count: int | None = None
    confidence: float | None = None
    summary: dict
    evidence: dict
    version: int
    created_at: str

class DrawingElementCreate(BaseModel):
    page_no: int = Field(default=1, ge=1)
    element_type: str = Field(min_length=1, max_length=80)
    label: str | None = None
    floor_number: int | None = None
    geometry: dict = Field(default_factory=dict)
    extracted_data: dict = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_kind: Literal["ai","manual","import"] = "ai"

class DrawingElementOut(BaseModel):
    drawing_element_id: str
    drawing_analysis_id: str
    page_no: int
    element_type: str
    label: str | None = None
    floor_number: int | None = None
    geometry: dict
    extracted_data: dict
    confidence: float | None = None
    source_kind: str
    review_status: str

class DrawingEquipmentCandidateCreate(BaseModel):
    drawing_element_id: str | None = None
    suggested_equipment_type_code: str | None = None
    suggested_label: str | None = None
    floor_number: int | None = None
    location_text: str | None = None
    quantity: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)

class DrawingEquipmentCandidateReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["accepted","rejected"]

class DrawingEquipmentCandidatePromote(BaseModel):
    expected_version: int = Field(ge=1)
    equipment_type_code: str | None = None
    notes: str | None = None

class DrawingEquipmentCandidateOut(BaseModel):
    drawing_equipment_candidate_id: str
    drawing_analysis_id: str
    drawing_element_id: str | None = None
    equipment_type_id: str | None = None
    suggested_equipment_type_code: str | None = None
    suggested_label: str | None = None
    floor_number: int | None = None
    location_text: str | None = None
    quantity: int | None = None
    confidence: float | None = None
    status: str
    facility_equipment_id: str | None = None
    version: int

class DrawingFactCandidateCreate(BaseModel):
    drawing_element_id: str | None = None
    target_path: str = Field(min_length=1, max_length=200)
    proposed_value: dict
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: dict = Field(default_factory=dict)

class DrawingFactCandidateReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["accepted","rejected"]

class DrawingFactCandidateApply(BaseModel):
    expected_version: int = Field(ge=1)
    expected_facility_version: int = Field(ge=1)

class DrawingFactCandidateOut(BaseModel):
    drawing_fact_candidate_id: str
    drawing_analysis_id: str
    drawing_element_id: str | None = None
    target_path: str
    proposed_value: dict
    confidence: float | None = None
    evidence: dict
    status: str
    version: int
    applied_by: str | None = None
    applied_at: str | None = None
    applied_facility_version: int | None = None

class DrawingAnalysisReview(BaseModel):
    expected_version: int = Field(ge=1)

class DrawingPreviewInfoOut(BaseModel):
    drawing_analysis_id: str
    document_id: str
    original_filename: str
    mime_type: str | None = None
    preview_mode: Literal["image_direct","pdf_pages","unsupported"]
    page_count: int
    pages: list[dict] = Field(default_factory=list)
    render_scale_policy: str | None = None


class DrawingAnalysisDetailOut(BaseModel):
    analysis: DrawingAnalysisOut
    elements: list[DrawingElementOut] = Field(default_factory=list)
    equipment_candidates: list[DrawingEquipmentCandidateOut] = Field(default_factory=list)
    fact_candidates: list[DrawingFactCandidateOut] = Field(default_factory=list)


class DrawingManifestElement(BaseModel):
    client_ref: str | None = None
    page_no: int = Field(default=1, ge=1)
    element_type: str = Field(min_length=1, max_length=80)
    label: str | None = None
    floor_number: int | None = None
    geometry: dict = Field(default_factory=dict)
    extracted_data: dict = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)

class DrawingManifestEquipmentCandidate(BaseModel):
    drawing_element_ref: str | None = None
    suggested_equipment_type_code: str | None = None
    suggested_label: str | None = None
    floor_number: int | None = None
    location_text: str | None = None
    quantity: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)

class DrawingManifestFactCandidate(BaseModel):
    drawing_element_ref: str | None = None
    target_path: str = Field(min_length=1, max_length=200)
    proposed_value: dict
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: dict = Field(default_factory=dict)

class DrawingAnalysisResultManifest(BaseModel):
    expected_version: int = Field(ge=1)
    model_version: str | None = None
    page_count: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    summary: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)
    elements: list[DrawingManifestElement] = Field(default_factory=list)
    equipment_candidates: list[DrawingManifestEquipmentCandidate] = Field(default_factory=list)
    fact_candidates: list[DrawingManifestFactCandidate] = Field(default_factory=list)


class FireInvestigationCaseCreate(BaseModel):
    case_number: str | None = None
    building_id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    occurred_at: str | None = None
    location_text: str | None = None

class FireInvestigationCasePatch(BaseModel):
    expected_version: int = Field(ge=1)
    case_number: str | None = None
    building_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    occurred_at: str | None = None
    location_text: str | None = None
    status: Literal["draft","active","review","closed"] | None = None

class FireInvestigationCaseOut(BaseModel):
    fire_investigation_case_id: str
    case_number: str | None = None
    building_id: str | None = None
    title: str
    occurred_at: str | None = None
    location_text: str | None = None
    status: str
    official_cause_text: str | None = None
    official_cause_candidate_id: str | None = None
    final_report_document_id: str | None = None
    version: int
    cause_approved_by: str | None = None
    cause_approved_at: str | None = None
    created_at: str

class FireInvestigationMediaCreate(BaseModel):
    document_id: str
    media_type: Literal["photo","audio","video","drawing","other"]
    sequence_no: int | None = Field(default=None, ge=0)
    captured_at: str | None = None
    location_label: str | None = None
    floor_number: int | None = None
    notes: str | None = None
    ai_metadata: dict = Field(default_factory=dict)

class FireInvestigationMediaOut(BaseModel):
    fire_investigation_media_id: str
    fire_investigation_case_id: str
    document_id: str
    media_type: str
    sequence_no: int | None = None
    captured_at: str | None = None
    location_label: str | None = None
    floor_number: int | None = None
    notes: str | None = None
    review_status: str
    ai_metadata: dict

class FireReviewStateChange(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
    status: Literal["accepted","rejected","reviewed","confirmed"] | None = None

class FirePhotoAnnotationCreate(BaseModel):
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    map_position: dict = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_kind: Literal["ai","manual","import"] = "ai"
    model_version: str | None = None

class FirePhotoAnnotationOut(BaseModel):
    fire_photo_annotation_id: str
    fire_investigation_media_id: str
    description: str | None = None
    tags: list
    map_position: dict
    confidence: float | None = None
    source_kind: str
    model_version: str | None = None
    status: str
    version: int

class FirePhotoAnnotationReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["accepted","rejected"]

class FireTranscriptSegmentCreate(BaseModel):
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    speaker_label: str | None = None
    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_kind: Literal["ai","manual","import"] = "ai"
    model_version: str | None = None

class FireTranscriptSegmentOut(BaseModel):
    fire_transcript_segment_id: str
    fire_investigation_media_id: str
    start_ms: int | None = None
    end_ms: int | None = None
    speaker_label: str | None = None
    text: str
    uncertainty_markers: list = Field(default_factory=list)
    text_sha256: str | None = None
    confidence: float | None = None
    source_kind: str
    model_version: str | None = None
    review_status: str
    version: int

class FireTranscriptSegmentReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["accepted","rejected"]

class FireStatementDraftCreate(BaseModel):
    fire_investigation_media_id: str | None = None
    person_label: str | None = None
    draft_text: str = Field(min_length=1)
    evidence_segment_ids: list[str] = Field(default_factory=list)
    ai_generated: bool = False
    model_version: str | None = None

class FireStatementDraftReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["reviewed","rejected"]
    uncertainty_reviewed: bool = False

class FireStatementDraftOut(BaseModel):
    fire_statement_draft_id: str
    fire_investigation_case_id: str
    fire_investigation_media_id: str | None = None
    person_label: str | None = None
    draft_text: str
    evidence_segment_ids: list
    source_uncertainty_markers: list = Field(default_factory=list)
    uncertainty_reviewed: bool = False
    ai_generated: bool
    model_version: str | None = None
    status: str
    version: int

class FireTimelineEventCreate(BaseModel):
    event_time: str | None = None
    event_time_text: str | None = None
    event_type: str | None = None
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    source_refs: list[dict] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)

class FireTimelineEventReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["confirmed","rejected"]

class FireTimelineEventOut(BaseModel):
    fire_timeline_event_id: str
    fire_investigation_case_id: str
    event_time: str | None = None
    event_time_text: str | None = None
    event_type: str | None = None
    title: str
    description: str | None = None
    source_refs: list
    confidence: float | None = None
    status: str
    version: int

class FireCauseCandidateCreate(BaseModel):
    cause_category: str | None = None
    cause_text: str = Field(min_length=1)
    hypothesis: dict = Field(default_factory=dict)
    evidence_refs: list[dict] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    extraction_method: Literal["manual","ai","import"] = "manual"
    model_version: str | None = None

class FireCauseCandidateReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["reviewed","rejected"]

class FireCauseCandidateOut(BaseModel):
    fire_cause_candidate_id: str
    fire_investigation_case_id: str
    cause_category: str | None = None
    cause_text: str
    hypothesis: dict
    evidence_refs: list
    confidence: float | None = None
    extraction_method: str
    model_version: str | None = None
    status: str
    version: int

class FireOfficialCauseApprove(BaseModel):
    expected_case_version: int = Field(ge=1)
    cause_candidate_id: str

class FireReportDraftCreate(BaseModel):
    report_type: str = Field(min_length=1, max_length=120)
    form_template_id: str | None = None
    narrative_text: str | None = None
    structured_content: dict = Field(default_factory=dict)
    evidence_refs: list[dict] = Field(default_factory=list)
    ai_generated: bool = False
    model_version: str | None = None

class FireReportDraftReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["reviewed","rejected"]

class FireReportDraftApprove(BaseModel):
    expected_version: int = Field(ge=1)

class FireReportDraftOut(BaseModel):
    fire_report_draft_id: str
    fire_investigation_case_id: str
    report_type: str
    form_template_id: str | None = None
    narrative_text: str | None = None
    structured_content: dict
    evidence_refs: list
    fire_evidence_snapshot_id: str | None = None
    source_manifest_id: str | None = None
    ai_generated: bool
    model_version: str | None = None
    status: str
    version: int

class FireInvestigationCaseDetailOut(BaseModel):
    case: FireInvestigationCaseOut
    media: list[FireInvestigationMediaOut] = Field(default_factory=list)
    statements: list[FireStatementDraftOut] = Field(default_factory=list)
    timeline: list[FireTimelineEventOut] = Field(default_factory=list)
    cause_candidates: list[FireCauseCandidateOut] = Field(default_factory=list)
    report_drafts: list[FireReportDraftOut] = Field(default_factory=list)
    evidence_snapshots: list[dict] = Field(default_factory=list)


class FirePhotoAIAnnotationInput(BaseModel):
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    map_position: dict = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)

class FirePhotoAIManifest(BaseModel):
    model_version: str = Field(min_length=1, max_length=200)
    payload_metadata: dict = Field(default_factory=dict)
    annotations: list[FirePhotoAIAnnotationInput] = Field(default_factory=list)

class FireTranscriptAISegmentInput(BaseModel):
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    speaker_label: str | None = None
    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)

class FireTranscriptAIManifest(BaseModel):
    model_version: str = Field(min_length=1, max_length=200)
    payload_metadata: dict = Field(default_factory=dict)
    segments: list[FireTranscriptAISegmentInput] = Field(default_factory=list)

class FireStatementAIInput(BaseModel):
    fire_investigation_media_id: str | None = None
    person_label: str | None = None
    draft_text: str = Field(min_length=1)
    evidence_segment_ids: list[str] = Field(default_factory=list)

class FireStatementAIManifest(BaseModel):
    model_version: str = Field(min_length=1, max_length=200)
    payload_metadata: dict = Field(default_factory=dict)
    statements: list[FireStatementAIInput] = Field(default_factory=list)

class FireAIManifestIngestOut(BaseModel):
    fire_investigation_ai_manifest_id: str
    manifest_type: str
    manifest_sha256: str
    model_version: str | None = None
    created: bool
    derived_ids: list[str] = Field(default_factory=list)


class FireEvidenceSnapshotCreate(BaseModel):
    metadata: dict = Field(default_factory=dict)

class FireEvidenceSnapshotOut(BaseModel):
    fire_evidence_snapshot_id: str
    fire_investigation_case_id: str
    case_version: int
    snapshot_sha256: str
    photo_annotation_ids: list[str] = Field(default_factory=list)
    transcript_segment_ids: list[str] = Field(default_factory=list)
    statement_draft_ids: list[str] = Field(default_factory=list)
    timeline_event_ids: list[str] = Field(default_factory=list)
    official_cause_candidate_id: str | None = None
    media_document_hashes: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    created_at: str

class FireReportAIManifest(BaseModel):
    evidence_snapshot_id: str
    report_type: str = Field(min_length=1, max_length=120)
    form_template_id: str | None = None
    model_version: str = Field(min_length=1, max_length=200)
    narrative_text: str | None = None
    structured_content: dict = Field(default_factory=dict)
    evidence_refs: list[dict] = Field(default_factory=list)
    payload_metadata: dict = Field(default_factory=dict)


class FireReportExportCreate(BaseModel):
    expected_report_version: int = Field(ge=1)

class FireReportExportVerify(BaseModel):
    expected_case_version: int = Field(ge=1)

class FireReportExportOut(BaseModel):
    fire_report_export_id: str
    fire_report_draft_id: str
    form_template_id: str
    template_document_id: str
    template_sha256: str
    report_draft_version: int
    request_sha256: str
    output_format: str
    field_values: dict
    render_manifest: dict
    output_document_id: str | None = None
    status: str
    error_detail: str | None = None
    created_at: str


class FirePhotoProfileOut(BaseModel):
    fire_photo_profile_id: str
    fire_investigation_media_id: str
    photo_number: int | None = None
    image_width: int | None = None
    image_height: int | None = None
    orientation: int | None = None
    exif_captured_at: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    exif_metadata: dict = Field(default_factory=dict)
    exact_sha256: str
    perceptual_hash: str | None = None
    duplicate_of_media_id: str | None = None
    duplicate_distance: int | None = None
    brightness_score: float | None = None
    contrast_score: float | None = None
    sharpness_score: float | None = None
    quality_flags: list[str] = Field(default_factory=list)
    search_text: str = ""
    analysis_version: str
    analyzed_at: str

class FirePhotoSearchItemOut(BaseModel):
    media: FireInvestigationMediaOut
    profile: FirePhotoProfileOut | None = None
    accepted_annotations: list[FirePhotoAnnotationOut] = Field(default_factory=list)
    search_score: int = 0


class FirePhotoPlanLinkCreate(BaseModel):
    drawing_analysis_id: str
    drawing_element_id: str | None = None
    page_no: int | None = Field(default=None, ge=1)
    floor_number: int | None = None
    position: dict = Field(default_factory=dict)
    label: str | None = None
    source_kind: Literal["manual","ai","import"] = "manual"
    confidence: float | None = Field(default=None, ge=0, le=1)

class FirePhotoPlanLinkReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["accepted","rejected"]

class FirePhotoPlanLinkOut(BaseModel):
    fire_photo_plan_link_id: str
    fire_investigation_media_id: str
    drawing_analysis_id: str
    drawing_element_id: str | None = None
    page_no: int | None = None
    floor_number: int | None = None
    position: dict
    label: str | None = None
    source_kind: str
    confidence: float | None = None
    status: str
    version: int


class FireTranscriptSearchItemOut(BaseModel):
    segment: FireTranscriptSegmentOut
    media: FireInvestigationMediaOut
    search_score: int

class FireEvidenceRef(BaseModel):
    type: Literal["transcript_segment","statement","timeline_event"]
    id: str

class FireEvidenceComparisonCreate(BaseModel):
    issue_type: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1)
    left_ref: FireEvidenceRef
    right_ref: FireEvidenceRef
    evidence_refs: list[FireEvidenceRef] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)

class FireEvidenceComparisonAIManifest(BaseModel):
    model_version: str = Field(min_length=1)
    comparisons: list[FireEvidenceComparisonCreate] = Field(default_factory=list)
    payload_metadata: dict = Field(default_factory=dict)

class FireEvidenceComparisonReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["accepted","rejected"]

class FireEvidenceComparisonOut(BaseModel):
    fire_evidence_comparison_candidate_id: str
    fire_investigation_case_id: str
    issue_type: str
    summary: str
    left_ref: dict
    right_ref: dict
    evidence_refs: list
    confidence: float | None = None
    extraction_method: str
    model_version: str | None = None
    status: str
    version: int


class UnifiedSearchHitOut(BaseModel):
    module: str
    source_type: str
    source_id: str
    title: str
    snippet: str
    score: float
    building_id: str | None = None
    parent_id: str | None = None
    occurred_at: str | None = None
    required_permission: str
    navigation: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)

class UnifiedSearchResponse(BaseModel):
    query: str
    hits: list[UnifiedSearchHitOut] = Field(default_factory=list)
    searched_modules: list[str] = Field(default_factory=list)
    skipped_modules: list[str] = Field(default_factory=list)
    total_hits: int = 0
    note: str


class FireAudioBenchmarkRunCreate(BaseModel):
    dataset_label: str = Field(min_length=1, max_length=300)
    result_payload: dict

class FireAudioBenchmarkRunReview(BaseModel):
    expected_version: int = Field(ge=1)
    human_decision: Literal["accepted_baseline","rejected_baseline"]
    review_notes: str | None = None

class FireAudioBenchmarkRunOut(BaseModel):
    fire_audio_benchmark_run_id: str
    benchmark_format: str
    dataset_label: str
    manifest_sha256: str | None = None
    result_sha256: str
    recording_count: int
    result_payload: dict
    review_status: str
    human_decision: str | None = None
    review_notes: str | None = None
    version: int
    created_at: str
    reviewed_at: str | None = None


class FireAudioBenchmarkComparisonOut(BaseModel):
    left_id: str
    right_id: str
    left_dataset_label: str
    right_dataset_label: str
    left_review_status: str
    right_review_status: str
    metrics: dict
    note: str


class FireEvidenceComparisonBenchmarkRunCreate(BaseModel):
    dataset_label: str = Field(min_length=1, max_length=300)
    result_payload: dict

class FireEvidenceComparisonBenchmarkRunReview(BaseModel):
    expected_version: int = Field(ge=1)
    human_decision: Literal["accepted_baseline","rejected_baseline"]
    review_notes: str | None = None

class FireEvidenceComparisonBenchmarkRunOut(BaseModel):
    fire_evidence_comparison_benchmark_run_id: str
    benchmark_format: str
    dataset_label: str
    manifest_sha256: str | None = None
    result_sha256: str
    case_count: int
    result_payload: dict
    review_status: str
    human_decision: str | None = None
    review_notes: str | None = None
    version: int
    created_at: str
    reviewed_at: str | None = None

class FireEvidenceComparisonBenchmarkComparisonOut(BaseModel):
    left_id: str
    right_id: str
    left_dataset_label: str
    right_dataset_label: str
    left_review_status: str
    right_review_status: str
    metrics: dict
    note: str


class DrawingBenchmarkRunCreate(BaseModel):
    dataset_label: str = Field(min_length=1, max_length=300)
    result_payload: dict

class DrawingBenchmarkRunReview(BaseModel):
    expected_version: int = Field(ge=1)
    human_decision: Literal["accepted_baseline","rejected_baseline"]
    review_notes: str | None = None

class DrawingBenchmarkRunOut(BaseModel):
    drawing_benchmark_run_id: str
    benchmark_format: str
    dataset_label: str
    manifest_sha256: str | None = None
    result_sha256: str
    drawing_count: int
    result_payload: dict
    review_status: str
    human_decision: str | None = None
    review_notes: str | None = None
    version: int
    created_at: str
    reviewed_at: str | None = None

class DrawingBenchmarkComparisonOut(BaseModel):
    left_id: str
    right_id: str
    left_dataset_label: str
    right_dataset_label: str
    left_review_status: str
    right_review_status: str
    metrics: dict
    note: str


class DrawingAnnotationSetCreate(BaseModel):
    coordinate_space: Literal["pixel","normalized"] = "pixel"
    page_dimensions: dict = Field(default_factory=dict)
    payload: dict = Field(default_factory=dict)
    source_method: Literal["manual","ai_seed","import"] = "manual"

class DrawingAnnotationSeedCreate(BaseModel):
    expected_analysis_version: int = Field(ge=1)
    coordinate_space: Literal["pixel","normalized"] = "pixel"
    page_dimensions: dict = Field(default_factory=dict)

class DrawingAnnotationSetUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    coordinate_space: Literal["pixel","normalized"] = "pixel"
    page_dimensions: dict = Field(default_factory=dict)
    payload: dict

class DrawingAnnotationReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["reviewed","rejected"]

class DrawingAnnotationSetOut(BaseModel):
    drawing_annotation_set_id: str
    drawing_analysis_id: str
    annotation_kind: str
    coordinate_space: str
    page_dimensions: dict
    payload: dict
    source_method: str
    status: str
    version: int
    created_at: str
    reviewed_at: str | None = None


class DrawingConsultationCreate(BaseModel):
    drawing_annotation_set_id: str
    answers: dict = Field(default_factory=dict)
    notes: str | None = None

class DrawingConsultationUpdateAnswers(BaseModel):
    expected_version: int = Field(ge=1)
    answers: dict

class DrawingConsultationClassify(BaseModel):
    expected_version: int = Field(ge=1)
    evaluation_date: str | None = None

class DrawingConsultationClassificationConfirm(BaseModel):
    expected_version: int = Field(ge=1)
    classification_code: str = Field(min_length=1, max_length=100)
    classification_label: str = Field(min_length=1)
    candidate_rule_version_id: str | None = None
    review_note: str | None = None

class DrawingConsultationEquipmentEvaluate(BaseModel):
    expected_version: int = Field(ge=1)
    evaluation_date: str | None = None

class DrawingConsultationOut(BaseModel):
    drawing_consultation_id: str
    drawing_analysis_id: str
    drawing_annotation_set_id: str
    status: str
    input_snapshot: dict
    classification_results: list = Field(default_factory=list)
    missing_information: list = Field(default_factory=list)
    confirmed_classification_code: str | None = None
    confirmed_classification_label: str | None = None
    confirmed_classification_rule_version_id: str | None = None
    equipment_results: list = Field(default_factory=list)
    placement_results: list = Field(default_factory=list)
    consultation_notes: str | None = None
    version: int
    created_at: str
    classification_confirmed_at: str | None = None


class OccupancyCatalogImportRequest(BaseModel):
    catalog: dict
    apply: bool = False

class OccupancyCatalogImportOut(BaseModel):
    apply: bool
    stats: dict
    note: str


class LegalStructureRebuildRequest(BaseModel):
    expected_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    force: bool = False

class LegalStructureRebuildOut(BaseModel):
    changed: bool
    result: dict

class OccupancyCatalogReadinessRequest(BaseModel):
    catalog: dict

class OccupancyCatalogReadinessOut(BaseModel):
    readiness: dict


class OccupancyAuthoringBulkConditionItem(BaseModel):
    draft_id: str
    expected_version: int = Field(ge=1)
    proposed_conditions: dict
    rationale: str | None = None

class OccupancyAuthoringBulkConditionRequest(BaseModel):
    source_xml_sha256: str = Field(min_length=64, max_length=64)
    updates: list[OccupancyAuthoringBulkConditionItem] = Field(min_length=1)
    apply: bool = False

class OccupancyAuthoringWorklistOut(BaseModel):
    source_xml_sha256: str | None = None
    expected_classification_count: int
    allowed_condition_fields: list[str]
    summary: dict
    items: list

class OccupancyAuthoringBulkConditionOut(BaseModel):
    result: dict

class OccupancyRuleCoverageOut(BaseModel):
    coverage: dict


class OccupancyRegressionCaseCreate(BaseModel):
    source_xml_sha256: str = Field(min_length=64, max_length=64)
    name: str = Field(min_length=1, max_length=300)
    input_snapshot: dict
    expected_classification_codes: list[str] = Field(min_length=1)
    notes: str | None = None

class OccupancyRegressionCaseUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=300)
    input_snapshot: dict
    expected_classification_codes: list[str] = Field(min_length=1)
    notes: str | None = None

class OccupancyRegressionCaseReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["reviewed","rejected"]

class OccupancyRegressionCaseOut(BaseModel):
    occupancy_classification_test_case_id: str
    source_xml_sha256: str
    name: str
    input_snapshot: dict
    expected_classification_codes: list[str]
    notes: str | None = None
    status: str
    version: int
    created_at: str
    reviewed_at: str | None = None

class OccupancyRegressionRunCreate(BaseModel):
    source_xml_sha256: str = Field(min_length=64, max_length=64)

class OccupancyRegressionRunReview(BaseModel):
    expected_version: int = Field(ge=1)
    human_decision: Literal["accepted_regression","rejected_regression"]
    review_notes: str | None = None

class OccupancyRegressionRunOut(BaseModel):
    occupancy_classification_test_run_id: str
    source_xml_sha256: str
    result_sha256: str
    case_count: int
    passed_case_count: int
    failed_case_count: int
    ambiguous_case_count: int
    result_payload: dict
    review_status: str
    human_decision: str | None = None
    review_notes: str | None = None
    version: int
    created_at: str
    reviewed_at: str | None = None


class EquipmentRequirementBatchImportRequest(BaseModel):
    items: list[dict] = Field(min_length=1)
    source_metadata: dict = Field(default_factory=dict)
    apply: bool = False

class EquipmentRequirementBatchImportOut(BaseModel):
    result: dict

class EquipmentRequirementBatchCoverageOut(BaseModel):
    coverage: dict


class EquipmentRegressionCaseCreate(BaseModel):
    worklist_sha256: str = Field(min_length=64, max_length=64)
    name: str = Field(min_length=1, max_length=300)
    input_snapshot: dict
    expected_equipment_type_codes: list[str] = Field(default_factory=list)
    notes: str | None = None

class EquipmentRegressionCaseUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=300)
    input_snapshot: dict
    expected_equipment_type_codes: list[str] = Field(default_factory=list)
    notes: str | None = None

class EquipmentRegressionCaseReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["reviewed","rejected"]

class EquipmentRegressionCaseOut(BaseModel):
    equipment_requirement_test_case_id: str
    worklist_sha256: str
    name: str
    input_snapshot: dict
    expected_equipment_type_codes: list[str]
    notes: str | None = None
    status: str
    version: int
    created_at: str
    reviewed_at: str | None = None

class EquipmentRegressionRunCreate(BaseModel):
    worklist_sha256: str = Field(min_length=64, max_length=64)
    evaluation_date: str | None = None

class EquipmentRegressionRunReview(BaseModel):
    expected_version: int = Field(ge=1)
    human_decision: Literal["accepted_regression","rejected_regression"]
    review_notes: str | None = None

class EquipmentRegressionRunOut(BaseModel):
    equipment_requirement_test_run_id: str
    worklist_sha256: str
    result_sha256: str
    case_count: int
    passed_case_count: int
    failed_case_count: int
    over_requirement_case_count: int
    under_requirement_case_count: int
    result_payload: dict
    review_status: str
    human_decision: str | None = None
    review_notes: str | None = None
    version: int
    created_at: str
    reviewed_at: str | None = None


class EquipmentPlacementBatchImportRequest(BaseModel):
    items: list[dict] = Field(min_length=1)
    source_metadata: dict = Field(default_factory=dict)
    apply: bool = False

class EquipmentPlacementBatchImportOut(BaseModel):
    result: dict

class EquipmentPlacementBatchCoverageOut(BaseModel):
    coverage: dict


class EquipmentPlacementRegressionCaseCreate(BaseModel):
    worklist_sha256: str = Field(min_length=64, max_length=64)
    name: str = Field(min_length=1, max_length=300)
    input_snapshot: dict
    rooms: list[dict] = Field(min_length=1)
    equipment_type_codes: list[str] = Field(min_length=1)
    expected_results: list[dict] = Field(min_length=1)
    notes: str | None = None

class EquipmentPlacementRegressionCaseUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=300)
    input_snapshot: dict
    rooms: list[dict] = Field(min_length=1)
    equipment_type_codes: list[str] = Field(min_length=1)
    expected_results: list[dict] = Field(min_length=1)
    notes: str | None = None

class EquipmentPlacementRegressionCaseReview(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["reviewed","rejected"]

class EquipmentPlacementRegressionCaseOut(BaseModel):
    equipment_placement_test_case_id: str
    worklist_sha256: str
    name: str
    input_snapshot: dict
    rooms: list[dict]
    equipment_type_codes: list[str]
    expected_results: list[dict]
    notes: str | None = None
    status: str
    version: int
    created_at: str
    reviewed_at: str | None = None

class EquipmentPlacementRegressionRunCreate(BaseModel):
    worklist_sha256: str = Field(min_length=64, max_length=64)
    evaluation_date: str | None = None

class EquipmentPlacementRegressionRunReview(BaseModel):
    expected_version: int = Field(ge=1)
    human_decision: Literal["accepted_regression","rejected_regression"]
    review_notes: str | None = None

class EquipmentPlacementRegressionRunOut(BaseModel):
    equipment_placement_test_run_id: str
    worklist_sha256: str
    result_sha256: str
    case_count: int
    passed_case_count: int
    failed_case_count: int
    state_mismatch_case_count: int
    marker_mismatch_case_count: int
    constraint_mismatch_case_count: int
    result_payload: dict
    review_status: str
    human_decision: str | None = None
    review_notes: str | None = None
    version: int
    created_at: str
    reviewed_at: str | None = None


class DrawingConsultationResponseReview(BaseModel):
    expected_version: int = Field(ge=1)
    evaluation_date: str | None = None
    review_notes: str | None = None

class DrawingConsultationResponseOut(BaseModel):
    response_format: str
    evaluation_date: str
    consultation_id: str
    source: dict
    classification: dict
    input_snapshot: dict
    existing_equipment: list
    required_equipment: list
    equipment_actions: list
    placement_results: list
    overlay_markers: list
    citations: list
    cited_provision_hashes: list
    unresolved_questions: list
    coverage: dict
    coverage_complete: bool
    blockers: list
    answer_state: str
    reviewable: bool
    response_sha256: str
    saved_response_sha256: str | None = None
    review_current: bool
    review_stale: bool
    reviewed_at: str | None = None
    response_review_notes: str | None = None
