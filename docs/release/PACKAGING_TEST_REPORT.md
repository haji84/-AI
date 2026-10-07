# ソース配布機構の検証記録

検証日: 2026-10-06。基準main: `707ccdd48b2cadacf77a90726377107ec5573fee`。

## 変更範囲

`scripts/build_release_bundle.py`、その回帰テスト、READMEの導入案内、`docs/release/`の7ファイルのみです。既存mainの勤務・財務・照会・違反是正、権限/共有セッション処理、DB schema/migrationを変更していません。別途検証中の財務原本upload画面変更は含みません。

## 配布機構の検証

- stdlib unittestおよびpytestで24件成功。決定的生成、未commit/未追跡ファイルの除外、追跡済み許可外パス・binary・symlink拒否、出力上書き拒否を確認。
- archive改変、重複、欠落、path traversal、不正metadata、深い不正JSONを拒否。JSONの深さによるRecursionErrorはCLIの通常エラーとして処理し、tracebackを表示しない回帰をRED→GREENで確認。
- archive内の実バイトとmodeからSHA-1/SHA-256 Git treeを再構築。偽tree、内容とSHA-256だけを置換した改変も拒否。
- partial cloneで不足blobを自動fetchしない。Git traceを使ったRED→GREEN回帰を保持。
- 最新mainの424追跡ファイルをallowlist/type/mode/必須asset検査で確認。合計4,207,640bytes、最大306,693bytesで上限内。
- 基準mainのsource bundleを2回生成し、両方を展開せずにverifyし、出力バイトの一致を確認。再構築treeは`ed32d307d34c9d1af70c5e1d2067fb51263858fe`。
- 生成器/テストのPython compile、49ファイルのmigration parser、全JavaScript構文、`git diff --check`成功。
- 配布差分を含むローカル全backend: **628 passed / 70 skipped / 286 warnings、169.79秒**。サービス依存skipを合格として数えない。
- 基準mainの実archiveを展開し、空SQLiteのbootstrap、実HTTP health/login/session、画面/static assets、finance_editorの共通原本uploadとSHA/picker照合、logout成功。

## 基準mainのCI

[main CI 37530330740](https://github.com/haji84/-AI/actions/runs/37530330740):

- backend/PostgreSQL: 654 passed / 20 skipped
- Chromium: 10 passed
- migration parser、JavaScript構文: success

これは基準mainの証跡です。配布差分を加えた最終commitのローカル全backend結果とexact-head CIはPR本文/checksに記録し、配布時にmanifest commitと照合します。過去commitのCIやskipを新しい機能の合格証跡として流用しません。

## 起動と配布のGate

- 信頼できる配布元、固定commit、archiveのSHA-256を照合する。
- 最終archiveのverify成功後、新規領域へ展開して合成データでbootstrap、実HTTP health、login/session、Web画面/static assets、logoutを確認する。
- ローカルSQLite確認はPostgreSQL固有制約・本部分離・実LANの代替ではない。
- 配布物はソースのみ。依存wheel、モデル、実データ、正式帳票は同梱しない。
- ハッシュは破損検知であり、発行者署名や機密判定を代替しない。

この記録は配布機構の検証です。全AIOS完成、本番利用承認、全5 Deployment Profileの実機受入、実AI品質の達成を表しません。残る内部実装とExternal Gateは `RELEASE_READINESS.md` および正本仕様を確認してください。
