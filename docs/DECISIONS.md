# Architecture Decision Log

## ADR-001: Local Web Architecture
庁内PCはブラウザを利用し、業務サーバー経由でAPI/DBへアクセスする。JUST Calc/VBA非依存。

## ADR-002: Concurrent Database
PostgreSQLを第一候補とする。共有フォルダ上の単一JSON/SQLiteへの多端末直接書込は採用しない。

## ADR-003: Inspection Ledger is a View, not a Copy
届出受付後に「査察台帳へ転記」するのではなく、対象物DB・設備DB・防火管理DB・届出DB等を査察台帳画面が参照する。受付確定処理で関係テーブルを同一トランザクション更新し、二重入力・転記漏れを防止する。

## ADR-004: Extensible Submission Type Master
消防用設備等点検結果報告、防火管理者、消防計画、火災予防条例関係、消防法令適合通知書関係その他を固定実装せず、届出種別マスタで追加できる。

届出種別ごとに以下を定義可能とする。
- 抽出項目
- 必須項目
- 添付書類要件
- 審査フロー
- 台帳更新先
- 自動更新可否
- Human Gate
- 適用法令/条例ルール

## ADR-005: Official Submission Number
正式な届出番号は既存番号取得システムを正本とする。値は数字のみ保存し、`submission_id` とは分離する。年度・届出種別は別フィールドで保持する。システムは「予防第」「号」等を推測で付加しない。

## ADR-006: Arbitrary File Names
`scan0001.pdf`、`IMG_1234.jpg` 等を正常系とする。ファイル名から業務意味を推測せず、本文/OCR/Vision解析で書類種別・対象物・項目を抽出する。原本ファイル名は監査情報として保持する。

## ADR-007: PDF and Photo Intake
PDFに加えてJPEG/PNG/HEIC等の画像を受付可能とする。複数画像を1件の届出として束ねる。解析用派生画像では回転・傾き・台形・明るさ等を補正可能とするが、原本は不変保存する。ページ順・欠落・重複・読取不能を検出し、人間が確定する。

## ADR-008: No Smartphone in Initial Scope
初期本番対象は庁内PC。個人スマートフォン利用、PWA、QR受付等は除外する。将来、組織管理端末が導入された場合のみ拡張候補とする。

## ADR-009: Managed AI Learning
職員訂正をLearning DBへ蓄積するが、本番AIを即時自己改変させない。Candidateを固定評価セットでChampionと比較し、昇格条件を満たした場合のみ切替える。Rollbackを必須とする。

## ADR-010: Formal Rules are Not Learned Freely
法令・条例・告示・権限・監査・証拠保全ルールはAIの自由学習対象外。管理されたルールVersionとして更新する。


## ADR-011: Emergency Reporting is Database-Derived
`救急報告関係.xlsm` の帳票シートやセルを正本にしない。事案・傷病者・出動隊員を正規化DBへ取り込み、病院別・傷病程度・隊員別・月次/年度累計等はDBクエリから生成する。現行ブックは移行時の回帰比較用Oracleとしてのみ利用する。

## ADR-012: Emergency AI Flags Keep Evidence
CPA、アレルギー、禁忌等のAI/ルール判定は正式値へ直接上書きせず、根拠、生成方式、Confidence、確認状態とともに候補フラグとして保存する。CPAは病名文字列単独ではなく、明示コード・処置・状態等を優先する。

## ADR-013: Emergency PII is Separately Authorized
救急データは個人情報を含むため、通常の対象物台帳権限と分離して `emergency.*` 権限を設定する。集計のみ閲覧できるロールと、個票閲覧可能ロールを分離できること。

## ADR-014: Preserve Legacy Rows Before Full Normalization
Phase 1 imports the current 611 inspection records before every one of the 574 columns is normalized. Core confirmed fields are projected into `facilities`; the complete source row is preserved in `legacy_facility_source_rows.raw_payload`. The 41 `review` mappings remain unresolved rather than guessed.

## ADR-015: Import Source Files Are Evidence
Legacy import workbooks are copied into the server-controlled storage root under a content-hash path. `source_files` stores the SHA-256 and archive path. The source workbook is included in normal storage backup and is not committed to Git.

## ADR-016: Identical Imports Are Idempotent
The pair `(source_kind, sha256)` identifies an import source. Normal re-import of an already completed identical source returns the previous import result without creating duplicate rows. Administrative forced reprocessing is allowed, but unchanged facility/case/patient/crew business rows remain skipped rather than being version-bumped solely because a new import batch exists.

## ADR-017: Extension Intake is Analysis-First
Excel/CSV/PDF/Word/画像/音声その他の新規ファイルは、本番機能へ直接反映しない。原本登録後、解析、既存Schema/画面/業務ロジックとの差分、追加候補、受入条件、Sandbox結果を記録し、Human Gateを経てVersion管理された変更として適用する。

## ADR-018: Human Change Request is a First-Class Entity
職員はAI提案を承認するだけでなく、「この画面のここへ追加」「この帳票とこの項目を連携」等を自然文でChange Requestとして登録できる。Change Requestは影響範囲、リスク、提案変更、受入条件、Sandboxテスト、承認、Deployment、Rollbackを追跡する。

## ADR-019: Official Form Original Has Priority
正式様式が登録されている業務ではAI独自レイアウトを正式帳票として生成しない。PDF/Excel/Word等の原本をDocumentとしてハッシュ保全し、Form Templateは原本Document ID、Version、施行期間、発行元、入力位置、印刷設定、改変方針を保持する。旧Versionは過去案件再現用に残す。

## ADR-020: Contracts Use a Dedicated Human-Gated Module
契約案件、相手方、見積、契約書、仕様書、変更契約、履行・検査・完了・請求関連を専用モジュールで扱う。OCR、転記、計算、差分、不足検出は自動化可能だが、契約相手、正式金額、契約条件、正式文書、契約締結は明示的Human Gateを必須とする。

## ADR-021: Deployment and Rollback are Audited
機能追加の本番反映はChange Requestの承認後のみ記録可能とし、release version、previous version、migration version、feature flag、evidenceを保存する。Rollbackも別Deploymentとして記録し、関連Feature Flagを停止可能とする。