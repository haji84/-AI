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
