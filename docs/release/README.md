# 検証用リリース候補の受け渡し

このパッケージは固定した Git commit のソース配布物です。インストーラー、依存ライブラリ同梱版、本番導入済みシステムではありません。AIOS 全体の完成判定は `docs/SPECIFICATION.md` 第52–54章に従い、未実装機能や未検証項目を残したまま完成扱いにしません。

## 内容

- 共通アプリ、Web画面、append-only migration、設定生成器、テスト、運用文書
- `RELEASE_MANIFEST.json`: 固定 commit/tree、各ファイルの SHA-256・サイズ・mode、release-candidate 表示
- 本ディレクトリの導入手順と受入チェック

ローカルの `.env`、DB、原本、バックアップ、認証情報、未追跡ファイル、作業中の未commit変更は配布対象ではありません。追跡済みでも許可外パスやリンクを検出したら生成を停止します。Gitへ実運用情報を入れない原則は引き続き必要です。ハッシュ検証は破損検知であり、発行者の電子署名や内容の機密判定を代替しません。

## 生成

Git checkout のルートで Python 3.11 以上を使用します。生成器自体には追加パッケージ不要です。

```bash
python scripts/build_release_bundle.py build \
  --ref HEAD \
  --release-id fire-ai-20261006-rc1 \
  --output /tmp/fire-ai-20261006-rc1.tar.gz
python scripts/build_release_bundle.py verify /tmp/fire-ai-20261006-rc1.tar.gz
```

公開時には `HEAD` の代わりに検証済みの完全な commit SHA を指定してください。生成前にその SHA の backend/PostgreSQL と Chromium CI が成功したことを確認し、CI URLを受入記録へ残します。ソースが固定されるため、未commitの修正はパッケージへ入りません。同名出力は上書きしません。

同じ commit・release ID・生成器・Python/zlib実行環境からの出力は同じバイト列になります。出力物を配布する前に verify を実行し、別途記録した SHA-256 と比較してください。verify は展開せずに検証します。

## 受け取り後

1. 承認された配布元と commit、外部に記録したパッケージハッシュを照合する。
2. 別途信頼できるcheckoutから取得した検証器でverifyを行う。受け取った未検証archive内のコードを先に実行しない。検証成功後、新しい空のディレクトリへ展開し、既存本番の上へ展開しない。
3. `INSTALLATION.md` の「ローカル合成データ確認」か「本部別PostgreSQL導入」を選ぶ。
4. `RELEASE_READINESS.md` の内部・外部Gateを記録する。

tar.gz だけではオフライン導入できません。Python、PostgreSQL、対応OS、必要なPython wheel、OCR/Local AIの外部実行環境等は別途準備・承認が必要です。現時点で全5 Deployment Profileの導入完了を保証するものではありません。
