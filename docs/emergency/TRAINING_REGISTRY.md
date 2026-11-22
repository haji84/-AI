# 救急監査の独立正解・family・固定dataset

`MODEL_RETRAINING.md` §3–4の先行実装である。
**トレーナー、実重み更新、実帳票のモデル評価、実機受入は実装・実行したものではない。**
APIは `model_training_performed:false`、datasetは `training_ready:false` を返す。
既存の傾向集計や辞書を実学習と表示する経路は追加しない。

## 専用API

既存救急監査の認証、本部、実帳票利用スイッチ、失効再確認、同一Origin、入力上限、
`no-store` と固定エラーを使う。原本・教師を一般Document・検索・学習資料へ登録しない。

| API | 内容・権限 |
| --- | --- |
| `POST /emergency/audit/training/families` | family_idとreport_idsの登録・追加。`emergency.audit.configure` |
| `GET /emergency/audit/training/families/{id}` | 全所属報告書への現在の参照権限が必要 |
| `POST /emergency/audit/revisions/{id}/training-truth` | 原本から独立正解を登録。`emergency.report.review` |
| `GET /emergency/audit/training/truths/{id}` | 対象原本への現在の参照権限が必要 |
| `POST /emergency/audit/training/datasets` | 正解・前処理digest・family分割を固定。`emergency.audit.configure` |
| `GET /emergency/audit/training/datasets/{id}` | 対象報告書全部への現在の参照権限が必要 |

追加で既存の救急事案・傷病者・報告書の参照権限を要する。自動付与はしない。
書込は職員管理と同じ直列化guardを通す。API形式は `emergency_training_schemas.py` が正本。

## 原本からの独立正解

- `task=transcription/content_review` を区別する。原本に書かれた `observed_text` と
  訂正先 `allowed_corrections` は別で、訂正先を転記の正解へ代入しない。
- 欄、ページ、矩形、モデルに依存しない誤りID、読取状態、正誤、根拠を保持する。
  同じ本文欄の異なる位置に複数の誤りを記録でき、同じ位置の二重登録は拒否する。
- 様式の適用日は `form_as_of`、内容判定の基準日は `as_of`。当時の規則と現在の規則を
  混同しない。転記は `basis=as_written`、内容確認は規則版と基準を明示する。
- `source_verified` は実際に原本を確認した職員が指定する。登録者は原本所有者と
  登録担当者の両方と別アカウント・別職員でなければならない。
  最初の読取jobの**原本登録時の職員**を使い、アカウント異動による自己確認を拒否する。
  担当記録が不足する場合は保留する。dataset固定時も確認者の現在の権限と対象範囲を確認する。
- `whole_scope_checked` がない正しい記載は負例にしない。未確認、読取不能、非印字、
  未対応、正誤不明、対象外、未確定の訂正先は隔離し、未読だけのfamilyも件数に残す。
- 訂正は `supersedes_id` を指定した新版で保持する。訂正された旧正解で新datasetを作れない。

原本SHA、原本版、様式・規則の定義digest、主/副根拠原本のSHAを結び付ける。
正解登録とdataset固定時に原本を復号・検証し、変更・欠落を拒否する。
内部実帳票には既存の独立承認済み設定を必要とする。合成試験のdraftは正式承認ではない。

## familyと固定分割

familyは人が確認した同一事案のまとまりで、ファイル名や文章の類似から自動確定しない。
同じ報告書の全改訂は所属を継承する。既知の同一SHAを別familyへ入れず、所属済み報告書へ
他familyの原本を新改訂として追加することも拒否する。固定時は選んだ正解だけでなく、
所属報告書の全改訂で衝突を確認する。異なるSHAの再スキャン・切出しは人の確認が必要。

最初のdatasetでfamilyのTrain/Validation/Holdoutを不変行に固定する。
新版や `supersedes_id` を省略した別datasetでも移動できない。
同じ原本・位置・正解の複製は隔離して標本数を増やさず、食い違う正解は入力順で採用しない。
各分割に利用できる正解が必要だが、同じ分割内の未読familyは隔離として保持できる。
各1例あれば実精度を承認できるという基準ではない。

Holdoutの調整利用履歴、正式なfamily訂正・統合の運用は後続実装。
新しいIDで過去の評価データを未見に見せてよいという意味ではない。

## 保存・上限

追記migrationは `061_emergency_training_registry.sql`。所属・固定分割・正解・datasetの
4表を追加し、PostgreSQL側でもUPDATE/DELETEを拒否する。教師テキストとmanifestはAES-GCMで
暗号化し、storage/通常backup外の既存監査鍵を使う。鍵の生成・置換はしない。
監査ログには操作ID・件数だけを残す。

manifestの各sampleは原本・正解・位置・分割を参照する。様式/規則の根拠proofは
`configurations` に一度だけ保存し、sampleからID参照する。教師の文字自体は複製しない。
検証cacheは1回の固定処理内だけで、次の要求では原本を改めて検証する。

正解100件、各200位置、family所属100報告書、dataset全体100報告書、固有原本100MiBを上限とする。
既存のJSON要求上限・vault上限も維持する。容量・学習性能の実測保証ではない。
モデル・checkpointはこの経路へ保存しない。

## 残件

ZBookの診断、正式様式・入力要領・基準評価、承認された教師データが必要。
さらにモデル/tokenizer/基準artifact、Trainだけを渡すworker、Holdoutアクセス分離・調整履歴、
学習job/lease、実optimizer stepとtensor差分、保存・別プロセス再ロード、分割モデル保管、
停止・失権・OOM・容量不足・復旧、固定評価、実配備形式での比較、独立承認・昇格・rollback、
5指標実測と本番受入が残る。前処理digestは登録識別子で、実体を審査・実行した証明ではない。
このAPIはworkerへ教師やHoldoutを渡すAPIでも、学習実行の許可でもない。
