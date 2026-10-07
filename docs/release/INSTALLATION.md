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

この配布差分の検証基準はmain `707ccdd48b2cadacf77a90726377107ec5573fee` です。勤務・財務・照会・違反是正と、その後の権限/共有セッション修正を含む既存mainを保持しています。配布機構以外の業務コードは変更しません。実際の収録内容はmanifest commitを正本として扱い、初回操作を合成データで受入確認してから組織へ渡します。

### 財務の初回原本登録について

検証基準707ccddの財務画面は既存の共通Documentを選択する方式です。この配布差分には財務画面のupload改修を含めません。CSV/XLSXの財務データ取込は任意の契約PDF等の原本uploadの代替にはなりません。原本登録を含む一般職員向けの初回Web操作は、対応する画面改修と実ブラウザ検証の受入Gateとして残します。

技術担当者の確認用には、同一サーバーの `/docs` から共通 `POST /documents/upload` を実行できます。同一originの `/ui/` でログインし、`document.create` 権限があることを確認してください。fileに合成原本を指定し、対象物と無関係な契約ではbuilding_idを未指定にします。成功応答のDocument ID・SHAを確認後、財務画面の原本pickerを再読込します。

現行 `/docs` の標準Swagger画面は外部CDNのassetを参照するため、組織が承認した接続環境が前提です。閉域・オフラインでは画面の表示を保証しません。その場合は承認済みのAPI clientから同じ共通APIを使う技術的確認とし、オフラインの一般職員向け画面が完成したとは扱いません。別の原本保存機構は作りません。本番での文書登録手順は組織が承認し、一般職員だけで初回操作を完結できるUIの受入とは分けてください。
