# 違反・改善措置 Evidence

正本基準main ecbd0a7d / CI37513897759 SUCCESS。開PRなしを再取得。現在このSliceはmain未反映であり、システム完成・実案件の正式判断を宣言しません。

正式仕様§13の候補/正式違反/指導/命令/処分/回答/現地Human確認/完了・訂正履歴を独立APIとブラウザへ実装。Migration049は新規4表、canonical001–048は変更しません。共通コード、本部別DB/runtime/original/backup方式を維持。

- Case初期RED11→GREEN15。Rule条文hashはcanonical ProvisionRecordを使用。AI Confidence/UUID/sourcehash/理由、改訂競合、未承認Rule候補を検証。
- 措置/改善初期RED6→GREEN21。指示変更RED1、旧回答原本改変RED1→GREEN23。回答/確認/完了の全証拠鎖を再照合。
- correction_eventsのapp-role更新/削除拒否RED1。原本権限喪失時の入れ子証拠漏れRED1→関連32passed1skipped。法令/原本根拠は履歴before/afterも再帰的に制限。
- source picker paging/独自RBAC RED1→GREEN1。検索/CSV candidate状態・式注入保護RED1→GREEN1。
- 実JavaScript: 権限失効中の遅延応答、画面切替、利用者交替を検証、3passed。最初のハーネスはファイル名をviolation.jsと誤記したため修正。実ファイルviolations.jsに対するGREENを確認し、修復時は有効なREDを別途記録する。
- 機能focused29passed6skipped26warnings25.28s。全49migration parser・shell/module構文確認。PostgreSQL/Chromiumは専用CIで実行し、local skipを本物の成功と扱いません。

実PG: 同時Case確定、Case完了と新指示、同じversionへの回答競合。実Chromium: 対象物/査察/Rule/原本選択→候補→Human正式確定→命令草案/確認/確定→改善指示→回答→否定/肯定確認→完了→履歴→logout消去。両者のexact-headCI・merge/mainGreen証拠は確定後追記。

運用手順: ../violations/WORKFLOW.md。残る内部業務/図面worker/成果物/10E2Eは連続して実装し、External Gateへ移さない。

## 独立レビューと1回のTDD修復

1名のfresh-contextレビュー: Critical0/Important6/Minor0。6件とも有効なRED（6failed7.59s）→GREEN（6passed8.34s）。再レビューは行わず、全体回帰とexact-headCIで検証します。

- canonical再解析後の古い承認引用: authoring契約と同じdisplay-label/heading/body全文snapshotとの一致を要求。過去の正式履歴は書換えず、新たな正式review/confirmを拒否。
- 一次資料raw_documentの欠落: 新たな正式review/confirmで原本必須、管理storage内の実hashを再照合。
- facility/inspection閲覧失効: case/measure/event/exportの入れ子根拠も再帰的に制限。
- cached画面・フォーム: 描画前の本人/世代/権限確認を追加。403時に古い原本・入力草案を消去。
- 完了済みCaseでも有効な命令/処分は改訂置換を妨げる。Human証拠付き措置撤回だけを完了済み親に許容し、正式履歴を保持。
- 改善取消/再開の画面権限を実APIと同じviolation.approveへ統一。担当に不可能な操作を表示せず、承認者が操作可能。

Rulings: Routine承認待ちは利用者の連続開発指示を採用。Human選択した承認Rule/条文/手続を正式判断の必要条件とし、AIから確定しない。改訂候補は複数可、正式置換は現行1件のみ。Draft Ruleは候補リンク可、正式採用不可。指導のみ改善はresolved_candidateで正式違反を作らない。指示/期限変更後は証拠鎖を再確認。共有routerのためTask2/3は1つのdomain commitで統合。最初の誤名JSハーネスREDは根拠として数えず、修復6件の実再現を使用。これらが誤る場合は追加のHuman根拠入力/レビューまたは仕様照合が必要になるが、AI自動確定を正当化しない。

残る内部AI候補生成worker接続は共通AI実処理のPartialに含める。APIでAI候補を受け取れるだけで、実worker/実図面Baselineやrelease完成を宣言しない。
