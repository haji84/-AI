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

完成状況の基準はmain `9d6f86b1c21e61b1df51eef058bf01b26e5c54e9`、tree `c3d4f2afa32bdf44b82c2fe62d183e63d678f7d0`。分類はCompleted12 / Partial44 / Missing0 / External Gate1です。PR74の勤務Human操作修復、PR75の車両配属・履歴、PR76の観測統計、PR77の学習再読込修復はmerge済みです。章34はMissingからPartialへ、章23は既定の独立配属・版/監査・現在配属/履歴の完了条件を満たしてCompletedへ変わりました。Missingが0でも重大Partialや全体受入は残ります。

各PR head・以前のmainのCIと、現在mainのpost-merge CI・実際の配布manifest commitを区別します。PR75後のmain f53084a [CI37604792930](https://github.com/haji84/-AI/actions/runs/37604792930) はbackend1098件成功/88件スキップ、browser job64件成功（実Chromium55＋Node/API9）。PR76最終head cc743990 [CI37605645865](https://github.com/haji84/-AI/actions/runs/37605645865) はbackend1184件成功/95件スキップ、browser job71件成功（実Chromium62＋Node/API9）で、両方ともmigration parser/JavaScript成功です。PR76後main c1b491eの [CI37607563240](https://github.com/haji84/-AI/actions/runs/37607563240) も同じ1184/95・71件とparser/JavaScriptの成功を確認しました。PR77最終統合head ee757220 [CI37606910763](https://github.com/haji84/-AI/actions/runs/37606910763) はbackend1198件成功/95件スキップ、browser job71件成功（実Chromium62＋Node/API9）、parser/JavaScript成功で、現mainと同じtreeを持ちます。**実装main 9d6f86bの [post-merge CI37609190838](https://github.com/haji84/-AI/actions/runs/37609190838) もbackend1198件成功/95件スキップ、browser job71件成功（実Chromium62＋Node/API9）、parser/JavaScript成功**です。この実行証拠を、後続の文書・配布物commitで新たに実行した結果とは扱いません。

車両は実フォームから追加でき、現在配属・履歴まで確認できます。章23の配属欠落は解消し、同章のcoreはCompletedです。配属の原本Document・取込/出力・横断検索連携は共通基盤の章9/41/35で未完として追跡します。車両検証手順書の過去のPartial表記は現在ledgerが更新し、使用手順と制限は維持します。観測統計は7指標の保存・Human確認・置換と汎用CSV/XLSXを提供し、確認後も網羅性unknownを維持します。財務/過去母数/年度・前年比較/残りのsource/網羅性宣言/正式様式は未完のままです。

初回packaging報告を変更せず、次の生成物ではそのmanifest commit/tree/hashと検証結果を別途記録します。`production_ready: false` は継続し、上の全体・本部・実機Gateを満たすまで本番受入完了としません。中央サーバー・dynamic worker・backup vault等の後続設計は実装やアクセス/導入権限に含めず、現行の本部別分離と復元手順を使用します。通常の状態・容量・最終成功の可視化と緊急復元権限は別途設計し、登録・鍵・privacy・policyを確認する必要があります。

利用者の初回操作は [今日の業務・文書受付・危険物台帳](INSTALLATION.md#first-use-common-workflows) と [車両追加・配属・観測統計](INSTALLATION.md#first-use-vehicles-statistics) の案内から確認できます。
