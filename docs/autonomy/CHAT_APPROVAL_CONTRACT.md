# 消防AIOS 自律開発のChat承認証拠（限定導入）

## 目的

ChatGPTはGitHub正本の状況確認・指示・重要判断の窓口とする。ChatGPTのチャット発話そのものをGitHubの承認や独立レビューと誤認しない。Workのセッション継続には依存しない。

GitHub所有者のアカウントで、特定PRの現在のhead SHAと短期有効期限を明記したIssueコメントを作成した場合、GitHub Actionsが読み取り専用の承認証拠を作る。

## 承認を記録する形式

具体的な承認対象のPR番号と現在の40文字head SHAをGitHubから読み取り、次の形式のコメントをGitHub認証済みの所有者としてPRへ投稿する。

~~~text
AIOS_APPROVE
PR=135
HEAD=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
EXPIRES=2026-10-13T02:00:00Z
NONCE=distinct-token-123456
~~~

この値は説明例であり、実際のPR番号・head SHA・日時ではない。nonceは重複しない12～64文字を利用する。発行したコメントは24時間以内に失効し、PRのhead更新でも無効になる。承認済みの古いHEADを新規HEADへ引き継いではいけない。

承認の効力：実装に関する次の限定作業へ進むための所有者の意思表示を記録するだけ。

承認の効力がないもの：独立したGitHubアカウントによるPRレビュー承認、branch protection解除、CIスキップ、main merge、本番環境適用、秘密鍵変更、正式な法令・医療判断。

GitHub上で実際に独立レビューが要求される場合は、実装者とは異なる権限を持つアカウントによる正式なReviewが引き続き必要。アシスタント自身が同じhaji84アカウントでコメントしても、独立レビューにはならない。

## 検証と保存

- .github/workflows/autonomy-chat-approval.yml は issue_comment.created でのみ起動する。デフォルトブランチへ導入後に有効化される。
- コメントのGitHub認証情報、作者区分（OWNER）、PR識別子、最新head SHA、期限を照合する。
- 承認証拠は7日保存のJSON Artifact。mergeやPR更新を実行する権限はない。
- 受け入れられない入力は SAFE_STOP として終了する。本文全文、アクセストークン、個人情報をWorkflowログへ表示しない。
- PR #133/#134のバックログ監視、#135の候補生成とは独立した、承認記録の最小単位。

## 未実装のもの

所有者のChat発話をPRコメントに自動変換するホスト承認インターフェース、承認証拠を使用した作業再開とPRへの安全な反映、独立レビューの確定、全レーンの自動実装・テスト・マージ、復旧と本番環境は未実装。

この限定機能の導入を消防AIOS自律開発全体の完成と扱わない。
