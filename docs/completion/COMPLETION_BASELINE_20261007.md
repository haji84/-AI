# Fire AIOS completion baseline — 2026-10-07, c1b684c

> Historical evidence, not the current status index. Every path/line below is fixed to [c1b684c](https://github.com/haji84/-AI/tree/c1b684c5c38fc52fe908d2116a21a16ef48dcb34). The current ledger and its delta entries supersede later work recommendations and merge states. All 57 chapter findings, their internal/external gates, workflow evidence, and reproduced probes are retained here. Editorial normalization removes coordination-only wording and clarifies checkpoint preservation; it does not credit later code to this baseline.

Audit date: 2026-10-07 UTC

Canonical source: `c1b684c5c38fc52fe908d2116a21a16ef48dcb34`

Verified Git tree: `854281ffccba7ed67dc5de9aa400311c1f0371ae`

Scope: all 57 chapters of Master Specification v2.0, read-only source audit.

## Baseline decision

The current source contains substantial, connected operational software. It does **not** yet satisfy the system Definition of Done. The identified gaps concern permissions, lifecycle, configuration, and acceptance. Existing workforce and statistics checkpoint material must be preserved and compared with canonical main before potentially overlapping work.

Two permission/configuration gaps were reproduced during this audit using the exact source and an isolated synthetic in-memory database:

1. A user denied direct inspection and submission access still receives their counts, submission state, and a submission ID through the facility dashboard.
2. Setting `module.operations.enabled=false` does not disable its operational API: the incident list still returns records.

The older completion matrix understates current work in several places. Release packaging exists; unified search already includes emergency cases, workforce, finance, inquiries, and violations; shared-session response guards exist; and several required cross-module chains have substantive API or browser evidence. Those items should not be reimplemented from stale “Missing” labels.

This ledger does not turn chapter counts into a completion percentage. Chapters differ greatly in scope, and an implemented foundation is not equivalent to whole-chapter acceptance.

**Validated primary status totals at c1b684c: Completed 11 / Partial 42 / Missing 3 / External Gate 1 = 57.**

| Primary status | Chapters | Count |
|---|---|---:|
| Completed | 2, 8, 11, 22, 24, 40, 42, 47, 55, 56, 57 | 11 |
| Partial | 1, 3–7, 9–10, 12–15, 17–21, 23, 25–33, 35, 37–39, 41, 43–46, 48, 50–54 | 42 |
| Missing | 16, 34, 36 | 3 |
| External Gate | 49 | 1 |
| Total | All canonical chapters 1–57, exactly once | 57 |

These statuses retain the established chapter-scope definitions. Completed credits the bounded chapter's implemented internal foundation and required core workflow; it does not imply system completion or production acceptance. Open whole-system tests, actual-host acceptance and future adapter conformance do not by themselves downgrade a finished chapter. Missing is strictly an integration gap in this exact main snapshot, not a declaration that inaccessible Run A/B work is absent or lost. Unmerged PR #67/#68/#69, local hazardous-register work, and the local dashboard repair contribute no completed-main credit. The separately incomplete historical architecture context remains unresolved.

### Validated changes from the historical matrix

The historical **14 Completed / 37 Partial / 5 Missing / 1 External Gate** totals are a dated baseline, not the current result. Independent classification review retained only these five evidence-backed changes; the earlier acceptance-only reclassification proposal is superseded.

| Chapter | Historical → current | Concrete reason and exact evidence |
|---|---|---|
| 5 Common Data Principles | Completed → Partial | Formal-data correction requires reason, source evidence and approval as well as before/after/version (`docs/SPECIFICATION.md:268`). Direct inspection/finding PATCH schemas and services do not collect/store the full context (`backend/app/schemas.py:311`, `:341`; `backend/app/routers/inspections.py:146`, `:210`); before/after audit alone (`:177`, `:240`) does not satisfy that contract. |
| 9 Document Platform | Completed → Partial | Common metadata includes logical display name, source module and derived-document/extraction provenance (`docs/SPECIFICATION.md:430`). The generic Document model and upload/read contract lack a complete independent display-name and generic source/derived relationship (`backend/app/models.py:155`; `backend/app/routers/documents.py:15`, `:39`). Domain-local manifests remain useful but do not complete the common contract. |
| 23 Fleet and Vehicle | Completed → Partial | The specification lists vehicle assignment independently from dispatch link (`docs/SPECIFICATION.md:1017`, `:1020`). Vehicle model, create/patch schemas and history have no independent vehicle-to-unit/station assignment workflow (`backend/app/operations_models.py:28`; `backend/app/operations_schemas.py:47`; `backend/app/routers/operations.py:182`). Dispatch unit/vehicle pairing is incident-specific, not registry assignment. No extra effective-date requirements are inferred. |
| 52 Release Artifacts | Missing → Partial | Reproducible committed-source packaging/verification and installation/readiness documents now exist (`scripts/build_release_bundle.py:214`, `:276`; `docs/release/INSTALLATION.md:1`; `docs/release/RELEASE_READINESS.md:1`). Complete required manuals/reports and final accepted-release evidence remain open (`docs/SPECIFICATION.md:1916`); the package correctly declares production readiness false. |
| 54 Required Cross-module E2E | Missing → Partial | Substantive linked dispatch/allowance/statistics, contract/payment/balance, asset/history and inquiry/output tests exist (`backend/tests/test_run_b_operations.py:56`; `backend/tests/test_run_b_finance.py:110`; `backend/tests/test_finance_browser.py:8`; `backend/tests/test_assets_browser.py:15`; `backend/tests/test_run_b_inquiries.py:133`). All ten canonical chains are not complete; the precise seams remain listed below. |

The validated recount preserves Completed chapter 2's approved canonical tenancy boundary without crediting unresolved worker/OwnerDR history, and External Gate chapter 49's functioning measurement framework without concealing missing domain adapters under chapters 19/29–32/37.

## Evidence and limits

- Read `AGENTS.md`, the complete canonical specification, the current state/matrix records, current models, routers, services, frontend, tests, CI configuration, deployment assets, and release material.
- `git rev-parse HEAD` and its tree match the requested snapshot. The source checkout was clean before and after the original read-only inspection. Publishing this documentation does not rerun that inspection or alter its source checkpoint.
- Source pointers below use `repository-relative-path:line`, fixed to the commit above. Test pointers show actual assertions/workflows in source; they are not claims that this audit reran each test.
- Recorded execution evidence for this baseline is **679 passed / 90 skipped** locally and **729 passed / 40 skipped**, plus **30 browser tests passed**, in the referenced exact-main CI: https://github.com/haji84/-AI/actions/runs/37557284958. The read-only audit did not rerun that suite. Skipped tests do not establish acceptance.
- This audit ran only the two isolated runtime probes described below. It did not run the complete suite, inspect production data, browse legal thresholds, access the user's PC, or run a local browser.
- `PROJECT_STATE.md:5` and `docs/completion/MASTER_FEATURE_MATRIX.md:1` are useful history, but their main checkpoint predates this snapshot. Historical test totals and the old 14/37/5/1 summary are not current audit results.
- A feature is not called absent merely because a correspondingly named test file is absent. Related generic code, API integration tests, and shared frontend paths were considered.

### Ledger terms

The only primary chapter statuses are **Completed / Partial / Missing / External Gate**, using the established chapter scope in `docs/completion/MASTER_FEATURE_MATRIX.md:10`.

- **Completed**: the bounded chapter's internal foundation and required core workflow exist in canonical main with relevant acceptance evidence. Actual-site and whole-system acceptance are recorded separately and do not erase implementation credit.
- **Partial**: a concrete chapter-specific internally implementable requirement remains. Existing substantive implementations receive explanatory sublabels and must not be rebuilt merely because the chapter is Partial.
- **Missing**: no adequate central workflow is integrated into this exact main snapshot. Known unmerged or inaccessible work can still exist and remains protected.
- **External Gate**: the chapter's internal framework exists and its decisive remaining acceptance needs real reference data, infrastructure or accountable Human input. Here chapter 49 requires real AI baselines and Human thresholds. Runnable domain model adapters remain explicit internal dependencies under their respective chapters.

“Implemented core/foundation,” “active,” “recovery hold,” and “governance/integration gate” are explanatory sublabels only. A **recovery hold** describes known checkpoint work outside the accessible canonical snapshot that could not then be verified. It does not establish loss or recovery. Preserve the originals and assess collisions before later bounded requirements; it is not a permanent development ban. All chapters retain explicit internal/external/exit-evidence statements below. Generic future conformity, a missing combined test or the whole-system Definition of Done is not a substitute for a concrete chapter-specific gap.

## Checkpoint scope and later changes

At this baseline, PR67 intake lifecycle, PR68 personal work list, PR69 learning-login, the hazardous register, and facility-dashboard repairs were not integrated into c1b684c and receive no implementation credit here. Their later merge/evidence decisions are recorded in [the current ledger](CURRENT_COMPLETION_LEDGER.md) and [status changelog](COMPLETION_STATUS_CHANGELOG.md).

Known Run A statistics and Run B workforce/protected-document/dispatch/template checkpoint work was not available for verification against this snapshot. This records an evidence boundary, not loss or recovery of that code. Preserve original checkpoints; compare available main, branches, PRs, and migration inventory before any overlapping bounded requirement. Recovery may be pursued, but its absence is not a permanent prohibition on a separately scoped, collision-assessed requirement. Current main is the implementation authority. Migration 051 was associated with that checkpoint work; no migration is allocated by this documentation. Existing migration history remains immutable.

Historical central-server, dynamic-worker/offline-requeue, and OwnerDR context needs a separately reviewed architecture reconciliation. No execution-topology change is credited or authorized by this audit.

## All 57 chapters

<a id="chapter-1"></a>

### 1. Product Vision — Partial; system integration gate

**Present:** one FastAPI application includes the business routers and common static shell (`backend/app/main.py:23`, `:43`, `:82`); common identity/evidence IDs connect operational modules. Finance and inquiry browser scenarios exercise cross-module records (`backend/tests/test_finance_browser.py:8`, `backend/tests/test_inquiries_browser.py:8`). Specification: `docs/SPECIFICATION.md:13`.

**Internal gate:** integrate the active modules and recovered work, enforce per-department module enablement, finish shared task/review/navigation coverage, and satisfy chapters 52–54. **External gate:** departmental operational acceptance. **Exit evidence:** ten mapped workflows, one authorization/audit/navigation contract, and a release record whose exact commit matches the executed evidence.

<a id="chapter-2"></a>

### 2. Canonical Architecture — Completed; implemented canonical boundary; separate architecture delta

**Present:** fixed department UUID, database/storage binding and fail-closed middleware (`backend/app/tenant.py:49`, `:67`, `:89`, `:138`); per-department deployment generator (`backend/app/tenant_deployment.py:7`); two-department, wrong-cookie, identity and PostgreSQL initialization tests (`backend/tests/test_tenant_boundary.py:101`, `:159`, `:209`). Approved architecture is separate DB/runtime/storage per department, with all its stations sharing that DB (`docs/architecture/TENANT_ISOLATION_DECISION.md:15`). Specification: `docs/SPECIFICATION.md:32`.

**Internal gate:** none established for the approved canonical isolation boundary. Historical central-server/dynamic-worker/OwnerDR expectations require a separate architecture reconciliation before choosing new execution topology; that unresolved context neither downgrades this implemented boundary nor authorizes replacing it. **External gate:** real OS ACL, DB role, network and physical-client acceptance. **Exit evidence:** approved architecture delta plus retained tenant-negative tests and host evidence.

<a id="chapter-3"></a>

### 3. Deployment Profiles — Partial

**Present:** Linux tenant generator, nginx/systemd configuration, Windows startup guidance, local installation guidance and signed legal bundles (`backend/app/tenant_deployment.py:7`, `deploy/windows/README.md:1`, `docs/release/INSTALLATION.md:45`, `backend/app/legal_update_bundle.py:1`). Specification: `docs/SPECIFICATION.md:110`.

**Internal gate:** explicit configuration/dependency/update/egress contracts and runnable acceptance for all five profiles. The source bundle excludes dependency wheels and models (`docs/release/RELEASE_READINESS.md:39`), so it does not by itself support a fully offline install. **External gate:** approved Cloud/LAN/LGWAN hosting and organization policy. **Exit evidence:** profile-specific install, disconnected-core, update and restore results from the same release.

<a id="chapter-4"></a>

### 4. Update, Release and Rollback — Partial

**Present:** module/flag/change-request/deployment records, reviewed approval and recorded rollback (`backend/app/models.py:305`, `:350`, `:458`; `backend/app/routers/extensions.py:64`, `:134`, `:151`); deterministic committed-source packaging and verification (`scripts/build_release_bundle.py:214`, `:276`; `backend/tests/test_release_bundle.py:105`, `:316`). Specification: `docs/SPECIFICATION.md:165`.

**Internal gate:** real application activation, compatibility checks, approved rollout and paired code/schema/storage rollback. The existing deployment endpoint records metadata; it does not install a release. Archive hashes establish integrity, not publisher authentication. **External gate:** publisher trust and department change approval. **Exit evidence:** upgrade an existing synthetic department, fail safely mid-upgrade, and restore its prior compatible release/database/originals as a unit.

<a id="chapter-5"></a>

### 5. Common Data Principles — Partial; implemented foundation; conformity work remains

**Present:** shared UUID identities, immutable originals, optimistic versions, audited before/after updates, logical facility lifecycle, and immutable financial/correction histories (`backend/app/models.py:124`, `:155`; `backend/app/finance_service.py:181`; `backend/app/violation_corrections.py:1`). Tests include stale writes and logical restore (`backend/tests/test_phase1_core.py:57`, `:96`) and reversal conservation (`backend/tests/test_run_b_finance.py:65`). Specification: `docs/SPECIFICATION.md:248`.

**Internal gate:** carry the complete reason/source/approval/correction contract into older mutable workflows and every new adapter. For example, inspection findings currently support audited versioned PATCH, but their API is not a complete evidence/approval correction lifecycle (`backend/app/routers/inspections.py:210`). **External gate:** official retention/correction policy approval where applicable. **Exit evidence:** per-module mutation inventory and verified non-destructive corrections, not a new competing data platform.

<a id="chapter-6"></a>

### 6. Employee, Organization and Account — Partial

**Present:** separate employee/login identities, organizations, primary/secondary effective assignments, transfers, accounts, password history/expiry and session revocation (`backend/app/personnel.py:10`, `:20`, `:40`; `backend/app/routers/administration.py:215`, `:270`, `:355`, `:447`). Tests cover history, overlap, loss of last admin, password reuse and dated grants (`backend/tests/test_personnel.py:50`, `:119`, `:139`; `backend/tests/test_password_expiry.py:1`). Specification: `docs/SPECIFICATION.md:298`.

**Internal gate:** personnel-document intake with source preview, known employee/code resolution, proposed before/after assignments, scheduled effective dates and explicit Human application. Existing manual administration is not that pipeline. **External gate:** actual personnel policies and source notices. **Exit evidence:** synthetic transfer notice → review → future-effective assignment, with unknown codes rejected and no AI-created permissions. Coordinate with Run B before changing qualification/duty integration.

<a id="chapter-7"></a>

### 7. Authorization — Partial; verified dashboard leakage

**Present:** backend permission dependencies; effective Human roles; source-bound custom/timed/acting grants; serialized mutation revalidation (`backend/app/authz.py:49`, `:59`, `:67`; `backend/app/personnel.py:58`; `backend/app/authorization_models.py:8`). Tests cover source authority, sensitive acknowledgement, expiry and account/role races (`backend/tests/test_human_authorization.py:15`, `:71`, `:187`). Specification: `docs/SPECIFICATION.md:353`.

**Internal gate:** fix facility-dashboard cross-module leakage (`backend/app/routers/submissions.py:584`); audit aggregate/search/detail boundaries consistently. Qualification/duty-derived rule selectors also remain beyond organization/title/kind selectors, coordinated with protected Run B work. **External gate:** role matrix acceptance. **Exit evidence:** a minimal facility reader cannot infer any restricted inspection/submission record, count, date or state; approved multi-permission users retain their views.

<a id="chapter-8"></a>

### 8. Audit — Completed; implemented append-only audit foundation

**Present:** common audit writer, account/admin audit API with keyset pagination and filters, and application-role restrictions (`backend/app/audit.py:1`; `backend/app/routers/administration.py:285`; `backend/app/tenant_deployment.py:7`). Actual PostgreSQL tests attempt forbidden audit DELETE (`backend/tests/test_tenant_deployment.py:83`); paging regression is in `backend/tests/test_personnel.py:360`. Specification: `docs/SPECIFICATION.md:382`.

**Internal gate:** no missing current audit foundation was established. Retain audit assertions as new operations are introduced and complete the cross-module coverage inventory under chapter 48; actual release execution remains chapter 4 work. **External gate:** approved operator access and retention/log procedures. **Exit evidence:** production application role cannot rewrite history, and all completion workflows retain the expected actor, source/version, transition and outcome without credentials.

<a id="chapter-9"></a>

### 9. Document Platform — Partial; with a strong common-original foundation

**Present:** common Document UUID, original filename, SHA, size, media type, creator and server-managed storage (`backend/app/models.py:155`; `backend/app/storage.py:15`; `backend/app/routers/documents.py:15`, `:51`). Module-specific manifests and rendered outputs preserve source relationships; inquiry-derived originals enforce transitive source rights (`backend/app/inquiries_service.py:109`; `backend/tests/test_run_b_inquiries.py:382`). Specification: `docs/SPECIFICATION.md:409`.

**Internal gate:** finish the common logical display-name/source-module/derived-document provenance contract. Those are not complete first-class fields in the Document model; current relationships are distributed across adapters. Preserve the working original store rather than replace it. **External gate:** real format/size/retention acceptance. **Exit evidence:** original and derivative retain distinct identities and navigable lineage with correct source permissions across consumers. Reconcile protected-document adapters with Run B first.

<a id="chapter-10"></a>

### 10. Document Intake and OCR — Partial; PR #67 active

**Present:** direct PDF/Office/text extraction and image/PDF OCR, bounded sizes, deterministic classification, Human review, receipt creation, and explicit facility-change proposals (`backend/app/document_intake.py:20`, `:54`, `:126`, `:154`; `backend/app/routers/intake.py:139`, `:196`, `:239`). The core test covers analysis → review → receipt; another covers explicit field paths and stale facility versions (`backend/tests/test_phase1_core.py:543`, `:602`). Specification: `docs/SPECIFICATION.md:456`.

**Internal gate:** first integrate/re-audit PR #67 lifecycle hardening. Remaining scope includes ordered multi-image/page assembly, derived correction/quality operations and warnings, configurable bounded limits, and destination adapters. HEIC should be decoder-capability-gated; the current image path can fail if its decoder is absent. **External gate:** real OCR reference material and approved accuracy. **Exit evidence:** no original mutation, deterministic page/source identity, explicit review/apply, stale/repeated/cancelled operation coverage.

<a id="chapter-11"></a>

### 11. Facility Registry — Completed; canonical registry core

**Present:** shared facility identity, details/contacts/floors, legacy raw preservation, CRUD/search, lifecycle and conflict handling (`backend/app/models.py:124`, `:142`, `:473`, `:493`, `:503`; `backend/app/routers/facilities.py:1`). Relevant tests cover nested update/history, duplicate floors, partial patch and legacy evidence (`backend/tests/test_phase1_core.py:197`, `:266`, `:283`, `:495`). Specification: `docs/SPECIFICATION.md:498`.

**Internal gate:** no missing canonical registry core was established. Keep newly integrated surfaces linked to its existing building ID; the reproduced dashboard disclosure remains a separate chapter 7/43 repair. **External gate:** real mapped legacy fields and user acceptance. **Exit evidence:** the completed operational flows navigate back to one facility identity, with original values preserved for unknown mappings.

<a id="chapter-12"></a>

### 12. Inspection — Partial

**Present:** per-inspection/per-finding records, due/completion dates, correction state, audit and CAS (`backend/app/models.py:521`, `:535`; `backend/app/routers/inspections.py:109`, `:183`, `:210`). Violations already accept a finding reference and verify its facility/version (`backend/app/violation_service.py:88`). Tests cover finding workflow and conflict (`backend/tests/test_phase1_core.py:299`, `:391`). Specification: `docs/SPECIFICATION.md:535`.

**Internal gate:** usable inspection photo/document evidence, structured inspector references/follow-up, and a complete workflow from unresolved finding to existing violation/correction records and back. Do not build a second violation lifecycle. **External gate:** local inspection practice/official documents. **Exit evidence:** repeat inspection displays prior unresolved findings, follows the correct evidence and due task, and records closure without automatically declaring a formal violation.

<a id="chapter-13"></a>

### 13. Violations and Corrective Actions — Partial

**Present:** candidate versus formal state, primary legal citations/originals, separate Human review/confirmation, measures, response/verification/completion and immutable correction history (`backend/app/violation_service.py:69`, `:111`, `:124`; `backend/app/violation_corrections.py:1`; migration 049). Tests cover separate formal gates and non-formal guidance (`backend/tests/test_violation_corrections.py:18`, `:25`, `:39`). Specification: `docs/SPECIFICATION.md:557`.

**Internal gate:** common AI candidate producer and explicit inspection/hazardous handoffs, preserving source hashes and stale-evidence rejection. Accepting an `origin=ai` payload is not a configured generation worker. **External gate:** approved legal rules and formal procedures. **Exit evidence:** a bounded producer emits candidates only, with Human review and official confirmation remaining independent; inspection follow-up navigates the same correction records.

<a id="chapter-14"></a>

### 14. Submission and Application — Partial; intake dependency active

**Present:** extensible type master, original links, digits-only supplied official numbers, receipt and specialized equipment/fire-manager/fire-plan projections in one transaction (`backend/app/models.py:551`, `:564`, `:584`; `backend/app/routers/submissions.py:85`, `:108`, `:291`). Tests cover original linkage, types, required document, number and optimistic-lock rules (`backend/tests/test_phase1_core.py:326`, `:363`, `:440`). Specification: `docs/SPECIFICATION.md:575`.

**Internal gate:** after PR #67, implement/enforce type-specific required fields, attachment roles, workflow states, target fields/permissions, Rule and official-template mappings. A free-form `SubmissionType.rules` object is not proof that all those constraints execute. **External gate:** authoritative filing families, numbering source and originals. **Exit evidence:** two materially different configured submission types enforce different workflows without hand-coded guessed official numbers.

<a id="chapter-15"></a>

### 15. Submission Requirement Tracking — Partial

**Present:** evaluations use explicitly approved presence Rules, distinguish missing candidates and legacy/unverified evidence, and retain the evaluation snapshot (`backend/app/routers/submissions.py:370`; `backend/app/models.py:736`). Existing legacy inspection reporting profile has cycle and next-due fields (`backend/app/models.py:639`). Regression: `backend/tests/test_phase1_core.py:1754`. Specification: `docs/SPECIFICATION.md:614`.

**Internal gate:** a durable per-facility/per-requirement lifecycle linking last accepted submission, current review state, next due, source Rule/version and recalculation/cancellation history. Current compliance evaluation and the generic dashboard are not that complete lifecycle. **External gate:** approved Rule coverage and local deadlines. **Exit evidence:** receipt/revision/withdrawal and Rule change update an evidence-bound obligation without promoting “missing” to a formal violation. Depends on finalized intake/submission lifecycle and worklist contract.

<a id="chapter-16"></a>

### 16. Hazardous Materials — Missing; main gap; migration 052 active and unmerged

**Present:** hazardous legal categories and generic facility/document/violation foundations; the audited `main.py:43` router registry and domain model set do not include an operational hazardous-material register. Specification: `docs/SPECIFICATION.md:633`.

**Internal gate:** integrate the active 052 register slice, then check its actual coverage for installation/category/quantity, permit/notification, changes, inspections, deadlines, legal evidence, documents and history. A register alone does not close the complete chapter. **External gate:** authorized category/quantity mappings, applicable approved Rules and actual permit originals. **Exit evidence:** source-linked record → Human change/inspection → due/review item → evidence/history, with no invented legal thresholds or automatic formal violation.

<a id="chapter-17"></a>

### 17. Legal and Rule Engine — Partial

**Present:** official-source/version/provision corpus, effective Rules with explicit conditions/outcomes, exact citations, draft/review authoring, impact candidates and signed offline input (`backend/app/routers/legal_rules.py:438`, `:624`; `backend/app/routers/legal_sources.py:261`; `backend/app/legal_update_bundle.py:1`). Tests include citation-required approval and hostile bundle rejection (`backend/tests/test_phase1_core.py:955`; `backend/tests/test_signed_legal_bundle.py:45`, `:92`). Specification: `docs/SPECIFICATION.md:655`.

**Internal gate:** remaining official-source adapters and complete amendment impact routes into affected submissions/equipment/templates/facilities and recalculation queues. Do not equate imported corpus counts with approved legal Rules. **External gate:** legal authoring/approval and production trust key/source selection. **Exit evidence:** changed cited provision produces bounded review work and never silently changes an Approved Rule or formal business record.

<a id="chapter-18"></a>

### 18. Equipment Requirement and Installed Equipment — Partial; implemented core; corpus/acceptance gate

**Present:** separate required-versus-installed data; installed verification state; Rule/provision-backed comparisons; authoring/regression and placement support (`backend/app/models.py:1021`, `:1033`; `backend/app/routers/equipment.py:160`, `:273`). Tests distinguish missing/unverified/verified and reject stale updates (`backend/tests/test_phase1_core.py:1862`, `:1948`, `:6002`). Specification: `docs/SPECIFICATION.md:749`.

**Internal gate:** complete workflow wiring to new due/worklist surfaces and retain source/state coverage. No new equipment master is required. **External gate:** production Rule/placement corpus and verification by responsible staff. **Exit evidence:** accepted AI/legacy evidence cannot become “verified installed” without its separate authorized verification, and every requirement retains the effective legal evidence.

<a id="chapter-19"></a>

### 19. Drawing AI — Partial

**Present:** drawing analysis manifests, element/equipment/fact candidates, Human annotation/revisions, geometry/scale/area, QA, and source-bound benchmark registry (`backend/app/models.py:1056`; `backend/app/routers/drawing_annotations.py:528`, `:619`, `:671`; `backend/app/drawing_benchmark_core.py:1`). Tests cover candidate separation, manifest replay, authoritative areas and baseline gating (`backend/tests/test_phase1_core.py:2043`, `:2345`, `:6957`, `:7479`). Specification: `docs/SPECIFICATION.md:770`.

**Internal gate:** runnable, bounded, server-configured Local Vision adapter and full upload → inference → review integration. Manifest ingestion and benchmark scoring do not perform model inference. **External gate:** actual drawings, Human references, real model baseline and thresholds. **Exit evidence:** malformed/timeout/late model responses fail safely and preserve CRUD; measured real-source output passes separately approved quality criteria.

<a id="chapter-20"></a>

### 20. Occupancy Classification and Drawing Consultation — Partial

**Present:** classification/consultation and equipment/placement evaluation, authoring workbench/regressions, answer package provenance and stale-review invalidation (`backend/app/routers/drawing_consultations.py:1`; `backend/app/consultation_response.py:1`; `backend/app/occupancy_regression.py:1`). Tests require classification before equipment and reject ambiguous or stale responses (`backend/tests/test_phase1_core.py:4352`, `:5533`, `:6584`). Specification: `docs/SPECIFICATION.md:854`.

**Internal gate:** finish the full connected acceptance chain, including navigable installed equipment after Human action; align generation with chapter 19's eventual adapter. **External gate:** approved occupancy/equipment/placement corpus and real consultation acceptance. **Exit evidence:** a reviewed reference plus explicit Human answers yields a traceable response package; missing equipment symbols do not suppress Rule-driven requirements, and unknown classification remains unresolved.

<a id="chapter-21"></a>

### 21. Emergency Module — Partial

**Present:** shared case/patient/crew/treatment models, raw workbook lineage, candidate/review separation, immutable report snapshots, multiple aggregates and safe exports (`backend/app/routers/emergency.py:70`, `:136`, `:160`, `:197`; `backend/app/emergency_reports.py:8`). Tests cover CPA candidates, privacy, stale treatments, real workbook import and separate case/patient counts (`backend/tests/test_run_b_emergency.py:37`, `:114`, `:132`, `:147`; `backend/tests/test_emergency_reports.py:66`). Specification: `docs/SPECIFICATION.md:882`.

**Internal gate:** authoritative code masters/mappings, full dated event chronology rather than only ambiguous-midnight warnings (`backend/app/emergency_service.py:44`), richer corrections/history and registered official report output. Coordinate template/protected-document work with the Run B recovery boundary. **External gate:** original 117/160/24-column workbook header review, approved medical/reporting definitions and official forms. **Exit evidence:** full treatment/transport/clinical review/monthly report flow, with sensitive details unavailable to aggregate-only users.

<a id="chapter-22"></a>

### 22. Incident and Dispatch — Completed; reviewed source-linked dispatch

**Present:** shared source-case references, crews/vehicles/timestamps, Human-approved allowance rates, reviewed dispatch, source snapshots and local statistics (`backend/app/operations_models.py:14`, `:43`, `:58`; `backend/app/operations_service.py:132`, `:160`, `:177`, `:256`). One substantive API test already runs dispatch → crew → rate approval → calculation → review/approval → official statistics (`backend/tests/test_run_b_operations.py:56`). Specification: `docs/SPECIFICATION.md:984`.

**Internal gate:** no missing source-linked dispatch core was established. Recovered workforce work results, common statistics, full combined browser acceptance and module-disable enforcement remain explicit work under chapters 25/34/54/46. **External gate:** Human rate/station/dispatch policy. **Exit evidence:** source facts remain references, a dispatch produces no automatic official allowance, and the final authorized aggregate matches the reviewed dispatch.

<a id="chapter-23"></a>

### 23. Fleet and Vehicle — Partial; independent vehicle assignment missing; other fleet core implemented

**Present:** vehicles, dispatch-linked trips, driver, mileage, fuel receipt/issue/stock, service/fault resolution, costs and deadlines (`backend/app/operations_models.py:28`, `:99`, `:112`, `:123`; `backend/app/operations_service.py:200`, `:216`, `:235`). Tests exercise odometer/fuel constraints and approved fault resolution; purchase cost excludes issue valuation (`backend/tests/test_run_b_operations.py:84`, `:243`, `:335`). Specification: `docs/SPECIFICATION.md:1010`.

**Internal gate:** implement an independent vehicle-to-station/unit assignment state and workflow, distinct from an incident-specific dispatch pairing. The requirement is explicit at `docs/SPECIFICATION.md:1017`, separate from dispatch link at `:1020`; the current Vehicle model (`backend/app/operations_models.py:28`), create/patch schemas (`backend/app/operations_schemas.py:47`) and history (`backend/app/routers/operations.py:182`) do not provide it. Do not invent additional effective-date requirements. Preserve existing mileage/fuel/service/history behavior. Common task/statistics and combined-chain acceptance remain separately tracked. **External gate:** real vehicle schedules and operational acceptance. **Exit evidence:** an authorized user can assign/reassign a registered vehicle to a station/unit without creating a dispatch, with versioned/audited changes and a readable current assignment/history. Existing mileage/fuel nonnegative and Human service/source-version tests continue passing; a deadline card opens the correct canonical vehicle/service.

<a id="chapter-24"></a>

### 24. Operational Assets and Inventory — Completed; stock and service core

**Present:** asset versus lot versus location/balance separation; immutable movements; receive/issue/transfer/loan/return; Human service, expiry and reorder candidates; imports/exports and same-shell UI (`backend/app/assets_service.py:161`, `:209`, `:272`, `:368`; `backend/app/assets_models.py:1`). Tests cover conservation, loan outstanding, expired issue, PostgreSQL races and the actual browser (`backend/tests/test_run_b_assets.py:54`, `:65`, `:92`, `:229`; `backend/tests/test_assets_browser.py:15`). Specification: `docs/SPECIFICATION.md:1041`.

**Internal gate:** no missing stock/service core was established. Common task/statistics projections and final combined acceptance remain work under chapters 34/36/54, preserving existing stock facts. **External gate:** actual inventory mappings, stock/service procedures and responsible-user acceptance. **Exit evidence:** complete asset chain with preserved IDs, no negative stock or excess return, and source-bound service/expiry history.

<a id="chapter-25"></a>

### 25. Workforce and Duty Management — Partial; protected recovery hold

**Present in main:** roster, effective assignments, shifts with explicit Human work intervals, qualification/staffing rules, leave, attendance, time entries/balances, warnings/available crew, import/export, stats and same-shell UI (`backend/app/workforce_models.py:13`, `:63`, `:87`, `:107`, `:125`; `backend/app/routers/workforce.py:84`, `:122`, `:172`). Tests cover overlap, 24-hour work rules, stale roster evidence, balance history and PostgreSQL contention (`backend/tests/test_run_b_workforce.py:95`, `:135`; `backend/tests/test_workforce_safety.py:33`, `:112`; `backend/tests/test_workforce_concurrency.py:1`). Specification: `docs/SPECIFICATION.md:1090`.

**Internal gate:** preserve existing Run B checkpoints and assess available main/branch/PR/migration overlap before bounded changes to teams/work results, checkout/cancel/correction/balance/crew UX, expiry/reconciliation policy or dispatch/template adapters. Those requirements are not proven absent from the unverified checkpoint work. **External gate:** actual staffing, leave, qualifications and allowance policies. **Exit evidence:** a reviewed integrated diff with explicit provenance, followed by roster → dispatch → work result → overtime/allowance acceptance and a reconciled migration inventory. Recovery is not asserted or made a permanent prerequisite for every new requirement.

<a id="chapter-26"></a>

### 26. Contract and Procurement — Partial

**Present:** reused ContractCase/Counterparty/Document, exact monetary values, quotes/commitments, delivery/inspection/invoice/payment links, amendment/renewal, original upload and deterministic assistance (`backend/app/finance_service.py:243`, `:284`, `:334`, `:575`, `:615`; `frontend/finance.js:1`). Tests cover complete procurement stages, original evidence, exact amounts, guarded first-use upload and session changes (`backend/tests/test_run_b_finance.py:110`, `:638`, `:663`; `backend/tests/test_finance_browser.py:242`, `:450`). Specification: `docs/SPECIFICATION.md:1123`.

**Internal gate:** common audio/transcription and generation adapters plus evidence-bound document differences/assistance where not yet implemented. Do not repeat the old “post-response permission checks missing” claim: the current shared response guard covers that concern. **External gate:** official procurement policies/terms/forms. **Exit evidence:** assistance never concludes contracts, changes approved money or bypasses Human approval; output/source rights survive revocation and revision.

<a id="chapter-27"></a>

### 27. Budget and Finance — Partial; implemented substantial core; integration acceptance open

**Present:** Human fiscal/account hierarchy policies, exact Decimal journal, budget/transfer/commitment/payment/reversal, requests and balances, immutable posting, original-form rendering and aggregates (`backend/app/finance_service.py:47`, `:62`, `:181`, `:514`, `:521`). PostgreSQL races and end-to-end browser budget/payment/balance flow exist (`backend/tests/test_run_b_finance.py:323`; `backend/tests/test_finance_browser.py:8`). Specification: `docs/SPECIFICATION.md:1161`.

**Internal gate:** common statistics/worklist integration, full source/permission conformance and final fiscal scenario inventory, including next-year estimates through the current proposal/request design. Recheck any uncovered scenario before adding a new model. The former shared-session gap is implemented (`frontend/shared-session.js:32`). **External gate:** organization-approved fiscal rules and adoption. **Exit evidence:** no overspend/double payment or destructive posted-ledger edit; exact balances reconcile through compensation and approved source evidence.

<a id="chapter-28"></a>

### 28. Council, Assembly and Inquiry Support — Partial

**Present:** source-bound questions/drafts/revisions, exact numeric claims and units, search, Human review/approval, safe import/export, original-template rendering and navigation (`backend/app/inquiries_service.py:176`, `:267`, `:328`, `:493`; `backend/app/routers/search.py:875`; `frontend/inquiries.js:50`). Tests cover stale/forged source, decimal formulas, privacy closure and browser navigation (`backend/tests/test_run_b_inquiries.py:45`, `:124`, `:382`; `backend/tests/test_inquiries_browser.py:8`). Specification: `docs/SPECIFICATION.md:1214`.

**Internal gate:** runnable production local-model adapter and recovered statistics integration. Current `local_model_adapter=None` falls back to labelled deterministic excerpt extraction (`backend/app/inquiries_service.py:351`); it is useful but not a deployed local-model service. **External gate:** formal answer acceptance/originals. **Exit evidence:** real adapter contract plus timeout/late-source/revoked-session tests; every official numerical claim still resolves to authorized source/query/date/unit.

<a id="chapter-29"></a>

### 29. Fire Investigation — Partial

**Present:** common case/media, photo annotations, transcript/statement, timeline, cause candidates, separate official cause/report gates and immutable reviewed snapshots (`backend/app/models.py:1156`, `:1177`, `:1231`; `backend/app/routers/fire_investigations.py:443`, `:574`). Tests exercise evidence/cause/report separation and cross-case protection (`backend/tests/test_phase1_core.py:2424`, `:2673`, `:2905`). Specification: `docs/SPECIFICATION.md:1240`.

**Internal gate:** runnable bounded local-model workers and usable source review controls; complete video metadata/frame evidence path beyond storing original video media; actual HTTP/browser investigation chain. **External gate:** real cases/media, Human findings and model acceptance. **Exit evidence:** approved manifests bind original hashes, candidate prose cannot change reviewed evidence or official cause, and missing AI leaves the case workflow usable. Architecture reconciliation precedes dynamic worker/distributed queue choices.

<a id="chapter-30"></a>

### 30. Fire Photo Intelligence — Partial

**Present:** immutable original photos, EXIF/quality/perceptual hash/duplicate metadata, annotation search, and Human-reviewed drawing location links (`backend/app/fire_photo_metadata.py:1`; `backend/app/routers/fire_photos.py:221`, `:419`, `:487`). Tests cover deterministic duplicate evidence and same-facility plan-link Human review (`backend/tests/test_phase1_core.py:3146`, `:3268`). Specification: `docs/SPECIFICATION.md:1280`.

**Internal gate:** real classifier/tag/description worker feeding the existing candidate manifest path, plus UI evidence review. The current metadata analyzer is already implemented and should be retained. **External gate:** representative labelled images and quality thresholds. **Exit evidence:** preserved original SHA, source/time/model/confidence provenance and explicit review; false positives are measured, not inferred from a model call succeeding.

<a id="chapter-31"></a>

### 31. Voice, Statement and Evidence Comparison — Partial

**Present:** original-audio media, transcript/speaker/time/uncertainty records, reviewed statements, immutable evidence-comparison candidates and benchmark tooling (`backend/app/models.py:1279`, `:1302`, `:1483`; `backend/app/fire_transcript_semantics.py:1`; `backend/app/routers/fire_investigations.py:797`). Tests cover accepted-only transcript use and non-mutating comparison (`backend/tests/test_phase1_core.py:2752`, `:3384`). Specification: `docs/SPECIFICATION.md:1301`.

**Internal gate:** configured runnable STT/diarization and comparison adapters, uncertainty-preserving correction/source playback UI and bounded processing. **External gate:** real Japanese audio/reference baseline and Human thresholds. **Exit evidence:** speaker/time alignment and uncertain words survive review, a contradiction candidate cannot rewrite statement/timeline/cause, and worker failure does not block manual records.

<a id="chapter-32"></a>

### 32. Fire Report Drafting — Partial

**Present:** reports bind reviewed evidence snapshots/manifests, official cause remains separate, and approved report output uses registered original templates (`backend/app/models.py:1364`, `:1392`; `backend/app/routers/fire_report_exports.py:187`, `:344`). Tests reject stale/out-of-snapshot evidence and render a registered original without changing it (`backend/tests/test_phase1_core.py:2905`, `:2962`). Specification: `docs/SPECIFICATION.md:1323`.

**Internal gate:** runnable evidence-to-draft adapter covering the required report sections, source-linked review UX and complete browser flow. **External gate:** actual official report originals and fire-report acceptance. **Exit evidence:** each generated section cites allowed reviewed evidence; Human approval is required before official output, and report approval cannot implicitly approve cause.

<a id="chapter-33"></a>

### 33. Official Form Platform — Partial

**Present:** version/effective-date/issuer/field-map/print/change-policy template model; original-preserving PDF AcroForm, XLSX and DOCX renderer; fire, finance and inquiry consumers (`backend/app/models.py:330`; `backend/app/official_form_renderer.py:76`, `:99`, `:131`, `:170`; `backend/app/routers/templates.py:31`). Tests include original Excel preservation, split DOCX placeholder rejection, finance mapping and inquiry derived-original guards (`backend/tests/test_phase1_core.py:2962`, `:3097`; `backend/tests/test_run_b_finance.py:190`; `backend/tests/test_run_b_inquiries.py:133`). Specification: `docs/SPECIFICATION.md:1344`.

**Internal gate:** remaining module adapters and administrator mapping/preview/validation workflows, with registered-source/output lineage. Reconcile Run B's protected template work before touching those adapters. **External gate:** missing official originals and approved field mapping. **Exit evidence:** representative synthetic PDF/XLSX/DOCX outputs preserve original layout/hash and can be traced to a fixed source snapshot/template version; real originals are then separately accepted.

<a id="chapter-34"></a>

### 34. Cross-module Statistics, Annual Reports and Surveys — Missing; main integration gap; protected recovery hold

**Present in main:** domain statistics already exist for emergency, dispatch/allowances/fleet, workforce and finance (`backend/app/emergency_reports.py:8`; `backend/app/operations_service.py:256`; `backend/app/routers/operations.py:190`, `:194`; `backend/app/workforce_service.py:449`; `backend/app/finance_service.py:514`). Existing tests distinguish incidents/patients and approved values (`backend/tests/test_emergency_reports.py:66`; `backend/tests/test_run_b_operations.py:56`). Specification: `docs/SPECIFICATION.md:1374`.

**Internal gate:** preserve and assess Run A's known cross-module metrics/snapshot/review/comparison/export checkpoint alongside current main, then reconcile all domain sources, definition/unit/denominator/date/unknown coverage, drilldown and prior-year null-versus-zero. No conclusion about its inaccessible uncommitted files is possible from main alone. **External gate:** official survey definitions/templates and Human adoption. **Exit evidence:** frozen, permission-aware report reconciles to original records and preserves missing prior-year values as missing.

<a id="chapter-35"></a>

### 35. Unified Search — Partial; broad module coverage already present

**Present:** a single search router has 20 permission-keyed categories, including emergency cases, incidents/fleet/assets/workforce, violations, procurement/budget and inquiries (`backend/app/routers/search.py:50`, `:787`, `:829`, `:849`, `:875`, `:917`). Provenance/navigation and query-hash audit are present; patient text is deliberately excluded. Tests cover module privacy, reviewed-only evidence, emergency exclusion and inquiry transitive rights (`backend/tests/test_phase1_core.py:3565`, `:3640`; `backend/tests/test_run_b_emergency.py:114`; `backend/tests/test_run_b_inquiries.py:63`). Specification: `docs/SPECIFICATION.md:1422`.

**Internal gate:** stable pagination/filtering and coverage semantics; the current result count is the capped returned hit list, not a total corpus count (`:948`, `:963`, `:987`). Some sources scan rows before scoring. Add new hazardous/statistics entities only after their canonical contracts settle. **External gate:** production data-volume/latency and relevance acceptance. **Exit evidence:** authorized users can reach later matches deterministically, no private existence leaks, and navigation opens the exact record.

<a id="chapter-36"></a>

### 36. Dashboard and Personal Work Queue — Missing; main gap; PR #68 active and unmerged

**Present:** facility-local dashboard and module-specific alerts/review queues (`backend/app/routers/submissions.py:584`; `backend/app/routers/operations.py:204`; `backend/app/assets_service.py:272`; `backend/app/routers/workforce.py:168`). These are useful producers, not yet a main-integrated personalized queue. Specification: `docs/SPECIFICATION.md:1455`.

**Internal gate:** finish the active local worklist, including role/assignment scoping, useful dates/reasons, original-record pointers, session revocation, and each producer's source permission. Fix the existing facility dashboard independently. **External gate:** task priority/ownership conventions and usability acceptance. **Exit evidence:** restricted modules contribute neither cards nor counts; cards do not copy official facts and open the correct source record; active/reviewed/overdue states update from the canonical source.

<a id="chapter-37"></a>

### 37. Learning Platform — Partial

**Present:** eight correction targets, source-bound reviewed corrections, frozen holdouts, immutable literal-correction artifacts, server-computed comparison, Human Champion promotion/rollback and audit (`backend/app/learning_models.py:8`; `backend/app/learning_engine.py:16`, `:64`; `backend/app/routers/learning.py:230`, `:290`, `:306`). Tests reject overlap of training/holdout sources, synthetic production references and concurrent promotions (`backend/tests/test_learning.py:79`, `:115`, `:141`, `:170`). Specification: `docs/SPECIFICATION.md:1485`.

**Internal gate:** integrate correction capture and approved artifact use into actual OCR/STT/photo/drafting adapters, plus model-level evaluation/version contracts. Existing literal correction is real functionality, but it is not model training. **External gate:** real references, measured quality and Human promotion acceptance. **Exit evidence:** correction → fixed evaluation → comparison → approved promotion → rollback works without live self-modification or leakage from training into evaluation.

<a id="chapter-38"></a>

### 38. Autonomous Task and Self-extension Platform — Partial

**Present:** ChangeRequest/intake, analysis/proposed changes/acceptance/sandbox-result records, review, approval and deployment/rollback metadata (`backend/app/models.py:350`, `:371`, `:458`; `backend/app/routers/extensions.py:46`, `:64`, `:84`, `:134`). Tests cover review-before-approval and audited flag/rollback records (`backend/tests/test_phase1_core.py:126`, `:174`). Specification: `docs/SPECIFICATION.md:1519`.

**Internal gate:** executable bounded goal/plan/tools/verification/evidence runner, sandbox/test orchestration, protected write-back and approved release execution. Supplied `sandbox_result` JSON is not actual sandbox execution. **External gate:** Human policy for consequential tools and deployment. **Exit evidence:** allowed synthetic task produces independently verified evidence, forbidden official actions are denied, and no model-selected command/path can obtain unrestricted access. Resolve the historical worker/OwnerDR architecture before implementing scheduling or recovery topology.

<a id="chapter-39"></a>

### 39. AI Decision Levels — Partial

**Present:** many strong domain Human gates already implement candidate/formal separation: legal approval, installed-equipment verification, cause/report approval, financial posting, learning promotion (`backend/app/routers/legal_rules.py:438`; `backend/app/routers/equipment.py:160`; `backend/app/finance_service.py:181`; `backend/app/routers/learning.py:290`). Specification: `docs/SPECIFICATION.md:1564`.

**Internal gate:** central machine-readable decision-level/capability policy with domain registration, enforcement and a coverage audit across actual write paths. Do not replace existing gates with a generic weak “AI approved” flag. **External gate:** organization decisions for configurable module levels. **Exit evidence:** a worker at any level cannot approve legal/financial/personnel/cause/violation/security decisions, and low-confidence cases route to the correct Human state.

<a id="chapter-40"></a>

### 40. AI Failure Mode — Completed; current core independent of AI

**Present:** core routers/database startup have no model dependency; health reports `ai_required=false` (`backend/app/main.py:31`); intake has deterministic/manual paths; inquiries fall back to labelled evidence extraction and explicitly report adapter outages (`backend/app/inquiries_service.py:351`). Tests cover AI-independent health and candidate adapter failure (`backend/tests/test_phase1_core.py:54`; `backend/tests/test_run_b_inquiries.py:100`). Specification: `docs/SPECIFICATION.md:1585`.

**Internal gate:** no current core model dependency was established. Future worker integrations must add outage regressions, and chapter 54 retains the combined acceptance obligation; these do not negate the current AI-independent core. **External gate:** real outage/operations drill. **Exit evidence:** login, normal CRUD/intake/search/manual review/template fill remain usable; queue backlog or model timeout cannot hold business transactions open indefinitely.

<a id="chapter-41"></a>

### 41. Import Framework — Partial

**Present:** source-file/run tracking, retained raw values, facility/emergency importers, and operational preview/confirm/hash/idempotency/export safety patterns (`backend/app/importers/common.py:15`, `:61`; `backend/app/importers/emergency.py:143`; `backend/app/assets_service.py:368`; `backend/app/finance_service.py:448`). Tests exercise atomic invalid-batch rollback and real CSV/XLSX round trips (`backend/tests/test_run_b_assets.py:125`; `backend/tests/test_run_b_finance.py:163`). Specification: `docs/SPECIFICATION.md:1608`.

**Internal gate:** consistent typed schema/version registry and common preview/Human confirm/atomic apply/stale-target contracts across adapters; existing ImportAdapterDefinition (`backend/app/models.py:445`) is a foundation, not execution coverage. Emergency's workbook route currently applies through its importer rather than a full shared preview endpoint (`backend/app/routers/emergency.py:238`). **External gate:** verified source header/code mapping. **Exit evidence:** repeat imports cannot silently overwrite official corrections, all rows roll back on failure, formulas are neutralized, and source hash/version is retained.

<a id="chapter-42"></a>

### 42. Backup and Restore — Completed; mechanisms and runbook implemented; actual-host drill open

**Present:** per-department binding/manifest checks, paired database/storage validation, service-aware scheduling and shared/exclusive maintenance (`backend/app/backup_contract.py:38`, `:87`; `backend/app/scheduled_backup.py:8`; `backend/app/department_maintenance.py:14`, `:24`). Tests cover wrong-department no-change rejection, PostgreSQL recovery, stop failure, SIGTERM and maintenance 503 (`backend/tests/test_tenant_backup_restore.py:71`, `:121`; `backend/tests/test_scheduled_backup.py:34`, `:59`; `backend/tests/test_department_maintenance.py:93`). Specification: `docs/SPECIFICATION.md:1631`.

**Internal gate:** no additional chapter-specific backup/restore mechanism was established as missing in this exact snapshot. Monitoring hookup and power-loss recovery are already documented (`docs/completion/AUTOMATIC_BACKUP.md:11`, `:31`); the final consolidated release index must reuse them. Repeat backup/restore regression when later migrations are integrated; application upgrade orchestration remains separately Partial in chapter 4. **External gate:** real production restore drill, actual systemd/OS ACL/monitoring delivery, and retention/storage operations. **Exit evidence:** restored DB and originals share the correct UUID/release/migration/source hashes, and only previously active services of that department restart.

<a id="chapter-43"></a>

### 43. Security — Partial

**Present:** tenant startup/Host/origin boundaries, secure production settings, Argon2/session hashing, role separation, storage containment, unsafe archive rejection and shared-session guards (`backend/app/settings.py:1`; `backend/app/security.py:9`; `backend/app/tenant.py:138`; `frontend/shared-session.js:15`, `:32`). Tests exercise wrong-host/cookie, bundle redirects, role mutation/session revocation and browser privacy (`backend/tests/test_tenant_boundary.py:101`; `backend/tests/test_signed_legal_bundle.py:240`; `backend/tests/test_shared_session_browser.py:9`). Specification: `docs/SPECIFICATION.md:1674`.

**Internal gate:** resolve reproduced dashboard disclosure and audit cross-module source guards; finish dependency/deployment hardening and a documented security review of final source. **External gate:** TLS, OS permissions, network separation, secrets provisioning and deployment review. **Exit evidence:** minimal-rights/API tests plus real isolated host negative tests, with no claim that CI alone establishes production security.

<a id="chapter-44"></a>

### 44. External Integration and Network Policy — Partial

**Present:** official collectors restrict origin/redirects; signed closed-network intake; department-controlled legal profiles and source update modes (`scripts/official_download.py:1`; `backend/app/legal_update_bundle.py:1`; `backend/app/routers/legal_sources.py:154`, `:228`). Tests reject off-origin access before reading bodies (`backend/tests/test_signed_legal_bundle.py:240`, `:251`). Specification: `docs/SPECIFICATION.md:1701`.

**Internal gate:** common per-department egress/integration allowlist with explicit data categories and disabled behavior for optional AI/SMTP/file exchange/LGWAN adapters. A legal source switch is not a general network policy. **External gate:** actual government-network gateway and approved data-sharing policy. **Exit evidence:** denied connections cannot send content, permitted adapters send only the configured categories, and the disconnected core still works.

<a id="chapter-45"></a>

### 45. User Experience — Partial

**Present:** common main shell, shared login/permissions/search, operational surfaces and response/session invalidation (`frontend/index.html:1`; `frontend/shared-session.js:53`; `frontend/auth-session.js:1`). Native browser tests exist for administration, assets, workforce, finance, learning, violations, inquiries and session changes (`.github/workflows/project-checks.yml:64`). Specification: `docs/SPECIFICATION.md:1720`.

**Internal gate:** integrate active worklist/hazardous surfaces; bring intake/fire/drawing/template/extension workflows under comparable actual-browser acceptance; complete consistent empty/error/409/retry/navigation states and Human-understandable labels. **External gate:** staff usability acceptance on supported PC browsers. **Exit evidence:** interruption, cancellation, double click, Back/Forward and account/permission change cannot expose old private state or silently apply stale work.

<a id="chapter-46"></a>

### 46. Module Configuration per Department — Partial; reproduced enablement gap

**Present:** department-specific database/config, seeded module manifests/flags, editable flag config and domain policies (`backend/app/module_seed.py:23`; `backend/app/routers/extensions.py:109`; `backend/app/finance_service.py:47`; `backend/app/routers/workforce.py:23`). Learning actually checks its enabled flag (`backend/app/routers/learning.py:87`; `backend/tests/test_learning.py:131`). Specification: `docs/SPECIFICATION.md:1743`.

**Internal gate:** enforce enabled state and dependencies consistently across backend routes, search, task producers and navigation; provide approved configuration history/UI. The disabled-operations probe below returns records. Protect security/tenant/audit core from disablement. **External gate:** departmental module/policy selection. **Exit evidence:** disabling an optional module closes its entry points and projections without deleting records or weakening safety; re-enabling restores access under normal RBAC.

<a id="chapter-47"></a>

### 47. Formal Evidence Model — Completed; layered evidence and Human transitions

**Present:** original SHA, parsed/provision versions, candidates, Human review, separate official decisions, immutable fire evidence snapshots and learning/finance/inquiry lineage (`backend/app/models.py:1231`; `backend/app/inquiries_service.py:256`; `backend/app/violation_service.py:69`). Tests reject stale or forged references and changed proof (`backend/tests/test_phase1_core.py:2905`; `backend/tests/test_run_b_inquiries.py:53`; `backend/tests/test_violation_corrections.py:46`). Specification: `docs/SPECIFICATION.md:1771`.

**Internal gate:** no missing current layered-evidence/Human-transition foundation was established. Conformance and source-permission checks remain mandatory when new adapters are integrated. The concrete generic Document metadata/lineage gap stays separately Partial in chapter 9. **External gate:** real evidence acceptance/retention. **Exit evidence:** every consequential output resolves source identity/hash, version, model/Rule where applicable, review and approval; a candidate can never skip directly to official status.

<a id="chapter-48"></a>

### 48. Testing — Partial; meaningful existing coverage

**Present:** broad backend tests, a real PostgreSQL service, migration parser, JS syntax and Chromium workflow (`.github/workflows/project-checks.yml:12`, `:36`, `:64`). Native migration/locking/tenant tests exist, rather than only SQLite fixtures (`backend/tests/test_tenant_boundary.py:209`; `backend/tests/test_run_b_finance.py:323`; `backend/tests/test_workforce_concurrency.py:1`). Specification: `docs/SPECIFICATION.md:1802`.

**Internal gate:** close chapter 54's actual seam gaps; add regressions for the two reproduced findings; test supported profile installation/upgrade and production-sized load. Link each required chapter invariant to execution evidence at the final commit. **External gate:** actual LAN/browser/host/load acceptance with approved data. **Exit evidence:** passing required checks with skip reasons and known gaps explicit; test counts alone never serve as functional coverage or system completion.

<a id="chapter-49"></a>

### 49. AI Benchmark and Acceptance — External Gate; measurement framework present; real baseline and Human thresholds pending

**Present:** drawing geometry/area, Japanese CER/speaker/uncertainty and evidence-comparison metrics, source-bound persisted runs and Human baseline review (`backend/app/drawing_benchmark_core.py:1`; `scripts/benchmark_fire_audio.py:1`; `scripts/benchmark_fire_evidence_comparison.py:1`; `backend/app/routers/audio_benchmarks.py:1`). Tests cover speaker mapping/non-double-counted overlap and human-reviewed registry (`backend/tests/test_phase1_core.py:3731`, `:3815`, `:3839`, `:4062`). Specification: `docs/SPECIFICATION.md:1841`.

**Internal gate:** no chapter-specific benchmark-harness omission was established. Functioning generation adapters remain genuine internal work under chapters 19/29–32/37; this external status does not excuse or complete those dependencies. The measurement framework independently accepts source-bound hypotheses and Human references. **External gate:** real references, baseline execution, Human-selected thresholds after baseline, and false-positive usefulness acceptance. **Exit evidence:** dataset/source/model hashes, metrics, limitations and explicit Human accept/reject; synthetic scores do not establish real quality.

<a id="chapter-50"></a>

### 50. Data Migration — Partial

**Present:** mapped legacy facilities/emergency import, source IDs/hashes, unknown raw values, idempotent source runs and operational CSV/XLSX adapters (`backend/app/importers/facilities.py:41`; `backend/app/importers/emergency.py:114`, `:143`; `backend/app/importers/common.py:61`). Reference mapping is `docs/phase0/legacy_to_target_mapping.csv:1`; synthetic workbook integration is tested (`backend/tests/test_run_b_emergency.py:147`). Specification: `docs/SPECIFICATION.md:1872`.

**Internal gate:** remaining legacy domain adapters, correction/re-import precedence, deduplication/missing reconciliation and migration rehearsal tooling/report. Do not infer that unsupplied legacy files contain specific fields. **External gate:** actual legacy files and Human header/code mapping acceptance, including the current 117/160/24 emergency workbook understanding. **Exit evidence:** row/field counts, rejected/unknown items and original hashes reconcile; re-import preserves subsequent official corrections.

<a id="chapter-51"></a>

### 51. Operational Hosting — Partial

**Present:** department UUID config generation, dedicated OS/DB service roles, runtime service/nginx, storage, backup timer and health endpoint (`backend/app/tenant_deployment.py:7`; `scripts/generate_department_config.py:1`; `backend/app/main.py:31`; `deploy/tenants/README.md:1`). Generator/idempotency/role tests exist (`backend/tests/test_tenant_deployment.py:1`). Specification: `docs/SPECIFICATION.md:1892`.

**Internal gate:** complete supported server setup/monitoring/log rotation/capacity and recovery runbooks, plus deployment-profile parity and final release rehearsal. Resolve OwnerDR/worker-topology delta before selecting failover architecture. **External gate:** approved dedicated parent PC/server, TLS/network/ACL, backups and two physical clients. **Exit evidence:** deployed fixed release has health/monitoring and recoverable DB+originals with no browser-client database.

<a id="chapter-52"></a>

### 52. Release Artifacts — Partial; source packaging is implemented

**Present:** deterministic committed-source package, immutable commit/tree/file hashes, archive safety verification, installation and candid readiness guide (`scripts/build_release_bundle.py:124`, `:214`, `:276`; `docs/release/INSTALLATION.md:1`; `docs/release/RELEASE_READINESS.md:1`). Twenty-four packaging test definitions cover corruption, secrets exclusion, tree integrity and partial-clone behavior (`backend/tests/test_release_bundle.py:105`, `:131`, `:316`, `:397`). Specification: `docs/SPECIFICATION.md:1916`.

**Internal gate:** complete/reconcile the required architecture/server/update/backup/admin/user/permissions/database/migrations/security/test/benchmark/limitations/release/final-completion documents, then build/verify a final candidate at the accepted exact source. Existing phase material is reusable; missing exact filenames do not prove missing content. **External gate:** release acceptance and any offline dependency/model distribution decisions. **Exit evidence:** chapter 52 document-to-content manifest, reproducible artifact, clean installation/upgrade/restore evidence and honest `production_ready` declaration.

<a id="chapter-53"></a>

### 53. Definition of Done — Partial; Definition of Done not met; integration gate

**Present:** the canonical stopping rule explicitly separates major internal gaps from external acceptance (`docs/SPECIFICATION.md:1949`); release readiness repeats the ten chains and complete manuals/package requirements (`docs/release/RELEASE_READINESS.md:15`).

**Internal gate:** this ledger's material internal items, recovery reconciliation, exact final migrations/upgrade/full E2E/CI/manuals/release evidence. **External gate:** separately enumerated organization/host/model/form acceptance. **Exit evidence:** signed-off final matrix tied to exact commit/artifact; no substantial Missing/Partial or unresolved duplicate/conflict/orphan hidden behind “external gate.” A single merged PR or green test run is insufficient.

<a id="chapter-54"></a>

### 54. Required Cross-module E2E — Partial; existing chains must be extended

**Present:** substantive integration scenarios already connect dispatch/crew/rate/statistics, contract/budget/payment, stock/history, inquiry/evidence/official output and several drawing/fire/intake seams. Exact test mapping follows below. Specification: `docs/SPECIFICATION.md:1990`.

**Internal gate:** complete and execute all ten specified chains with source/permission/stale/rollback failure cases, using the existing scenarios rather than inventing a new duplicate suite. Workforce/statistics seams require checkpoint preservation and collision assessment; intake/worklist/hazardous acceptance was pending at this baseline. **External gate:** real physical-client/user acceptance is additional, not a substitute. **Exit evidence:** an explicit ten-flow acceptance manifest ties each step and negative case to actual final-commit results; a missing `test_cross_module_e2e.py` filename is irrelevant.

<a id="chapter-55"></a>

### 55. Development Governance — Completed; established governing contract

**Present:** canonical-source order, bounded slices, evidence requirements, privacy constraints and server-owned business writes (`AGENTS.md:1`; `docs/SPECIFICATION.md:2068`); current CI runs on main and PRs (`.github/workflows/project-checks.yml:3`).

**Internal gate:** no missing governing contract was established. Ongoing obligations are to refresh stale PROJECT_STATE/matrix after merges, reconcile recovered Run A/B changes, preserve append-only migrations and record exact evidence. The original source audit did not update those repository files. **External gate:** accountable approval when architecture or release decisions require it. **Exit evidence:** no duplicate reimplementation, no 051 conflict, and every final claim resolves to canonical merged source or is explicitly pending.

<a id="chapter-56"></a>

### 56. Priority Rule — Completed; ordered precedence established

**Present:** precedence is explicit: Master Specification → approved architecture/tenant operations → current safety contracts → current module specifications → history (`docs/SPECIFICATION.md:2113`).

**Internal gate:** none for the precedence rule itself: the complete ordered rule and treatment of obsolete wording are present in `docs/SPECIFICATION.md:2113`. Applying that rule to incomplete historical architecture context remains open under chapters 2/38/51 and is not implied complete here. **External/Human gate:** any material architecture reconciliation requires a separate approval; the policy statement itself does not authorize a new topology. **Exit evidence:** the canonical ordered precedence and obsolete-wording rule are established; future decisions must identify preserved requirements, superseded wording and any explicit scope amendment.

<a id="chapter-57"></a>

### 57. Completion Principle — Completed; established Human/AI principle; system DoD remains separate

**Present:** canonical completion principle preserves Human authority and AI assistance (`docs/SPECIFICATION.md:2130`), reflected in legal/cause/report/finance/learning gate tests cited above.

**Internal gate:** none established for the governing Human/AI principle itself. Completing the operational system and its remaining usability/AI functions stays explicitly open under chapters 1/45/53 and the relevant module chapters; this policy status is not a system completion claim. **External gate:** final organizational acceptance. **Exit evidence:** a usable coherent system, traceable and permission-safe assistance, and a final report that distinguishes executed acceptance, known internal gaps and external decisions.

## Ten canonical workflow chains: evidence and precise remaining seams

These are workflow coverage findings, not new passing-test claims. Related assertions may reside in multiple test modules. Preserve and extend them.

| # | Required chain | Actual evidence in current source | Remaining acceptance seam |
|---:|---|---|---|
| 1 | Facility → drawing → Human annotation → occupancy → requirement → Human review → installed equipment | `test_phase1_core.py:2043` candidate/equipment gate; `:4212` annotations; `:4352` classification before equipment; `:6584` response staleness | Demonstrate the whole linked source identity and final installed registry/navigation; actual-browser drawing chain and real model/reference acceptance remain distinct |
| 2 | Document → intake → Human classification → submission → facility → search | `test_phase1_core.py:543` analysis/review/receipt; `:602` explicit field apply; `:326` receipt/facility projection; `:3565` search | Re-audit PR #67; combine actual HTTP/browser intake, authoritative source preview, field update, search navigation and repeated/stale/cancelled operation cases |
| 3 | Incident → dispatch → crew → vehicle → activity → allowance → statistics | `test_run_b_operations.py:56` already creates vehicle, dispatch and crew, approves rate, calculates and Human-approves allowance, checks official statistics | Preserve this existing complete local API chain; add browser chain and recovered common-statistics projection without duplicating dispatch facts |
| 4 | Emergency → patient → treatment → transport → clinical candidate → Human review → monthly report | `test_run_b_emergency.py:37`, `:123`, `:132`; `test_emergency_reports.py:66`, `:104` | Bind chronology/transport and reviewed clinical result to a single monthly workflow; complete official form adapter and browser acceptance, respecting Run B ownership |
| 5 | Fire → photo/audio → transcript/statement → evidence → cause candidate → Human gate → report template | `test_phase1_core.py:2424`, `:2752`, `:2905`, `:2962`, `:3384` | Runnable worker, source playback/review controls, complete browser chain and safe outage behavior; real model quality separately external |
| 6 | Workforce → roster → dispatch → work result → overtime/allowance | `test_run_b_workforce.py:95`, `:135`; dispatch/allowance core `test_run_b_operations.py:56` | Work-result bridge and associated pending workforce features are in protected Run B recovery scope; preserve checkpoints and assess collisions before extending the linked workflow |
| 7 | Fleet → dispatch → mileage → fuel → log | `test_run_b_operations.py:74`, `:84`, `:335` cover dispatch/vehicle mismatch, trip/fuel/history and cost meaning | One valid dispatch-linked trip through fuel/history and browser navigation, including stale vehicle and invalid stock/chronology |
| 8 | Contract → commitment → budget → payment → balance | `test_run_b_finance.py:110`, `:323`; `test_finance_browser.py:8` actual browser flow | Preserve substantive existing end-to-end evidence; add final common-report reconciliation and final release/host evidence, not a replacement financial module |
| 9 | Asset → receive → location → loan/issue → return/transfer → inspection/expiry → history | `test_run_b_assets.py:54`, `:65`, `:92`, `:100`; `test_assets_browser.py:15` | Consolidate coverage manifest/IDs, final common task/statistics links and host acceptance; preserve existing conservation/expiry/approval tests |
| 10 | Inquiry → evidence → numeric source → draft → Human review → official output | `test_run_b_inquiries.py:45`, `:124`, `:133`, `:382`; `test_inquiries_browser.py:8` | Add configured model/statistics adapters and exact source-to-output proof across the final browser scenario; retain deterministic fallback and source-rights closure |

All test filenames in this table are under `backend/tests/`. Browser CI currently invokes ten specific test files (`.github/workflows/project-checks.yml:79`), with parameterized tests accounting for more than ten executed cases. It does not yet demonstrate every canonical chain.

## Reproduced findings

### F1: Facility dashboard discloses restricted module information

**Source:** `backend/app/routers/submissions.py:584` requires only `facility.read`. Lines 592–610 query inspections/findings/submissions; lines 665–672 return their counts, dates, latest submission ID and status without checking the corresponding module permissions. `backend/app/authz.py:59` does not imply those other rights.

**Probe:** an isolated synthetic user was granted only `facility.read` and `incident.read`. One facility, inspection/finding and submission were created in the in-memory database. Direct inspection/submission lists returned 403. The facility dashboard returned 200, `inspections_total=1`, `open_findings=1`, a `reviewed` submission state and a nonempty submission ID.

**Impact:** contradicts the explicit “no existence inference through Dashboard counts” contract in `docs/SPECIFICATION.md:375`. No production data was accessed. **Fix boundary:** aggregate each authorized domain only; return an explicit unavailable/omitted section rather than a misleading zero that implies checked absence; preserve the authorized-user response contract and ensure the UI distinguishes unavailable data. Add minimal-role tests and a browser role-loss case. Coordinate with the active worklist, but do not treat its new route as a fix for this older route.

### F2: Optional module flag is metadata rather than a consistent runtime gate

**Source:** flags are seeded in `backend/app/module_seed.py:54` and changed in `backend/app/routers/extensions.py:109`. All domain routers are included unconditionally (`backend/app/main.py:43`). The source search found a runtime FeatureFlag check for learning (`backend/app/routers/learning.py:87`) but not the operations router.

**Probe:** after inserting `module.operations.enabled=false`, the same synthetic user with `incident.read` received 200 from `/operations/incidents` and the seeded incident. This proves the operations flag does not currently close that route. It does not claim every optional route was runtime-probed.

**Impact:** department module selection is not fully effective. **Fix boundary:** define the disabled-read/write/search/dashboard/navigation policy once, protect always-on security/tenant/audit foundations, then implement consistent enforcement with domain dependency tests. Do not change business records or erase history on disablement.

## Top five next bounded slices

These are historical recommendations at c1b684c, not a current task assignment. PR67/68/69 and the hazardous/dashboard work had no main credit at that checkpoint. Consult the current ledger before selecting a slice, so later integrated or active work is not duplicated.

### 1. Close facility dashboard permission leakage

- **Why first:** a reproduced breach of an explicit privacy requirement in an everyday shared screen.
- **Scope:** facility dashboard permission-aware sections and its existing UI renderer; no new schema, legal policy or workforce/statistics reimplementation.
- **Dependencies:** synchronize the small overlap with PR #67's submissions/intake files and the active worklist API shape.
- **Acceptance:** direct and aggregate routes agree for facility-only, inspection-only, submission-only and combined roles; no hidden IDs/dates/states/counts; same-session permission removal clears old values; existing full-permission behavior remains.
- **Exit:** focused regressions, current aggregate checks, exact-commit CI and browser evidence. The audit already provides a synthetic reproduction.

### 2. Make optional module enablement effective

- **Why:** departments cannot meaningfully select modules while disabled APIs remain active; this also constrains future dashboards and adapters.
- **Scope:** shared enabled-module dependency/policy, initially a small demonstrator using operations and the existing learning behavior, then deliberate inventory-driven expansion. Include search/navigation/task projections and audit. Keep tenant/auth/audit/security unconditionally protected.
- **Dependencies:** agree the disabled read/write semantics and dependent-module behavior in a short reviewable contract. Coordinate all shared files with active branches; no 051 allocation.
- **Acceptance:** disabled module route/projection tests, re-enable preserves original records, unrelated modules remain functional, invalid/cyclic dependencies fail clearly.
- **Exit:** actual enabled/disabled browser/API flows and immutable configuration history, followed by explicitly enumerated module coverage.

### 3. Assemble the release and acceptance evidence index

- **Why:** the working source bundle and existing tests can become an understandable delivery package without waiting for real legal/model/host inputs.
- **Scope:** map all chapter 52 required documents to existing content, fill genuine procedural gaps, and create a ten-flow test/evidence manifest using the table above. Update only verified current-source status. Do not claim missing content solely from filenames.
- **Dependencies:** fixed candidate commit and exact CI links; integrate active slices before final source/package claims. Recovery work remains visibly pending.
- **Acceptance:** a new operator can identify setup, account/RBAC, update, paired rollback, backup recovery, daily work and known limitations from one index; each flow identifies executed and not-executed steps. Package verifies its fixed tree and installs from its stated prerequisites.
- **Exit:** coherent candidate manuals/report and reproducible artifact with `production_ready=false` until the remaining gates actually pass.

### 4. Complete inspection evidence and follow-up handoff

- **Why:** builds on the existing inspection and formal violation/correction module to make follow-up work actionable and avoid a second independent lifecycle.
- **Scope:** canonical inspector/evidence references, usable original/photo selection, exact finding-to-existing-correction navigation, and prior unresolved finding display. Preserve separate non-formal guidance versus formal violation.
- **Dependencies:** current violation and Document contracts; coordinate protected-document adapter ownership before any shared guard changes. Allocate any needed migration only after the active migration inventory is confirmed.
- **Acceptance:** inspection finding → source-bound guidance/correction → response → verification/closure, with stale evidence/denied source/incorrect facility rejected and a next inspection showing only authorized unresolved work.
- **Exit:** linked backend and actual browser scenario, audit/history, and no new legal threshold or automatic formal decision.

### 5. Add durable submission requirement and due-state tracking

- **Why:** closes a high-value operational loop between approved requirements, actual receipts and the new “today's work” view.
- **Scope:** source-bound obligation state, last accepted receipt, Human review, explicitly configured next due and Rule revision/recalculation history. Reuse the Rule evaluator and existing Submission IDs.
- **Dependencies:** PR #67 and submission lifecycle stable; worklist producer contract stable; approved synthetic Rules sufficient for internal tests. Real jurisdiction deadlines are external Human inputs.
- **Acceptance:** received/revised/cancelled documents update the correct obligation atomically; changed Rule/facility evidence creates re-review rather than silently reasserting compliance; overdue/missing remains a candidate and restricted obligations do not leak counts.
- **Exit:** repeat/stale/concurrent intake and Rule-change tests plus a browser receipt → due card → source navigation chain.

## Next work after those slices

1. Preserve existing workforce/statistics checkpoints and assess overlap against authoritative main, branches, PRs and migrations before a bounded new requirement. Do not claim checkpoint code recovered or lost without evidence.
2. Reconcile central-server/dynamic-worker/offline-requeue/OwnerDR requirements with the approved tenancy and deployment design. This is a Human architecture decision, not a request to implement a guessed worker topology.
3. Implement a runnable bounded local-model adapter contract and source-safe task lifecycle, then connect drawing, audio/photo/fire reports, inquiry and learning incrementally. Missing model weights and quality datasets are external; missing runnable adapter code is internal.
4. Finish module-specific original-form/import/personnel-transfer/configuration workflows against the preserved common platforms.
5. Close all ten canonical workflow seams, upgrade/restore/profile/load testing, then issue the exact-commit final completion report with external acceptance recorded separately.

## External acceptance register

| Gate | Required evidence | Owner/input boundary |
|---|---|---|
| Production host and isolation | Approved service/DB roles, storage ACL, DNS/TLS, network path, capacity/monitoring, cross-department negative tests | Deployment organization and host administrator |
| Two physical clients | Login/role change, concurrent edits, reload/session isolation and full critical workflows on the real LAN | Organization's actual PCs/users |
| Recovery drill | Department-bound DB+originals backup and isolated restore, correct release/migrations/hash checks and service recovery | Host administrator; approved restore target |
| Legal rule coverage | Effective approved Rules, exact provisions, jurisdiction mapping and formal procedure approval | Authorized legal/business reviewers; no guessed thresholds |
| Finance/personnel/workforce policy | Approved fiscal hierarchy, precision/approval/leave/work/qualification/allowance definitions | Accountable organization staff |
| Official forms | Supplied original templates, issuer/effective version, mapping review and rendered-output acceptance | Form owner/business reviewers |
| Real AI quality | Authorized real datasets, frozen Human references, source/model hashes, measured baseline, later Human thresholds | Dataset owners and Human acceptance reviewers |
| Final adoption | Usability, training, known limitations, operating/recovery responsibility and go-live approval | Organization's authorized decision-maker |

An external gate does not excuse an absent parser, adapter, module, control, manual, or synthetic acceptance test. An inaccessible existing implementation is a recovery/reconciliation gate, not evidence that it never existed.
