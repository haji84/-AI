# リリース候補の受入確認

## 完成判定

パッケージ生成成功、単一PRのmerge、CI成功、単一モジュールの動作は、それぞれAIOS全体完成とは別の確認です。正本は `docs/SPECIFICATION.md` 第53章です。本パッケージは `release-candidate`、`production_ready: false` として配布します。

確認記録には次を記載します。

- 配布ファイル名とSHA-256
- manifestのcommit/tree/release ID
- その固定commitに対するbackend/PostgreSQL CIとブラウザCIのURL・結果
- 対象本部UUID、承認された担当者、検証日時（これら実運用値はGitへ保存しない）
- 導入・更新・復元・利用者受入で実施した項目と未実施項目

## 内部実装・自動検証

- [ ] exact-head CIが成功している
- [ ] 空PostgreSQLへの全migrationと再実行が成功する
- [ ] 既存DBの更新を隔離cloneで検証した
- [ ] 権限・監査・本部分離・同時編集・Human Gateが保たれる
- [ ] 文書原本を新規登録し、一般業務roleで必要なフローを完了できる
- [ ] 第54章の10本のcross-module E2Eが成功している
- [ ] 重大なMissing/Partial、Duplicate/Conflict/Orphanedが解消されている
- [ ] 同一commitからの再生成一致とarchive verifyが成功する
- [ ] マニュアル、更新/rollback、既知の制約、最終テスト報告が揃っている

未実装・未実施をExternal Gateへ振り替えないこと。現在の残作業は [CURRENT_COMPLETION_LEDGER](../completion/CURRENT_COMPLETION_LEDGER.md) の固定base・全57章・merge差分と実コードを照合します。分類変更は [STATUS_CHANGELOG](../completion/COMPLETION_STATUS_CHANGELOG.md)、c1b684cの全章Evidenceは [BASELINE](../completion/COMPLETION_BASELINE_20261007.md) に記録します。旧MASTER_FEATURE_MATRIXと過去の検証報告は履歴であり、現在の完成度や最新manifestの実行結果へ読み替えません。

## 本部・実機側のExternal Gate

- [ ] 承認済みhost、専用OS/DB role、ACL、DNS/TLS、容量、監視を確認した
- [ ] 別本部DB/storage/backupへのアクセス拒否を実機で確認した
- [ ] 2台以上の実PCでログイン・権限・競合・再読込を確認した
- [ ] 書込停止中のDB+原本backupと隔離復元演習を完了した
- [ ] 組織の予算・勤務・法令ルールと正式帳票原本を責任者が承認した
- [ ] 実図面/音声等のBaselineを測定し、Humanが閾値を承認した
- [ ] 実利用者による運用受入と責任者の本番移行承認を記録した

## この配布機構の制約

- ソース配布のみ。インストール、サービス登録、merge、deploy、DB変更は実行しません。
- 依存パッケージのwheelやOS依存、モデル、正式原本、実データは同梱しません。
- ハッシュinventoryは破損検知用です。署名・認証された更新機構ではありません。
- dirty/untrackedファイルは成果物に反映されません。必ずcommitしたソースで生成します。
- CIのskipは成功した機能検証として数えません。CI成功でも実LAN・本番受入を代替しません。
- 収録内容は生成時に指定した固定commitに従います。`PACKAGING_TEST_REPORT.md` の初回検証基準707ccddと、現在配布するmanifest commitの検証記録を区別します。他ブランチの未merge作業は自動収録しません。
- PR #63・#64統合後のmainには、財務画面からの共通原本登録・自動選択が含まれます。権限と年度設定の事前準備、登録から草案保存までの手順は `INSTALLATION.md` に記載しています。合成データによる実ブラウザ検証が成功していても、本部の実機・実利用者による受入は未完了として別途記録します。


## 現在の実装baseと受入の区別

完成状況の基準はmain `1b3bf5b7442941fb19c186095290231ab3dd2fbf`。分類はCompleted11 / Partial44 / Missing1 / External Gate1で、章16（危険物）・36（個人work list）はPartial、章34（共通統計）はMissingです。PR70の対象物dashboard権限修復とPR71の危険物台帳はmerge済みですが、これだけで全体完成とは扱いません。

各PR head・以前のmainのCIと、現在mainのpost-merge CI・実際の配布manifest commitを区別します。現在mainの [CI37584491507](https://github.com/haji84/-AI/actions/runs/37584491507) はbackend974件成功/67件スキップ、browser job52件成功（実Chromium43＋Node/API9）、migration parser/JavaScript成功を確認しました。初回packaging報告を変更せず、次の生成物ではそのmanifest commit/tree/hashと検証結果を別途記録します。`production_ready: false` は継続し、上の全体・本部・実機Gateを満たすまで本番受入完了としません。

利用者の初回操作は [INSTALLATIONの案内](INSTALLATION.md#first-use-common-workflows) から、今日の業務・文書受付・危険物台帳の各手順へ進めます。
