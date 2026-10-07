# 完成タスクの実行順 — 2026-10-08

## 正本と開始条件

GitHub `haji84/-AI` の main が唯一の正本。今回の開始点は PR78 の
`314100b728874890046ea162aff2fbd2513c4407`、tree
`d22724715b4178e3ba19b31ee3d127c0882b9d69`。
ローカル復元時に全494 tracked blobとtreeを照合した。旧作業フォルダの
未commit変更は保護し、既に統合された機能を復旧名目で再実装しない。

開始時の分類は Completed 12 / Partial 44 / Missing 0 / External Gate 1。
この数は完成率ではない。現在の章別根拠は CURRENT_COMPLETION_LEDGER と
COMPLETION_BASELINE_20261007、および正本コード・テストを突き合わせる。
PR78後の CI37613692346 は backend成功 / browser失敗だった。
先に車両一覧から詳細を開く非同期競合を修復し、正確なheadのCIとmerge後mainを
Greenにする。前の9d6f86bでの成功を最新mainの実行結果へ転記しない。

## Partialの優先度と依存順

各群を小さいPRに分割するが、全て同じ完成タスクの一部として扱う。
各章は既存実装の残差のみを埋める。全残差の実コード・テスト・CI・差分・merge
が揃った時だけCompletedへ変更し、別章の未完を移し替えて完了扱いにしない。

| 優先 | 対象章 | 埋める残差と後続への契約 |
|---|---|---|
| P0 | 5, 6, 7, 9, 43 | 訂正provenance、職員/資格/担当と有効日権限、原本・派生物の権限閉包、失効/競合。全後続の安全な共通基盤 |
| P1 | 10, 12, 13, 14, 15, 16, 17, 18, 20 | 再開可能な取込/審査、種別workflow、期限、一次資料Ruleと候補producer、危険物評価。AIと正式確認を分離 |
| P1 | 21, 25, 26, 27 | 救急正式workflow、勤務→出動→活動結果→時間/手当、契約補助、予算の残る年度シナリオ。既存台帳/ExactMoneyを再利用 |
| P1 | 28, 33, 34, 35, 36 | 原本様式、元DB統計/年度/比較/母数/網羅性、照会根拠、権限内検索、担当別作業queue。unknownを0と誤認しない |
| P2 | 19, 29, 30, 31, 32, 37, 38, 39 | 実行可能なlocal-model/worker adapter、写真/音声/図面/報告候補、学習評価、bounded runner、機械的AI level制御。Human昇格前に正式データへ反映しない |
| P2 | 3, 4, 41, 44, 45, 46, 50, 51 | 各profileの更新/rollback、typed import、ネットワーク、共通UX、本部別設定と履歴、移行rehearsal/監視。共通コード＋本部別DB/runtime/原本/backupを維持 |
| P3 | 48, 54 | 正式仕様§54の10本を、実装された全chainとして実行。断片テストやNodeを実ブラウザ証拠へ読み替えない |
| P4 | 1, 52, 53 | Release、手順/マニュアル/構成/DB/RBAC/security/結果/制約/判定レポートと展開起動を照合。成果物生成なしに完成としない |

上表の章は重複なく44章を含む。Completedの12章にも、新しい経路が既存の
tenant・監査・backup・Human Gateを弱めない回帰検証を行う。

## 10本の受入chain

1. Facility → Drawing → Human Annotation → Occupancy → Equipment requirement → Human Review → Equipment registry
2. Document → Intake → Human classification → Submission → Facility update → Search
3. Incident → Dispatch → Crew → Vehicle → Activity → Allowance → Statistics
4. Emergency → Patient → Treatment → Transport → Clinical candidate → Human Review → Monthly report
5. Fire Investigation → Photo/Audio → Transcript/Statement → Evidence → Cause candidate → Human Gate → Report Template
6. Workforce → Roster → Dispatch → Work result → Overtime/allowance
7. Fleet → Dispatch → Mileage → Fuel → Log
8. Contract → Commitment → Budget → Payment → Balance
9. Asset → Receive → Location → Loan/Issue → Return/Transfer → Inspection/Expiry → History
10. Inquiry → Evidence → Numeric source → Draft → Human Review → Official output

各chainについて通常成功・元版変更・権限失効・競合・AI停止・必要なHuman拒否を
証拠に結び付ける。実datasetなしの合成chain成功は実AI精度の合格ではない。

## ReleaseからExternal Gateへの引継ぎ

初期導入一式はcommit/tree・SHA・migration一覧・依存版・実行結果を固定する。
全ての要求成果物と安全な展開/起動確認をmanifestへ載せる。
リリース名や文書更新だけで本番受入済みにしない。

最後に、承認済みhost/LAN/TLS・複数PC・物理復元、実図面/音声のHuman正解と
実モデルBenchmark、正式な一次資料Rule/様式/本部policyのHuman承認を行う。
内部adapter/画面/試験が未実装ならExternalへ分類しない。
module無効時の履歴参照方針、Owner Recovery Vaultの登録/鍵/緊急復元権限等は
未決の設計判断として保持し、既存本部の原本・データへ新しいアクセス権限を
勝手に与えない。重大な判断が必要な箇所だけ、具体的な選択と影響をHumanへ示す。

## Slice終了時の必須証拠

- main最新、開PR/直近merge、rules、migration、対象コード/テストと未完Gateを再確認
- 回帰のRED → 最小実装 → GREEN、全体試験、差分と独立review
- exact-head PR CI、merge、post-merge main Green
- 完了した残差/残る残差と次の依存、成果物・テスト参照を更新

この文書は実行順の固定であり、44章の完成、10本の実行済み、Release完成を
主張するものではない。途中のPRや章数の変化はタスクの終了条件ではない。
