# Workforce canonical integration implementation plan

> Native execution using superpowers:executing-plans; one fresh whole-branch reviewer, one repair pass.

**Goal:** Repair and integrate existing PR53, preserving canonical personnel and Human-role safeguards rather than reimplementing its domain.

**Architecture:** Main is canonical. Reconcile the exact PR53 delta against its original base and latest main, retaining tenant/bootstrap, password, learning and custom-role changes. Workforce records use existing employee/organization identifiers and Human review/approval; stale assignment evidence must remain blocked.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL16, browser JavaScript, pytest and Chromium CI.

**Spec:** docs/SPECIFICATION.md §25, §6/7/42/47/48; AGENTS.md.

## Constraints and review focus

- No real data or originals in Git; per-department runtime/DB/original/backup isolation.
- No AI approval or weakening CAS, provenance, audit, source freshness or session/RBAC.
- Expired/imported preview comparisons work after SQLite timezone round-trip and in PostgreSQL.
- Approval of any roster tied to changed assignment stays 409, including previously created normal/support placements; replacement uses current evidence.
- Mixed offsets and persisted timestamps retain the same instant through CRUD and attendance/leave comparisons.
- Preserve canonical shared imports/navigation and all existing browser CI; no stale matrix claims about learning completeness.
- Check original-source permissions, role/session changes during Human mutation, and overlap/concurrent ledger safety in review.

### Task 1: Existing workforce integration

- [ ] Refresh main, CI, original PR53 head/base and AGENTS; reconcile per-file delta and review conflict resolutions.
- [ ] Run existing workforce tests before fixes: reproduce import naive/aware error and stale-source test contradiction.
- [ ] Add tests for expired preview (409), current preview apply/replay refusal, and stale normal/support rejection followed by replacement with current evidence.
- [ ] Normalize preview time using the established aware UTC helper. Correct test ordering/evidence recreation; never relax stale assignment rejection.
- [ ] Run workforce plus canonical role/personnel tests; add any necessary timestamp regression before implementing normalization.
- [ ] One fresh full-branch review, one RED/GREEN repair pass; record deferred minor diagnostics and rulings.
- [ ] Full backend, frontend syntax, migrations, diff/tree evidence. Update existing PR53 with expected-head lease and actual canonical main parent; exact-head CI to Green, merge, verify main Green.
- [ ] Update matrix based on code/tests and continue finance/formal violations/hazmat/release completion.
