# Phase 2 Test Evidence

更新日: 2026-10-05

## 自動テスト

Backend test suite:

- 18 passed

確認内容:

- Phase 1認証/RBAC/監査/拡張基盤の回帰
- 対象物検索
- 対象物詳細 nested CRUD
- 階別複数行保存
- nested partial PATCHで未指定値を保持
- 楽観ロック
- 409 conflict payloadに最新データを含む
- 廃止/復元
- 変更履歴
- 整理番号検索
- ページング/ソート
- 階番号重複拒否
- Browser UIにCRUD/競合/旧未確定項目表示が存在
- Frontend JavaScript syntax check PASS

## 実データ回帰

入力:

- `★新査察台帳システム.xlsm`
- `救急報告関係.xlsm`

Phase 1全体回帰結果:

- facilities: 611
- facility source rows: 611
- emergency cases: 2,958
- emergency patients: 2,950
- emergency crew: 8,981
- unresolved crew identity: 66
- forced re-import idempotency: PASS

Phase 2対象物正規化結果:

- facilities: 611
- facility_details: 611
- facility_contacts: 611
- facility_floors: 1,434
- legacy source rows: 611
- forced re-import idempotency: PASS

実データ値・個人情報はテスト証跡へ出力していない。

## 未実施ゲート

実庁内LAN環境のPostgreSQL/TLS/2端末同時操作試験はPhase 1 Host Gateとして未実施。
開発環境でPASSしたことと、実運用環境でPASSしたことは区別する。