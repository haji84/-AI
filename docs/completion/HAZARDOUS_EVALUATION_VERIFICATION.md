# Hazardous deterministic evaluation candidate — verification checkpoint

Canonical main at start: `be5185e53a5f126d6524bee1291d83a7e41fde92`, tree `3f56f3155343325c2d845fa5647ad23a66ad6618`.
Dependency: PR #82 hazardous Rule authoring, head `e4a1c1ecbf57b7bfeaede259c4f99e315ff4db32`, tree `d1c1fe35dfbd31d91006ab31db3a6980da93657b`.
This evaluation Slice is local and unmerged. Dependency CI run `37871180915` is still running at this checkpoint. No evaluation CI, actual PostgreSQL, or Chromium success is claimed.

Dependency backend job `113629410219` completed successfully on exact head `e4a1c1ecbf57b7bfeaede259c4f99e315ff4db32`: **1330 passed, 97 skipped, 289 warnings**, 484.42 seconds, followed by successful migration parser and JavaScript checks. Dependency Chromium job remains pending completion; this is not full dependency acceptance.

## Scope

- Dedicated candidate table and migration `057_hazardous_evaluations.sql`, separate from permits, violations and generic facility requirement decisions.
- Explicit active legal profile and evaluation date; only active, effective, Human-approved hazardous Rules within applicable jurisdictions.
- Compare current canonical Rule/source/citation evidence to immutable approval snapshots; verify originals and current original-specific permissions before exposing or mutating candidates.
- Independent material comparisons with exact decimal strings and explicit units. No unit conversion, heterogeneous totals, inferred legal categories or compliance completeness claim.
- Three outcomes: matched, not matched, unresolved. No available Rule/material means unavailable, never compliant.
- Bounded Rule/material/condition/evidence sizes. Shared audit contains evidence hashes; full facts, sources and Human reasons remain protected candidates.
- Separate Human review with literal acknowledgement, reason, optimistic version and active input/source/coverage checks. PostgreSQL protects saved evidence from update/delete; review never creates official decisions.
- Browser candidate history, explicit profile/date, comparison and exact citation/original trace, per-clause input/threshold/unit, independent Human review. Shared session, current rights and stale-view protections retained.

## Local evidence

- Initial API creation tests failed with missing routes, then passed after implementation.
- Empty-list rights regression reproduced unauthorized `200 []`; authority before listing fixed it.
- Known/unknown evaluation ID probe reproduced `403/404` after source-rights revocation; authority before detail/review fixed it.
- API plus actual JavaScript state tests: **39 passed, 1 native PostgreSQL skipped**, 29.69 seconds. The skip is not native evidence.
- Fresh isolated bootstrap: **1 passed**, 20.89 seconds; evaluation table registered before application import.
- Browser state suite before comparison-detail enhancement: **26 passed**, 6.44 seconds; delayed evaluation response is discarded on original permission loss.
- Independent review: no Critical issues; both Important findings (ID existence probe and native fixture missing explicit category) corrected. Independent API/Node run before these corrections: 38 passed, 28.49 seconds.
- Exact browser bootstrap and seed ran in fresh isolated subprocesses successfully; first run caught a missing synthetic storage directory and the fixture now creates it explicitly. This is fixture verification, not Chromium evidence.
- Comparison-detail enhancement: all **26 JavaScript state tests passed**, 4.44 seconds. Migration parser accepted **55 SQL migrations**. JavaScript syntax and diff checks passed.
- New Human-approved Rule coverage invalidates an old candidate and blocks review: **1 passed**, 10.83 seconds.
- Follow-up independent review approved both fixes, the native/browser fixture source and the threshold detail display; no remaining Critical/Important. Independent ID secrecy regression plus Node suite: **27 passed**, 14.42 seconds. Actual native execution remains pending.
- Broad focused authoring, engine, evaluation, Node, hazardous register/search and original-boundary regression: **152 passed, 40 skipped**, 154.24 seconds. PostgreSQL skips remain unverified locally. New coverage-change regression ran separately as stated above.
- Final evaluation API suite including four original/trust/citation/outcome drift rollback cases: **18 passed**, 31.44 seconds. Drift creates neither candidate nor shared audit entry.
- Module registration updated to v1.1.0, explicitly candidate-only, with no formal legal decision. Reseeding preserves department-disabled flags and evaluation GET/POST return 503. Regression **1 passed**, 7.52 seconds.
- Evidence size is checked before comparisons and incrementally before saving each result, preventing accumulation of an oversized final result set. Oversized-source test first reproduced unwanted 201, then related comparisons/registration/source-budget tests **3 passed**, 14.97 seconds. Independent final delta review found no Critical/Important; its two tests passed, 7.22 seconds.
- Updated API/Node suite: **46 passed**, 45.48 seconds. Additional result-growth test: **1 passed**, 7.37 seconds; comparison stops after two of four materials and saves no partial candidate/audit.

## Dependency merge checkpoint

PR #82 merged as `fc96af9dc6cd235487c5fe47ebf42d2b0553e887`, tree `d1c1fe35dfbd31d91006ab31db3a6980da93657b`, identical to its exact accepted head tree. Exact PR CI `37871180915` is SUCCESS: backend 1330 passed/97 skipped/484.42s, browser job 73 passed/706.14s, parser and JavaScript success. Artifact `11590374084` digest `73810fcf5d437ea42b39786face6c64554c6b787a3d805b4013bd415421ac9c1`.

Independent post-merge main CI `37872231434` is running, not yet accepted. The initial pending dependency paragraph above records the earlier local checkpoint. Evaluation publication waits for this dependency main verification; no chapter promotion yet.

Final dependency acceptance: independent main CI `37872231434` is **SUCCESS**, backend1330 passed/97 skipped/498.40s, browser job73 passed/751.64s, parser and JavaScript success. Main artifact11591396065 digest `d70f711b9706dab39de46447a807e748a6e106246070334738450a0fbc49fc86`. The running/pending statements above are historical checkpoints. Evaluation exact-head CI and native acceptance are still pending, distinct from its verified dependency.

## Required acceptance still pending

- Exact final-head review, broad regression, parser and JavaScript checks.
- Actual PostgreSQL baseline 056 → 057 upgrade/retry preserving existing facility, competing Human review `200/409`, one audit, immutable update/delete.
- Actual Chromium explicit profile/date → matching and incompatible-unit candidates → exact citation → separate Human confirmation → source permission revocation clears private view.
- Exact-head full CI, PR, merge, independent main CI and completion ledger reconciliation.
- Chapter 16/17 retain Partial until full specification is reconciled. No real policy approval, official violation/permit decision, real-original validation or ten-flow completion credit is claimed.
