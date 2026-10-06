# 救急Web集計・出力

ログイン後「救急集計」を開く。クライアント追加アプリ不要。
開始日・終了日・内訳を指定して集計する。日付指定なしは全期間。
期間の両端を含む。覚知日不明は期間指定時のみ除外し、その件数を表示する。

内訳: 搬送先コード、傷病程度コード、地区コード。
事案件数と救護者人数は別の単位で表示する。
搬送先コード入力人数は、入力が存在する人数であり、コードの意味や搬送完了を推測しない。
病院・傷病程度内訳に救護者がいない事案は含まれない。地区内訳には含まれる。
患者区分をまたぐ事案があるため区分内事案件数は加算可能とは限らない。
割合の分母は全救護者人数。ゼロ人時は0。Web表示だけ小数第2位へ丸める。

Excel/CSVは画面に表示した条件で出力する。条件変更時は再集計が必要。
Excelではコードを文字列セルとし、CSVでは数式開始文字を無効化する。
印刷・PDF保存はブラウザの印刷機能を使う。
正式提出様式を独自帳票で代替する機能ではない。

## 権限

- emergency.report.read: 集計のみの閲覧。
- emergency.report.export: 集計のみのExcel/CSV出力。
- 上記は診断文・氏名・raw_payload・個票IDの閲覧権限を含まない。
- emergency_reporter / emergency_detail_viewer / system_adminに出力権限を付与する。
- 更新後、管理者は既存 `scripts/seed_rbac.py` を対象DBへ実行し新権限を登録する。
- 集計/出力時に条件と合計の監査ログを保存し、診断文等は監査へ保存しない。

## API

- GET /auth/permissions: 現在ユーザーの権限コード。
- GET /emergency/reports/summary
- GET /emergency/reports/export?format=xlsx または csv
- 引数: start_date / end_date (ISO date)、group_by (hospital/severity/region)。
- 認証なし401、権限なし403、不正な期間/区分422。
- 集計/出力レスポンスはCache-Control: no-store。

## Evidence / 制約

新規8テストを実装前に実行し、未実装APIの404で失敗を確認。実装後8 passed。
合計の二重計上、複数患者、期間境界、不明日付、患者なし事案、権限、個票漏出、数式コード、Excel/CSV、監査を検証。
このSliceでE2全体完成を宣言しない。
病院/程度名称マスタ、隊員別帳票、日/月の正式提出様式、Web取込、報告チェック、CPA/アレルギー候補確認は残作業。
Clinical Flagはこの集計に勝手に適用しない。
実LAN・実データ/旧xlsm帳票回帰・ブラウザ受入は別途実行する。
