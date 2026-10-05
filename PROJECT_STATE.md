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

1. Phase 7 fire investigation case management, photos, audio/statements and report drafting
2. real drawing-model benchmark and symbol/geometry acceptance tests
3. continue legal Rule authoring and production Host Gates

<!-- superseded Phase 5.7 list retained in history -->

1. compare Approved submission-requirement Rules against actual submission records
2. report missing-submission candidates only when an Approved Rule explicitly requires that submission
3. build installed-equipment registry
4. compare Approved equipment-requirement Rules against installed-equipment records
5. preserve exact Rule/Provision evidence for every gap candidate
6. add Human confirmation for compliance/gap findings
7. continue legal Rule authoring through the 1,602-item requirement worklist
8. then connect Phase 6 drawing analysis to the same requirement engine

Do not report Rule completeness or production legal compliance until Human-approved Rules and production Host Gates are complete.

## Phase 6 drawing analysis foundation

Code-complete and CI-verified.

Implemented:
- Migration 017 drawing analyses/elements/equipment candidates/fact candidates
- Migration 018 fact application metadata
- drawing.read / drawing.analyze / drawing.review RBAC
- drawing upload status: pending
- normalized Local AI result Manifest
- idempotent Manifest SHA-256
- drawing element candidates
- equipment candidates
- Facility fact candidates
- Human accept/reject
- accepted equipment -> FacilityEquipment ai_candidate only
- independent verification required before verified
- accepted fact -> strict target-path Allowlist
- Facility optimistic lock on fact application
- exact source drawing Document linkage
- drawing review completion only after pending candidates are cleared
- facility UI for drawing upload/list/review
- equipment Rule comparison keeps AI/legacy/unverified evidence non-authoritative

Phase 6 verification:
- GitHub Actions run: 37251037051 SUCCESS
- backend pytest: 70 passed
- Migration 017: PASS
- Migration 018: PASS
- frontend JS syntax: PASS

Not yet a production-quality drawing AI claim:
- Local Vision model accuracy E2E remains unexecuted
- real architectural drawing benchmark remains unexecuted
- approved LAN PostgreSQL/physical-client Host Gate remains unexecuted

## Phase 7 fire investigation foundation

Implemented:
- Migration 019 fire investigation Case/evidence model
- original photo/audio/video/drawing Document linkage
- photo annotations
- transcript segments
- statement Drafts
- timeline candidates
- fire-cause candidates
- formal cause Human approval
- report Drafts and Human approval
- Migration 020 idempotent AI manifests
- Migration 021 immutable Human-reviewed Evidence Snapshots
- AI report provenance bound to Snapshot/Manifest
- Migration 022 approved report -> registered official FormTemplate rendering/export
- formal cause and formal report remain separate Human Gates

Verified Evidence Snapshot checkpoint:
- run 37253033331 SUCCESS
- backend pytest: 76 passed
- Migration 021 PASS
- frontend JavaScript syntax PASS

## Phase 8 fire photo intelligence

Implemented:
- Migration 023 photo profile/metadata/quality/duplicate foundation
- exact SHA-256
- perceptual hash
- EXIF metadata
- brightness/contrast/sharpness quality signals
- photo search text
- duplicate candidate support
- Migration 024 Human-reviewed photo -> drawing position links
- photo/drawing link is candidate until Human accepted
- original photo Documents remain immutable

## Phase 9 voice / statement intelligence

Implemented:
- Migration 025 transcript uncertainty/search/evidence comparison
- Migration 026 evidence_comparison AI Manifest type
- deterministic uncertainty markers
- transcript text SHA-256
- accepted transcript search
- uncertain-only search
- statement source-uncertainty propagation
- explicit Human uncertainty confirmation before statement review
- evidence comparison using Human-reviewed evidence only
- comparison Manifest idempotency
- pending/accepted/rejected comparison workflow
- optimistic review conflict protection
- canonical API consolidated under `/fire-investigations`
- transcript search UI
- uncertainty warning UI
- evidence comparison review UI

Last verified green Phase 9 checkpoint:
- run 37254735014 SUCCESS
- backend pytest: 83 passed
- Migration 025: PASS
- Migration 026: PASS
- frontend JavaScript syntax: PASS

Latest Phase 9 hardening currently includes:
- accepted comparison must not mutate reviewed statement text
- accepted comparison must not mutate confirmed timeline
- accepted comparison must not create/select official cause

Do not report the latest hardening/UI HEAD as final PASS until its current CI finishes.

## Current next gates

1. execute Benchmark v2 on real Japanese interview recordings
2. obtain the first real CER / Speaker Error Rate / uncertainty Precision-Recall-F1 Baseline
3. set acceptance thresholds through Human Gate
5. evidence-comparison usefulness/false-positive acceptance test
6. approved LAN PostgreSQL migrations through 026
7. backup/restore after Migration 026
8. HTTPS physical LAN clients
9. two-client concurrent E2E
10. continue Human legal Rule authoring / production legal Host Gates

Do not claim production-quality STT, legal completeness, formal compliance, or production Host readiness until those gates are executed.

## Phase 10 permission-aware unified search

Implemented and CI-verified:
- global permission-aware search API
- `search.use` gate
- per-module read-permission enforcement
- facilities / inspections / submissions / equipment / drawings
- fire investigation cases
- accepted transcripts only
- reviewed statements only
- accepted photo annotations only
- legal documents / legal Rules
- documents / contracts / templates / change requests
- deterministic lexical scoring
- provenance/navigation metadata
- query SHA-256 audit without raw-query persistence
- global search UI and module filters
- emergency personal records intentionally excluded

Verified checkpoint:
- commit: `9482d2fd83978446be236f696a30dccdaf117c43`
- run: `37255300365` SUCCESS
- backend pytest: 85 passed
- migrations 001-026 parser smoke: PASS
- frontend JS syntax: PASS

Not yet production claims:
- semantic/vector retrieval quality benchmark
- production PostgreSQL latency/load benchmark
- approved LAN physical-client search E2E



## Phase 9 Japanese audio benchmark v2

Implemented and CI-verified:
- benchmark format `fire-ai-japanese-stt-benchmark-v2`
- Japanese CER
- automatic speaker-label overlap mapping
- speaker confusion / missed / false-alarm metrics
- non-double-counted diarization timeline scoring
- uncertainty marker tolerance window
- bipartite marker matching
- multi-recording Dataset Manifest
- micro aggregate metrics
- Reference/Hypothesis/Manifest SHA-256 provenance
- recording-condition metadata passthrough
- example Dataset Manifest
- v2 benchmark contract

Verified checkpoint:
- run: `37256577150` SUCCESS
- backend pytest: 88 passed

Current external gate:
- real Japanese audio Dataset has not yet been supplied/executed
- therefore production-quality STT, diarization accuracy, and uncertainty-marker accuracy are NOT claimed
- next action is real-audio Baseline generation, then Human-set acceptance thresholds



## Phase 9 audio benchmark run registry

Implemented and CI-verified:
- Migration 027 benchmark-run persistence
- benchmark v2 result payload storage
- canonical result SHA-256
- Manifest SHA-256
- recording count
- Human baseline review
- optimistic concurrency
- duplicate result idempotency
- Benchmark Run history API
- two-run metric comparison API
- CER / Speaker Error Rate / uncertainty F1 deltas
- recording-condition metadata in benchmark results
- route-precedence regression protection

Verified checkpoint:
- run: `37257011265` SUCCESS
- backend pytest: 91 passed
- Migration 027: 4 statements PASS

Current Phase 9 external gate:
- no real Japanese interview/fire-investigation audio Dataset has been benchmarked yet
- first real CER / Speaker Error Rate / uncertainty-marker Baseline remains unexecuted
- production-quality STT/diarization accuracy is therefore NOT claimed

Next executable external step:
1. provide or collect real Japanese interview audio
2. create Human Reference JSON
3. generate Local STT Hypothesis JSON
4. run Benchmark v2
5. register result in benchmark-run registry
6. Human accepts/rejects Baseline
7. set acceptance thresholds only after Baseline review


## Phase 9 evidence-comparison benchmark v1

Implemented and CI-verified:
- exact Human Reference vs Local AI candidate comparison
- left/right evidence order normalization
- duplicate prediction false-positive accounting
- Precision / Recall / F1
- false-positive / false-negative candidate evidence
- per-issue-type metrics
- multi-case micro aggregation
- Reference / Hypothesis / Manifest SHA-256 provenance
- benchmark contract and regression tests

Verified checkpoint:
- run: `37258781446` SUCCESS
- backend pytest: 93 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Human Gate remains explicit:
- no production acceptance threshold is hard-coded
- real Human-labeled investigation cases are still required
- production-quality evidence-comparison accuracy must not be claimed until the real dataset is benchmarked and Human acceptance thresholds are set


## Phase 9 evidence-comparison benchmark run registry

Implemented and CI-verified:
- Migration 028 benchmark-run persistence
- benchmark v1 result payload storage
- canonical result SHA-256
- Manifest SHA-256
- case count
- duplicate result idempotency
- Human baseline review
- optimistic concurrency
- Benchmark Run history API
- two-run comparison API
- Precision / Recall / F1 deltas
- false positives per case delta

Verified checkpoint:
- run: `37259163834` SUCCESS
- backend pytest: 94 passed
- Migration 028 parser smoke: PASS
- frontend JavaScript syntax: PASS

Safety remains unchanged:
- benchmark acceptance cannot mutate reviewed statements, confirmed timeline, formal evidence, official cause, or report
- no production threshold is hard-coded
- real Human-labeled cases and Human-set acceptance thresholds remain external gates


## Phase 6 drawing benchmark v1

Implemented and CI-verified:
- benchmark format `fire-ai-drawing-benchmark-v1`
- multi-drawing Dataset Manifest
- bounding-box normalization for x/y/width/height, x1/y1/x2/y2, bbox and polygon points
- page-aware one-to-one geometry matching
- configurable IoU threshold
- geometry Precision / Recall / F1 and mean IoU
- element-type accuracy
- symbol classification accuracy
- equipment-candidate Precision / Recall / F1
- Facility fact-candidate Precision / Recall / F1
- Reference / Hypothesis / Manifest SHA-256 provenance
- benchmark contract and regression tests

Verified checkpoint:
- run: `37260088706` SUCCESS
- backend pytest: 97 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

External Gate remains:
- real architectural drawing Human Reference dataset has not yet been benchmarked
- production-quality drawing AI accuracy is not claimed
- acceptance thresholds remain Human-set after real Baseline measurement
