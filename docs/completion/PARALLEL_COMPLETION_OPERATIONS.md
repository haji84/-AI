# 消防AIOS 並列完成開発運用契約（v1）

> 設計・運用ルール。**この文書を追加するだけではAI workerは起動しない。** GitHub Issues/PR/Actionsは実行・検証の記録であり、自律開発エンジンや常駐スケジューラではない。

## 正本と開始条件

- コード正本は `main` の固定 SHA と tree。要件正本は `docs/SPECIFICATION.md`。進捗は `docs/completion/CURRENT_COMPLETION_LEDGER.md` の**監査対象SHAを確認して**参照。古い `MASTER_FEATURE_MATRIX.md` は履歴。
- 着手時に `main`、`AGENTS.md`、open PR、直近merge、migration一覧、対象ファイルと既存テスト、CI、他レーンの所有範囲を再取得。
- 既存実装の修復・再利用を優先。未mergeの旧Run A/Bチェックポイントは正本と区別し、重複追加・migration再利用を禁止。
- Local WorkerやWork/Codexが複数並走しても**単一PRのGreenは全体完成を意味しない**。

## 最初の4レーン（互いの共有ファイルを直接編集しない）

| レーン | 初期目標 | 第一所有領域 | 担当範囲外・衝突時の対応 |
|---|---|---|---|
| A 査察先行利用 | 査察/防火対象物の独立受入、査察CSV/期限・現場導入チェック | inspection/facility専用backend/frontend/test、導入QA文書 | 共通shell、RBAC、migration追加は統合担当へ申請 |
| B 救急 | 救急チェック、訂正履歴、帳票候補と検証 | emergency専用router/service/schema/test、QA | 共通forms/documentsはインターフェース依頼 |
| C 勤務・統計 | 承認済勤務実績/勤務結果と統計の残差 | workforce/statistics専用実装とテスト | A/Bの業務テーブルには触らない |
| D AI・法令 | 図面・写真・音声worker adapter、法令Ruleのhuman-reviewed候補・benchmark | drawing/fire/legal専用worker/adapter/test | 正式判断や本部運用RuleはHuman Gate。共通runtime追加は統合担当へ |

各レーンは独立branch `completion/<lane>/<issue>-<short>` と個別PR。機能所有者は各PRで `OwnedPaths`、`TouchedSharedPaths`、`MigrationRequest`、`SourceMainSHA` を宣言する。作業順に担当表を更新する（表は永久占有ではない）。

### 統合担当（専用の直列キュー）

`backend/app/main.py`、共通session/authz、`frontend/index.html`、`docs/completion/CURRENT_COMPLETION_LEDGER.md`、RBAC/module seed、`db/migrations/`、共有document/form/search、全体workflow・releaseは**統合担当のみ**更新する。各レーンは必要な変更をPR内の依頼・独立adapterとして提示し、統合担当が最新mainへ取り込む。単に別ブランチだから安全とは扱わない。

マイグレーション番号は統合担当がmain最新リストを見て予約し、**番号を先取りした並列PRをmergeしない**。レビューでスキーマ変更を伴わない別案が可能か確認する。

## PR単位の状態機械

`READY → CLAIMED → IMPLEMENTED → TESTED → REVIEWED → INTEGRATION_READY → MERGED → VERIFIED_MAIN → LEDGER_UPDATED`

`BLOCKED` は理由・失敗ログ・次の一手を保持。状態の推定や未実施のGreen宣言は禁止。

各PRに記録すること：
1. Issue / Scope / SourceMainSHA / OwnedPaths / SharedPath requests / Migration request
2. 変更前に再現した失敗（可能ならRED）と最小修正
3. 受入テスト：unit、対象API、PostgreSQL、本物のChromium（該当時）、権限・同時更新・原本保持・tenant境界
4. exact-head CI URL、成功/失敗/skip内訳、レビュー指摘と修復証拠
5. main最新との三者差分、競合処理、反転・戻し方、既知のPartial
6. merge SHA、post-merge main CI URL、台帳差分

**Green gate**: exact PR headの必須CIがすべて成功し、skipを合格に含めず、重大レビュー指摘が閉じており、最新mainに対する競合とmigration衝突を確認。統合後は新mainのCI成功を再確認し、それまでは `VERIFIED_MAIN` としない。CIログ不達・403/404なら原因不明のままmergeしない。

## タスク選択アルゴリズム

1. 現在のCompletion LedgerからInternal Partialのみ取り出し、利用価値・依存数・変更の衝突危険・テスト可能性で並べる。
2. まず査察先行受入の経路と全体のcritical path（共通基盤・10本E2E・Release）を優先する。
3. 互いに独立なレーンへ1件ずつ配布。タスクの共有ファイル・migration変更が重複するなら並行実装せず、統合担当で先にInterface Contractを定義する。
4. 各レーンは自分のPRが `VERIFIED_MAIN` になるまで新規共有基盤PRを開始しない。小さい追加課題はIssueに積む。
5. Release成果物・10本E2E・差分監査・最終57章判定は統合担当の継続タスクとして常に追跡する。

## Human Gate（削減禁止）

- 法令/条例、設備の適否、火災原因、医療上の正式判断、予算・支払、職員配置・給与・権限の正式決定
- 実原本/個人情報の取込と外部転送、バックアップ鍵やOwner Vaultの使用
- 本番環境への公開・切替、破壊的操作、重大なセキュリティ境界変更

合成データ実装・内部レビュー・テスト・修復・PR作成は追加承認なしでよい。Human承認の要否は **意味と影響** で判定し、コード操作を細分化して迂回しない。

## 事故予防と実行上の限界

- 5つのdeployment profile、実LAN/正式原本/2PC実機、独立バックアップ復元、実モデルbenchmarkは独立に検証してから本番判定。
- GitHub Actionsの同時実行数・branch protection・required checks・CODEOWNERS・secrets・AI worker実行基盤の有効性は別途確認が必要。**この文書はそれらが設定済みとは主張しない**。
- AIOSの運用元DB・原本・tenant secretを開発Issue/PR/CIログへ貼らない。
- 並行担当が実際に動くには、各Work/Codexセッション（または承認済み自律実行エンジン）を起動し、各レーンのIssueを与える必要がある。
