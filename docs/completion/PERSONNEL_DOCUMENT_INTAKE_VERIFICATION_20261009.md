# 人事原本からの辞令候補 — 使用手順と検証境界

実装中のbounded Slice。mainへの統合・正確なheadのCI・merge後mainの検証が揃うまで完成済みとしない。章6等の全条件を満たしたとの主張ではない。

## 使用手順

1. 共通Webアプリの職員・組織管理を開く。人事閲覧と原本閲覧の権限を持つ職員だけが「人事原本から辞令候補を作成」を使用できる。
2. 人事管理・原本登録の権限を持つHumanが原本を登録する。原本は保護された`personnel_notice`として保存する。汎用原本を推測で人事原本へ変更しない。
3. 抽出内容、対象職員、所属、役職、開始・終了日、本務・兼務、変更前履歴を確認する。候補作成だけでは正式な人事履歴は変更されない。
4. 未知コードや未解決項目があれば、原本の抽出内容から根拠引用を選び、既存の正しいコード・役職名をHumanが入力する。補正理由を保存する。未知の値をAIが推測して適用することはできない。
5. 原本・対象・期間を確認し、理由と確認チェックを入力して「Human確認」を実行する。この時点でも人事履歴は変更されない。
6. 別の「確認済の候補を正式適用」を実行する。本務異動は旧本務を開始日前日で閉じる。将来日付はその日から有効となり、既存のHuman権限ルールに従う。候補からRoleを作成・直接付与しない。
7. 元データや原本が変わった場合は409で拒否する。再読込・再確認が必要。同一候補は二重適用しない。却下は正式履歴を変更しない。

## 実装契約

- 原本SHA-256、抽出方法・文章・引用、候補項目、解決エラー、職員版・全履歴版、対象組織版、変更前後、Human確認者・適用者・理由・日時を保存。
- 原本は書換えない。抽出/OCR中は業務transactionとアカウント管理排他を保持せず、処理後に再認証・権限・元版・原本descriptor/hashを確認する。
- 適用は既存administration.assignと楽観ロック、期間重複拒否、最後の管理者維持を再利用。候補・人事・監査を同じtransactionでcommitし、途中失敗なら全体rollbackする。
- 原本・候補の閲覧はpersonnel.readとdocument.read、変更はさらにpersonnel.manage。登録はdocument.createも必要。共通原本API・根拠権限閉包にも人事保護typeを追加。
- UIはuser/session/tenant/current permissionsと表示所有権をHTTP前後に照合。権限喪失時には原文・候補・入力を消去し、遅い旧応答を復活させない。処理中の二重操作を拒否。Human確認と適用は別操作。
- Append-only migration055。既存migrationと予約051は変更しない。本部ごとのDB・実行環境・原本・backup分離を保持する。

## 検証記録

継続開始時に既存API18件を含む人事・Human権限49passed/18nativePGskipを再実行。画面所有権・session変更・権限喪失・二重操作・Humanチェック・409の6件は新controller未実装でRED、その後6passed。追加の処理中focus権限喪失は原文が残るREDを再現し、処理中でも権限照合する修正で7passed。skipは成功と数えない。

新しい実PostgreSQL試験は、旧migration集合で作った既存DBと人事履歴へ055だけを適用し、再実行が空であること、同じ確認済候補への競合適用が200/409一回だけで履歴・監査・候補が整合することを検証する。

実Chromium試験は合成人事原本登録→未知コード表示→Human補正→Human確認→将来適用→既存履歴→権限喪失後の原文消去を実HTTPで確認する。既存browser一覧に追加し、既存の全browser試験を残す。ローカルChromium取得はZIP破損で失敗したため、実browser成功はCI実行まで未検証。

全体試験・fresh review・PR head/native CI・merge後mainの実行結果は後続証拠として追記する。過去ログ・SQLite成功を新しいPG/Chromium成功へ転用しない。

### 独立レビュー後の追加検証

人事適用理由が既存の共通assignment監査へ平文で渡る経路を、audit.readだけの利用者による実API試験でREDとして再現した。理由全文は保護された候補に保持し、既存assignment操作には候補IDと理由SHA-256を渡す修復後にGreen。auditだけの利用者は候補403、監査200で、理由本文を取得できず、両assignment監査から候補IDを追跡できる。独立再レビューで1passed、Critical/Important指摘なし。

さらに認証contextが取得不能または不正な場合に再読込前の原文が残る2件をREDで再現し、現在ownerだけを消去する修復後に状態試験9passed。処理中focus時の即時消去と古い応答の無効化も保持する。独立レビューの状態試験も9passed。新しいPG/Chromium試験定義をレビュー済みだが、実行成功とは区別する。

最終ローカルfocused試験（API・人事・Human権限・実JavaScript状態）: **59 passed / 18 native PostgreSQL skipped / 1 dependency deprecation warning**。Python/JavaScript構文、53個のMigration parser、差分checkも成功。全backendローカル試験は実行環境の接続中断により完走結果を得ていないため、成功扱いしない。新PRで全backend・実PostgreSQL・実Chromiumを必須検証する。

PR80財務の権限閉包と人事原本の保護を同じ候補へ統合した実API試験: **56 passed / 1 PostgreSQL skipped**。独立統合レビューはCritical/Importantなし、財務キュー9件＋人事原本権限1件の10passed。財務child→commitment→人事原本という追加の実HTTP回帰試験も1passed。personnel.readなしでは原記録ID・件数を出さず、付与時だけpointerを表示し、失効後は再び件数0となる。本検証はPR80をmainへmergeした証拠ではなく、最新mainの確認後に公開する統合候補の証拠。

## 残る制約

人事原本・候補を含むHTTP応答のcache防止を追加検証した。create/list/getだけでなく、補正・確認・適用・却下まで実APIを通し、全応答の`Cache-Control: no-store`を要求する回帰試験は追加前RED、router共通dependency追加後Green。人事API全体は20passed、独立レビューの対象試験も1passed（7.63s）、Critical/Importantなし。権限・Human承認・transactionは変更しない。

- 最初のdeterministic adapterは抽出された明示JSON項目を読む。非JSON原本は抽出previewを残し、Humanが項目と正確な根拠引用を補正する。自然文辞令の実AI判読品質を主張しない。
- 役職は既存Employee/Assignment/HumanRoleRuleの完全一致名称のみ。独立の役職コードregistry・コード対応表の正式移行は別の内部未完。
- before表示には履歴の本務/兼務・役職・期間を出すが、旧組織名と閉じる予定日の比較表示は未拡張（レビューMinor）。before snapshotの元組織IDと版照合、既存異動処理の期間変更は保持する。
- 公的な人事判断、実人事原本の取扱い、現場の権限ルール承認はHuman Gate。新しい自動権限ポリシーを導入しない。
- 本Sliceで資格・担当・全人事コード体系・章6全体・10本のE2E・Release完成は宣言しない。
