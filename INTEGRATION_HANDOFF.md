# Completion Run B — integration handoff (live)

Status: IN PROGRESS; not the final completion handoff.
Baseline: main 6bf797d17929fe4ebd1f11c2e6000e5e09190113.
Detailed remaining scope: docs/completion/RUN_B_STATUS.md.

## Added module surface

Existing module emergency_reporting is extended; no parallel application or duplicated Case/Patient/Employee/Document master.
- Models in app.emergency_models; loaded by registered emergency router.
- Tables: emergency_treatments; emergency_report_drafts.
- Existing table emergency_clinical_flags gets optimistic version and unique candidate_fingerprint columns.
- Migration 038; append-only relative to baseline 001–037, re-number if main advances.
- Relationships: treatments.patient -> emergency_patients; treatment.source_document -> documents; treatment.created_by -> app_users; report.case -> emergency_cases; report creators/reviewers -> app_users. Existing crew.employee -> employees remains authoritative.

## API and permissions

router app.routers.emergency, /emergency:
- cases list/detail/create/update: emergency.case.read/create/update.
- patients list/create/update: emergency.patient.read/create/update; parent-case read on listing/creation.
- crew list/create: emergency.crew.read/manage; common employee required.
- treatments list/create: emergency.patient.read/update; source Document requires document.read.
- clinical candidates: emergency.clinical.generate + emergency.patient.read.
- candidate review: emergency.clinical.review + emergency.patient.read; expected_version and unchanged evidence required.
- report snapshots create/list/review: emergency.report.create/read/review plus case/patient/crew read.
- input checks: case/patient/crew read.
- clinical-statistics: emergency.report.read; aggregate counts only; no individual IDs/text.
- audited workbook import: emergency.import; reuses app.importers.emergency.

Permissions added by existing seed_rbac; new emergency_editor and emergency_reviewer roles.
Existing emergency_reporter remains aggregate-only; no patient privilege added.
Existing audited importer now locks and refreshes existing parent Case and Patient rows, matching operational lock order; original mapping is unchanged.
Existing main /emergency/reports/summary and /export + emergency.report.export are retained, not reimplemented.

## Frontend

Existing /ui/ header has emergency module button; /ui/emergency.js uses shared session/api/escaping/modal styles.
Uses main /auth/permissions. Main /ui/emergency.html remains the aggregate/output screen.
No smartphone-specific scope or external frontend package.
Case search joins existing search registry, requires emergency.case.read, excludes patient fields.

## AI / review / audit

No LLM inference added. Deterministic CPA/allergy candidates store rule version, source field snapshots, patient version, treatment IDs and provenance hash.
CPR/chest compression records only suggest CPA; Human must review evidence.
Unknown/negated free text is not assigned a fabricated diagnosis.
Candidates never mutate the patient diagnosis or source payload.
Confirmed flags with changed evidence are excluded from clinical counts; old evidence remains intact.
Reports capture source snapshots; Human review rejects changed evidence and reviewed reports are immutable.
Write/import/review/statistics actions use existing write_audit.

## Configuration, workers, dependencies

No new background process; no new package dependency.
Uses existing FIRE_AI_DATABASE_URL, FIRE_AI_STORAGE_ROOT and server session configuration.
Re-run existing scripts/seed_rbac.py after deployment; apply new migration using existing migration runner.
Tenant routing/isolation remains Run A's DB/service contract. This slice does not declare tenant isolation implemented or tested.

## Integration tests

backend/tests/test_run_b_emergency.py: operational CRUD/version conflict, candidate separation/Human review/stale evidence, negation, checks, source immutability, report snapshot, shared employee, audited workbook idempotency, RBAC privacy, case search, UI wiring.
Existing test_emergency_reports.py and all prior tests must remain green.
Migration parser and frontend JavaScript syntax are required. Production PostgreSQL migration and actual browser acceptance are still required.

## Known limitations / connection points

- Structured report forms, official template export, CSV mapping, code-name masters and full date/day-offset validation remain internal backlog.
- Case/patient deletion/retirement and treatment/report editing UI are not implemented in this slice.
- Text candidate rules are intentionally conservative and not a clinical classifier.
- Clinical candidates have database-unique source fingerprints; parent-case/patient row locks serialize PostgreSQL clinical/record/report operations. Actual PostgreSQL concurrent-client acceptance remains required.
- Run A must provide tenant/isolation and common organization/history contract before workforce integration acceptance.
- Shared Incident/Dispatch, fleet/assets, budgets/contracts execution, inquiries/statistics/dashboard remain Run B backlog.
- Full Run B completion and system release are not declared.
