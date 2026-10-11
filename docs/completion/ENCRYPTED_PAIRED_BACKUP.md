# 本部別暗号化 paired backup（Issue #100 境界）

## 実装境界

既存 format2 の `manifest.json`、DB dump、`storage.tar.gz` を一つの TAR payload にまとめ、その payload 全体を X25519 鍵合意、HKDF-SHA256、AES-256-GCM で認証暗号化する。公開後のフォルダは `envelope.json` と `backup.enc` の二つだけで、manifest、DB、原本archive、秘密鍵を平文で含まない。独自の backup/restore engine は追加せず、復号後は既存の release、migration、tenant UUID、DB/original marker、hash、archive traversal/link/special-file、target preflight をすべて再利用する。

外側 envelope version は 1 とし、algorithm、tenant UUID、recipient 公開鍵の SHA-256 fingerprint を用いた key ID、backup UUID、ephemeral public key、nonce、ciphertext filename を canonical JSON AAD に含める。これらの値、ciphertext、GCM tag のいずれかが変更・欠落・置換・切断された場合は復号しない。未知 version/algorithm、余分な公開ファイル、別本部、別鍵、`FIRE_AI_BACKUP_REVOKED_KEY_IDS` に列挙された key ID も拒否する。

## 鍵と staging

生成器は本部別の公開 recipient path `/etc/fire-ai/keys/<slug>-backup-recipient.pem` と `FIRE_AI_BACKUP_ENCRYPTION_REQUIRED=true` を設定する。scheduled entry point は公開鍵の内容やpathを子 process argv へ渡さず、環境変数名だけを渡す。required mode で公開鍵が未登録なら、writer/service を停止する前に fail closed し、旧 plaintext backup へ戻らない。

復号秘密鍵は backup、DB、原本、release、公開先、staging と分離した regular file かつ group/other 権限なしでなければならない。restore CLI には鍵内容/pathではなく、鍵pathを保持する protected environment variable 名を `--decryption-private-key-env` で渡す。復号は owner-only temporary staging で行い、成功・拒否・例外の全通常終了経路で削除する。復号済み format2 が全 preflight を完了する前に target DB/原本を変更しない。

## 操作

手動取得は全 writer 停止と既存確認に加え、承認済み本部 recipient path を protected environment に置き、次を実行する。

```sh
PYTHONPATH=backend python scripts/backup_phase1.py \
  --destination /var/backups/fire-ai/<slug> \
  --release-id <approved-release> \
  --confirm-writers-stopped \
  --recipient-public-key-env FIRE_AI_BACKUP_RECIPIENT_PUBLIC_KEY
```

承認済み復元では、別管理された秘密鍵pathを recovery environment にだけ設定し、既存の明示 target/release/writer-stopped 条件に鍵envを追加する。

```sh
PYTHONPATH=backend python scripts/restore_phase1.py <encrypted-backup-folder> \
  --target-database-env FIRE_AI_DATABASE_URL \
  --target-storage-root /var/lib/fire-ai/<slug>/storage \
  --confirm-restore --confirm-writers-stopped \
  --expected-release-id <approved-release> \
  --decryption-private-key-env FIRE_AI_BACKUP_PRIVATE_KEY
```

stdout/stderr は backup path、DB kind、成功状態だけを返し、鍵内容/pathを出力しない。

## 検証済み範囲と未完了条件

synthetic SQLite テストで、同一 UUID の DB/原本/監査 round trip、metadata/ciphertext/tag の改変、切断、別 envelope の完全置換、別鍵・別本部・失効鍵、秘密鍵 symlink/公開権限と backup・DB・原本・release/app・staging への co-location、公開先の余分なfile、暗号化 UUID folder からの pair 欠落、途中暗号化失敗、missing recipient、終了 signal、失敗時 target 不変を確認する。既存 plaintext format2 と scheduled stop/cancel/activity restoration の回帰も維持する。

この slice は §42.1 Completed ではない。実 PostgreSQL 暗号化 pair の同一 UUID 別 target 実証、実 recipient enrollment、秘密鍵 custody/rotation/revocation/emergency access、本番適用、immutable Owner Vault、保持/削除、別媒体、HA fencing、強制終了/電源断後の cleanup、新 PC/site-loss RPO/RTO は未実証で Human/External Gate のまま。公開鍵を設定したことを private key の保管承認や Vault 実装とみなさない。
