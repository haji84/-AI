# Issue 95: current crew source privacy guard

## Scope and baseline

Bounded Lane 5 changes only `backend/app/workforce_crew.py`, the existing
`backend/app/routers/workforce.py` available-crew endpoint,
`backend/tests/test_workforce_crew_privacy.py`, and this evidence file.
The original untracked personnel-permission RED fixture was preserved.

Fresh `git fetch origin main` resolved to
`46865f438ab7a7482678c0ed720c15f00f113a65`, canonical tree
`ccfe26ae18b34235cae81c6adf1804a38111c8bb`. Fresh GitHub Issue 95 body/comments
and source blobs were checked during the read-only preparation audit. Eleven
relevant route/service/source/helper/model/fixture/database blobs matched the
existing isolated RED worktree before advancing its branch to this baseline.
Root reported independent baseline main CI success before activation.

No shared authorization, CI, ledger, schema, migration, production grants,
personnel assignments, UI, pay, dispatch or Human decision flow was modified.
All new data and permission setup in tests are disposable synthetic fixtures.
Chapter 25 and the cross-chain overtime/allowance scope remain Partial.

## Design

The endpoint now requires current `workforce.read` and `personnel.read`, an
available account/employee/password/session and an enabled workforce module.
It reuses the existing statistics boundary helpers for preflight identity,
read-only coherent capture, and a fresh release session. PostgreSQL capture
uses REPEATABLE READ/read-only; postflight uses READ COMMITTED. The helpers
retain existing BoundSession tenant/maintenance behavior.

Existing `current_source`/`original_rights` guard roster originals. Each returned
qualification's optional original is separately checked through the existing
`document_permissions` typed/transitive closure. Missing or inaccessible
admitted originals reject the complete response with a generic 403. This
prevents an inaccessible original from appearing as a verified qualification.
No new permission codes or production grants are introduced.

Private exact content hashes cover the candidate set and roster, employee,
current and captured assignment, organization, shift/work-rule, overlapping
approved leave, admitted qualifications and their originals. Original ownership,
derived inquiry/template/evidence/source dependencies and document graph edges
are pinned with cycle protection. Existing closure helpers remain the source of
authorization; the new graph walk records dependency evidence only.

Only after baseline/original admission does the existing
`workforce_service.available_crew` create the captured wire projection. Its
eligibility checks and response shape remain unchanged. A fresh postflight
rebuilds eligibility and dependencies without projecting private fields again,
compares required rights and exact fingerprints, and rechecks current authority
before release. Source changes can produce 409 even when version and visible
fields did not change. Candidate/qualification/leave insertion is also detected.
Fingerprints, private dependency evidence and required-right lists are not
included in the response.

Only this endpoint uses the existing `PrivateTeamRoute` wrapper. Successful
responses, authorization/source rejection and request validation receive
`Cache-Control: no-store`. Other workforce routes retain their existing wiring.

## RED and focused GREEN

Before implementation, actual canonical-code tests reproduced all three
missing boundaries: personnel permission loss, roster typed original rights,
and qualification typed original rights. **3 failed in 4.44 seconds**, each
incorrectly returning 200. Explicit worktree PYTHONPATH avoided editable-install
source ambiguity. Tests use synthetic names/IDs and in-memory SQLite only.

Final focused command:

```sh
PYTHONPATH=/workspace/scratch/2fd534d68c1f/fire-aios-crew-red/backend \
PYTHONDONTWRITEBYTECODE=1 python -m pytest \
backend/tests/test_workforce_crew_privacy.py -q -p no:cacheprovider
```

Result: **40 passed, 7 skipped in 19.21 seconds**. Coverage includes admitted
typed-original success; original denial/missing original; session/account/
employee/password/module/right loss; exact-content changes without version
changes; roster/qualification/leave insertion; derived-template SHA, ownership
and typed permission changes; validation/unauthenticated no-store; unchanged
assignment/work-rule/partial-leave/inactive/qualification-date/filter eligibility.
Existing integrity and safety tests also passed in an initial combined focused
run (26 passed in 12.36 seconds).

A shared-original ordering regression first failed against the initial service
(1 failed in 3.61 seconds): reversing candidate query order changed evidence
representation despite unchanged data. The final service gives ORM and incoming
ownership rows the same canonical representation, retaining record identities
and complete content hashes including versions. The shared-original reorder
test now passes. This was one corrective hypothesis; no guard was weakened.

Seven genuine PostgreSQL cases use the existing migrated disposable
`statistics_pg` fixture and `FIRE_AI_TEST_POSTGRES_URL` CI environment. They use
a separate writer transaction and assert capture/postflight isolation, source
or authority rejection and connection-pool reset. No PostgreSQL URL was supplied
locally, so these were SKIP and are not credited as PostgreSQL acceptance.

## Final regression and limitations

The final full backend suite ran after all final service/test changes:

```sh
PYTHONPATH=/workspace/scratch/2fd534d68c1f/fire-aios-crew-red/backend \
FIRE_AI_GITLEAKS_BIN=/tmp/fire-aios-gitleaks-probe-YrxQnE/gitleaks \
PYTHONDONTWRITEBYTECODE=1 python -m pytest backend/tests -q -ra -p no:cacheprovider
```

Result: **1332 passed, 302 skipped in 440.49 seconds**, exit 0. The `-ra`
summary identifies environment-dependent real PostgreSQL and native Chromium
cases among the skips, including the seven new PostgreSQL cases. No skipped
case is credited as acceptance. The actual pinned secret gate also passed
fetched refs plus the final working tree with zero findings. `git diff --check`
was clean. Only this evidence document changed after that final suite began.

Actual migrated PostgreSQL execution, exact reviewed head CI, latest-main
integration and independent main CI remain root
acceptance requirements. No remote push/PR/issue/merge action is performed by
this lane. The guard verifies database metadata/authorization dependencies;
it does not read or rehash original file bytes or create formal crew decisions.

Final code/test Git blob identities, frozen before the final full suite started:

- Route: `c0ba458d7bf938f28caf4458faf9e896342adacc`
- Service: `a5e521b1b8dd3e5aa22ad0257a35260360ada7fd`
- Tests: `5f0ccfb26b17fce4c3e395a45e53cb59765f0679`
