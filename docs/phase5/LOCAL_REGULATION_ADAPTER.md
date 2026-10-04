# 消防本部別 公式例規Source Adapter

更新日: 2026-10-05

## 基本方針

指定消防本部ごとに、公式例規ソースを登録して全文保存する。
消防関係だけを事前に選別せず、設定された公式例規ソースの対象文書を全件保存する。

## Collector

`scripts/collect_official_regulation_snapshot.py`

Collectorは以下を必須にする。

- index URL
- allowed official host
- include regex
- crawl regex
- max depth
- max pages

同一公式Host外へは移動しない。
取得ファイルは原文Byteを保存しSHA-256を計算する。

## Completeness

Manifestに以下を出力する。

- visited_count
- captured_count
- failure_count
- truncated
- complete_candidate
- document URL / content type / hash / saved file

`complete_candidate=true`でも、人間またはSource Adapterの受入テストで「公式例規目次上の件数」と一致することを確認してからFull Corpusとして承認する。

## Adapter types

サイトの実装差を吸収するため、消防本部SourceごとにAdapterを選択する。

- official_html_crawl
- official_pdf_index
- official_api_xml_json
- browser_manifest
- manual_official_bundle

JavaScript必須の例規システムを単純HTTP Collectorで完全取得できるとは仮定しない。
その場合はBrowser Adapterを使用する。

## Update monitoring

現行例規集だけでなく、可能なら次を別Sourceとして登録する。

- 例規集
- 公布情報
- 改正文
- 告示/公告
- 公式PDF一覧

例規集への反映遅延を補う。

## Storage

各文書は次の階層で保持する。

Legal Profile
→ Jurisdiction
→ Source
→ Source Document
→ Source Document Version

旧Versionを削除しない。

## Rule relation

条例等の原文更新は自動保存可能。
業務判定Ruleの更新はHuman Gate必須。

AIは差分要約、影響Rule候補、影響対象物候補を生成できるが、正式Ruleを自動変更しない。
