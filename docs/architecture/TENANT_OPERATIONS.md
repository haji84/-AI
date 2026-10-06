# 本部別運用契約

確定日: 2026-10-06。利用者承認済みの方式A。手順の固定仕様であり、実機導入済みという意味ではない。

## 配置単位

| 資源 | 固定契約 |
|---|---|
| 共通コード | `/opt/fire-ai/releases/<release-id>`、不変版、管理者所有、実行ユーザーから書込不可 |
| 本部設定 | `/etc/fire-ai/<slug>.env`、本部UUID、DB資格情報、固定Host、専用保存先、0600 |
| 実行環境 | 本部別OSアカウント・venv・systemdサービス・待受ポート。DB接続は設定で固定 |
| DB | 本部専用PostgreSQL DB。所有/移行ロールと通常実行ロールを分離。PUBLIC CONNECTを取消す |
| 原本・派生物 | `/var/lib/fire-ai/<slug>/storage`、本部OSアカウントのみアクセス、0700 |
| backup | `/var/backups/fire-ai/<slug>`、他本部OSアカウント・アプリからアクセス不可 |
| ブラウザ | 本部専用DNS/HTTPS、Host許可リスト、Host-only/Secure/HttpOnly/SameSite cookie |
| 同一本部の署所 | 同じDB・アプリを利用。所属・権限で業務範囲を制御 |

slugは運用上の名前、不変UUIDが識別子。名称やサーバーが変わってもUUIDを変更しない。
共有DBのtenant列方式は採用しない。DB資格情報の誤設定をUUID照合で検出する。
同じサーバーの複数本部も別アカウント・DB・保存先・backupとする。
サービスごとに専用venvを共通releaseから構築し、共有コード書換えによる全本部一斉変更を防ぐ。

## 本部追加

1. 管理者がUUIDとslug、DNS、容量、backup先、担当者を登録する。
2. 専用OSアカウント、DB、移行ロール・通常ロール、ACL、実行環境、HTTPSを作成する。
3. 移行用資格情報で全migrationを適用する。通常ロールへ必要DMLのみを付与する。tenant_identityはSELECTのみ。
4. 専用設定で `python scripts/initialize_tenant.py --name '<本部名>'` を実行する。新規DBに業務データがある場合は拒否する。
5. 通常資格情報へ切替え、管理者bootstrap、ヘルスチェック、2PC同時利用・競合検出、別本部アクセス拒否を確認する。
6. 最初のbackupと復元演習を実行し、UUID、release、migration、hash、担当者、日時を記録する。

## 既存データの採用・サーバー移行

- 未識別既存DBを採用する前にアプリとCLIの書込を停止し、DBと原本のbackup/hashを取得する。
- 本部と元データの帰属を人が照合したうえでのみ `--adopt-existing-data` を使用する。
- 別UUIDが既に登録されたDB/原本はadoptでも拒否する。既存UUIDを書き換える手順は設けない。
- 移設は同じUUID・同じreleaseから開始し、停止中のDBdumpと原本を一組で移す。
- 新旧両方への書込を禁止する。新側の件数/hash/監査/ログイン/業務確認後にDNSを切替える。
- 別本部への個別データ移管は全DB復元で代替しない。別途Human承認・権限・証拠付き移管仕様を必要とする。

## 更新

1. 各本部の現在release・DB migration一覧・backup復元実績を確認する。
2. 本番cloneの隔離環境で新releaseのmigration・回帰・復元を先に検証する。
3. 対象本部の書込を停止し、DBと原本を整合した一組でbackupする。
4. その本部だけmigrationを適用し、専用venvのreleaseを切替える。
5. UUID照合、health、RBAC、Human Gate、件数、原本hash、2PC競合を確認して再開する。
6. 他本部のreleaseを自動切替えしない。migration後の失敗で旧コードだけへ戻さず、対応済み修正版かDB+原本の一組復元を使う。

## backup・復元

- UUID、release、migration一覧、DBdump hash、原本archive hash、実行日時をmanifestへ記録する。
- DBと原本の整合性のため全書込を停止して取得する。オンラインbackupは整合snapshotを実装・検証するまで採用しない。
- 復元先UUIDとmanifest・dump内DB identity・原本markerがすべて一致することを、対象DB/原本の変更前に検証する。
- 他本部UUID、欠落した識別子、hash不一致、不正archiveを拒否する。
- 対象本部を停止し、復元前backupを別保存したうえでDBと原本を一組で復元する。
- DBとファイルの復元は一つのtransactionにならない。双方の成功と復元後確認まで停止を維持し、失敗時は復元前の一組へ戻す。
- 本番とは隔離された同UUIDの演習先で定期的に復元する。演習先は本番DNS・外部送信・定期ジョブから隔離する。

## 実装と残作業

本SliceはDB/原本UUID、設定検証、起動/API/Sessionの拒否、明示初期化を実装する。
backup manifestの識別子検証、dump事前検証、専用サービスの自動構築、実PostgreSQLロール検証・復元演習は次の実装Sliceに引き継ぐ。
この文書に手順があることだけをもってそれらをCompletedにしない。
