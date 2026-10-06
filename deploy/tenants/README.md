# 本部別サーバー構成

正式契約: `docs/architecture/TENANT_OPERATIONS.md`。Linux/systemd + PostgreSQL + nginx/TLSを導入用構成とする。
共通releaseを変更せず、本部ごとにDB/通常・移行ロール/OSアカウント/venv/保存先/backup/Host/ポートを割り当てる。

## 設定一式の生成

サーバー操作を伴わない生成コマンド。UUID・DNS・ポート・releaseは実際の管理台帳に従って指定する。
以下は合成例であり、本番UUIDとしてコピーしない。

```bash
python scripts/generate_department_config.py \
  --slug example \
  --tenant-id 00000000-0000-4000-8000-000000000001 \
  --host example.fire.internal --port 8101 \
  --release-id release-20261006 --output /tmp/fire-ai-example-config
```

生成先は新規0700ディレクトリ、各ファイル0600。既存ディレクトリを上書きしない。
生成されるREADMEにその本部の追加・移行・更新・backup/復元手順と固定パスがある。
SQLにpasswordは含めず、psqlの `\password` で人間が設定する。envのplaceholderへURLエンコードした資格情報を設定し、Gitへ保存しない。

## 適用の順序

1. 管理者所有の不変release、専用OSユーザー、専用venv、専用storage/backupのACLを作る。
2. cluster管理者で `00-create-<slug>.sql`、本部DB ownerで全migrationと本部初期化を実行する。
3. DB ownerで `01-grants-<slug>.sql`。migration後の各更新でも再適用する。
4. runtime envはappロールのみ。migration envをアプリへ渡さない。env root所有0600、storageサービスユーザー所有0700、backup root所有0700。
5. nginx/service/TLSを管理者が確認して適用する。固定HostはLAN DNSまたは管理済み名前解決で各PCへ配布する。クライアントへの追加アプリは不要。
6. 他本部CONNECT拒否、identity更新/監査改変拒否、OS ACL拒否、2PC競合、バックアップ復元演習を記録する。

本番起動では通常DBロールにsuperuser/CREATEDB/CREATEROLE/BYPASSRLSやidentity書込・既存監査の更新/削除権限がある場合も拒否する。
DB ownerは明示migration/初期化/復元にだけ使う。Human管理者bootstrapや通常取込CLIはappロールを使う。

## backup/復元の契約

全書込を停止し `--confirm-writers-stopped` を指定する。停止はフラグだけで実施されない。service/定期sync/取込CLI等を管理者が停止する。
UUID・release・migration一覧・DB/原本hashをmanifestへ記録する。
復元はUUID、dump内identity、原本marker、復元先DB/root、`--expected-release-id` を事前照合する。
DSNをコマンドラインへ出さないため、`--target-database-env FIRE_AI_DATABASE_URL` を優先する。資格情報入りenvは管理者だけが扱う。
復元には事前に同UUIDで初期化した専用DB/rootが必要。復元後原本の所有者はarchiveのUIDではなく復元先サービスユーザーを保持し、0700/0600を設定する。

DBとfilesystemは単一transactionではない。双方と検証が完了するまで停止を維持する。失敗時には事前backupのDB+原本一組へ戻す。
Windows版の既存起動スクリプトはこのLinux用OS ACL検証の代替として本番承認しない。

## 検証範囲

CIでPostgreSQL16の全migration、再適用、専用ロール、他本部CONNECT拒否、identity/監査改変拒否、custom dump/復元を検証する。
生成したservice/nginx設定の実機適用、OS ACL・証明書・実LAN・2PCと復元後受入はExternal Gate。生成だけで導入完了としない。

運用上の固定制約: DB名は生成される `fi_<slug>` を使用する。手動DSNで特殊な接続文字列形式のDB名を指定しない。appロールに他DBロールへのmembership/SET ROLEや列単位のidentity/監査更新権限を追加しない。通常ロールのbackup→owner復元→権限再適用の実機一連確認は受入Evidenceへ残す。復元でテーブル/スキーマが再作成されるため、再開前に生成されたgrants SQLを復元先ownerで再適用する。
