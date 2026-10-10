# Revoked finance upload — native fixture correction

Parent #93, issue #107. Canonical implementation base46865f4. Runtime code,
session/original/Human guards, assertion timeouts and CI test selection are
unchanged.

## Actual RED and causal evidence

PR106 first diagnostic head `37bfd8b09240585366f23c2077df299b0971426b`
native CI38067038647/job114256675125 passed the hazardous journey, then
failed `test_finance_permission_loss_before_upload_is_authoritative`:
Locator.click waited30s for `financePick_document_id_upload` after replacing
the editor login with the reviewer login. Browser summary18 passed/1 failed
in326.85s. This is not an upload success or a product authorization bypass.

Artifact11676080002 was directly downloaded and SHA256 checked:
`597e2d786189f4f57719ec49f88e1f20d779d07c4c8175fe0a3cd5a28d9d23f4`.
Its exact failed-case JSON reports144 requests and responses, no pending
responses; the final auth/context401 is followed by UI reset around2.457s.
The finance identity is null, permissions/view are cleared, modal count0,
pending action false, and no upload action or POST occurred. The fixture
incorrectly demanded that the old button remain locatable after this already
safe asynchronous reset.

## Minimal correction and stronger assertions

Before replacing the session, wait for the real rendered upload control to
be enabled and retain its actual onclick handler, which captures the original
form/picker ownership. Replay that handler after replacement in both normal
timing and a controlled prior real SharedSession authority observation. The
pre-observed case must already have closed the modal. Both cases must reject
the stale action, emit no upload POST, leave identity/permissions cleared and
keep the private finance document list empty. Existing actual button-click
tests elsewhere still exercise document session preflight; this bounded test
explicitly exercises stale rendered action rejection even after DOM removal.
No conditional skip, timeout increase, retry, handler substitution or runtime
permission change is introduced.

Python syntax passed; the existing actual-JS finance/hazardous suites passed
43 tests in3.89s locally with explicit worktree PYTHONPATH. Exact changed-head
native CI and independent main CI remain required.
The older interrupted/failed CI cannot be credited as final acceptance.
This finance fixture correction does not establish the historical hazardous
loading cause in #105; diagnostic GREEN must not close that investigation or
grant chapter, environment, formal law or Release acceptance.

## Corrective hypothesis2 — capture must return no function

Changed head1c580a8 native CI38067965756 still failed the normal-timing
case (18 passed/1 failed in268.80s). Downloaded artifact11676126020 SHA256
`ad0ceb976683f4e6cf733c5d45df5536a98f8efd47e1d4fe86dc18476bcbbfda`
showed an original already uploaded and selected before session replacement.
The function-valued assignment passed to page.evaluate was executed during
capture, emptied the chosen file, and made the later stale call a no-op.
This was a defect in the first fixture correction, not a runtime change or
an authorization bypass after replacement.

Use an explicit zero-return callback to store the original handler without
calling it. Install the POST observer before capture and assert capture itself
emits no POST. Retain both stale-replay cases and all rejection assertions.
The first corrected-head failure is not accepted; only the final changed-head
CI can validate this repair. No unchanged rerun or skipped case is used.
