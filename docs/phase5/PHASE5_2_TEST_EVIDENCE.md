# Phase 5.2 Structured Legal Corpus Verification

更新日: 2026-10-05

## GitHub Actions

Full-corpus verification run: `37241690774`
Conclusion: SUCCESS

## e-Gov 全国法令

Source baseline:
- documents: 10,414
- parse failures: 0
- zero-provision documents: 0
- total structured provisions: 5,447,878

Provision counts:
- article: 1,030,986
- paragraph: 2,364,763
- item: 1,274,776
- subitem1: 278,051
- subitem2: 55,981
- subitem3: 11,971
- subitem4: 2,474
- subitem5: 217
- subitem6: 13
- supplementary: 332,030
- chapter: 24,713
- section: 21,850
- subsection: 11,515
- division: 2,856
- part: 680
- preamble: 68
- form: 28,112
- appendix_table: 5,371
- appendix_note: 1,296
- appendix_figure: 147
- appendix: 8

## 大島地区消防組合 例規

Source baseline:
- documents: 119
- parse failures: 0
- zero-provision documents: 0
- total structured provisions: 26,898

Provision counts:
- article: 3,577
- paragraph: 4,983
- item: 404
- supplementary: 744
- appendix: 190
- appendix_block: 16,970
- form: 29
- document_body: 1

The one article-less official designation notice is intentionally retained as a citable `document_body` provision instead of being treated as a parser failure.

## Safety checks

- structured Rule source requires exact provision citation before approval
- citation must belong to the Rule Version source document Version
- changed/removed cited provisions are reverse-mapped to impacted Rule candidates
- Rule evaluation output includes exact legal citations
- article-less official documents remain citable
- existing project regression: 46 tests passed
- Migration 010 parser: PASS
- Migration 011 parser: PASS
