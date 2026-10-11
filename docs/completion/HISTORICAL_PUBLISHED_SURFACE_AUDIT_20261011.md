# Historical published-surface audit continuation

## Scope

This bounded Issue #97 slice adds a restartable historical inventory in front of
the existing private GitHub published-surface scanner. It does not close Issue
#97 or promote Master Specification chapter 43.

The inventory enumerates every pull request and every repository workflow run
visible to the GitHub Actions token. It records the full run order and the
completed subset separately, binding both to one SHA-256 identity. A caller
then supplies the last successfully audited PR/run cursor, the preceding
cursor-prefix SHA-256, the first batch's fixed PR/run snapshot ceilings, and
snapshot-membership SHA-256 with bounded per-run limits. New surfaces above
those ceilings cannot create an endless moving target; deletion of any
unprocessed snapshot identity fails closed. The selected exact IDs are
processed by the existing metadata/comment/review/log/artifact collector and
pinned Gitleaks scanner.

## Fail-closed contract

- Pull-request pagination uses creation order and rejects malformed, duplicate,
  non-positive, boolean, or cross-repository identities.
- Workflow pagination deliberately does not use GitHub's status filter, whose
  filtered result is capped at 1,000 records. It enumerates all runs, validates
  exact total-count coverage, and selects completed runs locally.
- Every discovered page is re-read before accepting the inventory. Concurrent
  movement on any page, status transition, total-count drift, duplicate runs,
  or repository mismatch fails the run rather than producing a partial GREEN
  inventory.
- A maximum of 10,000 PR rows and 10,000 workflow-run rows bounds memory and API
  work. Exceeding either limit fails closed and requires a redesigned partition,
  not truncation.
- Cursors must be zero or an exact completed identity in the current inventory.
  Nonzero cursors require the exact cursor-prefix SHA-256 emitted by the
  preceding batch, so a late status transition below a cursor cannot be hidden
  by a fresh inventory. A batch never crosses the first incomplete run. Batch
  sizes are restricted to 1–100 per surface type.
- The first batch emits fixed PR/run snapshot ceilings. Every continuation
  reuses those exact ceilings, so newly created audit runs remain future-surface
  work and do not prevent the historical snapshot from reaching a finite end.
  A separate initialized marker preserves an exact empty (`0`) ceiling.
- Continuations require the first batch's membership SHA-256 over every PR/run
  identity through both ceilings. A deleted or unavailable unprocessed
  identity therefore becomes an explicit failed batch rather than silently
  disappearing; run status transitions remain allowed until their turn.
- An uninitialized first batch must start with both cursors at zero. Nonzero
  cursors are accepted only with the prior snapshot marker and both hashes, so
  a caller cannot create an unproved starting gap.
- The five-minute discovery deadline is propagated into each HTTP connection,
  header, and body read; an individual 60-second request cannot extend it.
- Historical mode still receives explicit-ID inputs, allowing the CLI to reject
  mixed historical/exact dispatches instead of silently discarding them.
- A cursor advances only after the selected exact batch completes collection
  and private scanning. Expired/unavailable logs or artifacts therefore remain
  explicit blockers.
- Downloaded bytes, API payloads, expanded artifacts, and raw scanner reports
  remain in the existing private temporary directory and are deleted. No raw
  material is uploaded.

## TDD evidence before publication

- Existing baseline: `32 passed`.
- Initial RED: 9 failures for absent inventory/batch interfaces and absent
  workflow dispatch wiring.
- Resource-bound RED: missing global history surface bound.
- Independent-review RED: seven focused failures reproduced later-page
  mutation, late-completion cursor skipping, silently discarded mixed inputs,
  and an in-flight request outliving the shared discovery deadline.
- Second-review RED: four focused failures reproduced deletion of an
  unprocessed snapshot run and ambiguity between an empty ceiling and automatic
  snapshot discovery.
- Current focused GREEN after those repairs: `51 passed` in
  `backend/tests/test_github_published_surface_audit.py`.
- Integrated scanner/audit focus with the pinned official Gitleaks binary:
  `72 passed`.
- Full local backend regression with the same pinned scanner: `1464 passed`,
  `304 skipped`, `327 warnings`, and `46 subtests passed`. Skips are not
  execution evidence.
- A read-only GitHub API observation after the implementation found 105 pull
  requests and 742 total workflow runs; all 742 were completed at observation.
  Eight run pages reported the same total, and all observed PR/run identities
  were unique, positive, and repository-bound. This confirms the inventory is
  below its explicit 10,000-row bounds, but it is not scanner execution
  evidence.

Exact-head CI, independent review, merge, independent main CI, and the first
real historical batch remain required before acceptance. The local runner has
no GitHub audit token and therefore provides no real-history execution credit.

## Explicit remaining gates

- GitHub Push Protection administration proof is unchanged and requires an
  authorized administrator.
- This mechanism does not decide whether operational content is personal data
  or authorize disclosure of any private payload.
- Historical surfaces that GitHub no longer retains cannot be converted to
  scanned evidence; each unavailable exact batch must remain recorded as an
  unverified coverage gap.
- Current/future source and published-surface scans do not prove that every
  historical surface has been successfully scanned. Completion requires the
  cursor to reach both inventory ends without an unresolved failed batch.
