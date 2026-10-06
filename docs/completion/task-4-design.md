# Task 4 finance design and test plan

Approved scope: extend the shared app, canonical ContractCase/Counterparty/Document/Change and server-bound tenant sessions. No duplicate vendor or contract master.

Finance years hold explicitly Human-approved currency/decimal precision policy. An approved ordered headquarters/year hierarchy policy supports variable depths (default款項目節細節, alternate事業→節 and extended細々節); immutable year-bound accounts preserve string codes. Contract profiles add fiscal/deadline metadata and immutable initial approval provenance, with no duplicate contract master. Evidence-linked quotes and requests are candidates. Financial proposals pass draft → reviewed → approved; review captures exact account, contract and document provenance. Approved journal lines are immutable; authorized reversals append compensating lines. Stable account locks and conditional version updates serialize spending. Allocation minus spending minus reservation is available. Payments release reservations and spend once, within approved commitments. Transfers conserve allocation in one transaction. Idempotency keys and unique reversal links prevent replays. Source changes require fresh review, including common vendor identity/version and Document SHA. Reviewed delivery/inspection/invoice events link typed common documents and payments without posting budget themselves.

Common-contract adapters expose exact decimals, search, parties, documents, and reviewed amendments. Legacy public signatures remain; status PATCH cannot approve and approved financial source edits cannot bypass the explicit amendment workflow. Source permissions also apply to nested snapshots, search and exports. Common extraction/OCR, source document diff, missing-document/similar-case candidates, factual drafts and exact sum support return candidates only. No AI writes financial authority. Registered original templates use the common renderer.

Sequential red-first slices:
1. Policy/account CRUD, permissions/version/audit, leading zeros, immutable hierarchy, precise money, isolated bootstrap.
2. Initial/amendment/transfer journal: draft exclusion, review gate, conservation, overspend, rollback and reversal preservation.
3. Contract/party/document pickers, quote/request candidates, reviewed commitments/payments/amendments; version/evidence/currency/year checks, legacy bypass rejection and exact-once execution.
4. CSV/XLSX schema templates, dry-run/confirm, common original/hash, atomic invalid-row rollback and safe roundtrip; search, alerts, fiscal aggregates, original template rendering.
5. Shared shell forms and searchable paginated pickers; synthetic real HTTP Chromium finance workflow; tenant databases and actual PostgreSQL concurrent approvals/replays in existing CI.

Every slice runs focused tests; completion runs full backend regressions, migration parser and JavaScript syntax. PostgreSQL/Chromium unavailable locally are explicit skips, executed by canonical CI. Genuine external gates are production acceptance, actual formal Human decisions, official originals/mappings and approved operational source data; implemented policy configuration is internal scope.
