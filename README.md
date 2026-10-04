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


## Phase 1 開発起動

Phase 1 backend is under `backend/`. Production target is PostgreSQL; SQLite is only a local test fallback.

```bash
cd backend
python -m pip install -e .
cp .env.example .env
# repo rootからmigration/RBAC seed
cd ..
PYTHONPATH=backend python scripts/migrate_database.py
PYTHONPATH=backend python scripts/seed_rbac.py

# 初回管理者
cd backend
python -m app.bootstrap --username admin --display-name 管理者
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Client PCs only open the server URL in a browser. Operational XLSM/PDF/photo/audio data must never be committed to Git.

## Phase 1 verification

PII-safe legacy import verification:

```bash
PYTHONPATH=backend python scripts/verify_phase1_legacy_imports.py \
  /path/to/inspection.xlsm /path/to/emergency.xlsm
```

LAN/PostgreSQL deployment steps are in `docs/phase1/LAN_DEPLOYMENT.md`.


## Phase 2 UI

`/ui/` から防火対象物の検索、詳細、新規登録、編集、廃止・復元、変更履歴を操作できる。
旧査察台帳の確認済み基本項目は正規化し、意味未確定項目は原値の閲覧専用とする。
既存DBをPhase 2構造へ移行した後は `scripts/backfill_phase2_facility_details.py` で保存済み原行から正規化可能。

Phase 2検証:

```bash
PYTHONPATH=backend python scripts/verify_phase2_facilities.py /path/to/inspection.xlsm
```