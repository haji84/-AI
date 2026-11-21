# fire-ai-local

消防業務Local AI統合システム。

庁内LAN上で複数職員がブラウザから同時利用し、防火対象物台帳、査察、届出受付、PDF/画像解析、図面解析、消防用設備・必要書類判定支援、火災調査、写真整理、録音・供述整理、救急報告・集計、AI横断検索、自己学習を統合する。

## 正本

- システム仕様: `docs/SPECIFICATION.md`
- 設計判断: `docs/DECISIONS.md`
- Phase 0監査: `docs/phase0/PHASE0_AUDIT.md`
- 救急追加監査: `docs/phase0/EMERGENCY_REPORT_AUDIT.md`
- 旧→新DBマッピング: `docs/phase0/legacy_to_target_mapping.csv`
- DB草案: `db/schema_phase0_draft.sql`
- 現在状態: `PROJECT_STATE.md`

## 基本原則

1. JUST Calc / Excelマクロを利用条件にしない。
2. 業務データはGitHubへ保存しない。
3. 正式な届出番号は既存番号取得システムを正本とし、数字のみ保持する。
4. 受付書類は任意名のPDF・画像に対応し、ファイル名ではなく内容を解析する。
5. 受付確定後、該当防火対象物の同一DBを更新し、査察台帳表示へ即時反映する。二重転記しない。
6. AI停止時も新規・編集・保存・廃止・受付等の基本業務を継続できる。
7. 法令・権限・証拠原本・正式判断はAIの自己改変対象にしない。
8. Local AIの学習はLearning DB → Candidate → 評価 → Champion昇格 → Rollback可能、の管理型とする。

## 開発フェーズ

- Phase 0: 現行台帳監査・DB設計・移行マッピング
- Phase 1: 共通基盤（DB、認証、権限、監査、同時編集）
- Phase 2: 防火対象物台帳
- Phase 3: 査察
- Phase 4: 届出受付・PDF/画像
- Phase 5: 法令ルール・消防用設備判定支援
- Phase 6: 図面AI
- Phase 7: 火災調査
- Phase 8: 写真AI
- Phase 9: 音声・供述AI
- Phase 10: 横断AI検索
- Phase 11: 学習基盤
- Phase 12: AI自律タスク
- Phase 13: 本番評価・改善


## 起動・導入

- localhostでの合成データ確認と本部別PostgreSQL導入: [導入手順](docs/release/INSTALLATION.md)
- 現行の本番配置契約: [本部別運用](docs/architecture/TENANT_OPERATIONS.md)、[設定一式の生成](deploy/tenants/README.md)
- 固定commitのソース配布: [リリース候補](docs/release/README.md)、[受入確認](docs/release/RELEASE_READINESS.md)

コマンドはreleaseルートから実行し、設定を環境変数として明示します。`.env` はカレントディレクトリ基準です。`backend/.env` を置いてもルートからのmigrationには読み込まれません。

本番は本部専用PostgreSQL・UUID・原本保存先・通常/移行DB roleを使用します。SQLiteはlocalhostでの開発・合成テスト専用です。通常職員のPCはサーバーURLをブラウザで開くだけです。実運用XLSM/PDF/写真/録音、DB、資格情報をGitや配布物へ入れないでください。

## 救急報告書の提出前チェック

「救急業務」から「報告書をチェック」(`/ui/emergency-audit.html`) を開きます。専用サーバー設定と権限が必要で、初期状態では無効です。PDF・画像の一括取込、原本表示、読取候補の確認、根拠付きチェック、訂正版・再チェック、独立確認、訂正傾向、5指標への測定記録出力を接続しています。

- [構築・操作・更新・復旧](docs/emergency/AUDIT_OPERATIONS.md)
- [APIと保存・権限の契約](docs/emergency/AUDIT_API_V1.md)
- [5指標の測定範囲と判定](docs/emergency/ACCEPTANCE_MEASUREMENT.md)
- [実装状態と未検証の受入条件](docs/emergency/REPORT_CHECK_GOAL.md)

Linuxサーバーで読取処理を行い、利用者PCにはOCRやVBAを要求しません。AIは任意のローカルモデルを接続します。正式な様式・ルール・モデルは本部内で検証して設定し、候補や読取不能を「問題なし」に変換しません。実データでの訂正率低下や本番導入済みを宣言する機能ではありません。

## Phase 1 verification

PII-safe legacy import verification:

```bash
PYTHONPATH=backend python scripts/verify_phase1_legacy_imports.py \
  /path/to/inspection.xlsm /path/to/emergency.xlsm
```

現行のLAN/PostgreSQL導入は `deploy/tenants/README.md` を優先します。`docs/phase1/LAN_DEPLOYMENT.md` は初期Phaseの履歴資料です。


## Phase 2 UI

`/ui/` から防火対象物の検索、詳細、新規登録、編集、廃止・復元、変更履歴を操作できる。
旧査察台帳の確認済み基本項目は正規化し、意味未確定項目は原値の閲覧専用とする。
既存DBをPhase 2構造へ移行した後は `scripts/backfill_phase2_facility_details.py` で保存済み原行から正規化可能。

Phase 2検証:

```bash
PYTHONPATH=backend python scripts/verify_phase2_facilities.py /path/to/inspection.xlsm
```
