# Phase 3 Implementation

更新日: 2026-10-05

## Scope
Phase 3 attaches inspection history/findings and submission receipt/status management to the Phase 2 facility detail workflow.

Implemented:
- inspection create/list/detail/update
- inspection findings create/update/complete
- optimistic locking for inspection and findings
- submission type master
- submission receipt/update
- official submission number: digits only
- original document linkage
- facility/document scope conflict prevention
- specialized records for equipment inspection report, fire manager appointment, and fire plan
- facility dashboard for inspection/open findings/core submission status
- browser UI for quick inspection registration and submission receipt
- original file upload from arbitrary filename
- legacy prevention data normalization from the supplied inspection ledger
- legacy records are marked separately from modern document-backed submissions

## Legacy safety policy
Legacy ledger values are not automatically promoted to modern formal submissions when the original filing document is not present.
- deterministically parseable Excel serial/Japanese era dates are normalized
- original source text is retained
- strings such as `提出済` remain raw evidence text when no date can be proven
- fire-manager name-only legacy records are distinguished from filing evidence
- presence of fire equipment is never treated as proof that an equipment inspection report was filed

## Host Gate
The approved-host PostgreSQL/TLS/two-client test remains unexecuted and must not be reported as PASS.
