# 署名付き閉域法令更新

仕様38の取得原本・Source URL・Source Hash・Version・差分・manifest・署名を、既存のe-Gov XML/公式条例snapshotの更新経路へ接続する。取込は原文Versionとreview_required候補を追加するだけであり、法令Ruleの承認を代行しない。

## 固定契約

- Collectorだけが秘密鍵を保持する。Ed25519 PEM、Collector所有、0600。秘密鍵・実データをGitに入れない。
- 本部ごとの公開鍵trustを管理者がbundleとは別に設定する。bundle同梱鍵は採用しない。
- 署名はdomain separatorとmanifestの正確なUTF-8 bytesを対象とする。manifestの空白変更も改変として拒否する。
- manifestの原本hashを全件照合し、専用一時領域へコピーする。パス逸脱、symlink、特殊ファイル、重複JSON、不正/巨大ZIP、壊れたLaw XMLを業務DB・原本変更前に拒否する。
- 同一本文を複数の公式URLが共有する場合は同じhashの原本を共用し、URLごとのVersionを保持する。異なるhashが同じパスを指す場合は拒否する。
- CollectorはHTTPSと取得開始時の公式hostを固定し、別host/HTTPへのredirectを追わない。effective URLと取得方針もmanifestに保存する。
- 未知/失効鍵、適用host外、hash/署名不一致、古い取得時刻、同時刻の異なるmanifestを拒否する。原本・Version・監査に署名者/manifest hash/取得時刻の証跡を残す。
- bound本部またはproductionの取込は署名を必須にする。unsigned互換は未boundの開発環境だけ。存在する不正署名をunsignedへ降格しない。

## 公開鍵の設置・交代

`FIRE_AI_LEGAL_UPDATE_TRUST_FILE=/etc/fire-ai/<slug>-legal-trust.json`を本部envに設定する。ファイルはroot所有、対象本部OSグループだけ読取可（0640）、アプリから書込不可にする。trustは以下の構造を持つ。鍵IDはraw公開鍵32bytesのSHA-256、公開鍵はBase64。

```json
{"format":"fire-ai-legal-trust-v1","keys":{"<SHA256-of-public-key>":{"public_key":"<Base64-32-bytes>","revoked":false,"allowed_hosts":["laws.e-gov.go.jp"]}}}
```

鍵の真正性と担当者を別経路で確認して管理者が設置する。交代時は新公開鍵を先に各本部へ追加し、Collectorを切替え、旧鍵をrevoked=trueにする。失効済み鍵の過去bundleも再搬入を拒否する。開発が本番鍵を自動選定・配布することはない。

## Collectorと搬入

Collector側でbackendを専用venvへinstallし、`PYTHONPATH=backend`を設定する。オンライン取得環境にのみ`FIRE_AI_COLLECTOR_SIGNING_KEY_FILE`を設定するか、collectorの`--signing-key-file`で保護されたPEMのパスを指定する。引数に秘密鍵そのものを渡さない。

```bash
PYTHONPATH=backend python scripts/collect_egov_update_bundle.py --mode all --output-dir /approved-out/new-bundle --signing-key-file /protected/collector.pem
```

条例は既存`collect_official_regulation_snapshot.py`の公式index/allowed-host/include/crawl指定へ同じ署名引数を追加する。署名済み出力を上書きせず、取得ごとに新しい出力ディレクトリを使う。原本・manifest・`<manifest>.signature.json`を一組として承認済み経路で搬入する。

## 更新フォルダ

本部専用サーバーでsourceのupdate_modeをbundleにする。フォルダ直下か1階層のbundleディレクトリに配置する。`source-id`は既存LegalSource UUIDで固定し、folder内ファイルからDB接続先・本部を選ばない。

```bash
PYTHONPATH=backend python scripts/process_legal_update_folder.py --source-id '<source-UUID>' --folder /var/lib/fire-ai/<slug>/updates/<source-UUID>
```

一つのfolderは同時実行を拒否する。正しい署名・原本を検証してから既存importerを固定プロトコルで実行する。成功receiptはDBの監査へ保存し、次回は再検証後に重複処理を避ける。folderのJSONマーカーを完了証拠として信用しない。拒否があればexit1と理由を返し、後続bundleの検証を継続する。運用スケジュールは対象本部OSアカウントでこのコマンドを定期実行する。

## 制約・実証

POSIX/Linuxサーバー用。クライアントには追加アプリ不要。署名はCollectorと原本の搬入証跡を保証するが、条文内容の正確性や正式Ruleを確定しない。一次資料と条文引用のHuman審査は既存Gateで継続する。本番公開鍵の真正性確認・承認搬入経路・正式Rule網羅性はExternal Gate。

テストは人工XML/HTMLと一時鍵のみ。production相当importで署名者証跡、候補作成、Rule未作成、再取込冪等性、不正署名時の原本/DB不変を確認する。実施結果はRUN_A_STATUS.mdとPR CIに記録する。

実装参照: https://cryptography.io/en/48.0.1/hazmat/primitives/asymmetric/ed25519/ 。暗号primitiveはライブラリのsign/verifyを使用し、独自実装しない。

ローカル最終検証: focused25件成功、全backend322件成功/6skip/168warnings。fresh-contextレビューの3重要指摘と不正署名schemaの指摘を修正。PostgreSQLと実ブラウザの既存CIはPRで再実行する。
