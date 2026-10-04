# PROJECT_STATE

更新日: 2026-10-05

## Current Phase

Phase 5 legal-rule engine is code-complete and CI-verified.
Phase 5.1 national/local legal-source update foundation is implemented in code.
Live full-corpus acquisition from e-Gov and a real designated fire-department regulation source remains an external-source E2E gate.
Formal approved-host PostgreSQL/TLS/two-client gate also remains unexecuted.

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

## Phase 5 completed in code

- legal rule registry
- numbered/effective-dated rule versions
- verified-source requirement before approval
- Draft / Approved separation
- deterministic requirement evaluation
- submission/equipment requirement domains
- evidence and candidate-only decisions
- rule management/approval/evaluation RBAC
- facility UI for candidate required documents/equipment
- no automatic operational DB mutation from legal evaluation

## Phase 5.1 source/profile foundation

- national/prefecture/municipality/fire-union/fire-department jurisdiction model
- fire-department legal profiles
- multiple jurisdictions per profile
- multiple official sources per jurisdiction/profile
- Source Adapter metadata
- online/bundle/manual update modes
- all-content scope
- sync frequency
- full legal source document/version chain
- raw-original Document linkage
- SHA-256 and previous-Version linkage
- update candidate / impacted Rule placeholder
- corpus completeness status: unverified/complete/partial/stale/error
- legal source/profile RBAC
- source/profile registry API

## Phase 5.1 collectors/importers implemented

### e-Gov
- full national-law XML collector
- date-based updated-law delta collector
- SHA-256 Manifest
- e-Gov XML Archive importer
- raw XML preservation
- normalized text
- Source Document / Version generation
- LegalUpdateCandidate generation

### Local official regulation
- official-host bounded HTML collector
- configurable include/crawl regex
- maximum page/depth guards
- raw HTML/PDF/etc byte preservation
- manifest with visited/captured/failure/truncated counts
- DB importer
- Source Document / Version generation
- update candidate generation
- corpus completeness tracking

### Scheduler
- due-source sync orchestrator
- online e-Gov adapter
- online official_html_crawl adapter
- initial e-Gov bootstrap requires explicit --allow-bootstrap
- daily delta after bootstrap
- systemd one-shot service
- daily 03:30 timer with randomized delay

## Important safety policy

- National/local legal original acquisition may be automatic.
- Rule interpretation/activation after legal amendment is NOT automatic.
- Legal update -> Version/Diff -> Impact candidate -> Human Gate -> Approved Rule Version.
- A local regulation Source is not declared complete unless corpus completeness validation succeeds.
- JavaScript-heavy or vendor-specific regulation systems may require a dedicated Browser Adapter.

## Verification already completed

- Phase 5 rule engine CI: SUCCESS
- Phase 5 safety tests: 39 passed at that checkpoint
- Phase 5.1 Source Registry CI: SUCCESS
- migrations through 009 included in parser checks
- operational scripts are now included in Python syntax CI

## Not yet reported as PASS

- live e-Gov full bootstrap
- live e-Gov daily delta -> DB end-to-end
- real designated fire-department full regulation corpus capture
- local regulation table-of-contents count reconciliation
- browser adapter for JS-only regulation systems
- official promulgation/update-page adapter
- signed closed-network Update Bundle verification/import
- real legal amendment -> Rule impact analysis acceptance test
- approved LAN PostgreSQL migrations 001-009
- PostgreSQL backup/restore after Migration 009
- HTTPS production LAN clients
- two-client concurrent E2E

## Next Phase 5.1 slice

1. execute live e-Gov bootstrap in an approved internet-connected collector environment
2. validate daily e-Gov delta
3. select a real fire department profile
4. discover and approve all official regulation/promulgation sources for that profile
5. build any required vendor/browser adapters
6. full-corpus import and completeness reconciliation
7. ordinance amendment diff E2E
8. Rule impact candidate generation
9. signed Update Bundle for closed networks
10. then proceed to Phase 6 drawing analysis

Do not report external-source gates as PASS until actually executed.

## Verified fire-department corpus

### 大島地区消防組合

- legal profile: `oshima-fire-union`
- official source: `https://fd-ohshima.jp/reiki_2026/`
- content current: 2025-04-01
- expected body documents: 119
- discovered: 119
- captured: 119
- failures: 0
- coverage status: complete
- acquisition run: 37240040293
- artifact ID: 11317595248
- artifact SHA-256: `2426f76c7a50609d63f231943f3058b8c196cd8563be54033dba9cbf6defc941`

This is the first real fire-department full-corpus acquisition E2E PASS.
The external approved-LAN database import remains separate from corpus acquisition.

## Verified national legal corpus

### e-Gov 全国法令

- profile: `jp-national-laws`
- official source: e-Gov 法令検索
- scope: all national laws XML
- XML documents: 10,414
- archive integrity: PASS
- coverage status: complete_official_bulk_archive
- acquisition run: 37240404083
- artifact ID: 11317001520
- source archive SHA-256: `830c24983bee6d9e7db8765b01ed671ee91ca9472324ec5c0d8d0e5a32e660cf`
- artifact ZIP SHA-256: `a834626b725f78e91b5682a9f1f891f988d4453819ff826c809d9a72acb81a9d`

This is the first real national full-corpus acquisition E2E PASS.
Daily delta sync remains the incremental update path after this baseline.

