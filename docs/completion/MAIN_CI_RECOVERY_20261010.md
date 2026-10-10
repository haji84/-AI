# Main CI recovery checkpoint — 2026-10-10

Canonical implementation: `2ba2c11e50fc2f0f84cc086fe5686a09917f36b1`; tree `d181486a45ed4d3d3144f8b242f5c033d982fc58`.

## Integrated change and acceptance boundary

Issue91 / PR92 added anonymous, durable failed-login audit events and reconciled the expanded specification and eight logical lane ownership. PR exact-head CI38052334810 passed: backend1459 passed/101 skipped/289 warnings; browser76 passed. Local full suite1265 passed/295 skipped/287 warnings. Independent review found no blocking finding.

Independent main run38053299552 has a failed browser job114216625329:30 passed/1 failed in384.16s, stopping at the existing violation Human-review workflow. Backend completion must be checked separately. Issue91 is not accepted or closed, and no chapter receives completion credit from this merge yet.

## Failure investigation, Issue96

`test_violation_candidate_measure_response_review_and_completion` receives409 at Human review, with `Rule/evidence/formal-procedure originals required for Human review`. `violation_service.py:source_snapshot()` raises that message solely when at least one persisted rule/evidence/procedure ID array is empty, before file hash, legal citation and effective-date checks. The violation backend, frontend and test are unchanged from847d793; PR head and merged main share the same tree.

The original browser helper verifies available options and clicks the picker, but does not check the resulting readonly ID input or saved candidate arrays. Missing selection, duplicate-toggle and asynchronous UI setup are hypotheses, not established root causes. The original enforcement must remain intact.

Failed artifact11670167625 was downloaded and inspected:76 files, predominantly earlier finance screenshots/logs/JSON and earlier module screenshots. It contains no failed violation DB, create payload or trace. Artifact ZIP SHA256 recorded by CI: `cb9f4f8c18136a1fb8ec65befe4987abaf2bbdc8333095a6ccedac1e44a23475`.

Local Playwright Python installation succeeded, but Chromium CDN downloads returned incomplete/zero-byte ZIPs and browser installation failed. This environment cannot currently supply an actual Chromium reproduction. Diagnostic PR CI must observe the actual input, POST and response values with synthetic fixtures. Never publish cookies, passwords or authorization headers. A green retry alone does not establish the cause or durable repair. Limit repair hypotheses to three, then revisit the design.

## Extracted-source installation and recovery rehearsal

The existing deterministic builder produced566 source files from the canonical commit above. The source bundle was verified before safe extraction. SHA256: `922dcc5721802ae1bca20b30e3dc7cd9e6b2082584b119caf4990b2c0b9a0900`. This is a development candidate with `production_ready=false`, not a final Release or authenticity claim.

In a new directory and a fresh virtual environment without inherited packages, `pip install -e 'backend[test]'` succeeded. The imported `app` path was verified to be the extracted source. A synthetic administrator was bootstrapped into a new SQLite DB, with a random password passed through standard input and omitted from evidence. Uvicorn bound only127.0.0.1, and real HTTP requests verified:

| Operation | Observed result |
|---|---|
| Health and DB / UI / teams asset |200 /200 /200|
| Unknown synthetic login / valid login |401 /200|
| Facility create / update |201 /200, version2|
| Stale version update |409|
| Failed-login audit |One anonymous failed event; submitted credentials absent|
| Logout / subsequent protected request |200 /401|

After the server stopped, `backup_phase1.py --destination <outside-storage>` made a paired SQLite-test-only backup. `restore_phase1.py <backup> --target-database-url <new-db> --target-storage-root <new-storage> --confirm-restore` restored into separate targets. `verify_restored_database.py` succeeded with one facility; direct verification confirmed the updated name/version2, retained anonymous failed-login audit, and byte-identical synthetic document.

This rehearsal proves only a synthetic SQLite localhost installation and separate-target restore. It does not prove production PostgreSQL migrations, LAN/TLS, external-network outage, completely offline dependencies, HA/fencing, immutable encrypted Owner Vault, new-PC disaster recovery, operational Human acceptance or full57-chapter completion. No GitHub Release was issued.

## Continuation and ownership

1. Complete Issue96 diagnostics and a reproduced root-cause repair; preserve original guards and run exact-head plus independent main CI.
2. Recheck canonical SHA/tree and acceptance evidence before closing Issue91 or adding its accepted ledger delta.
3. Stage logical lanes using the V2 ownership contract; maximum available workers is root plus six. Do not claim eight simultaneous workers.
4. Ready tasks: Issue94 explicit legal online-sync guard, Issue95 protected available-crew source projection, Issue97 common secret scan, Issue98 isolated dependency audit. All remain unimplemented.
5. Parent Issue93 tracks whole-system completion. Chapter42 remains Partial under expanded42.1; totals12 Completed/44 Partial/0 Missing/1 External Gate. Original four-lane PR90 remains unmerged and must be reconciled after stable main acceptance.

No production data, privileges, migration or site application is authorized by these synthetic diagnostics. Actual operational gates remain open.

## Subsequent observed base and selection-order repair, Issue96

The paragraphs above are the historical failed-main checkpoint. PR99 integrated diagnostic synchronization at main `75673ba67834255dde3674ff6e5627b5f04ca10f`, tree `19c488b225451f7c7f01d66a7e83024cded9d9fc`. Independent [main CI38060163414](https://github.com/haji84/-AI/actions/runs/38060163414) directly completed SUCCESS: backend1459 passed/101 skipped/289 warnings/812.23s; browser job76 passed/788.65s; migration parser and JavaScript syntax successful. Skips are unverified. This accepts the bounded anonymous failed-login and diagnostic changes, not chapter43, full-system release, or the original Issue96 causal mechanism.

An independently examined synthetic interleaving of the actual `shared-session.js` and `violations.js` shows that selecting a procedure first and submitting second can persist an empty procedure array when submit authority resolves first. Authority-gated events replay independently; the original picker has no pending-form lock. The original failed-main artifact still cannot establish which original array was lost or its exact timing. This reproducible product defect is a separately demonstrated repair target; diagnostic green alone did not remove it.

The committed Node regression uses actual product event capture, picker, form and ID parsing, with only synthetic DOM/server-authority dependencies. Five tests failed before runtime changes: incomplete save, stale-view paint, replacement-form paint, revoked old-form submit, and duplicate pending selection. The minimal fix reuses the shared preflight hook to lock only the current selection-dependent form controls while its authority probe is pending. The form independently rejects Enter/programmatic submits while selection is pending or ownership is obsolete. Picker replay checks view/form ownership. Original required-array/hash/effective-date/RBAC/Human guards remain unchanged; no migration or grant is added.

After the fix, all10 violation state tests pass. Focused violation/correction/shared-session regression:41 passed/1 skipped/30 warnings. The real Chromium workflow now holds actual authority HTTP requests, permits the submit response first, verifies no premature candidate POST, then releases selection and checks saved arrays plus the full Human workflow. It does not fabricate server authority or use a time-based sleep. Local native Chromium remains unavailable; exact PR CI and independent merged-main CI for this repair must still execute before acceptance. Full local suite evidence and independent review will be attached to the PR/checkpoint; chapter totals and Release readiness do not change from these local results.

## PR101 integrated and independently accepted repair

The preceding pending statements describe their earlier checkpoints. PR101
merged at exact repaired head `4d86676bd05df45927e3e0de6304348179974c0f` after
independent review and [CI38062677291](https://github.com/haji84/-AI/actions/runs/38062677291)
SUCCESS: backend1464 passed/101 skipped/289 warnings/863.06s; browser76
passed/609.53s. The initial native fixture cleanup failure was repaired once
by draining held routes before interception removal, preserving primary errors.
No original/Human/authority guard was changed or test skipped. Local full
runtime-tree regression completed1270 passed/295 skipped/287 warnings/388.29s;
local skips receive no native credit.

Main `adfede71a22e23f44faa6c53208a84cabcb433c5`, tree
`12358e2f14e554287e03d5a2aa36f5426a1ce4bc`, matches the PR head's tree.
[Independent main CI38063812901](https://github.com/haji84/-AI/actions/runs/38063812901)
SUCCESS was read directly: backend1464 passed/101 skipped/289 warnings/867.91s;
browser76 passed/746.16s; migration parser and JavaScript syntax successful.
Main artifact11674241561 was directly downloaded and SHA256 verified as
`4f456d8f50cb97eae25e903403e2303c31da861b42afa893013c7893852b5f53`.
The controlled authority ordering records `early-submit-rejected`, then
three nonempty matching request/saved-response original ID arrays and13
synthetic Human workflow POSTs, with empty page/artifact/cleanup errors.

Accept only this demonstrated selection/save race repair and the previously
accepted bounded failed-login/diagnostic deltas. The original failed-main
payload remains unavailable, so its exact lost array/timing is not asserted.
Issue96's historical investigation remains explicit. Chapter totals stay
12Completed/44Partial/0Missing/1ExternalGate; no Release, production or
full-system completion follows. PR90 is closed as superseded without merge;
main V2 governs staged eight logical lanes. Security97/98 and legal94 are
separate pending slices, with shared CI/ledger integration owned by root.

## Subsequent PR102 main regression checkpoint

Main `46865f438ab7a7482678c0ed720c15f00f113a65`, tree
`ccfe26ae18b34235cae81c6adf1804a38111c8bb`, adds only the bounded secret
CLI/hook/CI slice. Independent project CI38065202562 SUCCESS:
backend1486 passed/101 skipped/289 warnings/808.27s; browser76 passed/787.34s;
parser/JS successful. Dedicated main secret CI38065202530 reports findings0.
Downloaded native artifact11674113645 SHA256
`0010e560d4f1cc358c7c59d8a9af82aefd154846521bd28b43e596eb64eb7a60`
retains controlled early-submit rejection, three matching nonempty saved
original arrays,13 successful synthetic Human POSTs and empty page/artifact/
cleanup errors. D25 records the separate security acceptance and limitations.
PR103 legal enabled/online policy repair awaits its exact-head and independent
main evidence; Issue95 privacy RED remains unfixed. Chapter totals stay12/44/0/1,
with chapter42/43 Partial. Historical failed-main attribution remains unproven.
