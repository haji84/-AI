# Master Specification v2.0 統合差分

基準:
- 旧 docs/SPECIFICATION.md v1.8
- GitHub後発仕様: TENANT_OPERATIONS / RUN_A / RUN_B / task briefs / merged implementation contracts
- 2026-10-06までに会話で確定した消防業務AIOS要件

本書はレビュー用差分であり、正式仕様は docs/SPECIFICATION.md v2.0。

## 1. v2.0で正式追加した領域

### Product/Architecture
- モジュール型AI業務OSとしての全体定義
- 本部ごとのModule選択
- 本部別設定の分離
  - 条例/規則/内規
  - 正式様式
  - 承認フロー
  - 権限
  - 予算階層
  - 勤務/手当条件
  - UI設定
- 事実一元管理と訂正履歴

### Deployment
- Cloud
- Internet-connected Local
- Closed-network Local
- Fully Offline
- LGWAN等
- 共通コード + Deployment Profile
- 既存サーバーを使えない場合の専用親PC/Server運用
- PC Browser正式クライアント
- ClientごとのInstall/Update不要

### Release/Update
- Server-side update
- Browser reloadによる反映
- 本部別release適用
- Feature Flag
- Rollback
- Change Request
- Sandbox/Test/Human Gate/Deployment

### Common foundation
- 職員とAccountの分離
- 組織/本務/兼務/異動履歴
- 有効日権限
- temporary/acting permissions
- password history/expiry
- session revoke
- Personal work queue
- Human-readable evidence表示方針

### Operations
- Incident/Dispatch
- Vehicle/Fleet
- Operational Assets/Inventory
- Workforce/Duty
- Budget/Finance
- Council/Inquiry
- Cross-module statistics/annual report/surveys
- Dashboard

### Prevention/Legal
- Hazardous materials
- Violation/corrective action
- Signed offline legal Update Bundle
- 法令改正影響分析
- tenantとjurisdictionの分離

### Drawing
- Human Annotation editing
- snapping
- Undo/Redo
- calibration
- area summary
- overlap QA
- known floor target comparison
- reviewed Reference revision
- Drawing QA
- Benchmark
- occupancy classification
- equipment-less drawingへの必要設備/配置提案

### Emergency
- treatment
- transport
- clinical candidate
- CPA evidence aggregation
- allergy
- Human clinical review
- privacy-separated aggregate
- formal report/post-review/lifesaving form integration
- correction history

### Fire Investigation
- Photo intelligence
- Voice/speaker/uncertainty
- Evidence comparison
- Timeline
- Cause candidate vs official cause
- Evidence-linked report drafting
- official form output

### AI Platform
- Learning DB
- Champion/Candidate
- fixed evaluation
- promotion/rollback
- autonomous task framework
- natural-language system change requests
- Goal→Plan→Execute→Verify→Fix→Evidence→candidate write-back

### Production/Completion
- Release artifacts
- Full E2E
- PostgreSQL tests
- Browser tests
- Backup/Restore evidence
- Definition of Done
- External Gate separation

## 2. 古い仕様を明示的に上書きした項目

### PostgreSQL
旧:
PostgreSQLを第一候補。

v2:
Production PostgreSQL必須。
SQLiteは開発/テスト限定。

### tenant切替
旧:
利用者が適用消防本部を選択できるように読める記述が存在。

v2:
Runtimeは1本部UUIDへ固定。
HTTP利用者は本部/DB/Storageを選べない。

### 共有フォルダ
旧:
共有フォルダ中心の表現。

v2:
Server-managed Document Storage。
Client PCはWeb/API経由。

### Multi-headquarters update
旧:
共通更新を全利用者へ一斉反映するように読める余地。

v2:
同一本部内はServer更新1回で全Browserへ反映。
別本部は共通Releaseを利用しても本部単位で承認・切替・Rollback。

### Budget hierarchy
旧/会話:
款項目節細節、事業→節等の表現が混在。

v2:
固定列にせず本部設定可能な可変階層Account Master。

## 3. 旧v1.8の内容で維持した重要要件

- 原本不変
- SHA-256
- Human Gate
- AI candidate/official separation
- AI judgment Level 0-3
- AI停止時業務継続
- 楽観ロック
- 不変ID
- 論理削除/復元
- e-Gov/地方例規
- Rule versioning
- 文書内容ベース分類
- 正式届出番号をAI採番しない
- Gitへ実運用データ/秘密を置かない
- 正式様式原本優先
- Module Registry/Feature Flag/Rollback
- Champion/Candidate

## 4. 後発GitHub設計から取り込んだSecurity強化

- department UUID binding
- DB/Storage/Runtime identity check
- privilege-separated PostgreSQL roles
- server-selected database
- tenant-bound backup/restore
- restore preflight
- unsafe archive/path rejection
- signed legal update bundle
- trusted signing key
- origin/redirect validation
- Human review stale-evidence rejection
- PostgreSQL/browser CI gates
- per-department automatic paired backup
- runtime/backup/restore/migration maintenance exclusion
- maintenance-time retry-safe HTTP 503 behavior

## 5. 今後の開発者向けルール

古いPhase資料やTask briefに本書と矛盾する表現が残っていても、Master Specification v2.0を優先する。

実装状況はPROJECT_STATE等を使用し、本書へ「未実装だから仕様ではない」という扱いをしない。

Missing/Partialは仕様から削除せず、完成まで実装対象として残す。


## 6. 会話仕様の残差追記

Master Specification v2.0統合後に、過去会話との再突合で以下を追加確認した。

- 正式届出番号は原則数字のみ。年度・届出種別は別fieldで保持し、「予防第」「号」等をAIが推測付加しない。
- 人事異動通知・辞令・配置表等をDocumentとして解析し、所属/役職/兼務/発令日候補をHuman Review後に人事履歴へ反映できる。
- Human Change RequestのImpact Analysisに計算ロジックとWorkflow/承認フロー候補を含める。
- 救急既存ブックの最新既知入力構成は、事案117列、救護者160列、出動隊員24列。Importerは列数固定にせずheader監査とraw evidence保持を優先する。
- 過去の「出動隊員7列」表現は旧確認時点の記述として扱い、最新既知構成を上書きしない。

これらも正式仕様 `docs/SPECIFICATION.md` に反映済み。
