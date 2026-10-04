# PROJECT_STATE

更新日: 2026-10-05

## Current Phase

Phase 5 managed legal-rule / requirement-evaluation core is code-complete and CI-verified.
Formal approved-host PostgreSQL/TLS/two-client gate remains unexecuted.
Actual official legal content has not been populated and must not be treated as completed.

## Phase 0-4 retained

- legacy inspection ledger audit / 574-column mapping
- auth / RBAC / audit / optimistic locking / extensibility
- emergency reporting import foundation
- facility CRUD / normalized detail / conflict UI
- inspection / findings
- submission type / receipt / original document linkage
- PDF/image/DOCX/XLSX/text document intake
- OCR fallback path and deterministic document classification
- human review before receipt/facility change
- contract/form-template/extensibility foundation
- operational legacy values preserved as evidence without falsely promoting them to modern filings

## Phase 5 completed in code

- legal rule registry
- immutable numbered rule versions
- effective date ranges
- source document/reference requirement before approval
- draft / approved separation
- non-overlapping approved effective periods per rule
- deterministic condition engine
- submission-requirement / equipment-requirement domains
- requirement evaluation history
- candidate-only decisions
- evidence per matched condition
- rule management/approval/evaluation RBAC separation
- facility-detail UI for candidate required documents/equipment
- no automatic facility/submission/equipment mutation from evaluation

## Phase 5 verification

- backend tests: 39 passed
- Migration 008 parser: PASS (8 statements)
- frontend JavaScript syntax: PASS
- GitHub Actions project-checks: SUCCESS
- Phase 0-4 automated regression included

## Last verified real legacy dataset state

From the preceding real-workbook regression:
- facilities: 611
- facility details: 611
- facility contacts: 611
- facility floors: 1,434
- emergency cases: 2,958
- emergency patients: 2,950
- emergency crew: 8,981
- unresolved crew identity: 66 retained

Phase 5 did not rerun the supplied operational workbooks because production data is intentionally excluded from GitHub.
Do not report a Phase 5 real-workbook regression as newly executed.

## Not yet reported as PASS

- actual official legal-rule population from verified primary sources
- complete Japanese fire-law/ordinance requirement acceptance testing
- complex mixed-use/floor/windowless/underground conditions
- actual Japanese scanned-form OCR quality E2E
- HEIC decode
- Local LLM ambiguous-classification fallback
- approved LAN PostgreSQL migrations 001-008
- PostgreSQL backup/restore after Migration 008
- HTTPS browser test from production LAN clients
- two physical client concurrent edit/receipt/rule E2E

## Next Phase 5 Slice / Phase 6 preparation

1. register official source documents with provenance/version
2. expand rule-condition model for floor/use/windowless/underground conditions
3. compare required-document candidates against actual submission status
4. compare required-equipment candidates against installed-equipment records
5. add Human Review confirmation state for evaluation results
6. prepare Phase 6 drawing-analysis data model
7. keep AI explanatory only; formal rules remain deterministic and approved
