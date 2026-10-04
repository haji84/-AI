# PROJECT_STATE

更新日: 2026-10-05

## Current Phase

Phase 4 document intake core is code-complete and verified in the development environment.
Formal approved-host PostgreSQL/TLS/two-client gate remains unexecuted.

## Phase 0-3 retained

- legacy inspection ledger audited/mapped
- auth / RBAC / audit / optimistic locking / extensibility
- emergency reporting import foundation
- facility CRUD / normalize / conflict UI
- inspection / findings
- submission type / receipt / original document linkage
- legacy prevention values kept as legacy evidence, not falsely promoted to modern filings

## Phase 4 completed in code

- PDF embedded-text extraction
- scanned PDF OCR fallback path
- image OCR path for JPG/JPEG/PNG/WebP/TIFF
- DOCX direct extraction
- XLSX/XLSM direct extraction
- TXT/CSV/TSV direct extraction
- deterministic submission-type classification with evidence/confidence
- facility candidate ranking
- field extraction candidates
- facility difference proposals
- human review gate before receipt
- explicit accepted-path gate before facility update
- document analysis / proposal version conflict protection
- 100MB synchronous analysis cap / OCR page cap
- managed-storage path boundary
- Phase 4 browser receipt workflow

## Verification

- backend tests: 37 passed
- frontend JavaScript syntax: PASS
- migration 007 parser: 8 statements
- facility legacy regression: PASS (611 / 611 / 611 / 1,434)
- emergency regression: PASS (2,958 / 2,950 / 8,981; unresolved 66 retained)

## Not yet reported as PASS

- actual Japanese scanned-document OCR quality E2E
- HEIC decode
- Local LLM ambiguous-classification fallback
- approved LAN PostgreSQL migrations 001-007
- PostgreSQL backup/restore after migration 007
- HTTPS browser test from production LAN clients
- two physical client concurrent edit/receipt E2E

## Next Phase 4 Slice / Phase 5 preparation

1. real scanned-form OCR evaluation dataset and confidence thresholds
2. structured field mapping per official form template
3. multi-page image grouping/page-order assistance
4. Local LLM fallback only when deterministic classification is insufficient
5. legal-rule source/version schema hardening
6. Phase 5 legal requirement / equipment requirement rule engine