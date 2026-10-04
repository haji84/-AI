# Phase 0 現行査察台帳監査・DB設計報告

対象ファイル: `★新査察台帳システム.xlsm`
監査日: 2026-10-03
状態: Phase 0 基本監査完了 / 詳細項目の一部は実装時確認対象

## 1. 結論

現行台帳はブラウザ業務システムへ移行可能。既存Excelの「DB保存」をそのまま574列のテーブルとしてコピーする設計は採用しない。

現行の横持ち反復データ（階別、設備1～7、防火管理者1～3、条例等1～6、備考1～15、指導書1～76）を、1件1行の履歴・明細テーブルへ正規化する。

既存の内部キーは全611対象物で一意であり、移行時の照合キーとして有用。ただし新システムの正式主キーには新しい不変IDを発行する。

## 2. 現行ブック構成

| シート | 実使用範囲 | 役割 |
|---|---|---|
| 一覧表 | A1:AAA256 | 令別表等の一覧出力 |
| 査察台帳 | A1:BC395 | 画面・帳票・編集UI |
| システム管理 | A1:P121 | 対象物抽出、重複判定等の補助領域 |
| DB保存 | A1:VB698 | 主データ保存 |
| マスタ | A1:C31 | 良/不良/未提出、令別表区分等 |

## 3. DB保存の実態

- 物理列数: 574列（A～VB）
- 実データ対象物: 611件
- 内部キー非空: 611件
- 内部キー重複: 0件
- 旧定義番号: 最大562まで存在
- 実際に名称が付いている主要領域: SH列付近まで
- SI～UR: 旧予約フィールドでヘッダー・実値なし
- US～VB: 末尾空列

したがって、574列すべてが意味のある業務項目ではない。

## 4. VBA依存機能

フォームボタンから以下のマクロが呼び出されていることを確認した。

| 画面 | ボタン | マクロ |
|---|---|---|
| 査察台帳 | 新規作成 | btn_New |
| 査察台帳 | 保存 | btn_Save |
| 査察台帳 | 廃止 | btn_Delete |
| 管理系 | 重複一覧作成 | CreateDuplicateFacilityList |
| 管理系 | 保存 | ApplyDuplicateJudgement |
| 管理系 | 令別表抽出 | CreateFacilityListByCategory |
| 管理系 | 廃止一覧 | CreateDeletedFacilityList |
| 管理系 | 点検結果報告 一覧作成 | CreateInspectionReportBulkList |
| 管理系 | 防火管理者 一覧作成 | CreateManagerBulkList |

VBAプロジェクトにはThisWorkbook、UserForm1、複数Sheetモジュール、Module1～Module15等が存在する。

新システムではこれらをVBA移植せず、API/DBトランザクション/検索クエリとして再実装する。

## 5. 数式依存

DB保存には約2,878個の数式セルが存在する。主要な計算列は以下。

- 延面積
- 床面積合計
- 収容人員合計
- 従業員合計
- 総収容人員等

新DBでは生データと派生値を区別し、合計値はサーバー側計算またはDBビューで再計算する。旧合計値は移行検算用として保持可能。

査察台帳にはSUM/VLOOKUP等の数式があり、DB保存を参照する補助領域が存在する。画面表示ロジックはWeb UI/APIへ置換する。

## 6. 正規化が必要な主な横持ち領域

### 階別情報
1～7階が列として固定されている。

新設:
- facility_floors
- facility_floor_materials

階数上限をDB構造から撤廃する。

### 消防用設備
設備1～7 × 検査年月 × 各階状態で固定されている。

新設:
- equipment_types
- facility_equipment
- facility_equipment_floors
- equipment_inspection_reports

設備数上限を撤廃する。

### 条例・届出・検査系
6スロットの横持ち。

新設:
- facility_regulated_items

1件1行で履歴管理する。

### 防火管理関係
3人分の氏名・役職・選任届・消防計画を横持ち。

新設:
- fire_management_assignments
- fire_plans
- submissions

### 過去火災情報
4行の自由記述欄に既存火災履歴が存在する例を確認。

新設:
- fire_cases
- fire_case_legacy_notes

既存自由記述は原文保存したうえで構造化候補を生成する。

### 備考
15行固定。

新設:
- facility_notes

### 指導書
指導書1～76について、件名・交付日・内容の3列セットを横に保持しており、最大228列を消費している。

新設:
- guidance_records

1件1行に変更し、76件上限を撤廃する。

## 7. データ品質リスク

移行前に自動クリーニング＋人間確認が必要。

確認できた代表例:
- 面積に `㎡`、`㎥`、説明文が混在
- 収容人員/従業員数に `名`、漢数字、用途らしき文字が混在
- 日付にExcelシリアル値、和暦文字列、`同上`、年月のみ等が混在
- 地上階数に `中2` 等の例外値
- 名称単独の重複は存在するが、名称＋所在地では今回確認範囲で重複なし
- 旧複合キーに1件の重複値を確認したため、旧複合キーを新主キーには使用しない

## 8. 主要識別子

`DB保存!IP` の内部キーは611件すべて非空・重複なし。

移行方針:

- 新 `building_id`: UUID等を新規発行
- `legacy_internal_key`: 現在の内部キーをそのまま保存
- `legacy_serial_no`: 現在の整理番号を保存
- 令別表変更等で識別子が壊れない構造にする

## 9. Target DB（Phase 0時点）

### 共通
- employees
- user_accounts
- roles
- user_roles
- audit_logs

### 対象物
- facilities
- facility_versions
- facility_contacts
- facility_classifications
- facility_floors
- facility_floor_materials
- construction_records
- construction_events

### 設備・点検
- equipment_types
- facility_equipment
- facility_equipment_floors
- facility_power_systems
- equipment_inspection_reports
- inspection_reporting_profiles

### 防火管理・届出
- fire_management_assignments
- fire_plans
- submission_types
- submissions
- submission_files
- submission_reviews
- facility_regulated_items

### 査察・指導
- inspections
- inspection_findings
- guidance_records
- facility_notes

### 文書・図面
- documents
- document_versions
- drawings
- drawing_analyses

### 火災調査
- fire_cases
- fire_case_people
- fire_case_timeline
- fire_case_legacy_notes
- photos
- photo_analyses
- audio_files
- transcripts
- statements

### AI/法令
- legal_rules
- legal_rule_versions
- ai_results
- ai_feedback
- ai_learning_data
- ai_models
- ai_tasks

## 10. 共有フォルダ設計

共有フォルダにDB本体を1ファイルとして置き、複数PCが直接更新する設計は採用しない。

推奨:

```text
庁内LAN
├─ Local Web/API Server
│  ├─ PostgreSQL
│  ├─ Local AI
│  ├─ OCR / Speech / Vision
│  └─ Rule Engine
│
└─ Shared Storage
   ├─ documents/
   ├─ drawings/
   ├─ photos/
   ├─ audio/
   ├─ exports/
   └─ backups/
```

各利用PCはブラウザ経由でサーバーへアクセスする。

## 11. 競合制御

各更新対象に `version` を保持する。

- A職員: version 8を取得
- B職員: version 8を取得
- A職員保存 → version 9
- B職員保存 → 409 Conflict
- 差分を表示して再確認

これにより後勝ち上書きを防止する。

## 12. Phase 0成果物

- 消防業務ローカルAI 統合仕様書 v1.1
- 現行台帳監査報告
- DB全574列一覧
- 旧列→新DBマッピング初版
- Target DB SQLドラフト

## 13. Phase 0残確認事項

以下は実装開始前または移行テストで確認する。

1. DB保存 GE～GJ の1F～6F別項目の正式意味
2. HU～HW の液化石油ガス関連補助3項目の正式意味
3. 建築年月日①/②と既存・増築欄の運用ルール
4. 「内容現在」「区分」等の一部旧項目の正式定義
5. 廃止データの現在のVBA内部状態・保存方法
6. 指導書欄の件名/交付日/内容に混在する担当者表記の分離ルール

これらは不明なものを推測で確定せず、旧データを原文保存した状態で新DBに移行可能な設計にしておく。

## 14. Phase 0判定

Phase 0の「現行構造把握・移行方針・Target DB骨格」は完了。

次工程はPhase 1として、Local Server + PostgreSQL + 認証/権限/監査ログの最小基盤を作り、その上で611件を読み込む移行プロトタイプを作成する。