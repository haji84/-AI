# Personnel Document Human Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 原本人事Documentから将来日付の所属・役職・兼務候補を示し、Human確認と別の適用操作を経て既存人事履歴へ反映する。

**Architecture:** 既存Document、Employee、OrganizationUnit、EmployeeAssignmentとadministration.assignを再利用する。候補は独立のpersonnel_document_proposalsに保存し、原本SHA・抽出根拠・職員版・組織版・before/afterを保持する。AIによるRole決定や未知コード推測は実装せず、完全一致の既知コードだけを解決する。

**Tech Stack:** 既存FastAPI/SQLAlchemy/Pydantic、PostgreSQL migration055、SQLite合成試験、本番JavaScriptとCI Chromium。依存追加なし。

**Spec:** docs/SPECIFICATION.md §5–9、AGENTS.md、docs/completion/COMPLETION_BASELINE_20261007.md Chapter6、docs/architecture/TENANT_ISOLATION_DECISION.md。

## Global Constraints

- 実運用データ、個人情報、PDF原本、写真、録音、既存xlsmの実データをGitへコミットしない。
- AIが権限を決めない。
- 不明な職員コード、所属コード、役職コードを推測で補完しない。
- AI/OCR結果を原本へ書き戻さない。
- 業務DBはサーバー経由で更新する。
- 共通コード＋本部ごとのDB/実行環境/原本/backup分離を維持。予約051と既存migrationを変更しない。

## Review Focus

- 原本の変更・管理領域外path・抽出制限超過: 適用を拒否し、旧候補を正式化しない（Task1のsource_integrity試験）。
- 未知/非active職員・組織・役職: 推測せず候補の解決エラーとして表示し、review/applyを拒否（Task1のunknown_codes試験）。
- 確認後の人事・組織・元版変更: 409、候補/人事の一部だけcommitしない（Task1のstale_and_atomic試験）。
- 原本を読むだけの職員や失効session: 個人情報・候補件数の非露出とmutation拒否（Task1のsource_permissionsとTask2のrevocation試験）。
- ダブルクリック・遅い旧応答・将来日発令: 一度だけ適用し、現在の所属と将来履歴を混同しない（Task1のfuture_and_idempotence、Task2のloading_ownership試験）。

## Scope and rulings

- 人事Documentはpersonnel_noticeの保護typeでuploadする。既存generic原本を推測で人事原本へ改分類しない。
- 最初のdeterministic adapterは抽出されたJSONの明示項目employee_code、organization_code、title、kind、valid_from、valid_to、modeを扱う。その他の原本は抽出previewを残し、Humanが根拠quoteと同じ明示項目を入力する。未知codeは適用不可。
- titleはコードへ推測変換せず、既存Employee/Assignment/HumanRoleRuleの完全一致名称だけを解決する。独立役職code registryやコード対応表の移行は未実装として残す。
- 候補は明示Roleを追加しない。人事異動により既存HumanRoleRuleの有効日権限が変わり得ることを表示する。Account作成・永久grant・temporary grantは既存の独立Human操作を維持する。
- これは章6のDocument pipeline残差のSliceであり、章6全体・44章・Release完成を先取りして宣言しない。

### Task 1: Protected proposal, review and atomic effective-dated application

**Files:** Create backend/app/personnel_intake_models.py, personnel_intake_service.py, routers/personnel_intake.py, backend/tests/test_personnel_intake.py, db/migrations/055_personnel_document_intake.sql. Modify app/main.py, routers/administration.py (assignのcommit境界のみ), inquiries_service.py, routers/documents.py。

**Interfaces:**
- Consumes: extract_document(Document), administration.assign(db, actor, employee_id, AssignmentInput, transfer=False), administration.administration_lock(db,actor,permission), permission_closure(db,nodes).
- Produces: /personnel-intake/proposals GET/POST、/{id} GET/PATCH、/{id}/review|apply|reject POST。状態candidate/reviewed/applied/rejected、version、source_document_id/source_sha256、extraction preview/method、errors、before/after snapshots、applied_assignment_id。
- assignへcommit_result: bool=Trueを追加し、既存APIの挙動を維持。候補適用だけFalseで呼び、候補状態/人事/監査を同じtransactionでcommitする。
- POSTはdocument_id、PATCHはexpected_version・明示候補項目・source_quote・reason、review/apply/rejectはexpected_version・reason・acknowledged=trueを受ける。UUID/日付/enum/長さはclosed schemasで検証。

- [ ] Step 1: 書く test_candidate_does_not_change_assignment、test_unknown_codes、test_source_permissions、test_source_integrity、test_stale_and_atomic、test_future_and_idempotence。原本はtmp_path内の合成JSON/text、実API/認証/RBACを使う。
- [ ] Step 2: PYTHONPATH=backend FIRE_AI_DATABASE_URL=sqlite+pysqlite:///:memory: python -m pytest backend/tests/test_personnel_intake.py -q。Expected: 新router未登録で404のRED。
- [ ] Step 3: bounded serviceと保護type・migrationを実装。原本file hashと現在の全権限/元版をreview/applyで再照合。未知項目を公式記録へ反映しない。
- [ ] Step 4: 同コマンドとtest_personnel.py/test_human_authorization.py/test_hazardous_document_boundary.py/test_run_b_inquiries.pyを実行。Expected: 全成功、native PG skipは明示。
- [ ] Step 5: migration parser/差分・全体試験後にTask1をcommitし、ledgerへRED/GREENと残差を記録する。

### Task 2: Browser Human intake and evidence

**Files:** Modify frontend/admin.html, frontend/admin.js。Create frontend/personnel-intake.js、backend/tests/test_personnel_intake_browser.py、test_personnel_intake_browser_state.py、docs/completion/PERSONNEL_DOCUMENT_INTAKE_VERIFICATION_20261008.md。Modify .github/workflows/project-checks.ymlの実browser一覧。

**Interfaces:** Task1のclosed APIを利用。独立の候補owner/generationを持つ。管理画面の既存request/refreshと権限境界を維持し、入力中/適用中の操作を二重実行しない。

- [ ] Step 1: 実JavaScript状態試験loading_ownershipと実Chromiumjourneyを先に追加。原本upload→候補→unknownの表示→Human review→将来適用→既存人事履歴→権限失効時の消去を検証。
- [ ] Step 2: 状態試験を実行。Expected: 新画面未実装でRED。Chromiumはauthorized CIのみで実行する。
- [ ] Step 3: 原本/抽出previewとbefore/after、予定日、解決エラー、元版、Human理由を画面表示。reviewとapplyを分離し、原本のbytesは変更しない。
- [ ] Step 4: 全体・JS構文・migration parser・diff確認。Expected: 全成功。使用手順と既知adapter/役職code制限を文書化。
- [ ] Step 5: branch全体をfresh reviewerへ渡し、重大指摘をRED→GREENで修復。exact-head PR CI→merge→main CI Green→実ledgerへEvidenceを引き継ぐ。ユーザーの連続開発/merge許可を適用し、通常Sliceごとの追加確認は求めない。
