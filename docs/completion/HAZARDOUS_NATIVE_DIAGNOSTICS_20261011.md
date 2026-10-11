# Hazardous native loading failure — bounded diagnostics

Canonical implementation base: `46865f438ab7a7482678c0ed720c15f00f113a65`,
tree `ccfe26ae18b34235cae81c6adf1804a38111c8bb`. Parent #93, investigation #105.

## Observed native RED

Legal PR103 exact head `0a4a9cb863d8d1cd42c93743ba9f7e79d7db38e5`
ran project CI38066189526. Existing browser job114254204634 failed
`test_hazardous_browser.py:302`: after synthetic source-right revocation,
restoration and re-login, installation detail stayed `読込中…` instead of
rendering `変更履歴` within the existing5s assertion. The preceding name
assertion can match the old list row before guarded click redispatch.

Failed native artifact11674759137 was directly downloaded and SHA256 checked:
`730f336d163faed5be75c2f7876c649229da03c721fc59b77132159bfede00fa`.
It contained only two earlier screenshots, not the failing request or DOM
trace. Main468's earlier independent browser job76 passed with the same
hazardous frontend. The exact failed mechanism is therefore not established;
the unrelated two-line legal policy guard is not identified as its cause.

## Controlled actual-JS diagnosis

A separate read-only agent used canonical `shared-session.js`, `hazardous.js`
and existing synthetic harness behavior. Holding each of12 serial authority
responses showed old list at stage1 and loading at stages2–12, with valid
ownership and no session reset. Releasing each response rendered history;
all12 probes recovered. The nominal click traverses12 auth/context calls,
two permission GETs and one detail GET. This reproduces the visible symptom,
not a failing product invariant or proof of historical latency. No product
repair is justified solely by these probes.

## Diagnostic change and acceptance limit

The existing native journey now records its stage and the last512 request
lifecycle events for authority context, permission and hazardous scopes.
On failure, while Playwright is still alive, it saves pending request ages,
view/session generations, permission count, loading/modal state, bounded
synthetic content and page errors, plus a failure screenshot. Network records
contain only scope/method/status/time: no URLs/query strings, bodies, cookies,
credentials, authority payloads or session identifiers. Evidence uses the
existing dedicated synthetic browser artifact directory. Diagnostic errors
cannot replace the original failure. The original assertion/5s timeout,
session and original guards, test selection and CI workflows are unchanged.

Python syntax passed; the existing actual-JS hazardous state suite passed
28 tests in2.02s with explicit worktree PYTHONPATH. Actual Chromium execution
requires exact-head native CI. A diagnostic
GREEN is not resolution of #105. A future RED must be inspected directly;
any causal repair needs its own controlled RED, smallest change, regression,
independent review, exact-head CI, independent main CI and ledger evidence.
No chapter, law interpretation, environment or Release credit is claimed.

The first diagnostic head37bfd8b native CI38067038647 passed the hazardous
journey but stopped at a separate finance stale-upload fixture failure.
Issue107 and [its causal evidence](FINANCE_REVOKED_UPLOAD_FIXTURE_20261011.md)
record that correction independently. This observed hazardous GREEN is not
resolution of the original loading failure.

## Causal RED after dependency-gate integration

Independent main project run38111138927 at commit
`91ad92a22a84b3e3e3711706da44e314bb612201`, tree
`4d89032f3afed8a8c1bd9058dcbc33c51d426dd6`, reproduced the same native
failure in browser job114386775997 without a rerun. Artifact11692190291
contains the new bounded failure JSON and screenshot. The final click issued
the guarded list GET in13ms and then the installation-detail GET. That detail
request returned HTTP200 only after4836ms. The unchanged5s assertion fired
while the page still showed `読込中…`; diagnostic capture then observed the
completed request, no pending/page/diagnostic errors, loading false and the
correct history. This classifies the failure as server detail-read latency,
not a lost request, rejected authority, stale owner or missing render.

A focused synthetic service RED created two source-backed revisions and
counted only calls made through the hazardous service's current permission
resolver during one detail request. The unchanged implementation performed
485 identical permission-set queries and took5.36s including fixture setup:

```text
assert calls == 1
E assert 485 == 1
```

The amplification comes from correctly traversing every current and
historical source, but re-querying the same user's unchanged permission set at
each nested guard. The bounded repair snapshots that set once only while a
single detail request is assembling its response. All document, legal source,
inspection, violation, revision-lineage, original-byte/hash and history
visibility checks still execute. The snapshot is removed in `finally`; other
requests and all mutation paths continue to resolve current authority in the
existing way. Separate-request permission-revocation coverage remains part of
the regression. Native exact-head and independent-main CI are still required
before this section can claim accepted GREEN or close #105.
