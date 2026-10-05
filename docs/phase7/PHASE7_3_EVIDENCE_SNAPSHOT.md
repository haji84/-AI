# Phase 7.3 Fire Investigation Evidence Snapshot / AI Report Provenance

更新日: 2026-10-05

## 目的

AIが火災調査報告書Draftを生成する際に、どのHuman確認済み証拠を根拠にしたかをFreezeし、
後から証拠・供述・タイムラインが変わっても生成時点の根拠を再現できるようにする。

## 実装

Migration 021:
- `fire_evidence_snapshots`
- `fire_report_drafts.fire_evidence_snapshot_id`
- `fire_report_drafts.source_manifest_id`
- AI Manifest type `report_draft`

Evidence Snapshotに含めるもの:
- accepted photo annotations
- accepted transcript segments
- reviewed statements
- confirmed timeline events
- Human-approved official cause candidate
- selected source media Document SHA-256
- case version
- snapshot SHA-256

## 安全ルール

- pending/rejected AI evidenceはSnapshotへ入らない
- AI report DraftはEvidence Snapshot必須
- AI report Draftは専用 `report-ai-manifest` APIからのみ作成可能
- 手動report APIへ `ai_generated=true` を送ると422拒否
- Snapshot外Evidence参照は422拒否
- Case Versionが変わった古いSnapshotからAI report生成は409拒否
- 同一AI ManifestはSHA-256で冪等
- AI reportの正式承認にはHuman Reviewが必要
- AI reportの正式承認時にSnapshot/Manifest provenanceを再検証
- FormTemplate指定時はCase日付に有効なactive Versionのみ使用

## UI

Case詳細:
- Evidence Snapshot作成
- Snapshot SHA-256短縮表示
- Case Version
- 写真注釈 / transcript / statement / timeline / official cause 件数
- Report DraftにEvidence Snapshot ID / AI Manifest IDを表示

## Verification

GitHub Actions run: `37253033331`
- result: SUCCESS
- backend pytest: 76 passed
- Migration 021: 7 statements PASS
- frontend JavaScript syntax: PASS

Previous E2E updated so AI report follows:
accepted/reviewed evidence
→ Evidence Snapshot
→ report AI Manifest
→ report Draft
→ Human Review
→ formal approval

## 未実施

- 実Local AIによる報告文生成精度評価
- 正式様式原本への実差し込み出力
- approved LAN PostgreSQL/physical-client Host Gate
