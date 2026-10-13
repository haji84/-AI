# 消防AIOS Work非依存バックログ補充（限定版）

本コードはPR #133の安全な15分巡回を利用し、未完成の44章を仕様書に記載された依存順で**調査Issueとして管理**します。実装Issueを自動的に解決する機能ではありません。

## 補充順序

docs/completion/CONTINUATION_ORDER_20261008.md の P0 → P1 → P2 → P3 → P4 を採用します。個別chapterの最新状態は docs/completion/CURRENT_COMPLETION_LEDGER.md と現在のmainを照合します。

- CompletedとExternal GateのchapterにはIssueを新規作成しない。
- 一度にOPENの自動調査Issueは最大2件。
- 同じchapter・同じ残要件のIssueは再作成しない（閉じた後も）。
- 調査Issueが閉じられ、別章の未調査要件が残っていれば次を補充する。
- Completion Ledgerで同章の残要件（記載差分）が変更された場合は、新しいgap fingerprintとして扱う。ただし同章にOPENの調査Issueがある場合は重複起票しない。
- 並列制御はGitHub ActionsのconcurrencyとIssue上のOPEN状態で管理する。権限失効、ジョブ失敗、曖昧な分類、1000件超の取得不足ではfail closed。
- GitHubの公開コメントで他人が同じマーカーを書いても、データ取得時に作成者（オーナーまたはGitHub Actions）を照合し、重複回避や停止指示としては扱わない。

## Kill Switch

所有者haji84が、OPEN Issueの本文に次のマーカーを追加すると、次回実行から調査Issueの新規作成を停止します。

~~~text
<!-- aios-autonomy-pause -->
~~~

Issueを閉じれば次回実行から再開候補となります。これは**Issue起票の停止だけ**であり、未設置の自律コードワーカーや既存Actionsを停止する万能Kill Switchではありません。

## 完成判定

調査Issueの終了は業務機能完成ではありません。実装・テスト・独立レビュー・CI・main統合・完成台帳の受入証拠が必要です。15分cronは正確な実行間隔の保証ではなくGitHub Actionsのスケジューラに依存します。
