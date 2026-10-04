# e-Gov 全国法令 全件取得証跡

取得日: 2026-10-05
公式Source: https://laws.e-gov.go.jp/
Bulk Source: https://laws.e-gov.go.jp/bulkdownload?file_section=1&only_xml_flag=true

## 結果

- Scope: 全国の全法令XML
- XML文書数: 10,414
- Archive integrity: PASS
- coverage_status: complete_official_bulk_archive
- Workflow: acquire-egov-national-laws
- Workflow Run ID: 37240404083
- Artifact ID: 11317001520
- Artifact: egov-national-laws-all-xml
- Artifact size: 296,369,894 bytes
- Source Archive SHA-256: 830c24983bee6d9e7db8765b01ed671ee91ca9472324ec5c0d8d0e5a32e660cf
- Artifact ZIP SHA-256: a834626b725f78e91b5682a9f1f891f988d4453819ff826c809d9a72acb81a9d

## 取得方式

e-Gov公式「すべての法令データ」のXML-only Bulkを取得した。
ZIP全体の整合性を検証し、Archive内のXMLを列挙した結果10,414件を確認した。

## 保存・更新方針

このArchiveを全国法令の初回Baselineとする。

次回以降:
1. e-Gov更新法令データを日次取得
2. SHA-256で同一Version判定
3. 変更法令のみ新Version保存
4. 旧Versionとの差分生成
5. 影響Rule候補生成
6. Human Gate
7. Approved Rule Version更新

原文法令の取得は自動化可能。
法令改正の業務ルール解釈・正式Rule有効化は自動確定しない。
