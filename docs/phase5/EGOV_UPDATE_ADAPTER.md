# e-Gov 法令更新Adapter

更新日: 2026-10-05

## 正式Source

- e-Gov 法令API Version 2
- Base: `https://laws.e-gov.go.jp/api/2`
- Bulk XML: `https://laws.e-gov.go.jp/bulkdownload`

## Initial bootstrap

全法令XML:

```
https://laws.e-gov.go.jp/bulkdownload?file_section=1&only_xml_flag=true
```

## Daily delta

指定日の更新法令XML:

```
https://laws.e-gov.go.jp/bulkdownload?file_section=3&update_date=YYYYMMDD&only_xml_flag=true
```

e-Gov公式仕様では更新法令データの取得範囲は過去3か月。

## Collector

`scripts/collect_egov_update_bundle.py`

例:

```bash
python scripts/collect_egov_update_bundle.py --mode all --output-dir ./legal-updates
python scripts/collect_egov_update_bundle.py --mode delta --date 20261005 --output-dir ./legal-updates
```

Collectorは取得ArchiveのSHA-256とManifestを生成する。

## Important

このCollectorは法令原本取得パート。
法令本文をRuleへ自動昇格させない。

次段:
1. XML Archive import
2. LegalSourceDocument / Version生成
3. 旧Version Diff
4. LegalUpdateCandidate生成
5. 影響Rule候補
6. Human Gate
7. Approved Rule Version
