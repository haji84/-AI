# PROJECT_STATE

更新日: 2026-10-05

## Current Phase

Phase 5.1-5.6 legal-source, structured-citation, Human review, authoring-worklist, import, and workflow coverage foundations are implemented and CI-verified.

Real official corpora have been acquired and structurally verified:
- e-Gov national laws: 10,414 documents
- 大島地区消防組合 official regulations: 119 documents

Formal Rule conditions/outcomes remain Human-Gated.
Approved-host PostgreSQL/TLS/two-client production gate remains unexecuted.

## Phase 0-4 retained

- legacy inspection ledger audit / 574-column mapping
- auth / RBAC / audit / optimistic locking / extensibility
- emergency reporting import foundation
- facility CRUD / normalized detail / conflict UI
- inspection / findings
- submission type / receipt / original document linkage
- PDF/image/DOCX/XLSX/text document intake
- OCR fallback and deterministic document classification
- Human Review before receipt/facility change
- contract/form-template/extensibility foundation

## Phase 5 legal Rule engine

Implemented:
- legal Rule registry
- numbered/effective-dated Rule Versions
- verified source before approval
- Draft / Approved separation
- deterministic equipment/submission requirement evaluation
- candidate-only operational decisions
- exact audit trail
- Rule management/approval/evaluation RBAC
- facility UI for candidate required documents/equipment
- exact LegalProvision citations
- no automatic operational DB mutation from legal evaluation

## Phase 5.1 source/update foundation

Implemented:
- national/prefecture/municipality/fire-union/fire-department jurisdiction model
- legal profiles per fire department
- multiple official sources per profile
- online/bundle/manual update modes
- sync frequency and corpus completeness
- raw original + SHA-256 + Version chain
- e-Gov full/delta collectors and importer
- local official regulation collector/importer
- daily source-sync orchestrator / systemd timer
- update candidates and old/new Version preservation

### Verified national corpus

e-Gov:
- acquisition run: 37240404083
- documents: 10,414
- archive integrity: PASS
- source archive SHA-256: `830c24983bee6d9e7db8765b01ed671ee91ca9472324ec5c0d8d0e5a32e660cf`

### Verified local corpus

大島地区消防組合:
- source: `https://fd-ohshima.jp/reiki_2026/`
- content current: 2025-04-01
- expected/discovered/captured: 119 / 119 / 119
- failures: 0
- coverage: complete
- acquisition run: 37240040293
- artifact SHA-256: `2426f76c7a50609d63f231943f3058b8c196cd8563be54033dba9cbf6defc941`

## Phase 5.2 structured legal corpus

Implemented:
- Migration 010
- LegalProvision hierarchy
- part/chapter/section/article/paragraph/item/subitem
- supplementary provisions
- appendix/table/form/figure/note
- article-less notice `document_body` fallback
- Rule Version -> exact Provision Citation
- Citation text snapshot
- Provision-level amendment diff
- changed/removed cited Provision -> impacted Rule candidates
- legal document/version/provision search API
- exact citation display in requirement UI

Real full-corpus E2E run: 37241690774 SUCCESS

e-Gov:
- documents: 10,414
- structured provisions: 5,447,878
- parse failures: 0
- zero-provision documents: 0

大島地区消防組合:
- documents: 119
- structured provisions: 26,898
- parse failures: 0
- zero-provision documents: 0

## Phase 5.3 Human-Gated Rule drafts

Implemented:
- Migration 011
- Migration 012
- Rule Draft Candidate
- exact Draft Citation
- manual/deterministic/AI extraction source
- confidence/rationale/model metadata
- candidate fingerprint / idempotency
- Human editing of proposed Rule code/name/conditions/outcome
- pending -> reviewed/rejected
- reviewed -> promoted Draft Rule Version
- promotion never creates Approved Rule
- final Rule approval remains separate Human Gate
- centralized condition validation

Safety:
- relevance detection can create candidates with blank conditions/outcomes
- blank/unvalidated conditions cannot be reviewed/promoted
- structured-source draft requires exact Citation
- AI/deterministic candidate cannot directly become Approved

## Phase 5.4 Human legal review queue

Implemented:
- Migration 013
- Migration 014
- Migration 015
- Provision relevance review queue
- status: pending/reviewed/ignored/drafted
- category: equipment/submission/fire-management/inspection/hazardous/local prevention
- source priority: national_core/local_core/normal
- Provision context: main/supplementary_transition/document_body
- supplementary provisions retained but deprioritized
- reviewed equipment/submission Provision -> incomplete Rule Draft handoff
- exact original text displayed in UI
- optimistic concurrency on review

Real-corpus verification run: 37243458396 SUCCESS

e-Gov matched Provisions: 15,065
- equipment: 1,900
- submission: 1,688
- fire management: 522
- inspection/enforcement: 729
- hazardous materials: 9,294
- local fire prevention: 2,009

大島地区消防組合 matched Provisions: 2,226
- equipment: 69
- submission: 601
- fire management: 72
- inspection/enforcement: 524
- hazardous materials: 240
- local fire prevention: 1,129

These category counts overlap by design.

## Phase 5.5 core authoring worklist

Exact core source set:
- national: 5 / 5 found
- 大島地区消防組合: 13 / 13 found

Verified worklist run: 37248400904 SUCCESS
Artifact ID: 11320435391
Artifact SHA-256: `39688473f87fa888ae9db6840ec6f2f41a880a500f72c97f05dc4c96582221ec`

Worklist:
- total items: 7,854
- requirement_rules: 1,602
- management_review: 803
- hazardous_materials: 5,093
- local_fire_prevention: 1,223

Implemented:
- exact Provision content SHA-256 inside worklist
- source baseline evidence inside inventory
- dry-run/apply importer
- exact external ID + title + Provision Key + Provision Hash verification
- stale worklist rejection
- terminal review states are not overwritten
- repeated import is idempotent
- legal-review summary API
- title/text search
- category/lane/context/min-score/min-total-priority filters
- 50-item pagination
- status counts in UI

Important:
1,602 worklist items do NOT imply 1,602 final Rules.
Multiple Provisions can compose one Rule and one Provision can support several Rules.

## Phase 5.6 authoring workflow coverage

Implemented:
- workflow counts for equipment/submission
- review queue counts by status
- Rule Draft counts by status
- Rule Version counts by status
- Approved Rule count by domain
- exact citation count
- coverage displayed in legal review UI

Coverage is explicitly a work-progress count, not a percentage of legal completeness.

## Verification

Latest verified project-checks checkpoint:
- backend pytest: 58 passed
- Migration 010: PASS
- Migration 011: PASS
- Migration 012: PASS
- Migration 013: PASS
- Migration 014: PASS
- Migration 015: PASS
- frontend JavaScript syntax: PASS
- operational Python script syntax: PASS

## Not yet reported as PASS

- Human legal acceptance/review of all requirement Rule conditions/outcomes
- complete production Approved Rule set
- import of the verified 1,602-item requirement worklist into the approved production LAN DB
- live e-Gov daily delta -> approved production DB E2E
- every local official promulgation/update-page adapter
- signed closed-network Update Bundle verification/import
- approved LAN PostgreSQL migrations 001-015
- PostgreSQL backup/restore after Migration 015
- HTTPS production LAN clients
- two-client concurrent E2E

## Next slice

1. compare Approved submission-requirement Rules against actual submission records
2. report missing-submission candidates only when an Approved Rule explicitly requires that submission
3. build installed-equipment registry
4. compare Approved equipment-requirement Rules against installed-equipment records
5. preserve exact Rule/Provision evidence for every gap candidate
6. add Human confirmation for compliance/gap findings
7. continue legal Rule authoring through the 1,602-item requirement worklist
8. then connect Phase 6 drawing analysis to the same requirement engine

Do not report Rule completeness or production legal compliance until Human-approved Rules and production Host Gates are complete.
