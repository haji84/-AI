# 救急報告関係.xlsm 追加監査

監査日: 2026-10-04

## 結論

このブックは、3種類のCSV相当データを入力源として、病院搬送・傷病程度・隊員出場回数・年度累計等の複数帳票をVBAで生成する集計システムである。新システムではExcel/VBA処理を再現するのではなく、入力源を正規化DBへ一度取り込み、帳票をDBクエリから再生成する。

個人情報を含む実データはリポジトリへ保存しない。本監査資料にはシート名、列名、件数、処理名のみを残す。

## シート構造

- `設定`: used range `A1:Q46` / rows=46 / cols=17 / formulas=0
- `CSV_事案台帳`: used range `A1:DM2959` / rows=2959 / cols=117 / formulas=0
- `CSV_救護者台帳`: used range `A1:FD2951` / rows=2951 / cols=160 / formulas=0
- `CSV_出動隊員`: used range `A1:G8982` / rows=8982 / cols=7 / formulas=0
- `瀬戸内徳洲会報告`: used range `A1:M18` / rows=18 / cols=13 / formulas=3
- `瀬戸内徳洲会報告_病院別内訳`: used range `A1:B13` / rows=13 / cols=2 / formulas=0
- `救急隊員出場状況累計`: used range `A1:F36` / rows=36 / cols=6 / formulas=0
- `救急出場個人件数`: used range `A1:AT40` / rows=40 / cols=46 / formulas=0
- `救急出場総件数`: used range `A1:GD170` / rows=170 / cols=186 / formulas=30
- `役場報告瀬戸内徳洲会病院搬送傷病程度内訳`: used range `A1:F9` / rows=9 / cols=6 / formulas=0
- `役場報告瀬戸内徳洲会病院搬送件数`: used range `A1:G17` / rows=17 / cols=7 / formulas=0
- `役場報告町内医療機関傷病程度内訳件数`: used range `A1:F11` / rows=11 / cols=6 / formulas=0
- `ログ`: used range `A1:F12013` / rows=12013 / cols=6 / formulas=0

## 主要入力源

- `CSV_事案台帳`: 2958件、117列。事案・時刻・出動地区・車両・指令・連携等。
- `CSV_救護者台帳`: 2950件、160列。傷病者・搬送先・傷病程度・傷病分類・症状・救急蘇生等。
- `CSV_出動隊員`: 8981件、7列。隊員種別・隊員コード・資格・階級。

全列一覧は `emergency_source_columns.csv` を正本とする。


## 一意キー監査

- 事案: 2,958行すべてキー完備、重複0
- 傷病者: 2,950行すべてキー完備、重複0
- 出動隊員: 8,981行中8,915行は完全キー、66行は `隊員コード` 空欄、完全キー同士の重複0

隊員コード空欄66行は除外しない。`source_record_key` と `source_row_no` を持たせ、`source_identity_status=missing_crew_code` として保存し、後から職員マスタへ紐付け可能にする。

## 現行VBAで確認できた主要処理名

- `RunAllReports`
- `RunMonthlyReportsOnly`
- `RunYakubaReportsOnly`
- `ValidateCsvSheets`
- `ClearCsvSheets`
- `UpdateTokushukaiReport`
- `UpdateTokushukaiDayLabels`
- `WriteHospitalBreakdownSheet`
- `UpdateCrewMonthly`
- `BuildCrewMonthlyCounts`
- `UpdatePersonalYearlyCount`
- `UpdateTotalDispatchCount`
- `UpdateYakubaReports`
- `UpdateYakubaTokushukaiMonthly`
- `UpdateYakubaTokushukaiSeverity`
- `UpdateYakubaTownMedicalSeverity`
- `CollectTokushukaiData`
- `EnsureLogSheet`
- `WriteLog`

## 現行出力帳票

- 特定病院への搬送件数・病院別内訳
- 救急隊員出場状況累計
- 救急出場個人件数
- 救急出場総件数
- 役場向け病院搬送件数
- 役場向け傷病程度内訳
- 町内医療機関別傷病程度内訳
- 処理ログ

## 新システム移行方針

1. 事案、傷病者、出動隊員を別テーブルに正規化する。
2. 原CSVの全列を失わないため、主要列は型付きカラムへ格納し、それ以外も `raw_payload` JSONとして保持可能にする。
3. 同じCSVを再取込しても重複登録しない冪等キーを持つ。
4. 帳票はDB View/Queryから再生成し、Excelセルを正本にしない。
5. 現行VBAの帳票結果と新DB集計結果を同一期間で比較する回帰テストを作る。
6. 病院・傷病程度・職員マスタは共通マスタへ統合する。
7. インポート・集計・出力はすべて監査ログに残す。

## 救急AI拡張

将来のLocal AIは、傷病名・症状・病歴・その他情報・救急蘇生コード等を根拠に、次の候補フラグを生成できる構造とする。

- CPA候補
- アレルギー候補
- 禁忌・注意事項候補
- 入力矛盾・欠損候補
- 搬送先/傷病程度等の集計分類候補

AI出力を正本値に上書きせず、`emergency_clinical_flags` に根拠・生成方式・信頼度・確認状態とともに保存する。CPA等は明示コードや処置情報を優先し、病名文字列だけに依存しない。

## Phase 1への影響

Phase 1で以下の基盤を先行実装する。

- 救急CSVインポートバッチ管理
- 原本ファイルハッシュ・取込履歴
- 事案/傷病者/隊員の一意キー設計
- 共通職員マスタとのリンク
- 監査ログ
- 冪等インポート
- 帳票生成履歴

帳票UIおよびAI判定本体はPhase 1のExit Criteriaには含めない。