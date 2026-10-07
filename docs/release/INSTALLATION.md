# 導入と初回起動

対象: Python 3.11以上。通常職員のPCはWebブラウザだけを使います。この手順は配布ソースの起動・導入準備であり、本番承認を行うものではありません。

第1節の展開前検証を除き、コマンドは展開したreleaseのルート（`backend/` と `frontend/` があるディレクトリ）で実行します。`.env` の読込はカレントディレクトリ基準です。`backend/.env` を作成してからルートへ移動しても、その設定は読まれません。以下では設定を環境変数として明示します。

## 1. 配布物の確認

配布元のcommit・SHA-256・CI記録を照合します。以下の展開前verifyは、配布元のGit repositoryから別途取得した信頼できるcheckout、または別途提供された検証済み生成器のディレクトリで実行します。未検証archive内のコードを取り出して信用する手順ではありません。

```bash
python scripts/build_release_bundle.py verify /path/to/fire-ai-release.tar.gz
```

archiveだけを受け取った場合は、まずOSのSHA-256計算ツールでファイル全体を検証し、配布元から別経路で受け取ったハッシュと一致することを確認してください。必要な検証器は同じ公開commitから取得します。verify成功後に新規ディレクトリへ展開します。既存の本番コード、DB、storageへ上書き展開しません。

Python依存パッケージとOSツールは同梱されません。依存取得先や閉域への搬入方法は組織の承認手順に従ってください。

## 2. ローカル合成データ確認（Linux/macOSの例）

これは1台のPCのlocalhostで行う開発確認です。SQLite、Secure cookie無効、本部分離無効なので、LAN公開・本番データの投入はできません。新しい展開先と新しいターミナルを使い、本番用の`.env`を置かないでください。

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e 'backend[test]'

mkdir -p runtime/demo
unset FIRE_AI_TENANT_ID FIRE_AI_TRUSTED_HOSTS
export FIRE_AI_PRODUCTION_MODE=false
export FIRE_AI_COOKIE_SECURE=false
export FIRE_AI_DATABASE_URL="sqlite+pysqlite:///$PWD/runtime/demo/fire-ai.db"
export FIRE_AI_STORAGE_ROOT="$PWD/runtime/demo/storage"

python -m app.bootstrap --username demo-admin --display-name '合成検証管理者'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

bootstrapは12–128文字のパスワードを対話入力で求めます。パスワードをコマンド、文書、Gitに書かないでください。同じユーザーの再bootstrapは拒否されます。すでに作成済みなら最後のuvicornだけで再起動します。

ブラウザで `http://127.0.0.1:8080/ui/` を開き、作成した管理者でログインします。対象物の新規登録、検索、編集、ログアウトを合成データで確認してください。このSQLite確認ではPostgreSQL migrationは実行しません。SQLiteはbootstrapの開発用table作成を使い、PostgreSQL固有の制約・ロック・本番移行成功の証明にはしません。

静的画面はソースツリーの `frontend/` を参照するため、この構成では `pip install -e` を使い、展開後のreleaseディレクトリを移動しません。Python packageだけをコピーする配布には対応していません。

## 3. 本部別PostgreSQL導入

正本: `docs/architecture/TENANT_OPERATIONS.md`、実行手順: `deploy/tenants/README.md`。古いPhase 1文書よりこれらを優先します。

管理者が用意するもの:

- 本部UUID、slug、固定DNS、承認されたTLS、専用port
- 専用OSアカウント、storage/backupの所有権・ACL
- PostgreSQL 16で検証された専用DB、owner（移行）/app（通常実行）role
- 管理者所有・サービスユーザー書込不可の固定releaseと専用venv

以下は設定ファイルを生成するだけの合成例です。実本部のUUIDとしてコピーしないでください。

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e backend
python scripts/generate_department_config.py \
  --slug example \
  --tenant-id 00000000-0000-4000-8000-000000000001 \
  --host example.fire.internal --port 8101 \
  --release-id fire-ai-20261006-rc1 \
  --output /tmp/fire-ai-example-config
```

生成先のREADMEを確認し、実環境の値で別途生成します。生成だけではDB、OSアカウント、service、TLSは作られません。SQLにはpasswordを保存せず、管理者が対話設定します。編集後のenvはGitや成果物へ戻さないでください。

本番配置後は、本部専用venvに固定releaseのbackendをeditable installします。サービスユーザーにはreleaseとvenvの書込権限を与えません。管理者のmigration設定を読み込み、同じreleaseルートから順序どおり実行します。

```bash
# 管理者の管理されたshell。本部名に置換し、秘密値は表示しない。
set -a
. /etc/fire-ai/migration-example.env
set +a
/opt/fire-ai/instances/example/venv/bin/python scripts/migrate_database.py
/opt/fire-ai/instances/example/venv/bin/python scripts/initialize_tenant.py --name '承認済み本部名'
```

初期化はRBAC seed/管理者bootstrapより先です。新規本部には空DB・空storageを用い、既存データ採用フラグを安易に付けません。初期化後のstorageと `tenant-identity.json` は本部サービスOSアカウントが読書きできる所有者にし、rootは0700・通常ファイルは0600にします。管理者実行によりmarkerがroot所有になった場合も、service開始前に修正・確認します。

次にDB ownerとして生成されたgrants SQLを適用し、通常app roleの設定へ切り替えて管理者を作成します。

```bash
set -a
. /etc/fire-ai/example.env
set +a
/opt/fire-ai/instances/example/venv/bin/python -m app.bootstrap \
  --username admin --display-name '管理者'
```

bootstrapは共通role/moduleのseedも行います。既存本部の更新時は、migrationとgrants適用後に通常設定で `python scripts/seed_rbac.py` を実行し、新しいpermission/moduleを反映します。通常運用へowner/superuser資格情報を渡しません。

その後、生成service/nginx、承認TLSを管理者が適用します。HTTPSの `/ui/`、固定Host、別本部拒否、2PC競合、監査改変拒否を確認します。通常roleの起動検証が失敗したら安全設定を弱めず、UUID、role、grants、storage所有権を確認してください。

## 4. 更新・backup・復元

新releaseは対象本部だけに適用します。隔離cloneで検証し、全writer停止とDB+原本の一組backupを取得してからmigration、grants再適用、専用venv/serviceのrelease切替を行います。古いコードだけを戻すと新schemaと不整合になるため、失敗時は正本の復元手順を使います。

backup/restoreは `deploy/tenants/README.md` と生成READMEに従います。書込停止フラグはサービスを自動停止しません。scheduled orchestratorを使わない手動作業では、管理者がapp・CLI・timer等を停止して確認します。DBとfilesystemの復元は単一transactionではないので、両方と受入検証が完了するまで再開しません。

## 5. 検証と既知の境界

```bash
python -m unittest discover -s backend/tests -p test_release_bundle.py -v
python -m pytest backend/tests -q
```

後者のPostgreSQL/Chromiumテストは必要サービス・明示設定がなければskipします。全チェックの成功は固定commitのCIで照合し、実機受入は `RELEASE_READINESS.md` に記録します。

配布機構の初回検証基準はmain `707ccdd48b2cadacf77a90726377107ec5573fee` で、`PACKAGING_TEST_REPORT.md` はその時点の検証記録です。PR #63・#64を統合したmain `1dfb5cf233eb648f445a8201bca57394e9d2c24a` 以降は、財務画面から共通Documentへ原本を新規登録する機能も含みます。実際の収録内容はmanifest commitを正本として扱い、その固定commitのCIと展開後の起動を確認します。組織へ渡す前の初回操作・実機受入は別途記録してください。

### 財務の初回原本登録について

施設や原本が未登録でも、財務画面から共通Document原本を登録して草案に選択できます。まず合成データで次の手順を確認します。

1. 管理担当者が年度・通貨・小数桁などの財務設定を登録し、既存のHuman承認を完了します。これは原本登録とは別の事前準備です。
2. 財務・契約の登録権限に加えて `document.create` と `document.read` を持つアカウントで `/ui/` にログインします。「契約・予算」→「契約台帳」→「契約登録」を開きます。
3. 件名・年度・通貨・契約額を入力し、「新しい根拠原本」で合成ファイルを選び、「原本を登録して選択」を押します。登録中は進行説明が表示され、草案保存や画面内の移動がロックされます。
4. 登録後に原本が自動選択され、ファイル名・SHA256・Document ID・原本リンクが表示されることと、入力した草案が保持されることを確認します。財務画面からの原本登録では施設との関連付けを行いません。
5. 「保存」後、契約台帳の「契約・根拠」から草案と原本リンクを確認します。この保存だけで正式承認や予算執行は行いません。既存の根拠確認・Human承認を経て正式反映します。

原本はupload時点で共通Documentへ保存され、財務とのリンクは草案保存時に作成されます。草案を閉じても登録済み原本は残ります。登録成功後に選択確認を完了できなかった旨が表示された場合は、画面を開き直して原本を検索し、重複登録を避けます。セッション・権限の変更で画面が消去された場合も、現在のアカウントで再ログインして確認します。

PR #64の固定head `7c399cdd75ff89b1b1130f11acf9b8c5b6808908` では、初回登録から草案保存、権限拒否、連打、遅延応答、セッション変更を含む財務21件の実Chromium検証が成功しています（[CI記録](https://github.com/haji84/-AI/actions/runs/37550941548)）。これは当該headの合成データによる記録であり、最終manifest commitのCIや本部の実機受入を代替しません。

技術担当者は共通 `POST /documents/upload` からも確認できます。同一サーバーの `/docs` にある標準Swagger画面は外部CDNのassetを参照するため、閉域・オフラインでの表示を保証しません。通常の原本登録は上記Web手順で確認し、API確認が必要な場合は組織が承認した接続環境・API clientを使用します。CSV/XLSXの財務データ取込は、契約原本の登録とは別の機能です。


<a id="first-use-common-workflows"></a>

### 初回確認: 今日の業務・文書受付・危険物台帳

初回は権限を設定した合成データ用アカウントで確認します。利用できる範囲は、導入したmanifestのcommitと現在の権限に従います。

- 上部の「今日の作業」を押して「今日の業務」を開きます。資機材・車両の期限、改善措置、照会の確認待ちを確認し、「元記録を開く」から既存の詳細画面へ移動します。「自分が作成・借用したもの」は作成者・借用者との関係であり、全業務の担当者割当を意味しません。[利用範囲と確認手順](../completion/WORK_QUEUE_VERIFICATION_20261007.md)
- 対象物の「届出・報告受付」→「文書解析して受付」で原本を登録し、対象物と書類種別をHumanが確認します。正式番号は既存の採番元で取得した数字を入力し、受付後の台帳差分は項目ごとに明示確認します。確認済み受付の再確定は拒否されます。現在は対話を中断して再開する専用画面がないため、結果を確認してから操作を続けてください。[受付の動作・制約・検証](../completion/INTAKE_LIFECYCLE_VERIFICATION_20261007.md)
- 「危険物台帳」は必要な台帳・対象物・原本権限を管理者が付与してから使います。既存対象物に施設・設備と正確な数量・単位を登録し、原本と版を確認して「Human証拠確認済」にします。これは許可発行や法令適合の自動判定ではありません。変更時は改訂草案を使い、過去の根拠と履歴を保持します。[危険物台帳の使用手順と残る範囲](../completion/HAZARDOUS_REGISTER_VERIFICATION_20261007.md)

現在の実装範囲と未完了項目は [全57章の完成状況](../completion/CURRENT_COMPLETION_LEDGER.md)、本番導入の別途確認は [RELEASE_READINESS](RELEASE_READINESS.md) を参照してください。
