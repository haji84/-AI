# Work非依存・ローカルAI開発候補ワーカー（限定試験）

目的は **既存のAider + Ollamaを利用して、1ファイル限定の変更候補を隔離worktreeへ作る** ことです。開発ファクトリーを作り直しません。

## 安全境界

- 正本は最新 `main`。作業は必ずクリーンなGit checkoutから開始します。
- `docs/autonomy/tasks/` にある**Git管理済み契約**だけを扱います。基準commitがHEADの祖先であり、対象ソースのSHA-256が一致することを要求します。
- 対象は既存 `backend/app/` または `frontend/` の単一ファイルで、Python/JS/CSS/HTMLのみ。
- 認証、tenant、権限、監査、migration、機密等のパスは拒否します。
- Ollamaは `127.0.0.1` のみに接続。利用者のAPIキー・GitHubトークンをAIワーカーへ渡しません。
- GitHubへのpush、PR作成、CI、main mergeは**一切行いません**。生成したプログラムやテストの自動実行もしません。
- 生成内容が1ファイルの変更だけと確認できた場合も、結果は `candidate_unverified` です。レビュー・秘密検査・隔離テスト・PR/CIを別経路で行うまで完成と見なしません。

**注意：Windows/ZBook等の個人用PCでAiderを動かす場合、実行プロセス自体はOSへのアクセス権があります。隔離用PC・非特権アカウント・無機密データで検証し、公開GitHubのself-hosted Actions Runnerに常駐接続しないでください。** これは強固なOSサンドボックスではありません。

## 初期導入

1. ZBookにOllamaとAiderをインストールし、モデルをローカルに取得します。
2. GitHubの最新mainをクリーンにcloneします。
3. 人間が実在する仕様の具体的な受入条件、対象ファイル、基準commit、ソースSHA-256を確認したうえで、契約JSONをGit管理下の `docs/autonomy/tasks/` に追加します。
4. 契約の基準commitを変更せず、契約ファイルをcommitします。ワーカーは基準commitの祖先関係と対象ファイルのSHAを照合します。
5. PowerShellで実行します。

```powershell
cd C:\FireAI\AIOS
py -3.11 scripts/autonomy/bounded_worker.py \
  --repo C:\FireAI\AIOS \
  --task C:\FireAI\AIOS\docs\autonomy\tasks\approved-example.json \
  --worktrees C:\FireAI\worktrees\autonomy
```

PowerShellでは改行継続にバッククォート（`\``）を使用します。上記の `approved-example.json` は説明用の仮名です。実際にはGit追跡済みで審査されたタスクJSONを指定します。

契約JSONの形式は下記（値は**例**であり実在するcommit/ハッシュではありません）。

```json
{
  "schema_version": 1,
  "mode": "candidate_only",
  "chapter": 12,
  "base_commit": "0000000000000000000000000000000000000000",
  "source": "backend/app/routers/inspections.py",
  "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "acceptance": "査察の既存実装で証明した特定の未充足条件を、既存の権限と監査を変えずに解消する。"
}
```

## 次の統合工程（未実装）

現時点ではGitHub Actionsの監視・Issue起票候補PR #133/#134と、ローカルの候補生成が独立しています。

必要な残作業：Issueから具体的な受入条件を検証して契約化、隔離CIで安全な候補だけテスト、秘密検査、PR作成、CI結果の再照合、既存branch protection・Human Gateの遵守、main更新と次Issueへの継続。ここを完了するまでは自律開発完成と報告しません。
