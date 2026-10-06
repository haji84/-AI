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

未実装・未実施をExternal Gateへ振り替えないこと。現在の残作業は `docs/completion/MASTER_FEATURE_MATRIX.md` と実コードを照合して更新します。matrixの過去commit集計だけで現在の完成度を断定しません。

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
- この配布差分はmain707ccddを基準とし、既存業務・権限・共有セッション修正を保持します。他ブランチの未merge作業は自動収録しません。
- 基準707ccddの財務画面は既存原本の選択方式で、この配布差分にupload画面改修は含めません。共通upload APIによる技術担当者向け確認手順はINSTALLATIONに記載しています。一般職員のWeb初回操作の受入完了とはしません。
