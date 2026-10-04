# PROJECT_STATE

更新日: 2026-10-05

## Current Phase

Phase 5.2 structured legal corpus + exact Rule citation core is complete and real-corpus E2E verified.
Phase 5.3 Human-Gated Rule draft candidate core is complete and CI verified.
The next slice is review-queue generation and actual fire-related Rule authoring from verified provisions.
Formal approved-host PostgreSQL/TLS/two-client gate remains unexecuted.

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

Completed:
- legal Rule registry
- numbered/effective-dated Rule Versions
- verified-source requirement before approval
- Draft / Approved separation
- deterministic requirement evaluation
- submission/equipment requirement domains
- candidate-only operational decisions
- exact audit trail
- management/approval/evaluation RBAC
- facility UI for required-document/equipment candidates
- no automatic operational DB mutation from legal evaluation

## Phase 5.1 legal source/update foundation

Completed:
- national/prefecture/municipality/fire-union/fire-department jurisdiction model
- fire-department legal profiles
- multiple jurisdictions and official sources per profile
- Source Adapter metadata
- online/bundle/manual update modes
- sync frequency and corpus completeness state
- legal source Document / Version chain
- raw-original SHA-256 preservation
- update candidate and sync-run tracking
- e-Gov full/delta collectors/importers
- bounded official local-regulation collector/importer
- daily sync orchestrator and systemd timer
- corpus completeness: unverified/complete/partial/stale/error

## Verified source corpora

### e-Gov national laws
- official full XML corpus acquired
- documents: 10,414
- archive integrity: PASS
- coverage: complete_official_bulk_archive
- acquisition run: 37240404083
- artifact ID: 11317001520
- source archive SHA-256: `830c24983bee6d9e7db8765b01ed671ee91ca9472324ec5c0d8d0e5a32e660cf`

### 大島地区消防組合
- official source: `https://fd-ohshima.jp/reiki_2026/`
- content current: 2025-04-01
- expected/discovered/captured: 119 / 119 / 119
- failures: 0
- coverage: complete
- acquisition run: 37240040293
- artifact ID: 11317595248
- artifact SHA-256: `2426f76c7a50609d63f231943f3058b8c196cd8563be54033dba9cbf6defc941`

## Phase 5.2 structured legal corpus

Migration 010:
- `legal_provisions`
- `legal_rule_citations`
- structure status/parser metadata on legal source Versions

Supported structured concepts:
- part/chapter/section/subsection/division
- article
- paragraph
- item/subitem
- supplementary provisions
- appendix/tables/forms/figures/notes
- article-less official notices as `document_body`

Exact Rule citation:
- Rule Version -> LegalProvision
- citation roles: primary/definition/exception/reference/supplementary
- cited text snapshot preserved
- structured-source Rule cannot be approved without an exact citation
- changed/removed cited provisions reverse-map to impacted Rule IDs

### Real full-corpus parser E2E

Workflow run: 37241690774
Result: SUCCESS

e-Gov:
- documents: 10,414
- structured provisions: 5,447,878
- parse failures: 0
- zero-provision documents: 0
- article: 1,030,986
- paragraph: 2,364,763
- item: 1,274,776

大島地区消防組合:
- documents: 119
- structured provisions: 26,898
- parse failures: 0
- zero-provision documents: 0
- article: 3,577
- paragraph: 4,983
- item: 404
- article-less notice fallback: 1

## Phase 5.3 Rule draft candidates

Migration 011:
- `legal_rule_draft_candidates`
- `legal_rule_draft_citations`

Implemented flow:
LegalProvision
-> manual/deterministic/AI Rule Draft Candidate
-> Human Review
-> promoted Draft Rule Version
-> separate formal Rule approval
-> Approved Rule Version

Safety:
- AI candidate cannot directly become Approved
- promotion before Human Review is rejected
- structured-source draft requires exact provision citation
- promotion creates only a Draft Rule Version
- formal approval stays a separate Human Gate

## Verification

Latest main project-checks at commit `9b0fae6b065b7ce923017d625fc950450590903e`:
- backend pytest: 46 passed
- Migration 010: 7 statements PASS
- Migration 011: 5 statements PASS
- frontend JavaScript syntax: PASS
- operational script syntax: PASS

## Not yet reported as PASS

- complete production authoring of all fire-service Rules from 5.4M provisions
- legal acceptance review of Rule conditions/outcomes
- live e-Gov daily delta -> production DB
- official promulgation/update-page adapter for every local source
- signed closed-network Update Bundle verification/import
- approved LAN PostgreSQL migrations 001-011
- PostgreSQL backup/restore after Migration 011
- HTTPS production LAN clients
- two-client concurrent E2E

## Next slice

1. build legal-provision review queue for fire-service-relevant provisions
2. identify national source documents needed for prevention/equipment/submission Rules
3. identify 大島地区消防組合 local provisions that override/add local requirements
4. generate non-authoritative Rule Draft Candidates with exact citations
5. Human Review each candidate
6. promote reviewed candidates to Draft Rule Versions
7. legally review and approve only verified Rules
8. compare required documents/equipment against facility/submission/equipment records
9. then continue Phase 6 drawing-analysis integration
