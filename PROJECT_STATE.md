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


## Phase 6 drawing benchmark run registry

Implemented and CI-verified:
- Migration 029 benchmark-run persistence
- drawing benchmark v1 result payload storage
- canonical result SHA-256
- Manifest SHA-256
- drawing count
- duplicate result idempotency
- Human baseline review
- optimistic concurrency
- Benchmark Run history API
- two-run comparison API
- Geometry F1 / mean IoU / element-type accuracy / symbol accuracy deltas
- equipment/fact F1 deltas
- geometry false positives per drawing delta

Verified checkpoint:
- run: `37260374408` SUCCESS
- backend pytest: 98 passed
- Migration 029 parser smoke: PASS
- frontend JavaScript syntax: PASS

External Gate remains:
- real Human-labeled architectural drawing dataset has not yet been benchmarked
- production acceptance thresholds remain Human-set after Baseline review


## Phase 6 real-drawing benchmark hardening

Triggered by first supplied residential reference drawing:
- optional categories with no Human Reference targets no longer report fake perfect scores
- zero-reference/zero-hypothesis category -> applicable=false and null metric
- false-positive-only category remains scored and penalized
- symbol/equipment/fact N/A values are preserved through Benchmark Run comparison API
- benchmark contract documents N/A semantics

CI-verified on branch `phase6-drawing-benchmark-na-hardening`.

Verified hardening checkpoint:
- run: `37267047053` SUCCESS
- backend pytest: 101 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

The supplied residential plan is suitable for Geometry and Facility fact extraction Baseline.
It is not sufficient by itself for fire-equipment symbol accuracy coverage.


## Phase 6 Human Annotation

Implemented and CI-verified:
- Migration 030 drawing annotation sets
- manual Human Reference draft creation
- AI-seeded annotation draft from DrawingAnalysis
- editable room/element geometry and use labels
- pixel or normalized coordinate space
- page-dimension provenance
- optimistic annotation editing
- Human review/reject gate
- reviewed-only Benchmark Reference export
- source Drawing Document SHA-256 provenance
- room annotations require valid geometry and label/use before review

This allows room polygons and room-use labels to become Human-reviewed benchmark truth.
Verified checkpoint:
- run: `37268130556` SUCCESS
- backend pytest: 103 passed
- Migration 030 parser smoke: PASS
- frontend JavaScript syntax: PASS

AI-seeded content never becomes Reference truth without Human review.


## Phase 6 drawing consultation / occupancy classification

Implemented and CI-verified:
- Migration 031 drawing consultation persistence
- Managed Legal Rule domains expanded with occupancy_classification and equipment_placement
- consultation snapshot from Human-reviewed drawing annotation
- classification candidate evaluation from effective Approved Rules
- missing-information discovery for Rule-required inputs
- manual Human classification fallback requires review note
- hard gate: equipment evaluation is rejected until classification is Human-confirmed
- required equipment candidates use effective Approved equipment_requirement Rules only
- exact Rule Version / citations / source reference are preserved
- zero matched Rules is explicitly not treated as zero required equipment
- placement candidates are generated only from effective Approved equipment_placement Rules
- placement Rule absence blocks auto-placement
- room-candidate placement uses Human-reviewed room geometry only
- E2E tests cover classification -> confirm -> equipment -> placement

Verified checkpoint:
- run: `37269178086` SUCCESS
- backend pytest: 105 passed
- Migration 031 parser smoke: PASS
- frontend JavaScript syntax: PASS

Legal content Gate remains:
- occupancy classification Rule set is not yet declared complete
- equipment requirement Rule set is not yet declared complete
- equipment placement Rule set is not yet declared complete
- production legal advice must not be claimed until Human-approved Rule coverage and production Host Gates are complete


## Phase 6 occupancy classification Rule worklist

Implemented and CI-verified:
- exact target law title: 消防法施行令
- exact target appendix prefix: 別表第一
- e-Gov XML AppdxTable selection
- TableRow / TableColumn structural extraction
- source XML SHA-256
- per-row SHA-256
- Human review worklist output
- proposed Rule code/name/conditions/outcome remain blank
- no automatic Rule approval
- no automatic classification Rule generation
- workflow uses the previously verified e-Gov national-law artifact

Verified checkpoint:
- run: `37269627180` SUCCESS
- backend pytest: 107 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Next legal-authoring gate:
1. run the worklist workflow on the verified official corpus
2. Human reviews each Schedule 1 row
3. Human authors classification conditions/outcomes
4. create Draft Rule candidates with exact source evidence
5. separate Human approval before consultation auto-classification can rely on them


## Phase 6 occupancy classification catalog

Implemented and CI-verified:
- Schedule 1 worklist upgraded to v2
- official TableRow structure split into practical classification identities
- first-level イ/ロ/ハ/ニ groups become separate classification entries
- current official corpus expectation: 22 Schedule rows / 35 classification entries
- classification identity/outcome copied mechanically from official Schedule 1 text
- applicability conditions remain blank and require Human legal authoring
- exact table row provision keys generated for citations
- legal structure parser v2 emits citable table_row provisions
- flat occupancy classification catalog output
- legal-change guard fails when reviewed Schedule shape changes
- main push automatically rebuilds the official worklist/catalog from verified e-Gov artifact

Verified checkpoint:
- run: `37271737351` SUCCESS
- backend pytest: 110 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Next gate:
1. merge and run the official-corpus workflow on main
2. verify 22 rows / 35 entries and exact source hash
3. use the catalog to prepare Human-authored occupancy classification Draft Rules
4. do not approve Rules until conditions and exact source evidence are reviewed


## Phase 6 occupancy bulk artifact compatibility

Implemented on branch `phase6-occupancy-bulk-zip`; CI verification pending:
- Schedule 1 builder now supports loose XML and e-Gov bulk ZIP sources
- bulk ZIP resolution uses all_law_list.csv and exact law-title match
- exact law ID is resolved before selecting the current XML
- target XML title is revalidated after extraction
- no full bulk archive extraction is required
- regression test reproduces the verified e-Gov artifact layout

This fixes the first real official-corpus failure where the Actions artifact contained the nationwide bulk ZIP rather than loose XML files.


## Phase 6 official Schedule 1 verified catalog

Verified against the real e-Gov national-law artifact:
- workflow run: `37272303236` SUCCESS
- artifact: `occupancy-classification-worklist` (artifact ID `11329130740`)
- law title: 消防法施行令
- law number: 昭和三十六年政令第三十七号
- target: 別表第一
- official source XML SHA-256: `245b01995baddd226f5a29dfb08ee7d7e95737be601072a264f2d1a07735a5bb`
- Schedule rows: 22
- practical classification entries: 35
- flat catalog entries: 35
- sample verified codes: （一）イ, （一）ロ, （二）イ, （二）ロ, （二）ハ, （二）ニ, （三）イ, （三）ロ

The catalog contains official classification identity and text only.
Applicability conditions remain Human-authored.

## Phase 6 occupancy authoring skeleton import

Implemented and CI-verified:
- official occupancy catalog dry-run/apply importer
- exact target law ID/title verification
- source XML SHA must match stored LegalSourceDocumentVersion
- legal structure parser v2 is required
- exact `table_row` LegalProvision is required
- catalog official text must be present in the cited row provision
- pending LegalRuleDraftCandidate skeleton creation
- proposed classification identity/outcome is imported
- proposed_conditions remains empty by design
- exact row citation is attached automatically
- idempotent candidate fingerprint
- public arbitrary Draft creation rules remain unchanged
- existing Human review gate rejects empty conditions
- promoted Rule Version still requires separate Human approval

Verified checkpoint:
- run: `37272900566` SUCCESS
- backend pytest: 113 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Next gate:
1. ensure the stored official source version is restructured with legal-structure-v2
2. import the verified 35-entry catalog
3. Human-author applicability conditions for each pending skeleton
4. review/promotion/approval remain separate Human gates


## Phase 6 legal restructure / occupancy readiness

Implemented and CI-verified:
- reusable `legal_structure_service.structure_legal_version`
- CLI and API share the same structuring implementation
- legal document Version restructure API
- expected source SHA-256 conflict protection
- current-parser no-op behavior unless force=true
- legal-structure-v2 table_row generation
- existing provision diff / impacted Rule evidence preserved
- occupancy catalog readiness API
- readiness checks exact source SHA, parser version, entry validity, table_row existence and official-text match
- readiness reports existing pending/terminal skeleton counts and would-insert count
- E2E covers unparsed -> readiness blocked -> parser v2 restructure -> readiness PASS -> skeleton import

Verified checkpoint:
- run: `37275726652` SUCCESS
- backend pytest: 114 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Target production flow:
1. identify the stored 消防法施行令 Version matching official catalog SHA
2. restructure that Version with legal-structure-v2
3. run occupancy catalog readiness
4. require ready=true and 35 exact provision matches
5. import the verified 35 pending authoring skeletons
6. Human-authored applicability conditions remain required before review/promotion/approval


## Phase 6 occupancy authoring workbench

Implemented and CI-verified:
- official 35-entry occupancy authoring Worklist API
- classification code / label / official row citation / current conditions visible in one response
- condition state: blank / valid / invalid
- allowed condition fields are restricted to consultation facts the system can actually collect
- bulk condition authoring supports Dry-run and atomic Apply
- optimistic version checks per Draft
- duplicate Draft IDs in one bulk request are rejected
- one invalid item blocks the whole Apply
- classification identity, outcome, citations, review status and approval status cannot be changed by bulk condition authoring
- occupancy Rule coverage engine tracks 35 unique classifications
- coverage requires verified catalog batch-size marker
- coverage requires valid conditions for all 35
- coverage requires promoted Rule citations to still be present in the same source Version
- coverage requires all 35 Rule Versions to be Approved, active and effective
- drawing consultation surfaces an explicit coverage warning until coverage_complete=true
- E2E covers atomic bulk authoring and 35/35 Approved coverage completion

Verified checkpoint:
- run: `37276843143` SUCCESS
- backend pytest: 116 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Safety:
- Workbench accelerates Human authoring but does not generate legal applicability conditions
- Rule review, promotion and approval remain separate Human gates
- partial Rule coverage never presents itself as a complete automatic classification system


## Phase 6 occupancy classification regression gate

Implemented and CI-verified:
- Migration 032 regression test case / run persistence
- Human-authored regression test cases with Draft -> Review/Reject workflow
- reviewed cases require exactly one expected classification code
- reviewed cases may use only consultation facts supported by the occupancy condition engine
- Draft/rejected cases are excluded from regression runs
- regression evaluates current Human-authored conditions across all reviewed cases
- exact-match PASS, missed expected classifications, unexpected matches and ambiguous multi-hit cases are reported
- exact duplicate condition groups mapping to different classification codes are reported
- regression run result is SHA-256 idempotent and persisted
- PASS result still requires separate Human acceptance
- failed/stale runs cannot be accepted
- authoring-condition fingerprint is stored in each run
- reviewed test-suite fingerprint is stored in each run
- any condition change invalidates the accepted regression gate
- any reviewed regression case add/change invalidates the accepted regression gate
- occupancy Rule coverage_complete now requires a current Human-accepted passing regression run in addition to 35/35 Approved Rules
- E2E covers 35/35 Approved -> incomplete without regression -> PASS+Human accept -> complete -> reviewed case change -> incomplete
- E2E covers ambiguous double-hit -> regression FAIL -> Human acceptance blocked

Verified checkpoint:
- run: `37279357089` SUCCESS
- backend pytest: 117 passed
- Migration 032 parser smoke: PASS
- frontend JavaScript syntax: PASS

Safety:
- regression cases and expected answers are Human-reviewed truth, not AI-generated truth
- regression acceptance does not modify Rule conditions or legal classifications
- current fingerprints prevent reuse of stale validation evidence


## Phase 6 equipment requirement authoring batch

Implemented and CI-verified:
- Migration 033 equipment requirement authoring batch persistence
- official core legal Worklist batch SHA-256 binding
- equipment_requirement candidate extraction from the verified Worklist
- Human review candidates are linked to an immutable batch
- batch import supports Dry-run / Apply
- source provision content SHA-256 is stored per linked candidate
- Human `ignored` candidates count as correctly processed non-Rules
- Human `reviewed` candidates remain incomplete until Rule Draft handoff
- `drafted` candidates become terminal only when the Draft is Human-rejected or promoted to an Approved/effective Rule with valid source citation
- source hash drift immediately invalidates coverage
- drawing consultation reports an explicit equipment Rule coverage warning while the batch is incomplete
- CLI added for offline/production batch import

Verified checkpoint:
- run: `37289599466` SUCCESS
- backend pytest: 118 passed
- Migration 033 parser smoke: PASS
- frontend JavaScript syntax: PASS

Verified official Worklist evidence from run `37271954544`, artifact `11328598413`:
- artifact digest: `sha256:b1364930c7acd6d74804cf2e67fcc65d889a94cfb715242b6c503ba55db00805`
- full core authoring Worklist items: 7,854
- requirement lane items: 1,602
- equipment_requirement candidates: 794
- largest equipment candidate sources:
  - 消防法施行規則: 423
  - 消防法施行令: 205
  - 危険物の規制に関する規則: 60
  - 消防法: 42
  - 大島地区消防組合火災予防条例: 38

Coverage semantics:
- 794 is the current verified candidate count, not a legal Rule count.
- irrelevant/noise provisions must be Human-ignored rather than auto-promoted.
- a future rebuilt Worklist receives a different batch SHA and must be reviewed separately.
- equipment Rule coverage_complete is never inferred merely from the number of Approved Rules.

Target flow:
1. import verified equipment_requirement Worklist batch
2. Human process every linked review candidate
3. relevant candidates -> Rule Draft
4. irrelevant candidates -> ignored
5. Drafts -> Human rejected or promoted
6. promoted Rule Versions -> Human Approved and effective
7. require zero stale source hashes and all batch candidates processed
8. only then treat equipment requirement Rule coverage as complete for that batch


## Phase 6 equipment requirement regression gate

Implemented and CI-verified:
- Migration 034 equipment requirement regression case/run persistence
- Human-authored equipment regression cases support zero, one, or multiple expected equipment type codes
- reviewed case inputs are restricted to facts the drawing consultation equipment engine can evaluate
- expected equipment codes must exist in active EquipmentType master
- only Human-reviewed cases participate in runs
- regression executes the same effective Approved `equipment_requirement` Rule engine used by consultations
- required equipment is compared as an exact set
- missing equipment is reported as under-requirement
- unexpected equipment is reported as over-requirement
- matched Rule Version / citations / condition evidence are preserved per case
- regression run result is SHA-256 idempotent and persisted
- PASS still requires separate Human acceptance
- effective equipment Rule engine is fingerprinted across all active/effective Approved equipment_requirement Rules
- reviewed test suite is separately fingerprinted
- Rule changes invalidate previous accepted regression evidence
- reviewed test case changes invalidate previous accepted regression evidence
- authoring batch coverage and regression coverage are separate:
  - `authoring_coverage_complete`: all official batch candidates Human-processed with valid source evidence
  - `coverage_complete`: authoring complete plus a current Human-accepted passing regression
- E2E covers Approved authoring complete -> regression missing -> incomplete -> PASS + Human accept -> complete -> source drift -> incomplete
- E2E covers over-requirement -> regression FAIL -> Human acceptance blocked

Verified checkpoint:
- run: `37290673265` SUCCESS
- backend pytest: 119 passed
- Migration 034 parser smoke: PASS
- frontend JavaScript syntax: PASS

Safety:
- regression expected equipment sets are Human-reviewed truth
- zero equipment is a valid expected set for negative cases
- an old PASS cannot survive a current Rule-set or reviewed-test-suite change
- equipment consultation continues to warn while final equipment Rule coverage is incomplete


## Phase 6 equipment placement legal worklist

Implemented and CI-verified:
- deterministic legal relevance scanner upgraded to `fire-legal-relevance-v3`
- new `equipment_placement` review category
- placement candidates require co-occurrence of a supported equipment term and a placement-specific term
- placement-specific terms include walking/horizontal distance, placement location/position, visibility, entrance proximity, floor-height and interval expressions
- equipment term without placement evidence is not classified as equipment_placement
- generic placement wording without an equipment term is not classified as equipment_placement
- `table_row` LegalProvisions are now included in verified authoring Worklists
- core authoring config upgraded to `phase6-core-sources-v2`
- separate `placement_rules` authoring lane added
- `equipment_placement` is importable into the existing Human legal review queue
- Human-reviewed placement candidates can create Rule Drafts using the existing review -> Draft -> review -> promote -> approve gates
- regression tests cover co-occurrence guard and table-row extraction

Verified checkpoint:
- run: `37291518081` SUCCESS
- backend pytest: 122 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Next gate:
1. merge to main
2. rebuild the verified official core authoring Worklist
3. inspect the real equipment_placement candidate count and source distribution
4. bind that official placement Worklist to an immutable batch
5. Human process all placement candidates
6. add placement Rule regression before declaring placement coverage complete


## Phase 6 equipment placement authoring batch

Implemented and CI-verified:
- Migration 035 equipment placement authoring batch persistence
- official placement Worklist batch SHA-256 binding
- equipment_placement Human review candidates linked to an immutable batch
- Dry-run / Apply batch importer and CLI
- per-candidate source provision content SHA-256
- Human ignored placement candidates count as correctly processed non-Rules
- reviewed placement candidates remain incomplete until Rule Draft handoff
- drafted placement candidates become terminal only when the Draft is Human-rejected or promoted to an Approved/effective Rule with valid source citation
- source hash drift immediately invalidates placement authoring coverage
- drawing consultation exposes an explicit placement Rule coverage warning while incomplete
- placement authoring coverage and placement regression coverage are separated

Verified checkpoint:
- run: `37310422832` SUCCESS
- backend pytest: 123 passed
- Migration 035 parser smoke: PASS
- frontend JavaScript syntax: PASS

Verified official Worklist evidence from run `37291827627`, artifact `11337265684`:
- artifact digest: `sha256:e85a10327047f60c37b08cee052cc7f50356fdd3611a0d2a5a273d093e3c67ba`
- placement_rules lane items: 61
- equipment_placement candidates: 61
- source distribution:
  - 消防法施行規則: 39
  - 消防法施行令: 10
  - 危険物の規制に関する規則: 7
  - 大島地区消防組合火災予防条例: 5

Coverage semantics:
- 61 is the current verified candidate count, not a legal Rule count.
- irrelevant/noise provisions are Human-ignored rather than auto-promoted.
- relevant provisions must pass Draft -> Human review -> promote -> Human approve before authoring coverage can complete.
- even complete authoring coverage does not set final coverage_complete until a placement regression gate exists and is Human-accepted.
- a rebuilt official Worklist receives a new batch SHA and must be processed separately.

Next gate:
1. merge batch tracking to main
2. import/process the official 61-candidate placement batch
3. add Human-reviewed placement regression cases
4. test Rule constraints/room targeting/marker generation
5. require a current Human-accepted regression PASS before placement coverage_complete=true


## Phase 6 equipment placement regression gate

Implemented and CI-verified:
- Migration 036 equipment placement regression case/run persistence
- drawing consultation and regression now share one placement engine
- Human-reviewed regression cases include:
  - input snapshot / confirmed classification
  - Human-reviewed room geometry and room-use labels
  - target equipment codes
  - expected placement state
  - expected room refs
  - expected Rule constraint payloads
- placement regression validates:
  - placement_candidate / manual_with_constraints / approved_rule_missing state
  - exact target room refs
  - generated Marker center against Human-reviewed room geometry
  - exact Rule constraint payloads
- regression run preserves matched placement Rule/citation evidence
- PASS still requires separate Human acceptance
- placement Rule engine fingerprint is bound to every accepted run
- reviewed placement test-suite fingerprint is bound to every accepted run
- any Approved/effective placement Rule change invalidates old accepted evidence
- any reviewed regression case add/change invalidates old accepted evidence
- final placement coverage requires:
  1. official placement batch authoring coverage complete
  2. current regression PASS
  3. Human acceptance of that current PASS
Verified checkpoint:
- run: `37317066828` SUCCESS
- backend pytest: 123 passed
- Migration 036 parser smoke: PASS
- frontend JavaScript syntax: PASS

- E2E covers:
  - correct room targeting + Marker center + constraint match -> PASS
  - Human acceptance -> placement coverage complete
  - reviewed case added -> previous acceptance becomes stale
  - wrong expected room -> Marker mismatch -> regression FAIL
  - failed run cannot be Human-accepted
  - source provision hash drift invalidates authoring/final coverage

Safety:
- Regression truth is Human-reviewed.
- Regression does not alter Rule conditions, placement constraints or drawing annotations.
- A stale PASS cannot survive Rule, room-test or source-provision changes.


## Phase 6 consultation response package

Implemented and CI-verified:
- Migration 037 persists reviewed consultation response payload/SHA and review notes
- one response package combines:
  - Human-confirmed occupancy classification
  - current required equipment from effective Approved Rules
  - equipment already present in the Human-reviewed drawing annotation
  - add_candidate / present_in_drawing / existing_unmatched actions
  - current placement states, constraints and overlay markers
  - exact legal citations and current provision content hashes
  - unresolved questions
  - occupancy / equipment-requirement / placement Coverage gates
- response computation re-evaluates current Approved Rules instead of replaying stale stored equipment results
- equipment missing from the drawing but required by current Rules is surfaced as `add_candidate`
- existing equipment not matched by current requirement results is never auto-marked for removal
- answer states:
  - blocked: prerequisite classification/annotation missing
  - partial: answer can be shown but legal Coverage or required inputs are incomplete
  - review_ready: all three current legal Coverage gates pass and no unresolved blocker remains
  - reviewed: Human reviewed the exact current response SHA
  - review_stale: a previously reviewed response no longer matches current Rule/source/annotation evidence
- Human response review is blocked unless `review_ready`
- reviewed response stores canonical SHA-256 evidence
- re-running equipment evaluation clears previous response review evidence
- annotation/version, legal citation hash, Rule output, Coverage accepted-run IDs and evaluation date contribute to the current response evidence
- E2E covers equipment-less drawing -> required add_candidate + room Marker -> partial response -> review blocked
- E2E covers review_ready -> Human review -> Annotation version change -> review_stale -> Human re-review

Verified checkpoint:
- run: `37318496981` SUCCESS
- backend pytest: 124 passed
- Migration 037 parser smoke: PASS
- frontend JavaScript syntax: PASS

Safety:
- a partial consultation result is never presented as a fully reviewed answer
- existing unmatched equipment is not interpreted as removable
- stale Human review cannot survive changes to current evidence
- legal Coverage completeness remains dependent on current Human-accepted regression evidence


## Phase 6 drawing consultation UI

Implemented and CI-verified:
- facility drawing review now exposes a dedicated Human Annotation / consultation workspace
- original drawing document preview
- image drawings support direct polygon room annotation on top of the original drawing
- room annotation captures Human room label, room-use code and floor number
- seeded AI room geometry remains a Draft until Human review
- empty manual Human Reference drafts are supported
- draft Annotation save / Human review flow
- reviewed Annotation can start a drawing consultation
- consultation input form covers the supported occupancy/equipment Rule facts
- classify action saves current answers then evaluates current Approved occupancy Rules
- Human can confirm one Rule-backed classification candidate
- manual classification remains available only through the backend Human-note gate
- confirmed classification can evaluate required equipment and placement candidates
- unified consultation response is rendered with:
  - classification
  - required/additional equipment actions
  - placement state
  - current coverage for classification / requirement / placement
  - unresolved questions
  - legal citations
  - response SHA-256
- response Human review button is shown only when backend says reviewable
- accepted placement markers are rendered over the original image drawing
- PDF originals remain viewable, but direct polygon Annotation is explicitly guarded to image originals in this slice
- frontend contract tests protect critical Human-gate/API wiring

Verified checkpoint:
- run: `37321895072` SUCCESS
- backend pytest: 126 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Safety:
- AI seed is never labeled as Human truth before review
- UI cannot bypass backend classification, Rule coverage or response-review gates
- equipment already present but unmatched is not presented as removable
- stale reviewed consultation responses continue to be surfaced by backend response state


## Phase 6 PDF drawing Human Annotation

Implemented on branch `phase6-pdf-annotation-preview`; CI verification pending:
- deterministic PDF page preview renderer using existing PyMuPDF dependency
- no new runtime dependency added
- PDF preview version: `drawing-pdf-preview-v1`
- PDF pages are rendered as bounded PNG previews with max dimension 2400px
- preview metadata API exposes page count and deterministic pixel dimensions
- page preview API returns PNG plus page number / dimensions / preview-version headers
- ETag is bound to source document SHA, page number, preview version and rendered dimensions
- image drawing preview metadata preserves original pixel coordinates
- drawing consultation UI now supports page navigation for multi-page PDF drawings
- PDF pages use the same SVG Human Annotation overlay used for image drawings
- room polygons persist the correct `page_no`
- Annotation `page_dimensions` are stored per page
- only current-page room polygons and equipment placement markers are drawn
- AI-seeded and manual Annotation flows preserve multi-page dimensions
- backend E2E covers:
  - two-page PDF detection
  - PNG render for page 1 and page 2
  - out-of-range page rejection
  - deterministic preview headers
  - image original pixel-space metadata
  - PDF-only page-preview route guard
- frontend contract test protects preview-info, page-preview, page navigation and page_no wiring

Safety:
- the original PDF remains the source document and is not overwritten
- rendered PNG is a derived preview only
- Human Annotation stores source page number and preview pixel dimensions
- AI output still does not become Human Reference without explicit review
