# Emergency report audit pipeline implementation plan

> For agentic workers: use subagent-driven development for the explicitly owned
> files below; implement and verify the accepted scope, without inventing formal
> rules or repeated user approvals for ordinary reversible development.

Goal: deliver the working private PDF/image → page reading → configured fields
→ confirmed observations → reproducible check → human disposition → corrected
PDF revision/recheck → five-metric evidence pipeline.

Architecture: dedicated encrypted source/derivative store and tables, existing
FastAPI/PostgreSQL/authentication/audit/maintenance platform, durable subprocess
reader worker, browser UI with no installation. Optional loopback-only AI.

Tech stack: existing Python/FastAPI/SQLAlchemy/PostgreSQL/PyMuPDF/Tesseract/
cryptography, vanilla browser JS, pytest/Playwright. No cloud PHI processing.

Spec: `docs/emergency/REPORT_CHECK_GOAL.md`, `AUDIT_API_V1.md`, existing accepted
five indicators. Global constraints: no real originals/PHI in Git, no guessed
field mappings or automatic approval, no invisible incomplete reading, no
claim of actual efficacy or organizational production acceptance from tests.

Review focus: dedicated privacy boundary, fail-closed encryption, no stale
worker publish, tenant/permission revocation, tri-state checks and independent
truth, safe source/AI content, resumable processing, original immutability.

## Tasks and validation

- [x] Root: private models + migration060, AES-GCM vault with external key,
  scoped CRUD and body-bounded safe errors; meaningful ciphertext/denial/CAS
  tests, no shared document registration.
- [x] Reader owner: native PDF/image validation, page-level mixed-source
  extraction and bounded OCR, explicit missing Japanese, provenance boxes,
  mapping conversion tests; unknown never becomes confirmed.
- [x] Rule owner: bounded typed expression schema, three-valued evaluation,
  unchanged candidate catalog, optional bounded localhost AI with verified
  quotes; source/rule approval remains explicit human workflow.
- [x] Root: atomic durable jobs and leases, subprocess deadline, restart/retry,
  short transactions, original integrity and obsolete-source publication guard.
- [x] Root: rule/profile immutable snapshots, source evidence, impact preview,
  independent approval/effective periods/retire, current revision confirmation,
  runs/dispositions/history/recheck differences.
- [x] UI owner: accessible report inbox, upload/retry progress, page preview and
  mapped-field confirmation, scoped findings, corrected-file loop, visual form
  editor/rule builder, independent measurement events and export. Session reset
  and late-response tests. Actual desktop/mobile rendering is in the CI gate below.
- [x] Root: privacy-safe measurement projection preserving immutable pre-submission-source runs, repeat-warning burden and
  independently matched error IDs; baseline contamination guard, active work intervals,
  submission/followup unknowns and missing data remain visible.
- [x] Root: deployment worker/readiness/offline native manifest/checks, encrypted
  backup/restore integration, update user operation docs and roadmap accurately.
- [ ] Team: targeted tests, native PostgreSQL migration/integration, actual
  browser E2E, security/regression CI, independent code review and fixes;
  publish reviewed exact head to existing draft PR and report verified scope.

External acceptance remains distinct: organization-approved rule sources and
current form mappings, protected real-data evaluation of the five indicators,
and actual target hardware/network/restore validation. Development must supply
the software to perform those steps; it cannot fabricate their outcomes.

Observed local integration before the final UI review correction: 429 passed,
9 skipped (native PostgreSQL, native Japanese OCR and actual browser gates),
37 warnings. Deployment + host-operation tests separately passed37/skipped1.
These sets overlap and must not be added as independent tests. Native CI and
screenshot review are required on the published exact head.

Final UI binding review: revision switches and mapping-page switches now
require the matching decoded original image before confirmation/region save.
Five reproductions failed before the fix and passed afterward; the local UI
suite passed30/skipped3. Remaining checkboxes record publication-time CI work,
whose eventual exact-commit result belongs to the PR Checks/evidence record.
