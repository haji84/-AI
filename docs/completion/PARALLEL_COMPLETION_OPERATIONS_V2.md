# 8レーン完成開発契約（2026-10-10）

要求正本はMaster Specification v2.0の追加§55.1。mainだけを実装正本とする。PR90の未merge4レーン案は履歴として保持し、このv2がmergeされた後の実行契約を優先する。独自ファクトリーの新機能開発は凍結し既存機能だけ再利用する。

## 所有範囲と依存関係

| Lane | 担当 | 所有する専用領域 | 先行依存 |
|---|---|---|---|
| 1 | 認証・権限・本部分離 | authz/personnel/tenant専用serviceとtests | 固定tenant/人事 |
| 2 | セキュリティ・監査・暗号化 | security/audit専用service/tests、秘密情報検査 | Lane1境界 |
| 3 | 予防・査察・違反・危険物 | 各専用router/service/schema/tests | 原本/法令契約 |
| 4 | 救急・警防・火災調査・報告 | emergency/operations/fire専用service/tests | 人事・原本・監査 |
| 5 | 人事・勤務・休暇・時間外 | workforce専用service/UI/tests | Lane1人事、Lane4出動 |
| 6 | 予算・契約・資産・車両 | finance/assets/fleet専用service/UI/tests | 原本/ExactMoney |
| 7 | 文書・届出・法令・AI・図面 | intake/legal/drawing専用adapter/tests | 原本・ネットワークpolicy |
| 8 | UX・導入・更新・復旧 | deployment/release/backup専用script/tests | Lane2鍵、全module契約 |

これは候補領域で、永久占有ではない。各IssueにSourceMainSHA/tree、OwnedPaths、TouchedSharedPaths、MigrationRequest、完成条件、他PR依存を固定する。共有main.py、共通auth/session、RBAC/module seed、frontend/index.html、migration、正式仕様、台帳、CIは統合担当が直列所有する。専用レーンから共有変更を依頼し、所有者未定の同一file変更を開始しない。初回Issue91だけrouters/auth.pyをLane2へ一時割当しLane1変更を待機する。

## 実行と統合

初回実装のexact-head CI→merge→独立main CI成功を確認してから段階拡大する。最大7同時agentという本セッション上限では統合担当1+worker最大6とし、8論理レーンを順番に起動する。待機レーンを稼働済みと報告しない。Issue/PRは自動workerではなく証拠と管理の経路である。

状態: READY→CLAIMED→IMPLEMENTED→TESTED→REVIEWED→PR→CI_GREEN→MERGED→MAIN_GREEN→LEDGER_UPDATED。BLOCKEDは失敗証拠/次手を保存。1PR=小さい残差で、全体完成は57章/10受入chain/Release/External Gateで別判定する。

同じ原因の修復は最大2回。失敗継続時は権限/仕様/CIを弱めずcheckpointを保存する。GitHub保護ルールとレビュー条件を取得し、すべてのexact-head必須CI成功・重大指摘閉鎖・最新main競合確認の後だけmergeする。未保護mainでも直pushしない。merge後mainCI成功前に受入完了扱いしない。

## 初期残差と開始状態

監査実行済: Lane1/2、Lane3〜6、Lane7/8を3agentで読取監査。実装開始はIssue91のみ。他レーンは初回mainCI待機。

- Lane2: 認証失敗監査（Issue91）。MFA/試行制限/暗号化/検知/秘密検査は未完。
- Lane5: available-crewの個人/原本権限境界修復を実REDで確認してからUI接続。勤務実績→出動→時間外/手当chainは未完。
- Lane7: sync_source直接実行のdisabled/bundle/manual preflightを修復し閉域更新を保持。
- Lane8: HA/Vault内部設計・実装、暗号化/鍵分離、offline依存同梱、同一Release更新/復元rehearsalが未完。
- Lane3/4/6: 完成台帳の具体的残差を対象module正本へ再照合してからIssueをclaimする。既存実装を追加名目で再作成しない。

通常の実装/試験/PRは自律実行。正式法令/本番移行・適用/重要権限/鍵・緊急復旧のHuman Gateを保持する。
