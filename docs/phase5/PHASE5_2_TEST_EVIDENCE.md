# Phase 5.2 Test Evidence

更新日: 2026-10-05

## Automated verification

Latest main project-checks:
- commit: `9b0fae6b065b7ce923017d625fc950450590903e`
- backend pytest: 46 passed
- Migration 010 parser: PASS (7 statements)
- Migration 011 parser: PASS (5 statements)
- frontend JavaScript syntax: PASS
- operational script syntax: PASS

## Full real-corpus structural verification

Workflow:
- `verify-legal-structure-corpora`
- final successful run: `37241690774`
- parser: `legal-structure-v1`

### e-Gov nationwide corpus

Input:
- official e-Gov full XML acquisition
- documents: 10,414

Result:
- parsed documents: 10,414
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

### 大島地区消防組合 corpus

Input:
- official regulation corpus: 119 documents

Result:
- parsed documents: 119
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

The single `document_body` is an official article-less designation/notice:
`大島地区消防組合指定金融機関の指定について`.
It is intentionally preserved as one citable body provision rather than falsely inventing Article numbering.

## Rule citation safety

Verified behavior:
- structured-source Rule Version cannot be approved without an exact LegalProvision citation
- citation must belong to the same source document Version
- citation text snapshot is retained
- citation changes are allowed only while Rule Version is draft
- evaluation results expose exact cited provision(s)
- changed/removed cited provisions can be reverse-mapped to impacted Rule IDs
- source document -> Version -> Provision -> Citation -> Rule workflow is covered by automated tests

## Important limitation

Structural parsing proves that the legal text can be addressably stored and cited.
It does NOT mean all 5.4M provisions have been converted into operational fire-service Rules.

Formal Rule conditions/outcomes remain a separate Human-Gated authoring process.
