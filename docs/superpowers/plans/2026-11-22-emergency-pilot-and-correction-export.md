# ZBook実機準備と訂正確認用PDF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 実機診断の入口と、表示中の監査結果を原本上に記載したPDF出力を実装する。

**Architecture:** 現行専用RBAC/vaultとLinux子プロセスを維持。機密値は固定DTOだけをrendererへ渡す。診断は環境を変更しない独立CLI。

**Tech Stack:** Python3.11+, PyMuPDF, FastAPI, 既存のJavaScript UI。診断は標準ライブラリのみ。

**Spec:** docs/superpowers/specs/2026-11-22-emergency-pilot-and-correction-export-design.md

## Global Constraints

- 実帳票/個人情報/学習例/秘密値をGit・CIへ送らない。合成fixtureだけを使う。
- 既存8787/8796/8797、既存worktree、既存VMを変更しない。
- 原本は不変。未読・未検査・位置不明を成功へ補完しない。
- native読取は既存Linux子プロセス隔離を維持。Windows対応を偽装しない。
- 現地未測定の状態を未測定と表示。再学習を必須の残要件として保持する。

## Review Focus

1. 生成中にセッション/職員/権限/版/設定が変化した場合は機密PDFを返さない。
2. 過去run、別AIrun、取り消された判断を新しいPDFへ混入しない。
3. 回転/crop/EXIF後の原本と枠、日本語長文とページ送りが一致する。
4. コマンド失敗/権限不足を不在や安全と断定せず、パス/秘密値を診断へ反射しない。
5. UIの遅延応答・再認証・旧版化後に、古いPDFを保存しない。

### Task 1: 読取専用の実機診断

**Files:** scripts/check_emergency_workstation.py; backend/tests/test_emergency_workstation.py
**Interfaces:** inspect_workstation(...)->dict; main(argv=None)->int。標準ライブラリのみ、JSON stdout。
- [ ] 時間切れ・巨大出力・不正型・sentinel秘密値・権限不足の失敗試験を書く。
- [ ] 未実装の失敗を確認する。
- [ ] OS別の限定採取と固定形式/固定エラーの出力を実装する。
- [ ] 限定試験とこのLinux環境での読取専用実行を確認し、ZBook未実測を残す。

### Task 2: 固定した検査結果から訂正確認用PDF

**Files:** backend/app/emergency_audit_pdf.py; backend/app/emergency_audit_export.py; emergency_audit_schemas.py; routers/emergency_audit.py; emergency_audit_worker.py; emergency_reader_process.py; tests/test_emergency_audit_pdf.py; tests/test_emergency_audit_pdf_api.py
**Interfaces:** POST /emergency/audit/reports/{report_id}/annotated-pdf body {run_id,expected_version}; attachment application/pdf emergency-review.pdf。
- [ ] 権限/版/設定/生成中失効、履歴混入、原本不変の失敗試験を書く。
- [ ] 原本50頁/12Mpx、120秒、PDF32MiB/付録50頁の制限と子プロセスmodeを追加する。
- [ ] 凍結データの許可リストDTO、原本画像、番号枠、日本語付録、未検査の明示を実装する。
- [ ] 対象試験と合成PDFの保存・レンダリングを確認する。rootも画像を目視確認する。

### Task 3: 利用者画面

**Files:** frontend/emergency-audit.html; frontend/emergency-audit.js; backend/tests/test_emergency_audit_browser.py
**Interfaces:** Task2 API。表示名「訂正確認用PDF」、説明「表示中の検査の範囲を出力」。
- [ ] export権限、未検査/旧版、二重クリック、遅延応答と失権の回帰を書く。
- [ ] 保存中の状態管理とBlob破棄、同一run/versionの確認を既存download形式へ接続する。
- [ ] 実ブラウザの既存訂正ループにPDF取得/ヘッダー/中身の確認を追加する。

### Task 4: 仕様・利用手順・検証証拠

**Files:** docs/SPECIFICATION.md; PROJECT_STATE.md; docs/emergency/REPORT_CHECK_GOAL.md; AUDIT_API_V1.md; AUDIT_OPERATIONS.md; ZBOOK_PILOT.md; MODEL_RETRAINING.md
- [ ] 利用者の必須再学習・OA書戻し不要・正式帳票/5指標実測の要件を正本へ反映する。
- [ ] ZBook診断1回の手順と、本体/ゲスト/モデル/帳票/5指標の未確認を記録する。
- [ ] 独立レビュー・必要CI・日本語PDF目視を確認し、対象HEADをPRへ記録する。

## External inputs needed for actual execution

ZBookの現在の診断結果、使用可能なLinux実行経路、非公開の正式帳票/現行資料、独立確認した学習正解。これらがない間、実機配備・実学習・精度改善を完了にしない。実機の初期診断を利用者に依頼するときは、読取専用スクリプトを具体的に渡す。
