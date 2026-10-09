# PROJECT_STATE

更新日: 2026-10-09

## 最新の監査差分（main `f7b4058` 基準）

正本mainは `f7b4058c884454fed58f4cb1a02b931f8992f799`、tree `6bb7ae78e22daf9a0412a56a697d7d21cc82f45b`。PR79の車両権限再照合中の旧操作ロックと、PR80の財務確認・承認待ちから共通Work Queueへの接続を反映済み。PR80 exact-head [CI37864361725](https://github.com/haji84/-AI/actions/runs/37864361725) はbackend1213 passed/96 skipped、browser job72 passed、migration parser/JavaScript成功。独立した [main CI37865572873](https://github.com/haji84/-AI/actions/runs/37865572873) は本checkpoint時点で実行中。skipを成功と数えず、main成功を先取りしない。

分類は **Completed12 / Partial44 / Missing0 / External Gate1** を維持する。根拠・残要件は完成台帳D11/D12。人事通知取込と危険物Rule評価の未merge候補はmainの実装creditに含めない。下の9d6f86b基準と過去Phase説明は履歴で、最新の正本や完成判定へ読み替えない。

## 現在の完成状況（main `9d6f86b` 基準）

57章の現在地は [CURRENT_COMPLETION_LEDGER](docs/completion/CURRENT_COMPLETION_LEDGER.md) を参照。実装基準は `9d6f86b1c21e61b1df51eef058bf01b26e5c54e9`、tree `c3d4f2afa32bdf44b82c2fe62d183e63d678f7d0`。既存の全章baselineとPR67–72の記録を保持し、merge済みPR74（勤務Human操作の画面更新競合）、PR75（車両配属・履歴）、PR76（観測統計）、PR77（学習再読込競合）を追加した。**Completed 12 / Partial 44 / Missing 0 / External Gate 1**。章34はMissing→Partial、章23は基準baselineの独立配属・版/監査・現在配属/履歴の完了条件を満たしてPartial→Completed。章16・25・36はPartialを維持する。Missingが0でも重大Partialは残り、システム全体の完成・本番受入を意味しない。

PR75の最終head [CI37602962182](https://github.com/haji84/-AI/actions/runs/37602962182) とmerge後main f53084aの [CI37604792930](https://github.com/haji84/-AI/actions/runs/37604792930) は、backend1098 passed/88 skipped、browser job64件（実Chromium55＋Node/API9）、migration parser/JavaScript成功。PR76最終head cc743990の [CI37605645865](https://github.com/haji84/-AI/actions/runs/37605645865) はbackend1184 passed/95 skipped、browser job71件（実Chromium62＋Node/API9）、parser/JavaScript成功。PR76後のmain c1b491eも [CI37607563240](https://github.com/haji84/-AI/actions/runs/37607563240) で同じ1184/95・71件の成功を確認した。PR77最終統合head ee757220の [CI37606910763](https://github.com/haji84/-AI/actions/runs/37606910763) はbackend1198 passed/95 skipped、browser job71件（実Chromium62＋Node/API9）、parser/JavaScript成功で、現mainと同じtreeを持つ。**実装main 9d6f86bの [post-merge CI37609190838](https://github.com/haji84/-AI/actions/runs/37609190838) もbackend1198 passed/95 skipped、browser job71件（実Chromium62＋Node/API9）、parser/JavaScript成功**。これは9d6f86bの実行証拠であり、後続の文書・配布物commitで新たに実行した結果とは扱わない。配布物は別途、そのmanifest commit/tree・ハッシュ・展開後の起動を照合する。

車両は既存の「事案・車両」→「車両」→「新規登録」から追加できる。実フォームで追加した車両の配属・検索・履歴・監査・権限拒否まで検証した。章23の旧「配属未実装」は解消済み。配属の原本Document連携・取込/出力・横断検索拡張は共通基盤の章9/41/35に未完として残す。現在の章23分類は使用手順書のmerge前Partial表記より本ledgerを優先し、手順と制限は引き続き有効。[車両の使用手順](docs/completion/VEHICLE_ASSIGNMENT_VERIFICATION_20261007.md)。

「観測統計」は救急・事案/出動・車両運行の7指標、明示した業務日/既定の`Asia/Tokyo`時刻帯、不変の保存値、Human確認・置換履歴、汎用CSV/XLSXを提供する。確認後も網羅性はunknownで、0件と完全性・利用不可を混同しない。財務/通貨、過去母数、年度/前年比較、残りのsource、網羅性宣言、正式原本様式は内部未完。[観測統計の使用手順](docs/completion/OBSERVED_STATISTICS_VERIFICATION_20261007.md)。PR77の学習再読込修復は9d6f86bとしてmerge済み。遅い旧応答によるHuman評価画面の上書きを防ぐ修復であり、API・権限・モデル・Human判断の意味は変えず、章37等の状態もPartialを維持する。

[STATUS_CHANGELOG](docs/completion/COMPLETION_STATUS_CHANGELOG.md) に分類根拠、[COMPLETION_BASELINE_20261007](docs/completion/COMPLETION_BASELINE_20261007.md) にc1b684c全57章Evidenceを保存。旧MASTER_FEATURE_MATRIXと以下のPhase/過去集計は履歴として保持する。対象物dashboardの再現済み情報露出はPR70で修復済み。危険物のHuman証拠確認は法令適合判定ではなく、Rule評価は未実装。

章46のmodule無効時の履歴閲覧・出力・参照をどう扱うかは明示方針の決定待ち。新規業務の直接APIが既存flagで一貫して止まる状態ではない。履歴参照を一律に不具合と断定せず、方針と実行制御の残差を区別する。

未照合のRun A統計/Run B勤務等のcheckpointは原本を保持する。PR76は新たな限定実装で、旧Run Aの復旧ではない。mainを正本に、既存branch/PR/実装/migrationとの衝突を確認して残要件を小さく実装できる。予約051は保持し、配属053・観測統計054は既存SQLを変更せず追加した。未照合を「復旧済み」「消失」と扱わず、恒久的な開発禁止にも扱わない。後続のローカル変更にはこの集計で実装creditを付けない。

central server・dynamic worker・offline requeue・OwnerRecoveryVault等は後続の設計照合事項で、実装済み機能ではない。通常のサービス運営者向け状態/容量/最終成功情報と緊急復元は別の権限経路として整理し、登録・鍵管理・privacy・policyは未解決。本部の通常記録へのアクセスや導入の権限を与えるものではなく、現在の本部別DB/実行環境/原本分離を維持する。

## 完成タスクの現在地（2026-10-06再監査・履歴）

main922d292c（PR61、議会・照会統合後、main CI37523158483 SUCCESS）を正本として確認。小さなPRの完了はシステム完成を意味しない。
- PR41/43: 共通コード＋本部別DB/実行環境/原本/backupを固定。UUID照合、専用構成生成、PostgreSQL移行/復元/役割境界をCI検証済み。
- PR44: 組織・職員・人事履歴・有効日権限・Humanアカウント管理・パスワード履歴/変更・セッション失効・監査閲覧。PR CI302成功、実ブラウザ1成功。main CI37476512786 SUCCESS。
- RunB PR40/42/46の救急・事案/出動・車両・業務資産/在庫/貸出/保守を維持。main CI37482634204 SUCCESS。残り業務モジュールはRunBの連続実装対象。
- PR45の署名付き閉域法令更新は実装・merge・main CI37480963172 SUCCESS済み（正式判定はHuman Gate）。PR47の自動backup・保守排他はmerge済み（main CI37484877143 SUCCESS）。PR52学習基盤はmerge済み、PR CI390/backend＋3/browser成功、main CI37490791793 SUCCESS。本番trustの選定、法令正式承認、実図面Human正解/実モデル評価、実LAN受入はExternal Gate。
- 独立したMissing/Partial（学習、PR54で実装・merge済みの正式v2.0 password expiry、残る共通/図面機能、全マニュアルとrelease一式）を継続し、完成成果物と未完Gateの照合で判定する。

- PR59: 財務/旧契約の共通mutation guard、原本downloadのsession再照合、権限喪失時の状態消去、勤務画面の遅延応答競合を修復。PR CI37513136938/main CI37513897759 SUCCESS。違反・改善措置049はPR60でmain反映済み。

- PR60: 原本・現行一次資料に結び付く違反候補、Human確認/正式確認、措置、改善履歴/検証/完了を統合。PR CI37519910509 backend605件/browser8件成功、main CI37520767373 SUCCESS。AI候補producer接続は内部Partial。
- PR61: 既存議会・照会実装をmainへ統合。Migration050、根拠と正確な数値、Human確認/承認、権限内の検索・交換・原様式出力。候補採用中/画面再表示の操作競合を修復。PR CI37522253547 backend639件/browser9件成功、main CI37523158483 SUCCESS。共通の本番ローカルモデルworker/統計dashboard接続は内部Partial。

実コードとの照合とEvidence: docs/COMPLETION_AUDIT.md / docs/completion/RUN_A_STATUS.md / RUN_B_STATUS.md。
過去Phase見出しは履歴として保持し、完成判定の停止条件にはしない。

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


## Phase 6 PDF visual Annotation

Implemented and CI-verified:
- drawing preview metadata API
- original image documents remain direct visual previews
- PDF drawings are rendered page-by-page to PNG with existing PyMuPDF dependency
- adaptive PDF render scale caps longest preview edge at 3200px and scale at 2x
- no new browser/CDN dependency is introduced
- password-protected PDFs are explicitly rejected for visual preview
- multi-page PDF page count and deterministic preview dimensions are exposed to the UI
- page preview endpoint supports authenticated image/PDF drawing rendering
- drawing workspace page selector added for multi-page drawings
- Human room polygons are stored with the selected page_no
- page_dimensions are stored independently per page
- room overlays and equipment placement markers are filtered to the current page
- PDF and image drawings now use the same visual Human Annotation workflow
- two-page real PDF bytes regression verifies:
  - page count
  - deterministic rendered PNG dimensions
  - PNG response
  - page-specific preview dimensions
  - out-of-range page rejection
- frontend contract verifies PDF page Annotation wiring

Verified checkpoint:
- run: `37323108939` SUCCESS
- backend pytest: 127 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Safety / resource controls:
- preview rendering is read-only and never rewrites the original drawing
- managed storage path confinement is rechecked before rendering
- adaptive render size limits large-format PDF memory growth
- original Document SHA remains the authoritative source identity


## Phase 6 house-plan-001 Geometry Reference Draft

Implemented and CI-verified:
- existing supplied residential reference remains bound to source SHA-256 `2df43a8f5cebe48f2a55ae8968714319ca05491088d98a1e6038fd0b10aa26b6`
- 12 first-floor room/zone Geometry Drafts added:
  - UB
  - トイレ
  - 洗面脱衣室
  - 玄関
  - ホール
  - WIC
  - 主寝室
  - タタミコーナー
  - L
  - D
  - K
  - P
- geometry quality is separated into:
  - strict_wall_bounded
  - circulation_approx
  - open_plan_approx
  - service_area_approx
- visible printed room-area values are preserved for 主寝室 / タタミコーナー / L / D / K
- Reference remains `pending_human_acceptance`
- Human review checklist added at `benchmarks/phase6/reference/house-plan-001.review.md`
- drawing Benchmark now refuses Human Reference formats unless:
  - `reference_status=human_accepted`, and
  - when `human_gate.required=true`, `human_gate.accepted=true`
  - or the Reference is exported from a reviewed Human Annotation set
- plain synthetic unit-test fixtures without Human Reference format are unaffected
- E2E/unit coverage verifies pending Draft rejection and accepted/reviewed Reference acceptance

Human Gate:
- the 12 polygons are a Draft, not benchmark truth
- open-plan/circulation boundaries require explicit Human confirmation/correction
- first real Geometry Baseline remains blocked until this Reference is Human-accepted and a Local Vision Hypothesis is produced

Verified checkpoint:
- run: `37381610546` SUCCESS
- backend pytest: 132 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS


## Phase 6 DrawingAnalysis benchmark Hypothesis export

Implemented and CI-verified:
- `DrawingAnalysis` AI results can be exported as `fire-ai-drawing-hypothesis-v1`
- export requires:
  - `analysis_method=ai`
  - status `analyzed` or `reviewed`
  - non-empty `model_version`
- export contains:
  - source Document ID / filename / SHA-256 / MIME type
  - DrawingAnalysis ID/version/status/model
  - page count / confidence / summary / evidence
  - elements
  - equipment candidates
  - Facility fact candidates
- element references are stable DrawingElement IDs, so equipment/fact links remain intact
- repeated export of an unchanged DrawingAnalysis is deterministic
- pending AI analyses cannot be exported as benchmark Hypothesis
- manual analyses cannot be exported as AI benchmark Hypothesis
- drawing Benchmark now rejects Reference/Hypothesis source SHA-256 mismatch
- drawing workspace exposes direct links to:
  - reviewed Human Reference JSON
  - analyzed AI Hypothesis JSON
- house-plan-001 Baseline manifest template added
- hypothesis directory workflow documented

Target Baseline flow:
1. Human confirms/corrects house-plan-001 Geometry Draft
2. mark the Reference Human-accepted
3. run Local Vision on the same source drawing
4. export `/benchmark-hypothesis`
5. verify source SHA matches `2df43a8f5cebe48f2a55ae8968714319ca05491088d98a1e6038fd0b10aa26b6`
6. save as `benchmarks/phase6/hypothesis/house-plan-001.hypothesis.json`
7. run `house-plan-001.baseline-manifest.template.json`
8. persist Benchmark Run and send it through Human Baseline review

External/Human gate remains:
- house-plan-001 Reference is still pending Human acceptance
- real Local Vision Hypothesis #001 has not yet been produced

Verified checkpoint:
- run: `37382418987` SUCCESS
- backend pytest: 135 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS


## Phase 6 Annotation editing / automatic area calculation

Implemented and CI-verified:
- existing Draft room/zone polygons can be selected and edited by dragging vertices
- selected polygon vertices can be added or deleted with a minimum 3-vertex guard
- existing region label / use code / floor can be corrected manually
- new regions can be added as either:
  - `room`
  - arbitrary `zone`
- browser immediately recalculates polygon area/perimeter after geometry edits
- backend is authoritative and overwrites any client-supplied derived area values
- canonical backend calculation: polygon shoelace v1
- stored per region:
  - area_px2
  - perimeter_px
  - area_m2
  - perimeter_m
  - calibration status
  - meters_per_pixel
- page scale calibration uses Human-selected two points plus known real distance in meters
- calibration is page-specific and is not reused across PDF pages
- without calibration:
  - px² remains available
  - m² remains null
  - UI explicitly marks scale as unresolved
- create / AI seed / Draft update / Human review all pass through server-side geometry recalculation
- invalid calibration is rejected
- reviewed `room` and `zone` regions require label or use code
- Human Reference export naturally includes derived geometry and page calibration evidence
- backend tests cover:
  - 100x50px -> 5000px²
  - 100px=2m calibration -> 2.0m²
  - geometry edit -> automatic 4.0m² recalculation
  - arbitrary zone area
  - invalid calibration rejection
  - server overwrites fake client-derived values
- frontend contract covers:
  - vertex drag
  - vertex add/remove
  - manual metadata correction
  - two-point calibration
  - automatic area display
  - arbitrary zone creation

Safety:
- metric area is never invented from raw pixel dimensions alone
- browser-calculated area is feedback only; backend recalculation is authoritative
- reviewed Annotation cannot be edited through the Draft edit API
- a geometry or calibration change changes the resulting Human Reference evidence and downstream Benchmark SHA

Verified checkpoint:
- run: `37386057958` SUCCESS
- backend pytest: 143 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS


## Phase 6 Human Reference Draft import

Implemented and CI-verified:
- Human Reference Draft JSON can be imported directly into a DrawingAnalysis as an editable Annotation
- supported format prefix: `fire-ai-drawing-human-reference...`
- source Document SHA-256 must exactly match the DrawingAnalysis source
- bad/mismatched source SHA is rejected
- coordinate space is restricted to pixel/normalized
- imported Reference status is never trusted as current Annotation review status
- even a source Reference marked `human_accepted` is imported as `draft`
- imported Geometry passes through server-authoritative area recalculation
- fake client-derived area values are overwritten
- existing room/zone edit tools remain available after import:
  - vertex drag
  - vertex add/remove
  - room/zone add/remove
  - label/use/floor correction
  - scale calibration
  - px² / m² automatic recalculation
- import provenance is stored in Annotation payload under `reference_import`
- UI file picker added to the Human Annotation workspace
- existing Annotation and no-Annotation states can both import another Draft
- E2E covers source-bound import, forced Draft status, automatic area recalculation, later Human Review/export, source-SHA mismatch rejection, and coordinate-space rejection
- frontend contract protects Reference Draft import wiring

Verified checkpoint:
- run: `37388194605` SUCCESS
- backend pytest: 146 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Target house-plan-001 flow:
1. upload/open the same source drawing whose SHA is `2df43a8f5cebe48f2a55ae8968714319ca05491088d98a1e6038fd0b10aa26b6`
2. open Human Annotation workspace
3. import `benchmarks/phase6/reference/house-plan-001.reference.json`
4. manually correct the 12 Draft regions
5. add/delete arbitrary regions as needed
6. calibrate scale using a known dimension
7. verify automatic m² results
8. Human Review the Annotation
9. export reviewed Human Reference JSON
10. use that reviewed export for the first real Benchmark

Safety:
- source mismatch blocks import
- imported acceptance metadata is provenance only
- Human review remains mandatory before benchmark truth export


## Phase 6 Drawing Baseline readiness

Implemented and CI-verified:
- per-DrawingAnalysis Baseline readiness evaluator
- readiness checks:
  - source drawing Document exists
  - Human-reviewed Annotation exists
  - reviewed Reference contains at least one Geometry element
  - AI DrawingAnalysis is exportable as a benchmark Hypothesis
  - AI model_version is present
  - AI Hypothesis source SHA-256 matches the source drawing Document
- Geometry Baseline readiness and metric-area readiness are separated
- Geometry can be READY even when scale calibration is still missing
- metric-area readiness additionally requires calibration on every page used by Reference Geometry
- readiness output includes:
  - selected reviewed Annotation/version
  - draft/reviewed Annotation counts
  - Reference element/fact/equipment counts
  - Hypothesis element/fact/equipment counts
  - source SHA match
  - used/calibrated/uncalibrated pages
  - explicit blockers and warnings
  - direct Human Reference / AI Hypothesis endpoints
- multiple reviewed References produce an explicit warning; latest reviewed Reference is selected
- E2E covers:
  1. no Reference + pending AI -> BLOCKED
  2. AI analyzed + Human Reference reviewed -> Geometry READY
  3. no scale calibration -> metric-area not ready
  4. calibrated reviewed Reference -> metric-area READY
- drawing workspace renders a Baseline Readiness card with Geometry / area state and blockers

Verified checkpoint:
- run: `37391839458` SUCCESS
- backend pytest: 148 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Safety:
- readiness never marks a Draft Annotation as Human Reference truth
- metric area is not treated as ready without page calibration
- source mismatch remains a hard blocker
- readiness does not itself run or accept a Benchmark


## Phase 6 in-app Drawing Baseline run

Implemented and CI-verified:
- drawing Benchmark scoring core extracted to `backend/app/drawing_benchmark_core.py`
- CLI and backend API now use the same scoring implementation
- existing CLI behavior is preserved through a thin wrapper
- Human Reference export builder is shared between:
  - existing `/benchmark-reference` endpoint
  - in-app Baseline runner
- in-app Baseline run endpoint:
  - `POST /drawing-analyses/{analysis_id}/baseline-run`
- Baseline run requires:
  - matching expected DrawingAnalysis version
  - `geometry_baseline_ready=true`
  - Human-reviewed Reference
  - exportable AI Hypothesis
  - same source drawing SHA
- run builds canonical in-app manifest evidence containing:
  - DrawingAnalysis ID/version
  - Annotation ID/version
  - source Document ID/SHA
  - model version
  - IoU threshold
- Reference/Hypothesis payloads receive canonical JSON SHA-256 evidence
- Benchmark result is persisted directly to `drawing_benchmark_runs`
- identical evidence is idempotent and reuses the existing Run instead of duplicating it
- dataset label does not alter result evidence identity
- newly persisted Run remains `pending`
- Baseline acceptance still requires the existing separate Human Benchmark Review gate
- drawing workspace:
  - shows a `この図面でBaseline実行` button only when Geometry readiness passes
  - shows Geometry F1 / mean IoU / Fact F1
  - clearly labels Run as pending separate Human review
- E2E covers:
  - not-ready Baseline rejection
  - DrawingAnalysis version conflict
  - ready Baseline execution
  - Geometry F1 = 1.0 fixture
  - Fact F1 = 1.0 fixture
  - canonical manifest/result SHA
  - idempotent repeat execution
  - one persisted Benchmark Run
  - separate Human Baseline acceptance
- regression test verifies CLI and API scorer parity through the shared core

Verified checkpoint:
- run: `37392710772` SUCCESS
- backend pytest: 151 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Safety:
- in-app execution cannot bypass Human Reference review
- in-app execution does not auto-accept a Baseline
- source drawing mismatch remains a hard error
- old Benchmark Runs remain immutable evidence when Annotation/AI results change


## Phase 6 Drawing Baseline Human Review UI

Implemented and CI-verified:
- drawing workspace reloads recent drawing Benchmark Runs
- only in-app Runs for the current DrawingAnalysis are shown
- Run history remains visible after reopening the workspace
- current Run shows:
  - Geometry F1
  - mean IoU
  - Fact F1
  - review status / Human decision
  - optional review note
- pending Baseline Runs expose explicit Human actions:
  - accepted_baseline
  - rejected_baseline
- Human decision uses the existing optimistic-concurrency Benchmark Review API
- Human review note is collected at decision time
- reviewed Runs no longer show review buttons
- accepted Baseline is visually distinguished from pending/rejected Runs
- selecting an older Run never changes current DrawingAnalysis/Annotation evidence
- Baseline execution and Baseline acceptance remain separate actions

Verified checkpoint:
- run: `37393291076` SUCCESS
- backend pytest: 152 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Safety:
- no Baseline is auto-accepted after a good F1/IoU score
- Human can explicitly reject a technically passing Baseline
- Run history remains immutable evidence while current Annotation/AI results evolve
- optimistic version checks prevent stale review writes


## Phase 6 drawing area accuracy Benchmark

Implemented and CI-verified:
- matched Human Reference / AI Geometry pairs now receive area-accuracy scoring
- pixel-area metrics work without scale calibration
- calibrated metric-area metrics are emitted only when Human Reference page calibration exists
- per matched region:
  - Reference area
  - AI area
  - absolute error
  - relative error
- aggregate metrics:
  - mean absolute error px²
  - mean relative error
  - 5%以内率
  - 10%以内率
  - calibrated mean absolute error m²
- metric-area output is N/A without Human scale calibration
- Area scoring uses the same one-to-one Geometry match as IoU evaluation
- unmatched Reference/AI regions remain Geometry FN/FP and are not hidden by area metrics
- multi-drawing area metrics use micro aggregation by scored matched region
- Drawing Benchmark comparison API now compares:
  - area MAE m² (lower better)
  - mean relative error (lower better)
  - 10%以内率 (higher better)
- Baseline workspace displays:
  - 面積 MAE㎡
  - 平均相対誤差
  - 10%以内率
- tests cover:
  - 5000px² Reference vs 4500px² AI
  - 100px=2m calibration -> 2.0m² vs 1.8m²
  - 0.2m² absolute error
  - 10% relative error
  - N/A metric area without calibration
  - multi-drawing micro aggregation
  - Benchmark Run A/B area comparison

Safety:
- metric area is never inferred without Human calibration
- area accuracy does not replace Geometry Precision/Recall/F1
- production area-accuracy thresholds remain a Human Gate after the first real Baseline

Verified checkpoint:
- run: `37394061405` SUCCESS
- backend pytest: 157 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS


## Phase 6 floor / region area summary

Implemented and CI-verified:
- server-authoritative `geometry_summary` rebuilt on every Annotation create / seed / update / review
- browser live-preview summary rebuilt during vertex editing
- per-floor summary:
  - region count
  - room count
  - arbitrary-zone count
  - annotated area px² total
  - calibrated annotated area m² total
  - calibrated / uncalibrated region counts
  - metric-area completeness
- interior-overlap warning detection
- adjacent regions sharing only a boundary are not warned
- different pages are never cross-compared
- explicitly different floors on the same page are not treated as overlapping
- fake client-supplied summary values are overwritten by backend recalculation
- UI shows floor totals and overlap warnings immediately
- overlap warnings remain Human review aids rather than automatic rejection

Verified checkpoint:
- run: `37411992860` SUCCESS
- backend pytest: 163 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS

Safety:
- annotated region total is explicitly not represented as statutory floor area
- m² remains unavailable for uncalibrated regions
- overlap warning avoids silently double-counting likely overlapping regions
- backend remains authoritative over all derived area/summary values


## Phase 6 Human floor-area target comparison

Implemented and CI-verified:
- optional Human floor-area targets stored in Annotation payload
- target schema:
  - floor_number
  - target_area_m2
  - label/source/note
  - comparison_basis=rooms_only
- only one target per floor
- target area must be > 0
- server validates targets and rebuilds comparison on every save/review
- browser recalculates the same comparison live while Geometry is edited
- comparison uses calibrated `room` area only
- arbitrary `zone` area is excluded from known-floor-area comparison
- comparison outputs:
  - target area m²
  - measured room-area m²
  - difference m²
  - difference %
  - comparable / uncalibrated / missing-floor state
- Human UI can register or clear a target for a floor
- Human Reference Draft import derives targets automatically from `source_observations.floor_area_m2`
- house-plan-001 therefore carries:
  - 1F 78.66 m²
  - 2F 33.44 m²
  into editable Annotation as Human comparison targets
- target comparison remains informational and is not treated as a statutory floor-area determination

Safety:
- m² difference is never emitted before room Geometry has Human scale calibration
- arbitrary overlapping zones do not inflate the target comparison
- backend validation remains authoritative over comparison output

Verified checkpoint:
- run: `37412861883` SUCCESS
- backend pytest: 168 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS


## Phase 6 Annotation boundary snapping

Implemented and CI-verified:
- Draft room/zone vertex editing now supports optional boundary snapping
- snapping is enabled by default and can be toggled ON/OFF
- display-space threshold is approximately 10px and is converted to drawing coordinates
- snap candidates are limited to the current drawing page
- actively edited polygon is excluded from its own snap candidates
- snap targets:
  - vertices of other room/zone polygons
  - projected points on other room/zone edges
- exact vertex targets win ties against edge targets
- both existing-vertex drag and new-region point placement use the same snap engine
- current snap target is rendered as a visible crosshair/label
- snap state is transient and cleared after drag/new-region completion
- backend remains authoritative for saved Geometry-derived area and summary values
- frontend contract tests protect drag/new-point snap wiring and ON/OFF behavior

Safety:
- snapping is a Human editing aid only
- no polygon is moved automatically after the Human finishes the gesture
- no server-side Geometry is inferred from snapping state
- disabling snapping restores exact freehand point placement

Verified checkpoint:
- run: `37430859727` SUCCESS
- backend pytest: 170 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS


## Phase 6 Annotation Undo / Redo

Implemented and CI-verified:
- Draft Human Annotation now has bounded local Undo / Redo history
- max retained Undo depth: 50 snapshots
- persistent edit types covered:
  - room/zone metadata correction
  - vertex drag
  - vertex add/remove
  - room/zone add/remove
  - page scale calibration add/remove
  - Human floor-area target add/update/remove
- one vertex drag gesture creates one history checkpoint
- new edit after Undo clears Redo
- restoring history restores payload + page calibration together
- local Geometry metrics/floor summary are rebuilt after restore
- save establishes a new saved checkpoint and clears history
- visible `未保存 / 保存済み` state
- keyboard shortcuts:
  - Ctrl/Command+Z Undo
  - Ctrl/Command+Shift+Z Redo
  - Ctrl/Command+Y Redo
- global shortcuts do not override native input/textarea/select Undo
- unsaved-change guards protect:
  - closing Drawing workspace
  - switching Annotation
  - opening another Drawing
  - importing another Reference Draft
  - browser/tab close
- saved-state identity is tracked independently from history depth, so the 50-entry history cap cannot falsely mark an older retained state as saved
- frontend regression tests protect edit-history wiring and discard-guard ordering

Safety:
- Undo/Redo is UI-local until save
- backend remains authoritative after save
- backend still recalculates derived Geometry, m² and floor summaries
- reviewed Annotation remains immutable through Draft editing routes

Verified checkpoint:
- run: `37438357035` SUCCESS
- backend pytest: 175 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS


## Phase 6 reviewed Annotation revision workflow

Implemented and CI-verified:
- reviewed Human Annotation remains immutable
- reviewed Annotation can create a new editable Revision Draft
- optimistic source Annotation version check
- Revision Draft copies:
  - Geometry
  - page calibration
  - Human floor-area targets
  - equipment/fact candidates
  - existing provenance
- copied Draft passes through server-authoritative Geometry/area recalculation
- Revision Draft starts at:
  - status=draft
  - version=1
  - source_method=manual
- previous Human review state is never inherited
- revision provenance stored in `payload.revision_history`
- provenance records source Annotation ID/version/review timestamp plus Human note
- Revision Draft can use existing:
  - vertex edit
  - room/zone add/remove
  - calibration
  - floor-area target comparison
  - snapping
  - Undo/Redo
- old reviewed Reference remains exportable and unchanged
- revision requires a new Human Review before Reference export
- UI exposes `修正版Draftを作る` on reviewed Annotation
- UI shows Revision lineage
- E2E covers:
  - stale version rejection
  - reviewed -> Revision Draft creation
  - Draft cannot create a revision
  - derived area copied/recalculated
  - revision Geometry edit changes only the new Draft
  - old Reference keeps original 2.0m² evidence
  - revised Reference reaches 3.0m² after correction
  - both reviewed References remain immutable evidence

Safety:
- reviewed evidence is never edited in place
- Revision does not inherit review approval
- old Benchmark evidence remains reproducible
- downstream Baseline still requires explicit Human Review of the Revision

Verified checkpoint:
- run: `37439190828` SUCCESS
- backend pytest: 178 passed
- migration parser smoke: PASS
- frontend JavaScript syntax: PASS


## Phase 6 Human Annotation QA gate

Implemented in the current Phase 6 QA slice:
- one-screen Human Annotation QA summary before Reference review
- region/room/zone counts
- existing floor-area target comparison surfaced as QA evidence
- overlap blockers
- uncalibrated-page warnings
- missing label/use blockers
- explicitly marked open-plan approximation warnings
- explicit Reference-reviewable state
- server-side recheck before a Draft can become reviewed Reference
- live client-side QA during editing

Safety:
- QA does not auto-review a Draft
- QA does not auto-accept a drawing Benchmark
- geometry review can remain possible without metric calibration, while metric-area comparison stays incomplete
- statutory floor area is not inferred by this QA layer


## Continuous completion audit (2026-10-06)

Completion is governed by the user's operational Definition of Done, not Phase numbers.
See `docs/COMPLETION_AUDIT.md` for the main-code audit anchored to `3452fb20`.
Do not treat earlier "next slice" headings as an authoritative remaining-work inventory.

Current bounded slice: restore safety.
- validate and stage storage before changing the target database
- never extract into a neighboring `storage` directory
- reject escaping manifest filenames, archive links/special files and overlapping backup/target paths
- reject a target SQLite DB inside replaced storage
- PostgreSQL restore uses exit-on-error and a single transaction
- preserve original target storage until staged replacement is ready
- 7 regression cases reproduced failures against the previous main and pass after the fix

System completion, tenant isolation, production migrations, real AI baselines and LAN readiness are NOT declared complete.
Next independent work remains tenant/common administration, PostgreSQL verification and missing emergency Web workflows.

## Continuous completion: emergency Web aggregate reports

- browser-only reporting surface at `/ui/emergency.html`
- dedicated emergency.report.read / emergency.report.export gates
- hospital/severity/region code aggregates; incidents and patients counted separately
- period bounds inclusive, unknown call dates explicitly excluded/countable when bounded
- region aggregates retain incidents with no patients
- no patient diagnosis, raw payload or individual IDs in aggregate outputs
- Excel/CSV share report core; spreadsheet formulas disabled for source codes
- browser print/PDF path, explicit definitions and snapshot export conditions
- aggregate read/export audit; no-store responses
- new authenticated permission-code endpoint for the reporting UI
- 8 new behavioral tests cover permission, counts, dates, privacy, formula injection and audit
- no migration required; existing deployments must re-run RBAC seed to install the new export permission

Remaining emergency work: names/master mapping, per-crew and official time-series reports, Web import, validation checks and Human clinical-candidate review.
This is not a production-completion or emergency-module-completion claim.

## Completion Run B — emergency operational slice

Run B extends existing normalized emergency records and uses the main aggregate/export implementation from #39.
Added: case/patient editing, common-employee crew assignment, treatment records, CPA/allergy candidate generation, explicit Human review with stale-evidence rejection, immutable reviewed report snapshots, input warnings, audited workbook Web import, permission-gated case search and shared-shell UI.
Migration 038 adds emergency_treatments/emergency_report_drafts and clinical-flag optimistic version.
No candidate directly changes official patient source fields. No tenant-isolation or whole-module completion claim.
See docs/completion/RUN_B_STATUS.md and INTEGRATION_HANDOFF.md for internal backlog, interfaces and External Gates.

## 2026-10-06 Run A: 本部分離の確定

共通コード・本部別DB/実行環境/原本/backup方式は利用者承認済み。
正式構成と本部追加・移行・更新・復元契約: `docs/architecture/TENANT_OPERATIONS.md`。
本部識別子の境界実装と残GateのEvidence: `docs/completion/RUN_A_STATUS.md`。
全体の完成判定は実コード・CI・運用Evidenceと照合し、旧Phase記述だけで判断しない。

## Completion Run B — operations/fleet review candidate

Task2 local implementation15da8c2 adds shared incident/dispatch links and vehicle registry/use/fuel/service/fault workflows with Human allowance/service approval, preview-confirm CSV/XLSX and shared-shell search/UI. Migration040 follows canonical Run A tenant-identity039;31 focused and242 full tests passed. Independent review/CI/refreshed-main/merge pending; no whole-system, tenant or real-browser/PostgreSQL acceptance claim. Exact status remains docs/completion/RUN_B_STATUS.md and INTEGRATION_HANDOFF.md.

Task2 fixround1: permission-filtered mutation responses, complete mixed-source export columns, and separate fuel purchase expense/issue valuation implemented;31 focused and242 full tests passed. Scoped independent re-review is pending.

Task2 latest-main adaptation consumes Run A PR41/main8323930e without tenant redesign. Canonical startup/Host/storage/DB session guards and CI PostgreSQL service are retained;040 replaces only Run B provisional039. Two-DB/source and optional PostgreSQL-lock integration evidence is recorded in task-2-report.md; refreshed-base CI/independent review/merge and actual browser/production acceptance remain pending.

Task2 adaptation validation:52 focused passed/2 local PostgreSQL skips;263 full passed/2 skips;40 migration files parsed and001–038 unchanged; JS/compile/diff checks passed. The optional actual PostgreSQL source-lock test awaits inherited CI service execution.


## Master Specification v2.0 canonicalization

`docs/SPECIFICATION.md` is now the canonical Fire Service AIOS Master Specification v2.0.

It consolidates historical v1.8 requirements, current tenant/runtime/security contracts, Completion Run A/B requirements, all five deployment profiles, server-side update/no per-client install policy, all operational modules, learning/autonomous change governance, automatic per-department backup/maintenance exclusion, release artifacts and system-wide Definition of Done.

Resolved architecture conflicts:
- production PostgreSQL is mandatory; SQLite is dev/test only
- runtime is fixed to one department identity; users cannot select tenant/DB/storage
- originals use server-managed Document Storage, not client-written shared folders
- common releases are activated per department rather than forced globally

Review diff: `docs/SPECIFICATION_V2_DIFF.md`.

Implementation status remains tracked separately in PROJECT_STATE / completion ledgers; specification scope must not be reduced merely because a module is still Missing or Partial.


## Master Feature Matrix canonical completion audit (2026-10-07)

Master Specification v2.0 all 57 chapters have been re-audited against actual main code, migrations, routers, frontend, tests and deployment assets.

Canonical matrix:
- `docs/completion/MASTER_FEATURE_MATRIX.md`

Audited base:
- `6bcf537936915d3c891e9176b71a38f4886197e1`

Primary status:
- Completed: 14
- Partial: 32
- Missing: 10
- External Gate: 1

Completion work must now follow the Matrix backlog rather than historical Phase numbering.
A PR/module completion is not a stopping condition.
After each merged completion slice, refresh main and update the affected Matrix rows only.

## Task8 Human権限管理（PR56 merge済み）

main24a0ea8とmain CI37494620742 SUCCESS、開PR53、Migration001–043/045、実コード・テスト・未完Gateを再監査。customRole、完全一致RoleRule、期限付き/代理grant、本人向け根拠、原本preview hash、CAS・監査・session失効・ブラウザ操作をPR56でmerge。レビュー6件とbootstrap500をRED→GREEN修正、PR backend447/実browser5成功。資格/担当selectorと辞令Document候補は内部Partialのまま継続する。詳細docs/completion/HUMAN_ROLE_MANAGEMENT.md。

PR56 Human Role/Rule/期限付き・代理はmain b2fc2612へmerge。exact-head CI447/backend＋5/browser成功、main CI37500653453 SUCCESS確認済み。資格/担当selector・辞令Document候補は内部Partial。共通Migrationのdollar-quoted immutable trigger/percent/preflight不足を次Sliceで修復中。詳細docs/completion/MIGRATION_SQL_SUPPORT.md。

## 勤務管理の正本統合（既存PR53修復）

main ea15820e / main CI37503229005 SUCCESSを再確認。PR57共通MigrationはPG465/browser5成功でmerge。既存PR53 head e21eaa0の未merge差分を最新mainへ三者照合し、独立レビュー13Importantを1回のTDD修正passで修復。資格/人事/組織は既存正本を再利用。勤務区間のHuman設定/明示承認、滞在と正式勤務時間の分離、期限/残高全日付整合、session/permission再確認、重複配置排他、UTC、監査理由、共用PC状態消去・遅延response拒否、一覧pageを追加。新044のみ変更、既にmainの001–043/045/047は不変。§25はPartialのまま、team/work-result/checkout/cancel/balance/crew UI・期限/代休reconciliationが内部残差。詳細docs/completion/WORKFORCE_INTEGRATION.md。CI/merge/mainGreenは完了後にEvidenceを追記する。

PR55財務はmain0feb62e6へmerge、main CI37507500474 SUCCESS。財務048を再実装せず正本として採用。開PR53を最新mainへ三者統合し、両業務・tenant/password/Roleを保持、browser7workflowで再検証する。Matrixは13Completed/36Partial/7Missing/1External（勤務Slice反映後。main0febのみは13/35/8/1）。財務の操作待機中session権限再確認・共用PC状態は内部Partialで継続。

## 勤務統合と財務安全性の再監査

PR53は既存勤務実装を修復してmerge済み。正確なhead334b3246のCI37509352367: backend546passed14skip、Chromium7passed。ログアウト時に既に消去された勤務ナビをテストが再クリックする競合はPR58でテスト側を修復。main386582ceのCI37511281181 SUCCESS。47migration/379statements。勤務はteam/work-result、編集/checkout/cancel/balance/crew UI、expiry/reconciliationを残すPartial。

この差分の財務安全性は docs/completion/FINANCE_SAFETY.md に記録。共通更新guardを旧契約経路にも適用、応答/原本出力時の利用者照合、権限失効時のprivate state消去、複合権限メニューを修復。正式な金額/残額、承認ledger、Human原本確認は既存mainを再利用する。実モデル文字起こしの共通adapter等、法令Human承認、実host/実図面品質は未完扱いを維持。最新PRのexact-head CIとmain Greenを確認してから完成監査へ引き継ぐ。完成成果物はまだ未生成。
