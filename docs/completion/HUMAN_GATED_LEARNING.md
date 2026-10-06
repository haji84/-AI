# 修正・固定評価・Human昇格

正式仕様v2.0 §37の対象8種を本部DB内で管理する。共通Employee/User/RBAC、tenant binding、監査、原本Documentを再利用する。追加アプリを端末へ導入せず、`/ui/learning.html`をブラウザで利用する。

## 利用の流れ

1. 改善対象を選び、元のAI文字列/ラベルと職員の修正を原本に紐付けて記録する。この時点はpendingであり、学習に使わない。
2. 権限を持つHumanが原本・元出力・修正後を確認し、理由を付けてapprove/rejectする。確認済み記録は上書きしない。訂正は新しい記録として追加する。
3. 確認済み修正を選び、Candidateを作成する。初期エンジンは文字列のliteral補正またはラベルのexact対応であり、ニューラルモデルを学習したという意味ではない。同じ入力への矛盾する修正は拒否する。文字列補正は一度の置換で、順次再置換しない。
4. 別の原本を使う固定評価セットを作る。入力とHuman正解を全件確認し、セットを承認する。入力・正解・原本hashは固定される。改訂は新しいセットとして保存する。学習原本と評価原本のIDおよびSHA-256の重複を拒否する。同じバイト列を別IDで再登録しても評価用にできない。
5. Candidateを承認済みセットで評価する。現在のChampionとCandidateの全文/ラベル一致数・率をサーバーが算定する。リクエストからscoreを指定できない。画像IoUやCER/WERの実モデル評価と混同しない。
6. ケース別に退行がなく、一致数が改善した比較のみ昇格候補になる。Humanが証拠と理由を確認し、明示的に承認する。比較後にChampionが変わった場合は409となり再評価が必要。
7. 提案を確認する。元出力と提案、Champion版、artifact hashを分離する。学習機能は原本・正式データ・法令・権限を更新しない。業務側で提案を採用する場合も既存Human Gateを通す。
8. 問題があれば現在の履歴先端をHuman操作でrollbackする。直前Champion（初回なら補正なし）へ戻す。履歴・旧artifact・比較結果は残す。再度のrollbackは現在の先端を対象にする。

## 権限と安全性

learning.read/record/review/evaluate/promoteを分離する。初期付与はsystem_adminだけ。他ロールへはHumanアカウント管理で付与する。さらに原本参照と改善対象のintake.readまたはfire_investigation.readを必要とする。learning権限だけでは修正文字列・固定正解・artifactへアクセスできない。

Human変更はアカウント管理のPostgreSQL排他を共有し、ロック取得後に有効権限と職員状態を再確認する。同時昇格はChampion版と排他で1件だけ成功する。評価・artifact・transitionはAPIに編集/削除操作を持たず、本番app DB roleもUPDATE/DELETEを持たない。修正と固定セットのUPDATEはレビュー用columnだけに限定する。公式PG16権限仕様: https://www.postgresql.org/docs/16/sql-grant.html

未確認修正、未確認正解、入力hash不一致、原本hash変更、旧Champion比較、改善なし/退行、古いexpected_versionは昇格できない。合成例は非productionの管理者だけが使える。本番へ合成のCandidate/評価/Championを持ち込んでも処理を拒否する。合成画面テストを実データ精度と表現しない。

Module Registryのlearning Feature Flagが無効なら学習処理は503。productionではflag未設定も拒否する。他の業務CRUDは停止しない。ログアウト・認証失効時は画面の証拠・入力・提案を消去し、前アカウント/前対象の遅延応答を破棄する。bootstrap/更新時に既存seed_modules/RBAC手順で登録する。

## DB・移行

learning_corrections、learning_evaluation_sets、learning_artifacts、learning_evaluations、learning_champions、learning_transitionsを追加する。原本は既存documentsを参照し、別のファイルDBを作らない。artifactはimmutable JSON、training evidence、SHA、作成者を保持する。比較は固定セット、モデルhash、Champion版、result SHAを保持し、昇格時に再計算する。

Migration番号はPR直前のcanonical mainと再照合する。全本部で同じmigration codeを使い、各本部owner接続で順番に適用し、最新の生成grantsを再適用してRBAC/moduleをseedする。原本・学習DB・評価履歴は本部のpaired backup対象に含まれる。

## 制約と今後の接続

初期エンジンは説明可能な修正辞書。神経モデルの重み更新・自動本番自己改変を行わない。全8対象へ記録/比較/提案を提供するが、汎化能力や実OCR/STT/画像精度を保証しない。実モデルadapterはこのimmutable artifact/Champion/evaluation契約と既存AI Manifestを接続する。実モデルの配置、実原本とHuman正解・実精度受入は別のExternal Gate。独立したworker/運用不足は内部backlogとして残し、外部Gateへ隠さない。

Humanが入力した文字列は原本の内容だとAIだけで証明しない。原本hashとレビュー担当者/理由で追跡する。正式法令や臨床/原因判定への直接反映は禁止したまま。認証なしの外部AIや任意code実行・任意URLモデル取得は提供しない。

## 検証

Synthetic HTTP workflowでpending→review→Candidate→fixed review→server比較→CAS昇格→提案→rollbackを確認する。原本根拠なし/学習評価重複/権限不足/production合成拒否/無効Moduleを確認する。同じworkflowを実PostgreSQL CIで実行し、同時2昇格は200/409と単一履歴になることを確認する。専用Chromium jobはブラウザ操作とscreenshotを保存する。実LAN/実原本の成功は推定しない。

## 共通管理の追加

監査UIはaudit_id keysetで以前の履歴を追加表示し、操作名で絞り込める。新規サーバーbootstrapはHumanアカウントと同じ12..128文字制限、初期password history、秘密を含まないaccount.bootstrap監査を同一transactionに保存する。再実行で既存アカウントや監査を増やさない。
