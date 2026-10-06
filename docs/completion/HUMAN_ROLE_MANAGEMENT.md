# Human権限管理

Task8 canonical base: main24a0ea8db84a152a5bcf56a206c5c15181b18083 / PR54。main CI37494620742 SUCCESSを再取得。開PR53 workforceは未merge・CI失敗中のため正本へ取り込まず、Migration044を予約として避け、本Sliceは046を追加する。既存001–043/045を編集しない。

## 利用と権限

ブラウザ `/ui/permissions.html` を開く。通常の認証済み職員は自分の現在の有効Role、権限コードと説明、永続・辞令・所属/役職Rule・期限付き・代理という付与元と有効期間を確認できる。他の職員の氏名・代理元・私的理由を本人向けAPIへ返さない。

`account.manage` を持つHumanだけが本部Roleを作成・編集し、Rule/期限付き付与の登録・停止・取消履歴を閲覧できる。システムRoleは読取専用。本部RoleのコードはサーバーがUUIDから生成し、RBAC seed更新後も保持する。登録済み権限のみ選べる。機微権限は明示チェックと確認理由が必要。権限を空にして読み取り権限をすべて外すこともできる。無効Roleは新規付与できず、既存付与の効力も停止する。

Ruleは所属・役職のいずれかを必須とし、指定した条件をAND・完全一致で評価する。辞令の本務/兼務・本部業務日(JST)・所属の有効状態に従う。AIによる役職推測は行わない。Rule条件を変更する場合は旧Ruleを停止して新Ruleを作り、証跡を残す。Rule名・条件・根拠は作成後固定、状態変更はversionで競合を検出する。

期限付き付与は開始・終了必須、両端を含む。代理元は対象者と異なる有効職員を指定する。代理元が無効、原本hashが変更、期限切れ、取消済みなら次の要求から権限が適用されない。代理は本人の資格や法定職務を自動認定しない。system_adminは永続明示付与に限定し、Rule・期限付き・代理から付与できない。最後の有効管理者保護は維持する。

根拠を使う場合は同じサーバーの `/documents/UUID/download` 原本リンクを入力して「原本を照合」。`document.read` に基づく名前・SHA256を確認する。保存時に同じhashをサーバーが再照合し、プレビュー後の差し替えを409で拒否する。根拠を指定しないHuman管理も許容するが理由・監査は必須。根拠が変更されたRuleは再有効化できず、新しいHuman照合が必要。

重要操作は確認ダイアログと理由、監査、既存account_change_lock配下での最新Human認証/RBAC再検証、CASを伴う。変更に関係するアカウントのセッションを失効し、権限を要求ごとにサーバーで算出する。取消は元の理由を保存し別の取消理由と時刻/操作者を記録、レコード削除を行わない。共有PCでlogout/認証失効時はフォーム・根拠・管理一覧を消し、古い応答を破棄する。

## 構成とMigration

共通コード、本部別DB・実行環境・原本・backupを維持。046はrolesのactive/version、human_role_rules、temporary_role_grantsとFK・日付/根拠pair制約・索引を追加。User/Employee/Organization/Documentを再利用し、本部を跨ぐ参照APIは設けない。更新前に本部ごとのpaired backupと保守停止、migratorによるmigration、更新後の確認を既存本部運用手順どおり行う。復元はDB・原本を同じUUID・release manifest単位で実行する。実機をここでは操作していない。

## Evidence / 未完

初期3APIテスト404 RED→3成功。本人向け根拠API404 RED→成功。原本プレビューhashと無効Role再付与2失敗→修正後10成功10PGskip。Rule原本変更時の再有効化200 RED→409 GREEN。local全体399成功41skip188warnings181.36秒、JS syntax/compile/diff check成功。PG/browser CI・独立レビュー・merge証拠は本Sliceの終了時に追記する。SQLiteの結果でPostgreSQL・実ブラウザを成功扱いしない。

本Sliceで製品全体は完成しない。資格・担当業務からのRule selector拡張、辞令原本からの人事候補/確認、正式違反、危険物、図面/worker統合、全E2E、本番構成・全マニュアル・release成果物を継続。資格マスタは開PR53の本部人員業務と正本merge後に再利用し、重複作成しない。実権限設計の採用・正式法令承認・実図面Benchmark・実LAN受入はHuman External Gate。

## 独立レビュー修正

5 Importantを受領、1 Minorの「新規Roleの有効チェック無視」はHumanが無効を選択しても有効化する実害としてImportantへ再分類し、合計6件を同じfix passで修正。再レビューは行わない。

- personnel.manageだけの辞令操作がHuman Ruleを介してaccount.manageを取得できた。現在・将来の期間重複と旧/新の完全一致条件を検査し、Ruleによる権限に関わる辞令変更はaccount.manageも必須。転入/転出/役職・期間変更も対象。所属自体を変更できることを権限付与承認とは扱わない。
- lock待機中に元セッションが失効しても操作ができた。認証された元token hashを要求単位のSessionに保持し、lock取得後に同じUser/元sessionの失効・期限を再検証。人事/権限/パスワード・learning Human操作へ適用し、logoutも同じlockで直列化する。秘密のraw cookieをモデル・監査・出力へ保存しない。
- 機微Roleの再有効化時は既存のpermission setにもackを必須とする。
- Role editorに読み込んだ版を保存し、再読込で取得した新しい版へ古いdraftを付け替えない。衝突時は409で止まり、編集対象を選び直して新しい権限を確認する。
- 本人権限の再取得時にaccount.manageが消えたら管理一覧・原本・フォームを除去。403も認証再確認として全private stateを除去し、古い応答を破棄する。
- 新規Roleの有効/無効選択を保存し、初期無効Roleは自動的に付与候補にならない。

RED evidence: API4失敗4PGskip（現在/未来self assignment、revoked request、unacknowledged sensitive resume）、実JS2失敗（draft CAS、管理権限喪失）、新規無効Role1失敗1PGskip。GREENと全体最終結果は下記追記。実RoleポリシーのHuman採用はExternal Gate、資格/担当selectorは引き続き内部Partial。

修正後の関連統合51成功35PGskip43.73秒、全体406成功46skip188warnings160.54秒。その後の権限再取得UI回帰3成功0.29秒（再取得1件もRED→GREEN）。Migration parser45files、JSsyntax/compile/diffcheck成功。CI/merge待ち。
