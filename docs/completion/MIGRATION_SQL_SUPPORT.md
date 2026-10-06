# PostgreSQL Migration quote/trigger safety

Canonical main b2fc2612a35a86f7746da7ea968da570c87cb773 / PR56。PR56 exact-head CI37500100995 SUCCESS: backend447成功7skip136.29秒、実Chromium5成功46.70秒。local408成功46skip203.81秒。main CI37500653453 SUCCESSを再取得確認。Role/Rule/期限付き代理のHuman境界・本部別構成を維持。

開PR55 financeのCI37498399874は7failed/15errors。原因は共通split_sqlがPL/pgSQL dollar quote内のsemicolonを切り、append-only journal保護triggerをCREATEできなかったこと。Domain実装を再作成せず、共通Migration実行を修復する。開PR53 workforceも未merge/CI失敗のまま、正本に入ったものとして扱わない。

- 空/名前付きdollar quote、E文字列escape、二重quote・通常quote、入れ子block comment、line commentを保存してstatement境界を判定。
- 未閉quote/commentはValueErrorで拒否。すべてのMigrationを読込/分割検証してからDBへ接続し、不正な後続ファイルで先行schemaを書き換えない。
- raw DDLの実行でno_parametersを指定し、psycopgがLIKE文字列内のpercentをplaceholderと誤認しない。
- 本部境界、Migration advisory lock、保守排他、1file transaction、schema_migrationsの既存versionを維持。001–043/045/047のMigration自体を改変しない。
- immutable financial journalのtriggerを取り除いてGreenにすることは禁止。新regressionは実PGでfunction/triggerを作りUPDATE/DELETE拒否・原値保持とpercent付きLIKEの実行・再実行no-opを確認する。

Ruling: frameworkを総入替えせず既存append-only SQL formatのlexerを補強する。旧commentのdollar-body未対応は実コードの制約であり、正式仕様の不変履歴保護を省略する根拠にしない。費用/本番DB変更/外部接続/正式法令判断は実施しない。

RED: dollar guard等10失敗1成功1PGskip0.61秒。GREEN: 新lexerと既存Migration関連14成功1PGskip5.85秒。local全体419成功47skip188warnings173.96秒。独立レビュー・exact-headPG CI・mainmerge証拠はSlice終了時記録する。本Sliceだけで完成ではなく、正式違反・危険物・図面AI統合・全E2E・導入release一式を継続する。

独立レビュー: Important 1件（改行で連結したE文字列のescape mode喪失）は6件のREDを確認後、1回の修正でGREEN: 17成功1PGskip0.23秒。実PG regressionでも連結後の値を検証する。PostgreSQL16公式仕様 https://www.postgresql.org/docs/16/sql-syntax-lexical.html の改行連結・最初の文字列だけE prefixを付ける規則に従う。CR-only line commentも次のstatementを隠さない。

Minor 1件（preflight errorへのMigrationファイル名表示）は今回の安全性修正を妨げない診断改善として記録し、レビュー修正passに追加しない。release検証の診断改善で追跡する。未閉SQLはDB接続前に拒否される。

最終local全体: 425成功47skip188warnings202.16秒、compile/diff check成功。canonical45files331statements、未merge finance31statements/2functions intact。PGとChromiumはlocal未実行のためCI証拠で確認する。
