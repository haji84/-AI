# Phase 1 Scope

## Goal

AIなしでも業務が成立する共通基盤を構築し、Phase 2以降の全モジュールが同じ認証・権限・監査・同時編集・ファイルメタデータ基盤を使用できるようにする。

## In Scope

- PostgreSQL初期Schema
- migration framework
- users / employees / roles / permissions
- authentication
- RBAC
- audit_logs
- record_versionによる楽観ロック
- logical delete / restore metadata
- document metadata（原本ファイル自体は共有ストレージ）
- health check
- backup設計
- 旧データDry-run importerの足場
- emergency source/import batch foundation
- 事案/傷病者/隊員の救急データ正規化Schema
- 救急個人情報用RBAC権限の足場
- Module Registry / Feature Flag
- Extension Intake / Import Adapter基盤
- Human Change Request / Sandbox結果 / Deployment / Rollback監査
- 正式様式Template Version管理
- 契約管理共通Schema / 専用Human Gate

## Out of Scope

- AIモデル導入
- OCR
- 図面解析
- 音声認識
- 法令判定ロジック本実装
- 救急帳票UI本実装
- 救急Local AI判定本実装
- 本番対象物データのGitHub格納

## Exit Criteria

- 複数ブラウザセッションが同時利用できる
- 権限外操作が拒否される
- 変更前後が監査ログに残る
- 同一レコード競合を検出できる
- AIサービス停止を想定してもCRUD基盤が動く
- migrationを新規DBへ再現可能
- 新機能をChange Request→Review→Approval→Deployment→Rollbackの履歴で追跡できる
- 正式様式原本をDocumentとして保全しVersion選択できる
- 契約正式承認permissionが通常編集permissionから分離される