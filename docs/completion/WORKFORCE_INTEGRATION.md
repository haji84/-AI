# 勤務管理の正本統合・安全性証拠

正本再確認: main ea15820e57a73dd4ea721d43247fb63345271a53、main CI37503229005 SUCCESS。PR57はexact-head78602a7でPostgreSQLを含む465成功7skip、Chromium5成功。開PR53はe21eaa0でCI37493709157失敗・未merge、開PR55も未merge。既存PR53の差分を基底fbc7227fと最新mainへ三者照合して統合し、業務を再実装しない。

共通コード＋本部別DB・実行環境・原本・backupを固定。組織/職員/人事履歴は既存正本を利用し、tenant bootstrap、password policy、custom Role/Rule/代理grant、session、学習基盤を維持。新たなMigration044は開PR53が予約した未mergeファイル。mainに入った001–043/045/047は変更しない。

## 修復結果

初期RED: 3失敗5成功7.76秒。取込期限のnaive/aware比較、変更済み人事履歴の承認を期待する矛盾したテスト、別Pythonを起動するbootstrapテストを確認。期限/replay追加後RED2失敗7成功12.41秒。期限修復後、出力queryの未定義org/employee変数が再現（1失敗8成功12.09秒）。修復GREEN9成功11.13秒。

独立レビューは0Critical/13Important。1回の修正passで対応し、再レビューは行わない。API回帰RED13失敗23.47秒。監査理由テストのフィールド参照をafter_dataへ訂正し、理由保存を外した状態で改めてRED1失敗3.69秒を確認。実JavaScript回帰RED4失敗0.79秒、権限refresh成功時のread喪失もRED1失敗0.16秒。修正後、API/旧勤務/UI合わせて28成功11skip27.44秒。実PGとChromiumはlocalで実行できないため明示skipし、exact-head CIで判定する。

| 重要指摘 | 対応・回帰証拠 |
|---|---|
| 操作中のsession/権限失効 | 共通require_mutation_permissionでaccount-change transaction lock取得後、元session・active職員/組織・password・current permission再確認。session/permission/employee/passwordの4ケース |
| 過去日付・同時承認による残高不足 | 承認済み＋提案の全日付balanceを検査し、将来分を含め負数拒否。両Ledgerのbackdateテスト、PGの競合承認テスト |
| 重複配置競合 | 人事変更と同じtransaction lockで取込/手入力/承認を直列化。PG手入力同士・取込対手入力・同一preview同時confirmで1件のみ成功を検証 |
| timezone消失/partial patch | UTC保存・UTC応答。結合した勤怠期間をflush前に422検証。混在offset・checkoutだけPATCH・逆転期間テスト |
| 滞在時間を正式勤務時間にする誤り | 勤務開始からのHuman設定勤務区間を明示承認、配置へ承認者/理由/version/scheduleをsnapshot保存。区間と勤怠の重なりで正式分数を計算。24時間1440分の滞在に対し設定945分を検証。Ruleなしは正式承認不可 |
| 勤怠ボタン上書き | kind別selectorと正しい主キーでbind。勤怠と時間Ledgerが同じ画面にあるJS/Chromiumテスト |
| stale Ruleを不足0表示 | 判定不可・不明を明示、nullを0にしない。JS/Chromiumテスト |
| 日本の朝の休暇が422 | 日本時間で入力をserialize、business timezoneでeffective_on照合。UTC入力の日本朝/異なるbrowser timezoneテスト |
| stale承認配置の可用人数算入 | 現在の有効assignment/組織/approved work-rule snapshotを照合。crewから除外、warningへstale IDsと不足を返す |
| PATCHで日跨ぎ制約迂回 | 結合した勤務設定をcreateと同じ制約で検証、制度変更は承認を失効させる |
| Human理由消失 | 全transitionの監査after_dataにhuman_reason保存。取消も同じ処理を使う |
| 共用PCの過去state残留 | 401/403、identity変化、read喪失でDOM/cache/draft/controlを消去。generationで遅い過去responseを拒否。JS/Chromiumテスト |
| 200/1000件で切捨て | 安定した主キー順とoffset/limit、UI連続page取得。後半職員・1002件Ledgerテスト |

## Rulings

- 既存PR53をlease付き更新する。元headが変われば再照合する。重複実装を避けるため。並行変更があれば統合作業が必要になる。
- 変更済み人事履歴に結び付いた古い通常/応援配置は承認しない。最新根拠で再作成する。Humanの再配置作業が必要になる。
- 全勤務writeは共通account-change lockを取得する。人事/権限とのlock順を統一し、残高と重複も防ぐ。write throughputのproduction load検証は残る。
- payable_minutesだけから休憩位置や時間外制度を推定しない。Humanが勤務区間を入力・承認する。滞在と正式勤務分を分離し、時間外は独立Human Ledgerで確定する。実制度値/実RuleはHuman受入が必要。
- intervalは勤務開始からの分数。例はテスト用の合成値であり、本部の勤務制度の推奨値ではない。

## Deferred minors・残差

- export監査は共通監査完成Sliceへ引き継ぐ。
- source Document IDの表示権限/hash-binding/freshnessは原本連携完成Sliceへ引き継ぐ。既存原本download RBACは維持。原本内容の漏洩を示す証拠はない。
- 同時preview確認は重複正式配置につながるためImportantへ再分類し、PG競合テストに含めた。
- §25はPartial。team/work-result、checkout/edit/cancel/訂正のUI、残高/crewの利用画面、代休Ledger間の明示的なreconciliation、期限失効のHuman policyが内部残差。実環境へ逃がさず次のSliceへ継続する。
- expires_onは自動的に残高を消さない。Humanによるexpire Ledgerが必要。未確定な本部制度をAIが作らない。
- real PG/Chromium、実機共用PC、実Human制度受入は異なる証拠。CI完了/merge/mainGreenは更新時に記録する。

本Slice/PRが通ってもシステム完成ではない。財務統合、正式違反、危険物、図面AI/worker、横断E2E、本部別導入・更新・復元構成と最終release成果物まで同じ完成タスクを継続する。

最終local全体453成功58skip210warnings201.23秒、exit0。46migration/348statements、compile/diff/frontend syntax成功。独立レビュー1回＋修正pass1回を完了。PG並行処理5ケースとChromium勤務workflowはCI実行待ち。

CI repair: PR53 exact-head3a9c5f9 / CI37506984502のChromiumは5成功1失敗54.26秒。新fixtureのEmployeeAssignment.title必須値省略が原因。PG concurrency fixtureにも同じ省略があるため合成役職名を追加。実モデルのNOT NULLを維持。実browser fixtureの同じseedをlocal subprocessで実行しexit0、勤怠/時間Ledger/承認勤務Ruleの合成workflowを確認。改めてexact-headCIを実行する。

正本更新: CI中にPR55がmain0feb62e6へmerge、main CI37507500474 SUCCESSを確認。財務は048で正本化され、再実装しない。PR53の最新fixture修復head f6dc11b9はmain進行によるshared conflictでCIを起動できなかった。最新mainの32filesをexact SHAで取得し、ea15820eを基底として三者照合。bootstrap/main/router/search/navとworkflow7browserを両方保持して解消。財務body/models/money/schema/048/finance.js/finance-testsはcanonicalそのもの。新Migration一覧47files379statements。財務の共通session/permission recheckと共用PCクリアは内部Partialとして再監査に残す。

集計修正: 57章の行を再集計し、以前のsummaryのPartial/Missingに1章ずれがあることを確認。main0febのみは13Completed/35Partial/8Missing/1External。勤務Slice反映後は13/36/7/1。summaryを行の実集計に揃え、未mergeの勤務を正本のCompletedとはしない。

財務正本統合後local全体500成功60skip248warnings218.98秒、exit0。47migration379statements・compile/frontend/diff成功。canonical main32filesをea基底へ当てたtree80f9959dがGitHub main treeと完全一致することを確認し、財務の正本fidelityを保持した。
