# Explicit online legal-source sync policy — Issue94

Execution date: 2026-10-10 UTC. Implementation base: `adfede71a22e23f44faa6c53208a84cabcb433c5`.

## Problem and bounded repair

The scheduled path uses `is_due()` to exclude disabled and non-online sources, but explicit `--source-id` calls `sync_source()` without that check. Before this repair, an explicit request could collect a disabled, bundle-mode or manual-mode source, create a `LegalSyncRun`, and change source timestamps. An unknown stored update-mode string also bypassed policy.

`sync_source()` now requires an enabled source whose update mode is exactly `online`, immediately after its existing missing-source check. Rejection precedes run creation, timestamp mutation, commit, temporary workspace construction and collector/subprocess dispatch. The rejection occurs before the acquisition failure handler, so it does not mark coverage stale. An enabled online source may still be explicitly triggered when its configured frequency is not due. `allow_bootstrap` retains its existing meaning and cannot override source policy.

Only `scripts/run_legal_source_sync.py`, `backend/tests/test_legal_source_sync_policy.py` and this dedicated verification record are owned by this slice. The runtime change is two lines. No shared workflow, application/schema/grant, migration, signature/key policy or formal-law interpretation changes are included.

## Actual-source RED and focused GREEN

The pre-existing eight-test fixture was retained and executed after the worktree moved to the exact base above: **8 failed in 1.32s**. Both the former `2ba2c11` base and this base have sync-script blob `a9af061d1b1b9836fa0bc1a5b41903784bb4cae4`. Each denied state dispatched the synthetic collector or persisted a sync run.

Expanded tests were then executed before the guard was added: **24 failed / 5 passed in 3.05s**. The additional denied cases cover both supported adapters and both bootstrap flag values, including resource boundaries. Existing permitted-online and missing-ID behavior passed before the repair. The fourth denied state is an existing source with `update_mode='unknown'`; missing source ID is a separate test using an absent valid UUID.

After the two-line repair, policy, signed bundle/folder and source registry regressions completed **57 passed / 3 warnings in 8.94s**. The workspace spy was subsequently tightened to observe construction, not merely context entry; a fresh policy run completed **29 passed in 3.37s**.

The policy tests import the real script and use isolated SQLite databases with real `LegalSource`/`LegalSyncRun` models and session commits. They retain the entire source-column snapshot across rejected requests, including last-checked/success/full-sync timestamps, coverage and document counts. Collectors are boundary stubs with synthetic `.invalid` source URLs. Temporary workspaces are recorded without filesystem creation; any subprocess attempt raises an assertion. Permitted online cases prove successful run persistence, adapter dispatch and bootstrap-option forwarding while `is_due()` is false.

Focused regression command, from repository root with the isolated Python interpreter selected as `PYTHON`:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend "$PYTHON" -m pytest \
  backend/tests/test_legal_source_sync_policy.py \
  backend/tests/test_signed_legal_bundle.py \
  backend/tests/test_phase1_core.py::test_phase5_1_legal_profile_and_source_registry \
  backend/tests/test_phase1_core.py::test_phase5_1_rejects_source_for_unknown_jurisdiction \
  -q --tb=short -p no:cacheprovider
```

## Local full-suite evidence and acceptance limit

The isolated interpreter is Python3.12.14. With `PYTHONPATH=backend` from repository root, imported `app` was verified to resolve to this worktree's `backend/app/__init__.py`, rather than the interpreter's editable rehearsal source. CI uses Python3.11 and remains separate evidence.

An initial full-suite invocation from the backend directory stopped at collection because `test_phase6_annotation_qa.py` imports `backend.app` and the repository parent was not on the import path. The corrected repository-root command is:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend "$PYTHON" -m pytest \
  backend/tests -q --tb=short -p no:cacheprovider
```

Corrected full-suite result: **1299 passed / 295 skipped / 287 warnings in 404.72s**. The service/browser skips remain unverified gates. Reported warnings concern existing Starlette TestClient deprecation, SQLite cyclic table-drop ordering and Pillow image-data deprecation. No local test failure remained after correcting the invocation context.

This record establishes a synthetic source-configuration guard and preserves existing signed bundle/folder candidate workflows. It does not establish shared deployment egress policy, cancellation when configuration changes mid-flight, actual external legal acquisition, production PostgreSQL/LAN behavior, formal legal interpretation, or system/Release completion. Skipped local service/browser gates are not accepted functionality. Exact PR CI, independent review and independent main CI remain root's serial integration gates; no Issue94 or chapter-completion credit is claimed here.

## Root integration check

After the worker completed, root rebased the unpublished branch without
conflicts onto main `46865f438ab7a7482678c0ed720c15f00f113a65` (tree
`ccfe26ae18b34235cae81c6adf1804a38111c8bb`). The reviewed runtime guard and
policy tests are unchanged. At local `7e2d9dff`, the integrated policy, signed
bundle/folder, complete phase1 core, actual pinned scanner/hook and violation
state regressions passed **206 tests / 125 warnings in 58.57s**, exit0.
Warnings are the existing Starlette, SQLite schema-cycle and Pillow warnings.
These local checks do not credit skipped PostgreSQL or Chromium execution.
Prior main's dedicated secret gate succeeded, while its independent full
project CI and this slice's remote PR/main acceptance remain separate gates.
