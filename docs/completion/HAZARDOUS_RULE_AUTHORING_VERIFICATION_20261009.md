# 危険物Rule authoringと一次根拠の固定 — 検証境界

## 最終受入証拠（PR82・main）

PR82は `fc96af9dc6cd235487c5fe47ebf42d2b0553e887`、tree `d1c1fe35dfbd31d91006ab31db3a6980da93657b` としてmerge済み。exact head `e4a1c1ecbf57b7bfeaede259c4f99e315ff4db32` と同じtree。CI37871180915 SUCCESS: backend1330 passed/97 skipped/484.42s、browser job73 passed/706.14s、parser/JavaScript成功。056実PostgreSQLの旧DB更新・retry・同時Human承認200/409・audit1件・固定根拠UPDATE/DELETE拒否を実行済み。PR artifact11590374084 SHA256 `73810fcf5d437ea42b39786face6c64554c6b787a3d805b4013bd415421ac9c1`。

独立main CI37872231434もSUCCESS: backend1330 passed/97 skipped/498.40s、browser job73 passed/751.64s、parser/JavaScript成功。main artifact11591396065 SHA256 `d70f711b9706dab39de46447a807e748a6e106246070334738450a0fbc49fc86`。browser jobは既存Node/APIを含み、73本の別々のChromium journeyとは扱わない。skipもnative成功と数えない。以下のpending記述は過去の開発checkpointであり、この最終受入を取り消すものではない。章16/17はPartialで、専用installation評価workflow・実本番Rule承認は別の未完条件。

先行mainはPR81後のbe5185e53a5f126d6524bee1291d83a7e41fde92、tree3f56f3155343325c2d845fa5647ad23a66ad6618。独立main CI37868495428はbackend1245passed/97skipped、browser job73passed、parser/JavaScript成功。これは本Sliceのnative成功証拠ではない。

## 実装した契約

- 共通LegalRule/Version/Draft/Citationにhazardous_requirementを追加。既存4domainの条件/結論の意味を維持。
- 数量・容量は18桁整数/6桁小数までの正確な非負decimal文字列。単位の完全一致を要求し、変換・異種合算・法令分類推定をしない。純engineはmatched/not_matched/unresolvedを返すだけで業務DBを書かない。
- 条件は閉じたall/any・最大64句。登録済の名称/カテゴリーの完全一致・集合包含と、数量/容量の明示比較のみ。結論は必要事項の候補文とhuman_review_required=trueのみ。正式違反・許可・適合を自動確定する結論を拒否。
- Humanレビュー・Rule承認にはactive jurisdiction/official source、管理領域内原本・version hash・URL、一次条文引用を要求。自由文reference・参考引用だけで承認しない。canonical provision hashとserver-owned表示名/見出し/本文引用を確認。
- 作成/引用追加/草案編集/レビュー/昇格/承認は既存account/session exclusionを再利用。新domainの引用追加は版を更新し、旧版での承認409。Human承認後のRuleへ引用を追加できない。
- 一覧・版・引用・草案・coverage・関連source-provision本文は、selected sourceだけでなく引用先原本も現在の権限で照合。source-less草案に引用があっても迂回しない。権限不足403時に書込みを残さない。共通HTTP応答はno-store。
- shared auditは新domainのRule名/条件/必要事項/原文referenceを出さずhashを記録。保護されたimmutable hazardous_rule_approvalsに承認時Rule/source/citations/承認者/時刻を同一transactionで固定する。今後の専用評価は現在データとこの固定根拠を比較する。
- Migration056はappend-only domain拡張とapproval evidence table/immutable trigger。過去SQL・予約051は変更しない。空DBbootstrapへのmodel登録を追加。

## 実行した検証

APIのREDは非公式source・無効source・原本改変・引用差替え・source権限喪失・source-less引用・一覧/条文迂回・audit-only本文露出・参考引用のみの承認を再現。修復後のpure engine/validators/API/bootstrapと旧法令authoring回帰は94passed/1nativePGskip/108deselected（45.13s）。独立final authoring review20passed（23.67s）、Critical/Importantなし。追加のsource-less引用のみでの共有条文endpoint回帰も独立1passed（5.46s）。最新caseを含む既存危険物台帳/検索/原本境界との統合試験は126passed/41skipped（113.29s）。Skipはローカル未実施のnativePG等であり成功と数えない。54本SQLのparserとfrontend script syntax/diff check成功。

実PostgreSQL試験は055以前のDB・旧Ruleを維持して056だけを更新し、retry空、actual citation API、同時Human承認200/409・1audit・固定根拠1件・UPDATE/DELETE拒否を要求する。ローカルskipでnative成功と扱わない。exact-head CIとmerge後main CIを確認して追記する。

### 初回exact-head CIと既存照会テストの待機修復

PR82 head0f009bc6759fdf2b92c47a270f72a3ad65778a16、CI37870229132のbackend job113626373588は1329passed/97skipped（475.98s）、migration parser/JavaScript成功。実056 PostgreSQL更新・再実行・同時承認・不変triggerも実行された。Browser job113626373400は既存照会回答の根拠保存POST待機でtimeoutし、29passed/1failed（395.28s）。Actions起動や新危険物APIの失敗ではなく、全browser成功・merge条件は未達。

初期根拠previewと再検索の本文が同じため、本文の一致だけでは検索完了を証明しない。実JSの遅延検索回帰は、旧本文が一致していても保存がlockされ、処理中submitはPOSTを発行せず、応答後に有効化することを再現した。既存の処理中操作/Human Gateを弱めず、Chromium試験だけを正確な検索GETの応答・検索/保存controlの有効化待ちへ修復し、重複した同値source-type変更を避けた。Node状態試験6passed（1.21s）。修復後の新headで全CIを再実行し、前headのbackend結果を新head全Greenと混同しない。

## 内部未完とHuman Gate

本Sliceはauthoringとpure engineの基盤であり、installation評価candidate保存/選択profileとjurisdiction/effective Rule適用/固定承認根拠のdrift照合/独立Human評価確認/UI・Chromium連携は次の内部Slice。章16/17、10本Cross-module E2E、実図面Benchmark、Release完成を宣言しない。

正式な日本の法令・条例内容、閾値、対応コード、実運用原本と適用範囲は責任者による一次資料確認とHuman承認が必要。synthetic fixtureはmechanicsだけを証明し、本番の正式Ruleをseedしない。既存の本部別DB/実行環境/原本/backup分離を維持する。
