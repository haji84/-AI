# Source-backed hazardous-materials register plan

**Goal:** Implement a usable first Specification §16 register in the existing authenticated PC web application. Human staff record installation/material facts, permit/notification/change evidence, deadlines and related inspection/violation records. No legal classification or threshold is inferred.

**Base:** `c1b684c5c38fc52fe908d2116a21a16ef48dcb34`. Read `AGENTS.md` and `docs/SPECIFICATION.md` §§5–9,16–17,40,43,45,47–48,53–55.

## Design and boundaries

- Reuse Facility UUIDs, common Document originals/hash/storage and existing Inspection/Violation records. Do not copy facility masters, originals, personnel, workforce or statistics data into new masters.
- Store Human-entered category and material descriptions. Quantity and capacity use exact finite Decimal strings plus explicit units; reject excess precision instead of rounding. No automatic unit conversion or incompatible-unit totals.
- Installation has active/retired state and optimistic version. Materials belong to the installation revision. Permit/notification/change records describe existing evidence; the application does not issue a permit or decide legal compliance.
- Human evidence confirmation binds the current installation facts, record revision, actual original hashes and legal source versions. Changed facts make a previous confirmation historical rather than current. Confirmed history is preserved; corrections use explicit supersession/revision with a Human reason.
- Reuse granular permission and mutation-session guards. All mutations require current authority and compare-and-swap before side effects. Source visibility filters precede titles/counts/pagination; missing source permissions must not expose linked evidence.
- Inspection/violation links must reference the same building. Each linked surface retains its own read permission. Legal evidence is a source pointer, not a new executable Rule.
- Preserve append-only change/history evidence, with actors, timestamps, before/after and source versions. Retire/cancel/supersede instead of physical deletion.
- Module flag and source permissions are checked on reads/writes. Shared-session invalidation clears browser state, and obsolete navigation/requests cannot reappear.

## Migration coordination

Remote checked 2026-10-07 04:47 UTC: main remains the base above; only open PR67 is the no-migration intake repair. Provisional051 belongs to inaccessible RunB work and is reserved. This slice reserves **052_hazardous_materials_register.sql**, depending only on current-main tables. Existing046 gap and all historical migrations remain untouched. The runner tracks individual filenames and supports gaps. Recheck remote before publication.

## Ownership

Backend implementer: new hazardous model/schema/service/router files, migration052 and backend/PostgreSQL tests. Lead owns common model import, main router registration, RBAC seed, module seed, frontend shell, search wiring, CI and completion evidence.

Frontend implementer (after API contract is frozen): new hazardous module JavaScript, UI state tests and real Chromium acceptance. Lead integrates shared shell and preserves concurrent work-list/intake changes.

## Steps

- [x] Freeze a small concrete API contract after inspecting current source conventions; independent frontend consumes it.
- [x] Add failing backend tests for exact quantities, source provenance, visibility, current Human confirmation, immutable history, same-building links, stale versions and session/permission revocation.
- [x] Implement register/evidence/revision/history and source selectors using current service patterns; no legal thresholds or Rule-engine extension.
- [x] Add migration/rerun/upgrade and real PostgreSQL concurrent-change/confirmation tests. Never treat SQLite as PostgreSQL evidence.
- [x] Implement registry/detail/material/source upload/evidence confirmation/deadline/history browser flow with normal first-use controls; no developer IDs as the sole input path.
- [x] Integrate common registration and permissions; run full tests, migration parser, JavaScript syntax and independent review.
- [ ] Publish a draft PR and follow its exact-head PostgreSQL/Chromium CI to terminal. Merge only when specific applicable permission is confirmed.
- [ ] Package the verified merged source only after all combined checks pass; retain the release-candidate boundary.

## Acceptance and remaining scope

Synthetic facility → installation/materials → original upload → permit/notification record → explicit Human evidence confirmation → deadline list → related inspection/violation → correction/history. Test stale confirmation, modified/missing original, exact units/decimals, permission-redacted counts, concurrent mutations, failed transactions, cancellation and shared-PC session changes.

This changes §16 from Missing to Partial. Hazardous Rule evaluation, its approved source corpus and remaining whole-product flows remain separately tracked; the missing Rule implementation is internal work, not an external gate. Production legal sources/policies, operational host/roles and real-site acceptance require their own Human inputs. No distributed PC worker or disaster-recovery architecture is implemented here.
