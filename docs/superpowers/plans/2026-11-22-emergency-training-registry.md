# Emergency Training Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 独立正解と原本familyを暗号化して登録し、重複・改訂の分割漏えいを拒否する固定datasetを作る。

**Architecture:** 既存救急監査の権限、失効再確認、private route、AES-GCMを再利用する。
familyは報告書に固定し、正解とdatasetは不変行として新版で訂正する。
実機・正式資料・モデルの未確認状態はそのまま残す。

**Tech Stack:** 既存Python 3.11、FastAPI、Pydantic、SQLAlchemy、PostgreSQL 16、AES-GCM、pytest。

**Spec:** `docs/superpowers/specs/2026-11-22-emergency-training-registry-design.md`

## Global Constraints

- 原本、個人情報、教師テキスト、重み、診断の生出力を公開GitHub/CIへ入れない。
- 既存の8787/8796/8797、VM、WSL、既存checkoutとサービスを変更しない。
- 権限追加や正式資料の承認を自動で行わない。実測と合成試験を区別する。
- DBはサーバー経由、migrationは追記のみ。実機の資源からモデルを決める。

## Review Focus

- 同一職員の別アカウントによる独立確認の偽装を拒否する。
- 改訂/同一原本の複製を異なるfamily・分割へ入れない。
- 未確定・判読不能・非印字を正しい負例へ変換しない。
- private入力をエラー、ログ、平文DBへ反射しない。
- 古い正解・設定失効・原本改変・権限喪失で新datasetを固定しない。

## Task 1: APIとデータ契約をテスト先行で追加

**Files:** `backend/app/emergency_training_schemas.py`、`emergency_training_models.py`、
`emergency_training_service.py`、`routers/emergency_training.py`、
`backend/tests/test_emergency_training.py`、`emergency_vault.py`、`main.py`。

**Interfaces:** `POST /emergency/audit/training/families` はfamily_idとreport_ids。
`POST /emergency/audit/revisions/{id}/training-truth` は転記・訂正・位置・根拠と原本確認。
`POST /emergency/audit/training/datasets` はtruth_idsとfamily_splits、前処理digest。
GETは現時点で全対象原本への権限を持つ場合のみ返す。

- [x] 合成API試験を追加し、未実装の404で失敗することを確認。
- [x] 原本作成者・同一職員の自己正解登録を403、古い版を409にする。
- [x] family所属と既知重複の検証、正解の暗号化・追記訂正を実装。
- [x] 固定manifestとfamily分割の不変性、未確定ラベルの隔離を実装。
- [x] 同じ試験を実行し、原本/ラベル/ログ/一般Documentの境界を確認。

## Task 2: PostgreSQLの追記・不変性

**Files:** `db/migrations/061_emergency_training_registry.sql`、
`backend/tests/test_emergency_training_postgres.py`。

**Interfaces:** Task 1のORMテーブルを060以降へ追加。既存のmutation guardが
職員管理と直列化するため、所属・正解・manifestの確認と保存を同一transactionで行う。

- [x] 060からのupgrade、再実行、DB側UPDATE/DELETE拒否の試験を先に書く。
- [x] 不足する表の失敗を確認し、追記SQLと不変triggerを実装。
- [x] 専用使い捨てPostgreSQLで実行。既存DBをmigrationしない。

## Task 3: 回帰・現状記録・同じPR系列への保存

**Files:** `docs/emergency/TRAINING_REGISTRY.md`、`MODEL_RETRAINING.md`、
`CODEX_ZBOOK_HANDOFF.md`、対象の開発記録。

- [x] 対象API・診断・PDF・計測の回帰試験と既存バックエンドの標準試験を実行。
- [x] 差分をレビューし、不備はRED→GREENで修正。
- [x] ZBook/正式帳票/実再学習/実測/最新Checksの未確認を明記し、機微情報を除いて保存。
- [x] 同じPRへの送信対象を確定。mainへの統合は含めない。remote refの送信結果は別に確認する。

## 実行記録

レビュー差分: 固定分割をdatasetの親指定に依存させず、4番目の不変表に固定する。
職員情報は原本登録時の読取jobを使用。様式適用日と判定日は別で、主/副根拠原本を検証する。
同一欄の複数位置、未読familyの隔離、原本複製の重複排除を保持する。
manifestの根拠proofは重複保存せず、1回の固定処理内で原本検証を共有する。

Ruling: 利用者の「計画だけで止まらず実行」と既存引継ぎ§5に従い、
追加の設計選択待ちを設けずこの限定範囲を同一セッションで実装する。
ZBookへの接続方法のみ非同期確認中で、それに依存する実行は行わない。
作業場所は `/workspace/emergency-pr142`、開始headは `6d80334aae7b85619c4fabcbc64befdb93010353`。
既存API/PDF/傾向集計のbaselineは67 passed。実機・実精度の証明ではない。
