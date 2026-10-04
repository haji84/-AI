# Phase 5.1 全国法令・消防本部別例規 自動更新仕様

更新日: 2026-10-05

## 結論

Phase 5のルールエンジンへ、全国法令と指定消防本部の例規を供給するSource Layerを追加する。

全国法令はe-Gov法令APIを正本候補とし、地方例規は消防本部ごとに公式ソースAdapterを設定する。

## Source hierarchy

1. 公式API/公式XML
2. 公式現行例規集
3. 公式公布・改正情報
4. 公式PDF/添付ファイル
5. 手動登録された公式原本

民間まとめサイトや検索結果本文を正式原本として自動採用しない。

## Full capture policy

指定した消防本部プロファイルについて、公式例規ソースに掲載された文書は消防関連だけに絞らず全文保存する。
分類は保存後に行う。

## Version model

Original Source -> Legal Document -> Legal Document Version -> Approved Rule Version

法令本文Versionと業務判定Rule Versionを別物として管理する。

## Update state

- unchanged
- new
- amended
- repealed
- source_missing
- parse_failed
- review_required
- rule_update_required

## Auto-update safety

原文Versionの取得は自動。
正式Ruleの有効化は自動にしない。

法令改正検知後はAIがRule変更案を作ってもHuman Gateへ送る。

## Fire-department adapters

各消防本部プロファイルは複数Sourceを持てる。

例:
- 組合例規集
- 構成市町村例規集
- 条例/規則公布ページ
- 組合Webサイトの公式PDF
- 独自例規DB

SourceごとにAdapter Type、URL、取得頻度、Parser、Content-current Date、信頼レベルを保持する。

## Closed network

完全閉域では外部自動巡回が物理的に不可能なため、Internet Collector + signed Update Bundleを正式経路として用意する。
庁内側はUpdate Folderを監視し、Bundle到着後は自動検証・取込候補生成まで進める。

## Acceptance criteria

- 全国法令全文Version保存
- 指定消防本部の公式例規全文保存
- Source Hashで差分検知
- 旧Version保持
- 判定日時点Version再現
- 改正検知
- 差分生成
- 影響Rule候補
- Human Gate
- 複数消防本部の厳格分離
- 閉域Update Bundle
- 監査ログ
