# PR #142 続行記録（2026-11-22）

実装commit: `0bfaa3234df7347dfc15cb5ab5538e886409eff0`。
開始PR headは `6d80334aae7b85619c4fabcbc64befdb93010353`、mainは
`034cd44978705f0272e466e0f63d879d2fc2fe06`。
作業はクラウドの専用worktreeで行い、元checkoutと既存サービスを停止・上書きしなかった。

## 実装した範囲

[独立教師記録・family・固定dataset登録](TRAINING_REGISTRY.md)とmigration061を追加。
転記/訂正先の分離、登録当時の職員による独立性、現在の権限、主/副根拠原本の検証、
dataset間の分割固定、改訂と複製の漏えい防止、未読・未確定・重複の隔離を扱う。
根拠proofの重複を避け、検証cacheは1要求内だけにする。
実トレーナーやworkerへの教師配信、モデル/重み/配備の管理は追加していない。

## 開発検証

すべてクラウドでの合成データによる実装試験。実帳票、ZBook、実モデル精度の証拠ではない。

| 実行 | 確認した結果 |
| --- | --- |
| 既存API/PDF/傾向集計の開始時baseline | 67 passed |
| 新registry APIと使い捨てPostgreSQL | 23 passed、22 warnings。skipなし |
| バックエンド標準全体の初回実行 | **2498 passed / 2 failed / 108 skipped / 67 subtests passed**、434 warnings |
| 移行fixture修正後の救急API/PDF/設定/registry等 | **124 passed**、72 warnings。失敗した監査PostgreSQL試験を含む |
| 新規の専用試験DBで本部分離テストを再確認 | **18 passed**、1 warning。失敗した初期化試験を含む |
| migration parser | 59 SQLファイルを解析 |
| 秘密情報検査 | fetched refs + working tree、検出0 |
| 実装commitのソース配布生成/verify | 成功。新registryとmigrationの同梱内容が作業ファイルと一致 |

標準実行の失敗を隠して全件成功とは記録しない。原因と再確認は次のとおり。

1. `test_emergency_audit_postgres.py::test_audit_native_upgrade_private_approval_workers_and_competing_writes`:
   059→060に固定したDBへ、061を使う最新APIを実行して `UndefinedTable`。
   059→060のassertionは維持し、その確認後に現行の追記migrationを適用するようfixtureを修正。
   上の124件の再実行で成功。
2. `test_tenant_boundary.py::test_complete_postgresql_migration_initialization`:
   既に初期化済みの試験DBを使い、「039が今回初めて適用される」という前提に不一致。
   実装やassertionは変更せず、新規の使い捨てDBで本部分離18件を再実行して成功。
   既存DBを空に戻して通す操作はしなかった。

これらの再確認後、標準全体を再び一括で実行した結果は未取得。
途中の1回はmanifest修正のため中断しており、成功回として数えない。
警告には既存のSQLAlchemy循環FKとStarletteの非推奨警告を含む。

独立コードレビューの分割固定・失権・原本登録時の職員・旧改訂の衝突・根拠保管・
複数位置・歴史的様式・隔離・manifest容量の指摘を再現し、修正後に確認した。
公開側には診断の生出力、原本、教師テキスト、重み、鍵、詳細評価ログを保存していない。

## 実機・実測の未完了

利用者はクラウドからZBookへの既存接続が**ない**と回答した。
クラウドの読取専用診断は終了したが、ZBookの診断へ読み替えない。

| 必須工程 | 状態 |
| --- | --- |
| ZBook本体・既存Linuxゲストの読取専用診断 | 未実施。本人の実行結果が必要 |
| 現行正式様式・入力要領・欄対応・基準精度 | 未確認 |
| 訂正確認用PDFの正式帳票・実機操作 | 未実施 |
| 過去帳票の独立した教師データ | 未作成・未確認。登録APIの開発とは別 |
| 実optimizer step・重み差分・保存・別プロセス再ロード・独立評価 | 未実装部分あり、未実行 |
| 5指標の実測 | 未開始・数値なし。0や合成値で補完しない |
| 本番昇格・配備・復旧・受入 | 未完了 |

正式帳票の検証開始時に、既存の比較群・作業区間・提出・追跡記録を並行開始する。
再学習の終了まで測定を待たない。数値目標、最低件数、追跡日数などの未確定も保持する。

次はZBookで既存 `scripts/check_emergency_workstation.py` を標準Pythonで実行する。
単独スクリプトのフォルダーなら `py -3 .\check_emergency_workstation.py`。
Pythonが見つからなければエラーを記録し、診断のためにVM/サービスやパッケージを変更しない。
原本・鍵を診断結果と一緒に送らず、診断に予期しない識別情報がないことを確認する。

## GitHubと統合

GitによるPR headとブランチの一致、公開PR画面でDraft状態を確認した。
GitHub APIのREST/GraphQLはForbidden、Checks画面はcommit listの読込失敗。
従ってこの変更の最新CI結果は未確認で、旧headのCI成功を流用しない。
mainへの統合、環境公開、本部導入は行わない。
