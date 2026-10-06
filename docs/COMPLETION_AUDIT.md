# 実運用完成監査

監査基準: 2026-10-06、main base `0feb62e6ab78dcb77bceedb4154ab5aa4d8bc8da`。
正本: GitHub haji84/-AI main。過去の会話・Phase番号・PROJECT_STATEだけで完成判定しない。

## 判定方法

Completedは下記に限定した実装要素の完了であり、システム全体の完成を意味しない。
Partialはコードがあるが仕様・実運用証拠が不足。Missingは対応コードを確認できない。
External Gateは承認済み実環境・Humanによる正式判定・提供されていない評価原本などが必要な項目。
直近確認: PR52学習merge、PR51の全57章matrix、PR50/48仕様更新とPR47/46/45 merged。main project-checks run37490791793 SUCCESS（fbc7227f）。開PRは次Slice/merge前に再取得する。

## Completed / Partial / Missing / External Gate

| 対象 | 判定 | コード・テスト証拠 | 残作業 |
|---|---|---|---|
| 対象物基本CRUD・廃止/復元・競合検出 | Completed（この実装範囲） | routers/facilities.py、test_phase1_core.py | 実LAN・利用者受入は別Gate |
| 査察・指摘事項・届出受付 | Partial | routers/inspections.py、submissions.py、intake.py | 正式仕様の全審査フロー・運用受入照合 |
| 原本/派生物分離・文書内容解析 | Partial | document_intake.py、storage.py、routers/documents.py | HEIC・画像補正・ページ束ね/欠落検知の仕様差分 |
| 法令原文・Version・条文引用・ルール候補/承認 | Completed（基盤） | legal_structure*.py、routers/legal*.py、migrations 008-015 | 内容の網羅性は別Gate |
| 法令・条例正式ルール網羅性 | External Gate | 条文worklistとHuman review APIは存在 | Humanが条件/結果/引用をレビューして承認。AIが代行不可 |
| 署名付き閉域更新bundle | Completed（基盤・PR45） | Ed25519外部trust、原本hash、origin、XML/ZIP事前検証、古いbundle拒否、folder候補取込。main CI37480963172 SUCCESS | 本番の信頼鍵選定・法令正式承認はHuman External Gate |
| Human Reference編集/QA/改訂・Baseline実行・承認 | Completed（基盤） | drawing_annotations.py、drawing_baseline_*、benchmark core、図面テスト | 実図面・モデル精度は別Gate |
| 項判定・必要設備・配置候補・相談回答Human Gate | Partial | drawing_consultations.py、occupancy_*、equipment_placement_* | 正式ルール集合・モデル実測・実業務受入 |
| 実図面Benchmark結果 | External Gate | reference/house-plan-001.reference.json はDraft。Baseline機能あり | Human正解確認、実Vision Hypothesis、初回測定、受入閾値 |
| 火災調査・写真・音声・報告 | Partial | fire_investigations.py、fire_photos.py、fire_report_exports.py | Local AI実処理・正式様式・実評価の受入証拠 |
| 実日本語音声/証拠比較精度 | External Gate | audio/evidence benchmark API/CLI | 提供原音声/正解・Human有用性判断 |
| 横断検索 | Partial | routers/search.py、unified_search.py | 意味検索品質・本番負荷・権限受入 |
| 救急取込・正規化 | Completed（取込範囲） | importers/emergency.py、models Emergency*、Migration 002 | Web提供は別項目 |
| 救急Web集計・帳票・チェック・候補レビュー | Partial（今回の集計Slice後） | emergency_reports core/router/UI、新規8テスト。臨床flagテーブルあり | 名称マスタ・隊員/時系列/正式帳票、Web取込、チェック、Human候補確認 |
| 契約管理 | Partial | routers/contracts.py、Contract* | 一覧UI・書類/見積/履行/検査/請求/変更契約の全フロー |
| Module/Feature Flag/Change Request | Partial | routers/extensions.py、Module* | Sandbox実行・Deployment実反映/rollback証拠 |
| 学習・Champion/Candidate昇格・rollback | Partial（PR52基盤完了） | 正式v2.0 §37。修正/固定原本/比較/辞書Candidate/明示Human昇格/rollbackをPG/browser CI確認 | worker/model adapter接続は内部残差、実モデル/実データ品質は別Gate |
| tenant分離 | Completed（コード基盤・PR41/43） | 承認済み本部別DB方式、UUID照合、生成専用roles/paths、PG別DB接続・更新拒否、backup/restore境界CI | 実OS ACL・実機復元・LAN受入はExternal Gate |
| 職員とアカウント分離 | Completed（データモデル） | EmployeeとUser.employee_id | 管理操作は別項目 |
| 組織マスタ・人事履歴・異動追随 | Completed（基盤・PR44） | OrganizationUnit/EmployeeAssignment、Migration041、有効日権限、管理ブラウザCI | 実辞令/所属・LAN受入は別Gate |
| 認証・RBAC | Partial（v2.0再監査） | PR44有効日所属/管理UI/password履歴/変更/reset/login排他/session失効/最後の管理者保護 | PR54 password expiryはmerge/main CI37494620742 SUCCESS。PR56 customRole/RoleRule/期限付き・代理管理はmerge、PG447/browser5成功。資格/担当selector・辞令Document候補は内部Partial。実運用権限受入はExternal Gate |
| 監査ログ | Completed（基盤） | audit.py、AuditLog、管理閲覧API/UI、PostgreSQLの更新/削除拒否CI | 実サーバーOS/運用受入は別Gate |
| migration | Completed（001-043/045/047・基盤） | PostgreSQL全実行/再実行/制約/排他CI、schema照合 | 本番clone移行・実機受入は別Gate |
| backup/restore | Completed（コード基盤・PR43/47） | UUID/hash/release/所有者/PG復元、本部timer停止/復帰、SIGTERM、保守排他・拒否再利用防止。PR47 PG367/browser2成功、main Green | 実systemd/監視/実機復元受入はExternal Gate |
| 本番LAN・TLS・複数PC競合 | External Gate | deploy/nginx、systemd、LAN_DEPLOYMENT.md | 承認サーバー/名前/証明書/経路と実機検証 |
| 完成成果物・release一式 | Missing | READMEとPhase手順あり | 全マニュアル、構成/DB/権限/制約/検証/完成判定を束ねる |

## 最優先の実装順序

1. 復元時の非対象storage巻込みと検証前DB更新を防止する。
2. tenant分離、職員/組織/人事履歴・認証管理・監査閲覧の共通基盤。
3. PostgreSQL migration/backup/restoreの自動回帰と本番構成。
4. 救急Web集計/出力/チェック/Human候補レビューと契約の不足。
5. 署名更新、学習/昇格/rollback、主要モジュール残差。
6. 全仕様再照合、実図面/音声/法令/実LANのExternal Gate、導入成果物。

External Gateが未実施でも独立したMissing/Partialを続行する。
各PRはこの完成タスクのSliceであり、完成宣言は行わない。

## 復元不具合の再現Evidence

backend/tests/test_restore_safety.py を修正前のmainコードで実行: 7 failed。
- targetの隣のstorageがrenameされ、無関係なファイルが復元先へ混入した。
- 不正tarを拒否する前にtarget DBが上書きされていた。
- manifestの../参照を許容していた。
- backup自身をstorage targetにするとbackupを削除してから読み込みに失敗した。
- target storage配下のSQLite DBを消して成功報告していた。

修正後: 7 passed。元mainの復元を本番へ使用する前にこの修正が必要。

## 後続Slice: 救急Web集計

事案/救護者を分離した病院・程度・地域集計、Excel/CSV、専用権限、集計監査を追加。
`docs/emergency/WEB_REPORTS.md` に操作/集計定義/制約を記録。個票/候補の正式確定は行わない。

## 次の重大設計判断

tenant分離は現行コードに存在しない。
`docs/architecture/TENANT_ISOLATION_DECISION.md` で本部別DB方式と共有DB/RLS方式を比較。
推奨は共通コード + 本部別DB/サービス/原本/backup。複数拠点は本部内で同じDBを共有。
この判断は本部追加方式、migration、backup単位、運用コストを固定するため確認対象。
実装済みと報告しない。

## 2026-10-06 Run A 再監査差分

基準main: 240703a9（PR40を含む）。開PRなし、main CI37448233992 SUCCESS。migration038までを照合済み。
本部分離の設計判断は利用者承認済み。署所ごとのDB分割は行わない。
最新共通基盤Evidenceは `completion/RUN_A_STATUS.md`、未完業務モジュールの担当・Evidenceは `completion/RUN_B_STATUS.md`。
分類は上表の範囲を維持し、本Sliceのtenant境界実装だけでtenant全体や本番導入をCompletedにしない。

## Run A 職員管理Slice（未merge）

main89e87e17 / PR42を照合し、RunB機能を維持。組織・主所属/兼務・異動履歴・有効日権限・アカウント管理・パスワード履歴/変更・監査閲覧を実装中。専用9件、統合291件成功、5skip。PostgreSQL・画面操作・PR CI確認前のためCompletedとはしない。仕様のパスワード期限、実LAN受入、最終成果物は引き続きPartial/External Gateとして残す。詳細はcompletion/PERSONNEL_ADMINISTRATION.md。

## 署名付き法令更新Slice（main未反映）

main fb2c9900 / PR44の実装・CIを再監査。署名付き閉域更新Missingに対し、両collector/importerの外部trust・全原本hash・取得origin・XML事前検証・古いbundle拒否・候補限定・更新folder処理を追加中。25 focused tests成功。正式Ruleは作成しない。PR CI/merge後にmain実装として再分類する。詳細completion/SIGNED_LEGAL_UPDATES.md。

## 2026-10-06 main c4e692ed 再監査

PR45署名更新とPR46業務資産/在庫/貸出/保守を実コード・テスト・CIと照合。RunBの残る届出/契約/人員/予算等はRUN_B_REQUIREMENTS.mdとそのledgerで継続。学習基盤はSPEC17の専用実装を未確認でMissingのまま。図面worker・実model設定・比較出力と最終成果物はRunAで次に照合・実装する。Task5の自動backup/保守排他はレビュー修正と全体CI前なので未Completed。

Ruling: パスワード固定期限を以前の監査が未実装としたが、正式SPECに固定日数/期限要件を確認できない。Human管理の変更/reset・履歴・失効を実装済みとして扱い、任意日数の強制失効は発明しない。運用ポリシーによる将来設定は本番管理者判断。監査履歴のページ送り等、実用上必要な不足は別途内部Partialとして継続する。

## Master Specification v2.0 追補監査

PR48/50（main6bcf537）の正式仕様を採用。旧v1の説明/Phaseは履歴であり、新要求をCompletedと推定しない。学習は§37へ対応を実装中。§6のpassword expiryは内部Missing/Task7となり、旧仕様に固定期限がなかったという以前のRulingを適用しない。既存の基盤コード・Human Gate・別本部境界は維持し、危険物/違反改善、改正影響、個人work queue、AI worker/自己拡張等の新正式要求を実コード/テストで次に照合する。既存RunB担当業務を重複実装しない。

## PR56正本確認

main b2fc2612、main CI37500653453 SUCCESS、exact-headPR CI447/backend＋5/browser。HumanRole/RoleRule/期限付き・代理・本人向け根拠は基盤としてmerge済み。初期bootstrapのcontext500も修復済み。13Completed/33Partial/10Missing/1External Gateの57章分類は維持し、資格/担当selector・辞令Document候補と未実装業務を内部残差として扱う。共通Migration lexerのfinance trigger破断は内部不足として修復中。

## 勤務管理統合の再監査

main ea15820e / main CI37503229005 SUCCESS。既存PR53のCI失敗を修復して統合するSlice。共通人事/権限/tenantを維持し、独立レビュー13ImportantをTDD修復。章25はMissingからPartialへの基盤統合であり、team/work-result/checkout/cancel/balance/crew UI、期限/代休reconciliationは内部残差。Matrixは13Completed/34Partial/9Missing/1External Gate。CIとmergeを確認せず完成扱いしない。詳細WORKFORCE_INTEGRATION.md。

PR55/main0feb62e6、main CI37507500474 SUCCESSを再取得。財務048は正本化され、重複実装しない。§26/27の共通session/permission guardと共用PCの状態消去は内部Partialとして残す。13Completed/36Partial/7Missing/1External（勤務Slice反映後。main0febのみは13/35/8/1）へ再分類。勤務PR53は新mainの両業務統合・exact-headCI待ち。
