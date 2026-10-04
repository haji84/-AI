# Phase 5 Test Evidence

更新日: 2026-10-05

## GitHub Actions

Project checks:
- Phase 5 safety-test commit `8f9f7ad4a680223b1ee371185b2adc4bb0ad4818`: SUCCESS
- backend pytest: 39 passed
- Migration parser smoke: PASS
- `008_phase5_legal_rule_engine.sql`: 8 statements
- frontend JavaScript syntax: PASS
- Phase 5 UI commit `456b7ead631d08840911fb3455944124c8e98ab0`: SUCCESS

## 検証済み

- Draft Rule Versionは候補判定に使用されない
- 出典無しRule Versionは承認拒否
- 承認済み・適用期間内Ruleのみ評価
- 判定結果はcandidateとして保存
- 未定義フィールドを使うRuleは422拒否
- Rule作成・Version作成・承認を権限分離
- 対象物Snapshotに対する決定的条件評価
- 評価結果にRule Code / Version / 出典 / 条件一致Evidenceを保持
- Phase 5対象物画面の必要書類/必要設備候補UI
- Phase 0-4自動テスト回帰

## 意図的に未実装・未検証

- 実法令・条例・告示のRule投入
- 実法令一次資料の全件照合
- 複合用途・用途変更・階別の高度なルール表現
- 正式な必要設備/必要書類判定の業務受入試験
- approved LAN PostgreSQL Migration 001-008
- 実PostgreSQL backup/restore after Migration 008
- HTTPS production LAN clients
- 2端末同時Rule管理/評価E2E

実施していない項目をPASS扱いしない。
