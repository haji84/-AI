# Completion Run B Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development task by task. User explicitly authorizes normal implementation/PR/CI/merge without repeated approval questions.

Goal: implement remaining shared operational modules and integrate into the single main application.
Architecture: existing FastAPI/SQLAlchemy/PostgreSQL core; additive domain modules; common IDs; existing RBAC/audit/Document/template/search interfaces. No common-base redesign.
Spec: docs/completion/RUN_B_CONTRACT.md plus original user Completion Run B requirements.

## Global Constraints

- User request and AGENTS.md binding; reuse main latest and preserve Run A boundaries.
- Source evidence / AI candidate / Human-reviewed / official separate; no automatic official promotion.
- backend read/create/update/review/approve/admin as appropriate; dedicated sensitive read rights.
- Database-backed optimistic concurrency and transactionally committed audit.
- Shared Employee/Facility/Document/Equipment/Incident/Vehicle IDs, no separate masters.
- No real operational files or individual data in Git; synthetic tests only.
- PC browser, same shell/session/navigation; no new app or paid package.
- Existing migrations immutable; new numbers provisional until refreshed-main checks.
- Every task: focused failing tests first, implementations, full regression/SQL parser/frontend syntax, independent review, CI and main merge.

## Review Focus

- Editing zero-valued data must preserve zero.
- Concurrent import/edit/review cannot approve stale evidence or lose versions.
- Missing codes/IDs and unknown dates remain explicit; no guessed legacy meaning.
- Aggregate/search/export must not leak details beyond permissions.
- Existing source-linked cases and masters must be reused, including inactive/history semantics.

## Tasks and boundaries

1. Emergency operational first slice — DONE via PR40/main240703a9; 211 tests; current internal gaps retained in status.
2. Shared Incident/Dispatch + fleet operational module — detailed task brief in docs/completion/task-2-brief.md. Own backend operational models/schema/service/router, migration040 (after canonical Run A tenant-identity039), shared-shell operational.js, synthetic tests, integration/rbac/search registration. No editing Run A core semantics.
3. Operational assets/inventory — assets_model/schema/router/service; append-only movement history; location/quantity/loan-return/inspection/repair/renewal/disposal/pressure-test/expiry/calibration/consumable-drug stock/reorder candidates; no confusion with FacilityEquipment. CRUD/RBAC/lock/audit/import/export/search/PC UI tests.
4. Contract procurement + budget — extend existing ContractCase/Counterparty/Document; quotes/commitments/payments/year/deadlines and budget year/account款項目節細節/initial/amendment/transfer/execution/remaining/request/next-year estimates. Decimal money; explicit Human approvals; transactional cross-links; CSV/Excel; existing template output.
5. Workforce — shared Employee and Run A current/effective-history adapter; teams/rosters/shift types/placement/minimum staffing/available crew/leave-special leave/balances/attendance/overtime/comp-time/support/moves/warnings/statistics. No new Employee master or invented legal policy; configurable approved staffing/leave rules.
6. Evidence-required council/inquiries — question/history/year/source document/numeric source/module links/similarity/draft/Human confirm; reject unsupported figures and ungrounded answer promotion.
7. Cross-module statistics/surveys — emergency/fire/rescue/inspection/submission/equipment/personnel/fleet/other; monthly/yearly/prior-year; source lineage; CSV/Excel/official templates. Reuse domain query services.
8. Document intake and generic official output adapters — retain Document content parsers; audio candidate adapter; candidate classification/submitter/date/content/attachments/targets/destination; Human apply; original templates PDF/XLSX/DOCX binding and hashes; source evidence tracking.
9. Complete emergency gaps — transport/severity/classification masters, full dated time checks, structured reports/post-review/lifesaving forms, normalized CSV/XLSX import with source provenance, correction/retirement histories, crew statistics and official template rendering. Existing module stays authoritative.
10. Fire investigation remaining audit/gaps — retain existing evidence/photo/transcription/speaker/uncertainty/Human statement/compare/timeline/cause/report-template workflows; complete real worker adapters without claims of measured accuracy. All AI cause and official cause distinct.
11. Permission-based shared dashboard — today's tasks/deadlines/unprocessed/review/expiry/inspection/repair/contracts/budget/statistics; connect existing search with backend gates, pagination and provenance.
12. Full Run B audit/integration completion — all module APIs/UI/DB/migrations/permissions/integration/background/config/dependencies/tests/limitations tracked; no internal Partial/Missing remains; all CI main green; final INTEGRATION_HANDOFF and completion report. Actual External Gates explicit.

## Verification / task execution

Task N begins by reading current main commit/state/AGENTS/PRs/migrations and checking whether function already landed. Implementer works only specified domain paths; never dispatches helpers. Parent coordinates review/CI/merge. Task completed only after source and tests integrate, not merely because scaffolding exists. Missing requirements remain explicit until implemented.

Task2 latest-main integration base: main8323930e / PR41. Exact canonical tenant/startup/Host/storage/BoundSession semantics are adopted; operations router remains additive. Only Run B provisional039 is renamed040. Operational two-DB/source-isolation regressions and optional inherited-CI PostgreSQL lock test are required before refreshed review/CI/merge.
