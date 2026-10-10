# Controlled violation routes — callback readiness

Parent #93, issue #109. Runtime frontend, original/session/Human guards and
native assertions are unchanged.

Draft crew PR108 head97107af native CI38068057368/job114259644451 passed30
then failed the existing controlled selection ordering fixture at `held>=2`:
only one route callback had appended to the Python list. It failed before any
save POST. Artifact11675712268 was directly downloaded and SHA256 checked:
`fa508a7e793646c0935ce9e27e20a1d8d75419a75be9f296308561d7e766efd6`.
Its violation diagnostic records selection-held, no mutation network entries,
and no page/artifact/cleanup errors. This failure does not identify a defect
in the unrelated four-path crew change or the historic saved-array failure.

Request notification can arrive before the corresponding interception
callback. The fixture now publishes only a numeric browser marker after
appending each actual held route. Before inspecting the count/continuing the
submit response first, wait for both real callbacks to have appended. Keep
the original count assertion, early-submit replay/rejection, no POST while
selection is pending, nonempty matching saved arrays and cleanup safeguards.
This is callback readiness, not synthetic completion of an authority response.
No route is bypassed, no assertion or timeout relaxed, no retry or skip added.

Python syntax passed; actual-JS finance/hazardous/violation regressions passed
53 tests in4.07s with explicit worktree PYTHONPATH. The native controlled
callback path still requires exact changed-head
CI, independent review and post-merge main evidence. Diagnostic GREEN does not
establish historical failure attribution, full chapter or Release acceptance.
