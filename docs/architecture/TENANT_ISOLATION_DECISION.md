# tenant分離方式の設計判断

状態: 提案。実装済み・承認済みとして扱わない。
前提: 共通コードを使用し、本部間の職員・認証・業務データ・法令プロファイル・原本・監査・backupを厳格分離する。
監査: main 3452fb20では業務DBが単一SessionLocal、全業務テーブルはtenant境界なし。
既存導入先のDB/職員データはこの作業環境へ提供されていない。

## 比較

| 方式 | 分離境界 | 既存コードへの影響 | 運用上の代価 |
|---|---|---|---|
| A: 本部別DB・アプリプロセス・保存先 | DB資格情報、サービスアカウント、原本ACL、Host、cookie | 同じ共通コードを各本部へ起動。既存の全routerが専用DBへ接続 | 本部数ぶんのDB/サービス/backup/更新管理 |
| B: 共有DB + tenant列 + PostgreSQL RLS | 全テーブルのtenant列、複合FK、RLS、毎transactionのtenant context | 全モデル・migration・API・取込・検索・認証・監査・CLI・テストを変更 | DBは集約できるが全コード経路でtenant保証が必要 |

推奨: A。現在のコードを保ち、DB接続自体を分離境界にする。
1本部の複数拠点は同じ本部DBを共有する。拠点ごとにDBを分ける提案ではない。
共通コードのreleaseは1つで、tenant別DB/実行プロセスへ同じ版を適用する。
1つの承認済みサーバー上で複数本部を運用することも、別サーバーへ分離することも可能。
ただし各本部のCPU/メモリ・ストレージ/ネットワーク容量を実測してから本番容量を決める。

## Aの実装契約

1. 不変tenant_idを持つtenant単一行を各DBに登録。通常APIから変更不可。
2. 本番起動時に設定tenant_idとDB登録tenant_idを照合。不一致・未登録は起動拒否。
3. 原本storageにtenant identity markerを登録。別tenant markerなら起動/書込み拒否。
4. tenant設定は管理者のサーバー設定のみ。利用者のHTTP body/header/queryで接続先を選ばせない。
5. 本部別の専用DBアプリロールを使用。superuser/CREATEDB/他本部DB CONNECT不可。
6. 本部別サービスアカウント/環境ファイル/原本/backup ACL。
7. 本部別の固定HostとHTTPS。Host-only cookie、Secure、HttpOnly、SameSiteとHost許可リスト。
8. tenantごとのmigration/backup/recovery/drill evidenceを管理。共通release manifestへ列挙。
9. backup manifestにtenant_idを持たせ、復元先tenantと不一致ならDB更新前に拒否。
10. 全国法令の取得bundleは共有可だが、適用プロファイル・Rule承認・判定履歴は各本部DBへ分離保存。
11. 本部間の自動データ共有は実装しない。将来必要なら別の明示承認仕様で追加する。
12. 組織/職員/人事履歴はこのtenant DB内に実装。不変employee_idとlogin account分離は維持。

## Acceptance tests

- 同じログインID・別password/同じ対象物IDを2本部で作成して互いを読めない。
- AのcookieをBへ送っても認証不可。
- AのDB roleでBのDBへCONNECT不可。
- AのサービスアカウントからBの原本/backupを読めない。
- 設定/DB/storage markerのtenant不一致はAPI提供前に失敗する。
- A backupをBへ復元しようとするとDB/原本を変更せず失敗する。
- 既存のHuman Gate/RBAC/監査/原本hash/競合検出は回帰PASS。
- 1本部の複数クライアントは同じDBを参照し、更新競合を409で検出する。

## 判断が必要な理由

A/Bは単なるテーブル命名や画面配置と異なり、全migration、更新配布、backup単位、サーバーの運用コストと本部追加方法を固定する。
現行正式仕様はtenant厳格分離を求めるが、DB分割方式と共有DB方式を確定していない。
実運用データを移行した後の方式変更は大きいため、本部別DB方式で確定してよいか、人間の設計判断を必要とする。

この判断以外のboundedな復元修正・救急集計は独立して検証/PR/mergeする。
承認後も実LAN、Human法令承認、実図面/音声Referenceは別External Gate。
