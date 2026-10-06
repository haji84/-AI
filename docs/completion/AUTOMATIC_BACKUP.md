# 本部別の自動バックアップと保守排他

共通releaseを使用し、本部ごとにDB・実行環境・原本・バックアップを分離する。生成器は本部専用のアプリserviceに加え、毎日03:00（Asia/Tokyo）のbackup service/timerを生成する。生成しただけではサーバーを変更しない。

## 導入

1. `scripts/generate_department_config.py`で承認済みUUID・slug・DNS・port・releaseを指定する。既存の本部追加手順でDB、アプリ、原本を初期化する。
2. `/var/backups/fire-ai/<slug>`をroot所有0700で作成する。容量・別媒体への保存・障害通知を運用管理者が確認する。backup envはroot所有0600、専用本部のapp DB認証のみを使用する。owner/cluster管理者の資格情報をbackupへ渡さない。
3. `FIRE_AI_BACKUP_WRITER_UNITS`へ、この本部の原本またはDBを更新する全CLI/同期処理のsystemd service/timerをJSON配列で登録する。命名は`fire-ai-<slug>-<処理>.service`/`.timer`。他本部のunitとbackup自身は拒否する。未登録の手動writerは停止・運用禁止時間を管理者が定める。未登録の書込を自動発見したとみなさない。
4. 生成した`fire-ai-<slug>-backup.service`と`.timer`を`/etc/systemd/system/`へ配置し、`systemctl daemon-reload`、まずserviceを手動実行して成否/復帰を確認、その後timerを有効化する。root serviceは対象本部のservice制御とowner-only出力のために使用する。DBアクセスはその本部のapp資格情報のまま。
5. journalと`systemctl --failed`を庁内監視へ接続し、失敗時に担当者へ通知する。自動バックアップは取得を自動化するもので、成功監視や容量監視を省略しない。

## 処理と競合

実行前にproduction PostgreSQL、UUIDとDB/原本markerの一致、固定保存先、owner-only backup先を確認する。保存先の排他flockで同時実行を拒否する。既存の稼働状態を取得し、timer→登録writer→アプリの順に停止する。停止に失敗した場合は取得しない。

取得CLIは本部UUIDのPostgreSQL exclusive advisory lockを保持する。通常のBoundSessionは毎transactionにshared lockを取得するため、実行中transactionが残っている場合は保守開始を拒否し、保守中の新規transactionはHTTP503/Retry-Afterとなる。停止したサービスのうち元々稼働していたものだけをfinallyで再開する。バックアップは読取取得であり、失敗時も元のDB/原本へ復元処理を自動実行しない。再開失敗はエラーとなり担当者対応が必要。

migration CLI/restore CLIも本部exclusive lockを使用する。migrationライブラリはDB内のmigration操作をさらに直列化し、同時適用を拒否する。初期構築のmigrationだけ未初期化DBを許容する。既存UUID不一致は拒否する。アプリを停止しない管理者CLIや独自直接SQLは自動バックアップと併走させない。

## 保存と復元

既存のformat2 manifestにUUID、release、migration一覧、DB/原本hash、停止確認を記録する。`tenant.backup.started`はdumpに含まれる。manifestのない途中失敗フォルダは完成バックアップとして扱わない。自動削除/保持期間は設定しない。保持・別媒体複製・削除は管理者の承認済み方針に従う。

復元は人が指定する別の明示操作であり、timerからは呼ばない。停止、復元前保存、同一UUIDの初期化済み対象、選択したrelease、hashと原本markerを検証する。owner envでrestoreを実行し、grantsを再適用し、DB件数・原本hash・監査・loginを確認してから起動する。DBとfilesystemは単一transactionでないため、復元失敗時は停止を維持する。既存の`TENANT_OPERATIONS.md`と生成READMEの復元手順を使用する。

## 検証範囲

synthetic unit testsは停止順、他本部拒否、停止失敗、dump失敗時の復帰、重複起動拒否を確認する。実PostgreSQL CIはruntime/exclusive競合、保守例外後のlock解放、UUID不一致、同時migration拒否を確認する。実systemd・OS ACL・通知配送・容量・庁内LAN・本番復元受入は実機External Gateで、開発テスト成功から推定しない。

SIGTERMによる通常停止はbackup子プロセス群を終了して待機してから、元のサービスを再開する。起動中のoneshot同期も復帰対象に含める。停止中など他の遷移状態はサービス変更前に拒否する。SIGKILL、電源断、OS停止はfinallyを実行できないため、自動復帰を保証しない。管理者は本部のservice/timerの開始前状態と停止ログを確認し、manifest未完成の取得を除外して元の稼働状態へ戻す。バックアップ中の強制killは運用手順で禁止する。
