# Emergency acceptance measurement implementation plan

**Goal:** Make the user's five completion indicators measurable, persistently reviewable, and incapable of treating missing evidence or synthetic data as production completion.

**Architecture:** Strict measurement schemas and a deterministic calculation core; authenticated immutable evaluation snapshots on the existing server; a plain Japanese evaluation screen. Original reports and patient values stay outside this measurement payload. Candidate-check coverage connects to the existing provisional rule core without approving rules.

**Tech stack:** Existing Python/FastAPI/SQLAlchemy/PostgreSQL and local HTML/JavaScript. SQLite is tests only.

**Spec:** `docs/emergency/ACCEPTANCE_MEASUREMENT.md`, `docs/emergency/REPORT_CHECK_GOAL.md`, `docs/SPECIFICATION.md`.

## Global constraints

- No real personal information, original documents, or source-derived hashes in Git or CI.
- No unapproved rule activation, clinical decision, automatic OA correction, or claim of production completion.
- No arbitrary effectiveness targets; missing data remains missing.
- Existing session, fixed headquarters boundary, dedicated emergency permissions, safe audit allowlist, and no-store responses apply.
- Preserve immutable previous evaluations; use expected versions for independent review.

## Review focus

- Unreadable and unchecked true errors disappearing from recall.
- No alerts or no errors becoming an artificial perfect score.
- Duplicate warnings, wrong report versions, and late warnings inflating performance.
- Missing or overlapping labor time and unmatched follow-up cohorts.
- Payload reflection, stale browser responses, authority self-approval, and synthetic data disguised as production evidence.

## Tasks

- [ ] 1. Write tests, strict schemas, deterministic metrics and explicit incomplete-data gates.
- [ ] 2. Write tests, immutable DB snapshots/migration, scoped safe API, independent review and provisional coverage endpoint.
- [ ] 3. Add a Japanese evaluation screen using existing shared-session handling; verify the actual UI with synthetic records.
- [ ] 4. Correct the existing P01 gate wording failure without loosening its rule; run relevant regressions and project checks; independently review and publish the tested commit to the existing draft PR.

Work records and test output are kept in local task notes during execution; the public evidence document contains only synthetic test results and limitations. Real acceptance remains pending until internal evidence exists.
