# AGENTS.md

## Project Goal
消防業務Local AIを、庁内LAN・複数職員・Local AI・監査可能な業務システムとして段階的に実装する。

## Source of Truth
1. `docs/SPECIFICATION.md`
2. `PROJECT_STATE.md`
3. `docs/phase0/PHASE0_AUDIT.md`
4. `docs/phase0/legacy_to_target_mapping.csv`
5. `db/schema_phase0_draft.sql`
6. Phaseごとの実装・テスト証跡

## Hard Constraints
- 実運用データ、個人情報、PDF原本、写真、録音、既存xlsmの実データをGitへコミットしない。
- JUST Calc/Excel VBAを必須依存にしない。
- AI停止時にもCRUD/受付/検索を継続できる。
- 法令判定はLLM単独で確定しない。
- 火災原因、正式違反、権限変更、証拠原本改変はAI自動確定禁止。
- 原本とOCR/AI派生物を分離する。
- 重要変更は監査ログを残す。
- 共有フォルダ上の1個のJSON/SQLiteを複数端末が直接書く構成は禁止。
- 業務DBはサーバー経由で更新する。
- 同一レコードの同時編集は楽観ロック等で競合を検出する。
- 救急個人情報は専用RBACで保護する。
- AI候補は根拠・Confidence・確認状態を保持し、元データへ直接上書きしない。

## Development Rule
小さいbounded sliceで実装し、migration/test/evidenceを伴わせる。
未確認の旧項目を推測でマッピングしない。
