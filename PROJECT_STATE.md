# PROJECT_STATE

更新日: 2026-10-05

## Current Phase

Phase 5 core legal-rule engine is code-complete and CI-verified.
Phase 5.1 legal-source / fire-department profile registry core is code-complete and CI-verified.
Live national/local legal-source collectors are the current implementation slice.
Formal approved-host PostgreSQL/TLS/two-client gate remains unexecuted.

## Phase 0-4 retained

- legacy inspection ledger audit / 574-column mapping
- auth / RBAC / audit / optimistic locking / extensibility
- emergency reporting import foundation
- facility CRUD / normalized detail / conflict UI
- inspection / findings
- submission type / receipt / original document linkage
- PDF/image/DOCX/XLSX/text document intake
- OCR fallback and deterministic document classification
- Human Review before receipt/facility change
- contract/form-template/extensibility foundation

## Phase 5 completed

- legal rule registry
- numbered/effective-dated rule versions
- source requirement before approval
- Draft / Approved separation
- deterministic requirement evaluation
- submission/equipment requirement domains
- evidence and candidate-only decisions
- management/approval/evaluation RBAC
- facility UI for candidate document/equipment requirements

## Phase 5.1 source registry completed

- national/prefecture/municipality/fire-union/fire-department jurisdiction model
- fire-department legal profiles
- multiple applicable jurisdictions per profile
- multiple official sources per profile/jurisdiction
- online/bundle/manual update modes
- all-content source scope metadata
- sync frequency metadata
- legal source document/version model
- raw original-document linkage
- hashes and previous-Version chain
- sync-run tracking
- legal-update review candidates
- Rule Version -> legal source Version provenance link
- legal source/profile RBAC
- API for jurisdictions/profiles/profile-jurisdiction/source registration

## Verification

- Phase 5 backend tests previously: 39 passed
- Phase 5.1 source/profile registry GitHub Actions: SUCCESS
- Migration 009 included in project migration parser smoke
- frontend JavaScript regression: PASS through project-checks

## External-source facts driving the design

- e-Gov Law API Version 2 is the national source target.
- e-Gov supports law lists, revision history, law text, attachments, and bulk XML.
- e-Gov offers latest-updated-law bulk data by date.
- local regulation systems do not have one universal API or uniform refresh cadence.

## Current Phase 5.1 implementation slice

1. e-Gov Version2 live adapter
2. initial national-law bootstrap
3. daily national-law delta sync
4. local official-regulation generic adapter contract
5. official promulgation/update-page adapter
6. per-fire-department full-corpus source discovery
7. full ordinance/regulation text/version import
8. amendment diff + impacted Rule candidates
9. signed Update Bundle for closed networks
10. Update Folder automatic verification/import

## Hard safety rule

Legal text acquisition may be automatic.
Formal Rule interpretation/activation after a legal amendment remains Human Gate protected.

## Formal Host Gate remaining

- approved LAN PostgreSQL migrations 001-009
- backup/restore after Migration 009
- HTTPS production LAN client access
- two-client concurrent E2E
- closed-network Update Bundle transfer E2E

Do not report these as PASS until actually executed.
