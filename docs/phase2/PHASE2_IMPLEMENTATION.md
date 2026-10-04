# Phase 2 Implementation - 防火対象物台帳

更新日: 2026-10-05

## 実装済み

- 防火対象物一覧 / 検索
  - 名称
  - 所在地
  - 旧内部キー
  - 整理番号
  - 使用中/廃止フィルタ
  - ページング
  - 名称/所在地/整理番号/更新日時ソート
- 対象物詳細
  - 基本情報
  - 令別表区分
  - 用途地域
  - 構造
  - 令8条区画
  - 階数
  - 建築面積/延べ面積
  - 収容人員/従業員
  - 代表者情報
  - 階別情報
- 新規登録
- 編集
- 楽観ロックによる競合検出
- HTTP 409時に最新サーバー値を返却
- ブラウザ側の競合差分表示と再読込
- 廃止 / 復元
- 監査ログを利用した変更履歴表示
- Phase 0で意味未確定の41列は旧原値のみ閲覧可能
- Phase 0確認済みフィールドの正規化
- 旧.xlsm再取込時の正規化更新
- 既存DB向けbackfillスクリプト

## 新規正規化テーブル

- `facility_details`
- `facility_contacts`
- `facility_floors`

## 正規化方針

Phase 0で `confirmed` とした項目だけを編集可能な新DBへ正規化する。
意味が確定していない41列は推測で割り当てず、`legacy_facility_source_rows.raw_payload` を正本として閲覧専用表示する。

階別データは旧1～7階横持ち列を `facility_floors` の行形式へ変換する。
収容人員・従業員合計は、階別データが存在する場合は正規化後の階別値から再計算する。

## API

- `GET /facilities`
- `GET /facilities/{building_id}`
- `GET /facilities/{building_id}/detail`
- `POST /facilities`
- `PATCH /facilities/{building_id}`
- `POST /facilities/{building_id}/abolish`
- `POST /facilities/{building_id}/restore`
- `GET /facilities/{building_id}/history`
- `GET /facilities/{building_id}/legacy-review`

## Phase 2から次工程への接続

対象物詳細画面に以下のモジュール接続口を用意済み。

- 査察
- 届出受付
- 消防用設備

現時点では誤って未完成機能へ入らないよう無効表示にしている。