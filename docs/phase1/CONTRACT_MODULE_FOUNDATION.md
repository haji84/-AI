# Contract Module Foundation

Phase 1では契約業務の共通データ基盤とHuman Gateを実装する。

初期Entity:
- contract_counterparties
- contract_cases
- contract_documents
- contract_changes

Phase 1で実装する操作:
- 相手方登録
- 契約案件作成
- 契約案件更新（楽観ロック）
- 契約正式承認（専用permission）
- 正式様式への紐付け基盤
- 変更契約差分保存用Schema

後続Phaseで追加:
- 見積比較
- 仕様書/契約書横断照合
- 必要書類チェック
- 履行/検査/完了
- 請求・支払連携
- 類似契約検索