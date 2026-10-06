# 消防業務AIOS Master Specification v2.0

作成基準日: 2026-10-07

本書は消防業務AIOSの唯一のMaster Specificationとする。
旧v1.8までの仕様、2026-10-06までに確定したGitHub上の後発設計、Completion Run A/B、TENANT_OPERATIONS、各Task brief、および会話で確定した追加要件を統合した。

実装状況はPROJECT_STATE.md、docs/completion/RUN_A_STATUS.md、docs/completion/RUN_B_STATUS.md、INTEGRATION_HANDOFF.mdを参照する。
本書は「何を作るか」を定義し、PROJECT_STATE等は「どこまで作ったか」を定義する。

---

## 1. Product Vision

消防業務AIOSは、単一業務アプリの集合ではなく、消防本部全体の業務データ、文書、法令、判断根拠、Human Review、監査、AI支援を1つの共通基盤で接続するモジュール型業務OSとする。

目的は以下。

- 二重入力、転記、集計、照合、検索、期限確認、下書き作成を極小化する。
- 事実を一元管理し、同じ情報を業務ごとに複製しない。
- AI候補と正式データを厳格に分離する。
- 正式判断はHuman Gateを通す。
- すべての重要な結論を元データ・原本・Rule・Human Reviewへ遡れるようにする。
- AI停止時も通常業務を継続できる。
- 1つの共通コードを複数の消防本部へ導入できる。
- 各消防本部は必要Moduleを選択でき、後から追加できる。
- 本部ごとの条例、規則、内規、帳票、承認フロー、権限、予算構造、勤務条件、手当条件、UI設定を個別管理できる。
- 最終的に、対象物、予防、救急、警防、火災調査、人事、勤務、車両、資機材、契約、予算、議会、統計、文書を横断して利用できる1つのシステムとする。

---

## 2. Canonical Architecture

### 2.1 共通コードと本部分離

共通AIOSコードを使用し、本部ごとに以下を分離する。

- PostgreSQL DB
- アプリ実行環境
- Document Storage
- Backup
- 設定
- 人事
- 権限
- 監査ログ
- AI候補
- Human Review
- 法令Rule
- 正式様式
- Release適用状態

各本部は不変のdepartment UUIDを持つ。
DB、アプリ設定、Storage marker、Backup manifestは同じdepartment UUIDに固定する。

本番起動時にUUID不一致、未設定、Storage不一致を検出した場合はFail Closedとする。

HTTP利用者がtenant、本部UUID、DB接続先、Storage接続先を選択する機能は持たせない。

同一消防本部内の複数署所、分署、分駐所、複数PCは同じ本部DBを利用し、リアルタイムに同一データを共有する。

別消防本部間では、データ、職員、アカウント、権限、監査、原本、Backupへ相互アクセスできない。

### 2.2 jurisdictionとtenantを分離する

消防本部のtenant境界と法令適用範囲は別概念とする。

1本部DB内に複数の自治体、組合、管轄地域、法令Profileを持つことは可能とする。
法令判定時には適用jurisdiction、評価日、法令Version、条例Version、Rule Versionを固定する。

### 2.3 本番DB

本番DBはPostgreSQLを必須とする。

SQLiteは以下に限定する。

- 開発
- Unit Test
- 軽量Fixture
- 一部CI

本番で共有SQLiteや共有JSONを複数PCが直接更新する方式は禁止する。

### 2.4 Document Storage

旧仕様の「共有フォルダ」は、サーバー管理Document Storageへ置き換える。

利用者PCはStorageを直接更新しない。
原本の登録、閲覧、派生物生成、出力はWeb/API経由で行う。

Storageには以下を保存できる。

- PDF
- Word
- Excel
- CSV
- 画像
- 動画
- 音声
- 図面
- 添付資料
- AI派生物
- 帳票出力
- Update Bundle
- Backup対象原本

原本と派生物を同じfile identityとして扱わない。

---

## 3. Deployment Profiles

同一コードベースから以下のDeployment Profileを構成可能とする。

1. Cloud
2. Internet-connected Local
3. Closed-network Local
4. Fully Offline
5. LGWAN / Government Network compatible

5種類の別製品を作るのではなく、共通AIOSにDeployment Adapter、Policy、Update方式を組み合わせる。

### 3.1 Cloud

- 本部ごとのDB/Runtime/Storage/Backup分離を維持する。
- 公開Internetへ業務データを不用意に出さない。
- 外部AIを利用する場合は組織Policyに従い、送信項目を明示制御する。

### 3.2 Internet-connected Local

- 本部内サーバーまたは専用親PCでAIOSを稼働する。
- 各PCはブラウザから接続する。
- 公式法令等の外部更新を直接取得可能とする。

### 3.3 Closed-network Local

- 本体は閉域内で稼働する。
- 外部更新は署名済みUpdate Bundle等を承認経路で搬入する。

### 3.4 Fully Offline

- 外部Networkを前提としない。
- CRUD、検索、受付、帳票、ローカルAI等はオフラインで利用可能とする。
- 法令・モデル・Releaseは物理または承認済みBundleで更新する。

### 3.5 LGWAN等

LGWAN等ではPolicy Gateway/Adapterを用い、閉域側処理と外部側処理を分離可能とする。
外部側Agentへ送る情報は権限・機密区分・許可Policyで制御し、必要最小限の結果のみ戻す。

### 3.6 初期正式クライアント

初期正式クライアントはPC Web Browserとする。

初期正式スコープに以下を必須としない。

- 個人スマートフォン
- PWA
- スマホカメラ直接受付
- QR主体の現場運用

将来の組織管理モバイル端末へ拡張可能な構造は維持する。

---

## 4. Update, Release and Rollback

### 4.1 クライアント更新不要

利用者PCへModuleごとのInstallerやHTMLファイルを配布しない。

原則:

Server Release更新
→ AIOS Runtime更新
→ Browser再読込
→ 同一本部の利用者へ反映

利用者PCごとのDownload、Install、Macro更新を必要としない。

### 4.2 本部ごとのRelease適用

共通コードReleaseを作成しても、全本部を強制同時更新しない。

各本部は以下を持つ。

- current release
- previous release
- migration version
- feature flags
- deployment evidence
- rollback history

本部ごとに承認、更新、Rollbackできる。

### 4.3 Module Registry

各Moduleは以下を持つ。

- module_id
- version
- manifest
- dependency
- required permission
- feature flag
- migration dependency
- release compatibility

本部ごとに必要Moduleを有効化できる。

### 4.4 Change Request

自然文要望をHuman Change Requestとして保存できる。

例:
「対象物詳細画面へ未提出件数を表示し、クリックすると受付一覧へ移動したい」

AIは以下を候補として生成できる。

- 対象Module
- 画面影響
- DB影響
- API影響
- 計算ロジック影響/候補
- Workflow/承認フロー影響/候補
- Permission影響
- Audit影響
- Migration候補
- Test候補
- Risk
- Acceptance Criteria

変更手順は原則:

Request
→ Impact Analysis
→ Candidate implementation
→ Sandbox
→ Automated Test
→ Human Gate
→ Deployment
→ Monitoring
→ Rollback可能

AIが直接本番変更を確定しない。

---

## 5. Common Data Principles

### 5.1 Single Source of Truth

同じ事実をModuleごとにコピーしない。

共通IDを使用する。

例:

- employee_id
- organization_unit_id
- building_id
- document_id
- incident_id
- vehicle_id
- equipment/asset ID
- contract ID
- fiscal year/account ID

### 5.2 訂正と履歴

正式データの訂正は履歴付きUpdateとする。

最低限保持する。

- before
- after
- changed_at
- changed_by
- reason
- source evidence
- approval
- version

重要データを訂正のたびに物理削除して作り直さない。

### 5.3 楽観ロック

同時編集可能なRecordはversion等で競合検出する。
stale updateは409等で拒否し、後勝ち上書きをしない。

### 5.4 論理削除

正式業務Recordは原則、廃止、取消、無効、退職、retired等の状態で残す。

原本、監査ログ、Human-reviewed evidenceをAIが物理削除しない。

---

## 6. Employee, Organization and Account

職員マスタとLogin Accountを分離する。

職員はemployee_id等の不変IDで管理する。

管理対象:

- 職員
- 組織
- 署所
- 課/係
- 役職
- 本務
- 兼務
- 異動履歴
- 有効期間
- 資格
- 担当業務
- 状態

Account:

- login ID
- password hash
- password history
- password expiry
- account state
- session revocation
- last login等

Passwordは平文保存禁止。

権限は現在の所属・役職・担当・Human設定されたRole Ruleから算出する。
AIが権限を決めない。

対応可能な権限形態:

- Role
- Module permission
- temporary grant
- acting/代理
- 期限付き権限
- 将来日付の異動/権限予約
- Humanによる明示grant/revoke

最後の重要管理者を失わせる変更等は保護する。

人事異動通知、辞令、配置表等のDocumentを取込対象にできる。
AI/OCRは所属・役職・発令日・兼務等の変更候補を生成できるが、Employee/Assignment/Permissionへ自動確定しない。
元Document、抽出根拠、適用予定日、対象職員、before/after候補を表示し、Human Review後のみ人事履歴へ反映する。
不明な職員コード、所属コード、役職コードを推測で補完しない。

---

## 7. Authorization

Frontend表示だけで権限制御しない。
Backend endpointで必ず確認する。

Moduleに応じて以下を定義可能とする。

- read
- create
- update
- delete/retire
- review
- approve
- admin
- import
- export
- aggregate
- AI use
- sensitive read

救急、職員、財務、火災調査等は必要に応じて追加のSensitive Permissionを持つ。

権限のないRecordの存在をDashboard件数やSearch snippetから推測できないようにする。

内部Rule ID等は一般利用者へ無理に露出せず、人間が理解できる名称・根拠・条文・理由を優先表示する。
監査・管理権限では内部IDを確認可能とする。

---

## 8. Audit

重要操作を監査する。

例:

- Login
- Logout
- Data create/update/retire/restore
- Human Review
- Approval
- Rule approval
- AI generation
- Import
- Export
- Search of sensitive data
- Backup
- Restore
- Tenant initialize
- Account/permission change
- Release/rollback

Auditは原則append-only。
通常アプリRoleにAudit改変権限を与えない。

---

## 9. Document Platform

Documentを全Module共通基盤とする。

対応入力:

- PDF
- DOCX
- XLSX/XLSM
- CSV/TSV
- TXT
- JPEG/JPG
- PNG
- WebP
- TIFF
- HEIC等はdecoder availabilityに応じて有効化
- 音声
- 動画

保存:

- original SHA-256
- media type
- original filename
- logical display name
- source module
- uploader
- created time
- derived documents
- extraction method
- provenance

ファイル名は業務内容の正本にしない。

Document解析の標準フロー:

Original
→ deterministic extraction
→ OCR/Vision/AI when needed
→ candidate
→ Human Review
→ explicit apply

AI/OCR結果を原本へ書き戻さない。

---

## 10. Document Intake and OCR

解析候補:

- document type
- submission type
- facility
- submitter
- date
- content
- equipment
- area
- usage
- occupancy
- attachment relationship
- destination module
- target fields

複数画像を1受付の複数ページとして束ねられる。

派生画像処理:

- rotation
- deskew
- perspective correction
- brightness/contrast
- margin detection
- page order candidate
- duplicate page detection
- missing page warning
- unreadable area warning

安全上限は設定可能とし、v1系互換の初期値として以下を利用できる。

- sync file: 100MB
- OCR: 20 pages
- extracted text: 250,000 chars

これらは運用設定で変更可能だが、無制限処理は禁止。

---

## 11. Facility Registry

building_idを不変IDとする。

管理:

- name
- address
- phone
- owner/representative
- manager
- occupancy
- 令別表分類
- structure
- above/below ground floors
- building area
- total floor area
- floor area
- floor use
- occupancy count
- employee count
- windowless classification
- flame-retardant information
- fire safety equipment
- fire management
- inspections
- submissions
- violations/corrections
- drawings
- photos
- fire history

旧台帳由来の未確定項目を推測で正規化しない。
原値をEvidenceとして保持する。

---

## 12. Inspection

管理:

- inspection case
- date
- type
- inspector
- findings
- one finding per record
- correction status
- due date
- completion
- photos
- documents
- past unresolved findings
- follow-up

次回査察時にAIは過去指摘、未処理、届出状況、台帳差分を要約できる。

---

## 13. Violations and Corrective Actions

査察指摘と正式違反確定を分離する。

AIは以下の候補を提示できる。

- possible issue
- applicable Rule
- evidence
- missing information
- recommended confirmation step

正式違反、命令、処分等はHuman Gateと正式手続を必須とする。

改善指導、回答、期限、確認、完了Evidenceを追跡する。

---

## 14. Submission and Application

submission typeはMaster化し、後から追加可能。

少なくとも:

- 消防用設備等点検結果報告
- 防火管理者選任/解任
- 消防計画
- 火災予防条例関係
- 消防法令適合通知関係
- 使用開始
- 消防用設備関係
- 訓練関係
- その他届出/申請/通知

Submission typeごとに設定可能:

- required fields
- extract fields
- attachments
- workflow
- target DB fields
- update permission
- Human Gate
- Rule link
- official template

正式届出番号は既存採番System等の正本から受領する。
AIOSが推測で正式番号を生成しない。
正式届出番号は原則として数字のみを保存・表示し、年度・届出種別等は別fieldで保持する。
「予防第」「号」等の接頭辞・接尾辞をAIが推測で付加しない。

submission_idは内部不変IDとする。

受付確定後、対象物台帳等への反映を別転記せず同一DB transactionで接続する。

---

## 15. Submission Requirement Tracking

対象物ごとに:

- requirement candidate
- submission status
- last submitted
- next due
- review state
- missing candidate
- source Rule
- evidence

を管理できる。

未提出違反をAIが独断確定しない。

---

## 16. Hazardous Materials

危険物関連を独立Moduleとして追加可能とする。

対象:

- facility/installation registry
- permission/notification records
- quantity/capacity
- category
- inspection
- change
- deadline
- document
- legal evidence
- violation/correction
- history

法令判断はRule Engineを使用する。

---

## 17. Legal and Rule Engine

LLMによる自由推論を正式判定Engineにしない。

正式判定はVersion管理されたRule Engineを用いる。

Rule:

- domain
- conditions
- outcomes
- effective dates
- status
- citations
- source version
- Human approval

AIはRule Candidate、影響候補、説明を作成できる。

### 17.1 National law

e-Gov等公式一次Sourceを優先。

保存:

- law ID
- title
- number
- promulgation/effective dates
- full text
- structured provisions
- source URL
- acquired_at
- SHA-256
- version
- previous version difference

### 17.2 Local regulations

本部Profileごとに公式Source adapterを登録する。

対象:

- 条例
- 規則
- 規程
- 訓令
- 告示
- 要綱
- 別表
- 様式
- PDF/画像
- 公布情報

「消防関係らしい文書だけ」をAIが勝手に削除しない。

### 17.3 Amendment impact

変更時に候補提示:

- changed provision
- old/new diff
- impacted Rule
- impacted submission
- impacted equipment requirement
- impacted template
- impacted facility
- recalculation candidate

正式Rule変更はHuman Gate。

### 17.4 Signed Offline Update Bundle

閉域環境では署名済みBundleを利用できる。

Bundle:

- official original
- metadata
- source URL
- source hash
- version
- diff
- manifest
- bundle hash
- signature
- signing key identifier

検証失敗時はImport禁止。

未知鍵、失効鍵、不正署名、hash mismatch、path traversal、unsafe archive、許可外origin等を取込前に拒否する。

---

## 18. Equipment Requirement and Installed Equipment

法令上必要な設備と、実際に設置されている設備記録を分離する。

Rule Engineからrequired equipment候補を生成する。

FacilityEquipment等の設置情報にはverification stateを持つ。

AI/旧台帳/図面抽出だけでverified installedとしない。

比較結果例:

- verified installed
- missing candidate
- unverified evidence only
- manual review required

根拠Rule/Provisionへ遡れること。

---

## 19. Drawing AI

図面入力:

- PDF
- image

候補抽出:

- floor
- room
- use
- wall/region
- area
- opening
- stair
- exit
- fire compartment
- equipment symbols
- equipment locations
- building facts

Human Annotationを正解データ層として持つ。

Human editing:

- polygon vertex drag
- add/remove vertex
- add/remove room
- arbitrary zone
- label/use correction
- floor
- snapping
- Undo/Redo
- unsaved-change protection
- reviewed Reference revision Draft

Metric area:

- pixel area
- two-point scale calibration
- meters_per_pixel
- automatic m2 recalculation
- server authoritative calculation
- floor summaries
- overlap warnings
- known floor-area comparison

Reviewed Referenceは直接上書きしない。
修正時は新Revision Draftを作る。

### 19.1 Drawing QA

確認前に表示:

- region count
- floor totals
- target floor-area comparison
- overlaps
- uncalibrated pages
- missing label/use
- open-plan approximation
- Reference reviewability

### 19.2 Benchmark

Human ReferenceとAI Hypothesisをsource SHAでbindする。

評価:

- geometry Precision/Recall/F1
- IoU
- element type
- symbol accuracy
- equipment candidate
- fact candidate
- pixel area accuracy
- calibrated m2 accuracy

HumanがBaselineをaccept/rejectする。
良いscoreでも自動acceptしない。

---

## 20. Occupancy Classification and Drawing Consultation

図面、対象物情報、Human answers、正式Ruleから令別表等の分類候補を生成する。

分類確定はHuman Gate。

分類確定後、必要設備、追加設備、配置候補を評価する。

設備が図面へ記載されていない場合でも、確認済み用途/規模/Ruleに基づき必要設備と配置候補を提示可能とする。

回答Package:

- classification
- input snapshot
- required equipment
- existing equipment
- actions
- placement
- unresolved questions
- legal citations
- source hashes
- coverage
- Human review state

AIが法令適合を無根拠に保証しない。

---

## 21. Emergency Module

VBA/Excelを正本とせずDBを正本とする。

Data:

- cases
- patients
- crew
- treatments
- transport
- hospital
- severity
- classifications
- reviewed clinical flags
- report snapshots
- import batches
- source hashes
- correction history

既存Excel/CSVの全情報を失わず移行し、未正規化項目はraw evidenceとして保持可能。

既存 `救急報告関係.xlsm` の移行元について、会話で確定した最新の既知構成は以下とする。
- 事案台帳: 117列
- 救護者台帳: 160列
- 出動隊員: 24列

列数そのものをImporterへ固定せず、実ファイルのheaderを監査して全列をraw evidenceとして保持する。
過去資料にある出動隊員「7列」表現は旧確認時点のsubset/旧記述として扱い、最新既知構成を上書きしない。
実ファイルが将来変更された場合は、推測で列を落とさず、header auditとmapping更新をHuman Review対象とする。

### 21.1 Clinical candidates

候補:

- CPA
- allergy
- contraindication/caution
- disease/state classification
- input inconsistency
- missing fields

CPAは傷病名だけで判定しない。

Evidence候補:

- explicit CPA code
- resuscitation code
- CPR/chest compression treatment
- patient state
- diagnosis/injury

CPRだけを正式CPAへ自動確定しない。

clinical candidate:

- flag_type
- value
- derivation_method
- evidence
- confidence
- source version
- review status
- reviewer

Human-reviewed flagとsource fieldを分離する。

### 21.2 Emergency reporting

集計:

- hospital
- day/month
- severity
- region
- crew activity
- yearly individual activity
- incident count
- patient count
- disease/state
- external report

incidentとpatientを混同しない。

正式救急報告、事後検証、救命処置録等は登録済み正式様式へ出力可能とする。

### 21.3 Privacy

権限例:

- case read
- patient read
- sensitive personal read
- import
- aggregate only
- report export
- AI search

Aggregate権限だけで個別診断等を漏らさない。

---

## 22. Incident and Dispatch

救急、火災、救助、警戒、風水害、その他業務を共通Incident/Dispatch概念へ接続する。

管理:

- incident
- source case
- dispatch
- station/unit
- crew
- vehicle
- timestamps
- activity
- document
- report
- allowance candidate
- review/approval
- statistics

既存の救急Caseや火災調査Caseの事実を複製せず参照する。

同一事案を複数帳票へ再入力しない。

---

## 23. Fleet and Vehicle

Vehicle masterを共通化する。

管理:

- registry
- assignment
- trip
- mileage
- dispatch link
- driver
- fuel purchase
- fuel issue
- fuel inventory
- inspection
- service
- repair
- fault
- resolution
- cost
- next inspection
- vehicle inspection/registration due date
- history

燃料購入費と払出評価を混同しない。

重要な修繕/故障resolution等はHuman approvalを設定可能とする。

---

## 24. Operational Assets and Inventory

建物の消防用設備台帳と、業務用資機材在庫を混同しない。

対象:

- durable asset
- consumable
- drug/medical stock
- equipment
- PPE
- test instruments
- other operational item

管理:

- asset definition
- lot/batch
- location
- quantity
- receive
- issue
- transfer
- loan
- return
- inspection
- repair
- renewal
- disposal
- pressure test
- calibration
- use expiry
- lot expiry
- service due
- reorder threshold
- reorder candidate
- immutable movement history

同じ薬剤/消耗品Masterを有効期限ごとに複製せず、MasterとLotを分離する。

Stockを負数にしない。
ReturnがLoan残量を超えない。
Transferで総量を増減させない。

期限切れ在庫を通常Issueしない。
廃棄/write-offはHuman actionと理由を必要とする。

---

## 25. Workforce and Duty Management

Employee/Organizationを再利用する。

管理:

- roster
- team
- duty type
- station placement
- support placement
- minimum staffing
- qualification requirement
- available emergency crew
- annual leave
- special leave
- attendance
- check-in/out
- overtime
- compensatory time/day
- work result
- leave balance
- shortage warning
- statistics

最低人員や資格要件は本部設定されたRuleとして管理し、AIが勝手に制度を作らない。

24時間勤務等の勤務時間計算は本部のHuman-approved勤務Ruleで算定し、単純に滞在時間を勤務時間としない。

同一職員の重複配置を防止する。

---

## 26. Contract and Procurement

既存ContractCase/Counterparty/Documentを共通利用する。

管理:

- vendor
- quote
- contract
- specification
- decision documents
- term
- amount
- fiscal year
- renewal
- commitment
- inspection
- delivery
- invoice
- payment link
- contract change
- deadline
- documents

AI支援:

- OCR
- transcription
- amount calculation
- document diff
- missing document candidate
- similar case search
- Draft

正式相手方、金額、契約条件、締結はHuman Gate。

---

## 27. Budget and Finance

財務Moduleを正式Moduleとする。

管理:

- fiscal year
- account hierarchy
- initial budget
- amendment
- transfer
- commitment
- execution
- payment
- reversal
- balance
- budget request
- next-year estimate
- contract link
- procurement link
- aggregate

### 27.1 Account hierarchy

「款・項・目・節・細節」等を固定DB columnで決め打ちしない。

可変階層Account Masterとし、各本部が表示名と階層を設定できる。

例:

- 款
- 項
- 目
- 事業
- 節
- 細節
- 細々節

Codeはstringで保持し先頭0を失わない。

### 27.2 Financial Human Gate

正式な予算変更、流用、支出、Payment等はHuman Review/Approvalを必須にできる。

Approved ledgerを破壊的上書きしない。
取消はreversal/compensating entryを使用する。

Double paymentやoverspendを防止する。

AIが価格や正式残額を捏造しない。

---

## 28. Council, Assembly and Inquiry Support

管理:

- past question
- answer
- year/session
- subject
- draft
- evidence
- numeric source
- related module record
- document
- similar question search
- Human review

AIは回答Draftを生成できるが、根拠のない固有名詞、数値、制度、答弁を正式回答へ混入させない。

数値ClaimはEvidenceの値、Query条件、取得日、単位へ追跡可能とする。

Sourceがstale/削除/無権限の場合、review/approveを拒否できる。

Approved answerはrevisionで更新し、直接書換えない。

---

## 29. Fire Investigation

fire_case_idで一元管理。

Data:

- case
- facility
- people
- photos
- video
- audio
- drawing
- note
- interview
- evidence
- statement
- timeline
- cause candidate
- official cause
- report
- template output

AIは原因を独断確定しない。

候補として:

- confirmed facts
- hypotheses
- supporting evidence
- contradicting evidence
- missing information
- next investigation candidates

を整理する。

Official causeは独立Human Gate。

---

## 30. Fire Photo Intelligence

Original photoは変更禁止。

派生情報:

- EXIF
- captured time
- perceptual hash
- duplicate candidate
- quality
- category
- tag
- description draft
- search text
- plan/drawing location link

Human-reviewed evidenceとAI candidateを分離する。

---

## 31. Voice, Statement and Evidence Comparison

Original audio
→ transcript
→ speaker/time
→ uncertainty
→ AI organization
→ Human correction
→ reviewed statement

を分離する。

「たぶん」「頃」「と思う」等の不確実表現をAIが消さない。

原音声timestampへ戻れる。

複数供述、写真、Timeline等の矛盾候補をEvidence Comparisonとして生成できる。

Evidence Comparisonは reviewed statement、confirmed timeline、official causeを直接変更しない。

---

## 32. Fire Report Drafting

案件Evidenceから以下のDraftを作成できる。

- summary
- building description
- discovery
- notification
- initial response
- evacuation
- burn damage
- statements
- timeline
- cause discussion

各文章は根拠Evidenceへ遡れる。

Official reportはHuman Review/Approval後に登録済み正式様式へ出力する。

---

## 33. Official Form Platform

正式様式が存在する場合は原本を優先する。

対応:

- PDF AcroForm等
- XLSX
- DOCX
- その他安全にfill可能な登録様式

Template:

- template_id
- module
- version
- effective date
- expiry
- issuer
- original SHA-256
- field mapping
- print settings
- change policy

AIが勝手に正式様式を再デザインしない。

出力にはsource snapshot、template version、output hash、generated_at、review stateを保持する。

---

## 34. Cross-module Statistics, Annual Reports and Surveys

元Module DBを正本にして再入力しない。

対象:

- emergency
- fire
- rescue
- dispatch
- inspections
- submissions
- equipment
- personnel
- workforce
- fleet
- assets
- contracts
- budget
- other configured modules

出力:

- monthly
- yearly
- prior-year comparison
- survey
- CSV
- Excel
- PDF/original template

Metricごとに:

- definition
- unit
- denominator
- date basis
- excluded unknowns
- source module
- source query/version
- drilldown

を保持する。

Missing prior-year valueを0と同一視しない。

---

## 35. Unified Search

Permission-aware searchを全Moduleに適用する。

検索対象例:

- facility
- inspection
- submission
- violation
- equipment
- document
- legal
- drawing
- emergency
- incident
- fleet
- fire investigation
- reviewed statements
- assets
- workforce
- contracts
- finance
- inquiries

救急個人情報等は個人閲覧権限を持たないSearchから除外する。

Search結果にはsource ID、module、必要Permission、navigation、provenanceを持つ。

Semantic/vector retrievalは追加可能だが、品質Benchmark前に精度を誇張しない。

---

## 36. Dashboard and Personal Work Queue

Login後、利用者のRoleと担当に応じて「今日やること」を表示する。

候補:

- unprocessed
- Human Review waiting
- submissions due
- inspection due
- corrective action due
- asset expiry
- calibration
- pressure test
- vehicle inspection
- repair
- contract expiry
- budget action
- roster shortage
- leave approval
- inquiry draft
- report due

Cardは元Recordへのpointerを持つ。
Dashboardが正式データを複製しない。

権限のないModuleの件数や内容を表示しない。

---

## 37. Learning Platform

職員の修正をLearning DBへ保存できる。

対象:

- OCR correction
- document classification correction
- facility link correction
- place/proper noun dictionary
- photo classification
- STT correction
- phrase/draft correction
- operational review pattern

本番Modelをその場で自己改変しない。

Lifecycle:

Champion
→ collect corrections
→ Candidate
→ fixed evaluation set
→ benchmark
→ comparison
→ Human approval
→ Champion promotion

性能悪化時はRollback可能。

Training data、evaluation set、model version、metrics、approvalを追跡する。

---

## 38. Autonomous Task and Self-extension Platform

Phase 12の「AI自律タスク」を以下として正式化する。

AIはHumanから与えられたGoalに対し:

Goal
→ Plan
→ Execute bounded tools
→ Verify
→ Fix
→ Evidence
→ Write-back candidate

の流れで作業できる。

対象:

- research
- aggregate
- reconciliation
- report draft
- document preparation
- data quality checks
- change request implementation candidate

Human Gate必須領域:

- contract conclusion
- formal expenditure
- official external statement
- permission change
- security setting
- legal Rule
- official violation
- official cause
- official personnel decision
- audit alteration
- evidence alteration
- unrestricted confidential access

System改修自律化はChange Request/Sandbox/Test/Approval/Deploymentの枠内だけで行う。

---

## 39. AI Decision Levels

Level 0:
deterministic/OCR/search/duplicate etc.

Level 1:
classification/tag/link candidate.
Low confidence時はHuman確認へ。

Level 2:
DB change candidate、missing submission等。
Human approval必須。

Level 3:
legal equipment requirement、important violation、official cause、financial/personnel official decisions等。
AIは補助のみ。

ModuleごとにLevelを追加設定可能。

---

## 40. AI Failure Mode

AIが停止しても以下を継続する。

- login
- CRUD
- facility
- inspection
- submission intake
- documents
- normal search
- emergency record
- dispatch
- workforce basic operations
- fleet
- assets
- contracts/finance basic records
- official template fill where AI不要

AI availabilityを業務DB availabilityの前提にしない。

---

## 41. Import Framework

Excel、CSV、PDF、Word、画像、音声等からModule取込候補を作成可能。

共通原則:

- explicit schema/version
- dry-run
- validation
- source SHA
- provenance
- Human confirm
- atomic apply
- idempotency
- rollback on invalid batch
- formula injection neutralization in spreadsheet export
- unknown code is not guessed
- stale target version rejection

既存の正式Recordを再Importで無言上書きしない。

---

## 42. Backup and Restore

本部単位でBackup/Restoreする。

本番では本部ごとの自動定期Backupを構成可能とする。
自動Backupは、当該本部に登録されたWriter/TimerとApplication Runtimeを保守排他の下で停止または排他し、DB dumpとDocument Storageを同じBackup単位として取得する。
通常Runtime transactionは共有Maintenance Lockを取得し、Backup/Restore/Migration等の明示Maintenanceは排他Lockを取得する。
保守中の通常HTTP要求は再試行可能な503等でFail Closedし、秘密情報を含まない案内とRetry-Afterを返せる。
自動Backup処理は成功/失敗/SIGTERM時に、開始前にactiveだった当該本部Serviceだけを復元する。
別本部Serviceを停止・起動してはならない。
Backup Timerは自動削除や自動Restoreを行わない。
Hard power loss等、Process外の障害については復旧Runbookと監視で扱う。

Backup manifest:

- department UUID
- release
- migration
- DB hash/dump evidence
- original/storage evidence
- stopped-writer acknowledgement where required
- created_at
- tool version

Restore前に:

- destination department identity
- source manifest
- dump identity
- Storage marker
- release compatibility
- archive safety

を検証する。

別本部Backupを誤Restoreしない。

DatabaseとStorageは完全な単一transactionではないため、停止、事前Backup、staging、失敗時の一組復元手順を定義する。

本番Recoveryは定期的にRestore Testする。

---

## 43. Security

最低限:

- TLS/HTTPS for production network where applicable
- secure session cookies
- CSRF/origin policy where required
- password hashing
- privilege separation
- application DB role
- migration/restore role separation
- no runtime superuser
- no client DB credentials
- server-managed storage
- path traversal rejection
- archive link/special file rejection
- safe redirect/origin validation
- secret outside Git
- no production data in Git
- no raw credentials in process arguments where avoidable
- audit
- least privilege

実データ、個人情報、原本、DB dump、秘密鍵、Password、API keyをGitへCommitしない。

---

## 44. External Integration and Network Policy

外部接続が必要な機能は本部Deployment PolicyでON/OFFできる。

例:

- e-Gov
- official local regulation source
- optional external AI
- SMTP
- approved file exchange
- LGWAN adapter

外部へ送信するData categoryを明示し、無制限送信しない。

完全オフラインで外部機能が無くてもCore業務は動作する。

---

## 45. User Experience

1つのWeb Applicationとして見せる。

共通:

- one login
- header
- navigation
- search
- dashboard
- Human Review queue
- user/role state
- notices
- consistent error/409 handling

「Moduleが増えるたび別アプリへ飛ぶ」構造を避ける。

内部実装用語やRule IDを一般画面へ過剰表示しない。
人間が理解できる業務名、根拠、状態、次に必要な操作を優先する。

---

## 46. Module Configuration per Department

本部別に以下を設定可能とする。

- enabled modules
- legal profile
- local regulations/internal rules
- official forms
- approval flow
- permissions
- organization
- duty rules
- minimum staffing
- qualifications
- allowance rules
- budget account hierarchy
- submission types
- deadlines
- equipment mappings
- UI labels
- AI adapters
- update mode
- backup policy

ただしSecurity Core、tenant binding、Audit等の基盤をFeature Flagで無効化してはならない。

---

## 47. Formal Evidence Model

重要なAI/Human処理では次のレイヤーを区別する。

1. Source Evidence
2. Parsed/Derived Evidence
3. AI/Rule Candidate
4. Human Reviewed
5. Official/Verified

CandidateからOfficialへ直接飛ばさない。

可能な限り:

- source document ID
- source hash
- record version
- model
- model version
- rule version
- confidence
- generated_at
- reviewed_by
- reviewed_at
- approved_by
- approved_at

を保存する。

---

## 48. Testing

各Moduleの最低試験:

- CRUD
- RBAC
- tenant boundary
- optimistic concurrency
- audit
- Human Gate
- candidate/official separation
- import
- export
- search
- integration
- invalid data
- source version
- stale evidence
- rollback where applicable

PostgreSQL固有:

- migrations from empty DB
- re-run/idempotency where defined
- constraints
- locking/concurrency
- roles
- tenant identity

Browser:

- main workflows
- permission visibility
- Human review
- form behavior
- stale conflict

---

## 49. AI Benchmark and Acceptance

AI機能は実Referenceで測定する。

対象例:

Drawing:
- geometry
- IoU
- symbols
- equipment
- facts
- area

Audio:
- CER
- speaker error
- uncertainty detection

Evidence comparison:
- Precision
- Recall
- F1
- false positives

実データBaselineの前にProduction Qualityを主張しない。

Acceptance ThresholdはBaseline後にHumanが決定する。

---

## 50. Data Migration

既存台帳・Excelから移行する。

原則:

- mapping
- normalize known fields
- preserve unknown raw values
- immutable new IDs
- legacy IDs retained
- deduplication
- missing detection
- idempotent re-import
- migration evidence

未確認列の意味をAIが推測で正式Mappingしない。

---

## 51. Operational Hosting

役場等の既存Serverを利用できない場合でも、専用親PC/Server機を本部内に設置して運用可能とする。

同一Network外の拠点利用は、承認されたVPN、閉域、LGWAN等のNetwork Architectureに従う。

Browser端末にDBを置かない。

Production Deploymentは本部ごとに:

- OS service account
- DB roles
- environment
- service
- reverse proxy
- TLS
- storage
- backup
- health check

を生成/設定できる。

---

## 52. Release Artifacts

完成時には少なくとも以下をRepositoryまたはRelease成果物として用意する。

- completed source code
- migration set
- release version
- deploy configuration
- sample environment
- initial tenant setup
- initial admin setup
- SYSTEM_ARCHITECTURE
- INSTALLATION
- SERVER_SETUP
- UPDATE_GUIDE
- BACKUP_RESTORE
- ADMIN_MANUAL
- USER_MANUAL
- PERMISSIONS
- DATABASE
- MIGRATIONS
- SECURITY
- TEST_REPORT
- AI_BENCHMARK_REPORT
- KNOWN_LIMITATIONS
- RELEASE_NOTES
- RELEASE_READINESS
- FINAL_COMPLETION_REPORT

可能なら初期導入一式をRelease Artifactとしてまとめる。

---

## 53. Definition of Done

Phase番号の完了をSystem完成としない。

System完成条件:

- External Gate以外の重大Missingなし
- 重大Partialなし
- Duplicate/Conflict/Orphaned解消
- 1つの認証
- 1つの権限基盤
- 1つの監査基盤
- 1つのNavigation
- Module間ID連携
- Empty PostgreSQLから全Migration成功
- Existing DB upgrade success
- Integration Tests PASS
- Full E2E PASS
- CI Green
- Backup/Restore procedure and evidence
- Installation procedure
- Update/Rollback procedure
- User/Admin manuals
- Release package
- Known limitations明示

External Gateは完成報告で別枠表示する。

例:

- Human legal Rule acceptance
- actual production host
- real LAN/TLS/two-client test
- real drawing/audio benchmark
- official original forms not supplied
- organization-specific legal/financial/personnel approvals

External Gateを内部実装Missingの言い訳として使用しない。

---

## 54. Required Cross-module E2E

最低限:

1. Facility
→ Drawing
→ Human Annotation
→ Occupancy classification
→ Required equipment
→ Human Review
→ Equipment registry

2. Document
→ Intake analysis
→ Human classification
→ Submission
→ Facility update
→ Search

3. Incident
→ Dispatch
→ Crew
→ Vehicle
→ Activity
→ Allowance
→ Statistics

4. Emergency
→ Patient
→ Treatment
→ Transport
→ Clinical candidate
→ Human Review
→ Monthly report

5. Fire Investigation
→ Photo/Audio
→ Transcript/Statement
→ Evidence
→ Cause candidate
→ Human Gate
→ Report Template

6. Workforce
→ Roster
→ Dispatch
→ Work result
→ Overtime/allowance integration

7. Fleet
→ Dispatch
→ Mileage
→ Fuel
→ Log

8. Contract
→ Commitment
→ Budget
→ Payment
→ Balance

9. Asset
→ Receive
→ Location
→ Loan/Issue
→ Return/Transfer
→ Inspection/Expiry
→ History

10. Inquiry
→ Evidence
→ Numeric source
→ Draft
→ Human Review
→ Official output

---

## 55. Development Governance

GitHub mainを唯一の実装正本とする。

基盤実装の依存順序は原則として、
tenant identity/境界
→ common data
→ employee/organization/history
→ authentication
→ authorization
→ audit
→ business modules
とする。
既存mainがこの順序を満たしている場合は再実装しない。

開発開始時:

- latest main
- AGENTS.md
- PROJECT_STATE.md
- migrations
- models
- schemas
- routers
- frontend
- tests
- permissions
- audit
- open PR
- merged PR
- CI

を確認する。

既にmainにある機能を再実装しない。

小さなbounded PRを利用できるが、PR完了をSystem開発終了条件にしない。

Migrationはappend-only。
過去Migrationを安易に書換えない。

並行Workはmainを定期refreshし、番号・API・Model競合を避ける。

---

## 56. Priority Rule

仕様が矛盾した場合の優先順位:

1. 本Master Specification v2.0
2. 明示的に承認されたArchitecture Decision / TENANT_OPERATIONS
3. Current Security and Human Gate contracts
4. Module-specific current specifications
5. PROJECT_STATE and completion ledgers
6. Historical Phase documents

古い文書に「利用者が本部を切替」「PostgreSQLは候補」「共有フォルダへPCが直接アクセス」等が残っていても、本v2.0を優先する。

---

## 57. Completion Principle

AIOSの完成とは、AIが何でも自動確定することではない。

AIが:

- 転記
- 検索
- 照合
- 集計
- 不足検出
- 候補生成
- 説明
- 下書き
- Risk提示
- Evidence整理

を担い、人間が正式判断へ集中できる状態を目標とする。

使いやすさをSafetyと同時に要件とし、Human Gateの存在を理由に不必要な二重入力、確認画面、複雑操作を増やさない。

