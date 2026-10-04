# 大島地区消防組合 例規集取得証跡

取得日: 2026-10-05
公式Source: https://fd-ohshima.jp/reiki_2026/
公式体系目次: https://fd-ohshima.jp/reiki_2026/reiki_taikei/taikei_default.html
内容現在: 令和7年4月1日（2025-04-01）

## 結果

- 体系分類: 第1類〜第7類
- 期待本文件数: 119
- 発見本文件数: 119
- 取得本文件数: 119
- 取得失敗: 0
- coverage_status: complete
- Workflow: acquire-oshima-reiki-fast
- Workflow Run ID: 37240040293
- Artifact ID: 11317595248
- Artifact: oshima-fire-union-reiki-full-2025-04-01
- Artifact size: 1,021,384 bytes
- Artifact SHA-256: 2426f76c7a50609d63f231943f3058b8c196cd8563be54033dba9cbf6defc941
- Artifact expiry: 2027-01-02T22:26:46Z

## 取得対象の確認

公式体系目次から本文URLを抽出し、`/reiki_2026/reiki_honbun/` 配下の119件を全件取得した。
旧 `/reiki/`（内容現在 令和6年8月30日）は正本Sourceとして使用せず、より新しい `/reiki_2026/` を使用した。

## 代表的な予防関係例規

- 大島地区消防組合火災予防条例
- 大島地区消防組合火災予防条例施行規則
- 大島地区消防組合火災予防査察規程
- 大島地区消防組合建築同意事務処理規程
- 大島地区消防組合消防用設備等の検査及び点検を要する防火対象物を指定する規程
- 大島地区消防組合喫煙，裸火の使用を禁止する場所を指定する規程
- 大島地区消防組合防火対象物点検報告等の特例認定に関する事務処理要綱
- 大島地区消防組合危険物の規制に関する指導規則

## 保存方針

この取得結果は大島地区消防組合の `legal_profile=oshima-fire-union` の初回Full Corpus証跡として扱う。
本番Local AIへの取込時はArtifactまたは同一公式Sourceから再取得した原本を、
`LegalSourceDocument -> LegalSourceDocumentVersion` にSHA-256付きで保存する。

次回以降は同一Sourceを日次監視し、文書Hash変更を検出した場合に新Versionを作成する。
条例等の原文更新は自動取得可能だが、業務判定Ruleの更新はHuman Gate必須とする。
