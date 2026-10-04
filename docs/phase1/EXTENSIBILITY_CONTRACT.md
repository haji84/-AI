# Extensibility Contract

## Purpose
後から渡された業務ファイルや人間の追加要求を、既存本番を壊さずシステムへ取り込むためのPhase 1共通契約。

## File Intake Flow
1. 原本をDocumentとして保存しSHA-256を保持
2. `extension_intakes`を作成
3. AI/Parserが種類・構造・項目・既存ロジックを解析
4. 既存Module/DB/API/UI/権限/監査との差分を生成
5. 追加候補をManifestとして生成
6. Sandboxへ適用
7. 自動テストと受入条件を実行
8. Human Gate
9. Version/Migration/Feature Flag付きDeployment
10. 問題時Rollback

## Human Change Request Flow
自然文で要求を登録できる。最低限、対象Module、対象画面/機能、要求本文、影響解析、リスク、提案変更、受入条件、Sandbox結果、承認者を保持する。

レビュー前のChange Requestは本番Deploymentできない。承認前のDeploymentも禁止する。

## Runtime Safety
- 新ファイル解析だけでDB Schemaを変更しない
- 権限をAIが自動昇格しない
- 原本を変更しない
- migrationはVersion管理する
- Feature Flagで新機能を停止可能にする
- Rollbackを監査ログへ残す