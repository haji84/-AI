# Existing interface audit — Run B

Inspected main: `240703a9f0fa752da7b282a25f60c234f309703d`.
This records inspected interfaces, not completion or operational acceptance.

| Shared source | Existing interface | Run B use |
|---|---|---|
| Staff | `Employee.employee_id`, active flag, organization_unit/title strings | Reference the immutable employee ID. No independent staff master. Historical organization assignments must use Run A's eventual adapter; current strings cannot prove historical placement. |
| Emergency | `EmergencyCase.emergency_case_id`, patient/crew/treatment/review/report services | Link dispatch to case; source address/date/number remain in emergency source. |
| Fire investigation | `FireInvestigationCase.fire_investigation_case_id`, fire_investigations/fire_photos/fire_report_exports routers | Preserve existing Phase APIs, candidate review, official cause approval and Evidence snapshots. |
| Original files | `Document.document_id`, managed storage, upload/read/download | Preserve originals; source permission required independently of target-module permission. |
| Official originals | `FormTemplate.form_template_id`, templates router, existing original renderer | Add explicit report adapters. A successful fill is not Human verification of official output. |
| Vendors/contracts | `ContractCounterparty.counterparty_id`, `ContractCase.contract_case_id`, ContractDocument/ContractChange | Extend fiscal/procurement workflows; do not create parallel vendors/contracts. |

## Inspected fire functionality to retain

Case/media APIs, photo analysis and EXIF, duplicate candidates, plan links and review,
transcript manifests/segments/search/corrections, statement manifests/drafts/review,
evidence comparison manifests/review, timeline events/review, cause candidates/review,
separate official-cause approval, evidence snapshots, report manifests/drafts/review/
approval and original-template export/verification exist. Their presence alone does
not prove actual model execution, every UI workflow or operational acceptance.

## Inspected document intake boundaries

Existing extract_document supports PDF text/OCR, images/OCR, DOCX, XLSX/XLSM and
text/CSV/TSV. Analysis uses extracted content rather than filename for submission
classification. Audio is not a supported extraction input in this inspected version.
Current deterministic classifiers cover equipment inspection reports, fire-manager
appointments and fire plans. Extend through compatible typed adapters; preserve the
existing review/confirm-receipt/apply gates.

## Verification limitations

SQLite regression tests cannot prove PostgreSQL two-transaction lock behavior.
No Chromium binary or agent-browser CLI is available in this workspace at this
inspection. JavaScript syntax and synthetic renderer tests are available; browser
interaction verification must be obtained separately before claiming it passed.
Tenant isolation and common organization/history are Run A integration dependencies,
not existing guarantees inferred from these module tests.
