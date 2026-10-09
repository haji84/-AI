# Draft checkout and explicit Human cancellation

## Scope and canonical dependency

Canonical accepted main is 70953bab88116318cf9f69342be39361c75da4d8/tree3a81c1b7b7aac271019f83cdc79b2b72e4dfd228 (PR87, D19). PR86 source detail and PR87 protected common search have exact-head and independent-main acceptance. PR87 mainCI37886725333: backend1417 passed/99 skipped/798.48s; browser75 passed/778.63s; parser/JS SUCCESS. Main artifact11596498778 SHA256313d699e72e75bf0b16187d4fe521aa92f4c6c082b6288ba1449bd8683333f95. This checkout delta is local, not accepted main and not deployment approval.

The browser connects existing draft-only attendance PATCH and reasoned draft/reviewed cancel APIs. No migration, grant, automatic approval or payroll policy is added. Approved records remain immutable. Draft checkout keeps expected_version and explicit Japan time independent of the browser timezone. Existing seconds and fractional seconds are preserved; text timestamp fields avoid browser datetime-local precision truncation. Human transitions remain separate actions with reasons and current permissions. Pending transitions lock both Human and draft-edit controls; obsolete handlers and navigation during authentication cannot send old drafts.

## Verification evidence

- Draft-only edit controls, expected-version checkout, duplicate click and obsolete-handler regressions: initial genuine RED 3 tests (missing edit control), then PASS.
- Separate cancellation regression: missing cancel control RED; cancellation sends expected_version and explicit Human reason once. Approved records have no edit/cancel controls.
- Edit-control lock during pending Human cancellation: genuine RED, then lock plus current-permission restoration PASS.
- Authentication/navigation regression with the actual workforce API wrapper: remove the new pre-send view check and the old draft writes after navigation (RED); restoring the check cancels before PATCH.
- Timestamp regression reproduced minute-only truncation of `37.123456` seconds; explicit seconds/fraction formatting now preserves it.
- Combined actual frontend scripts and existing workforce Human/state, statistics, source and search Node tests: **81 passed, 18.33s**. Shared synthetic DOM now parses all data-attribute controls and comma/prefix selectors, so actual Human buttons and readonly absence are exercised instead of ignored.
- Actual Chromium continuation is extended: America/New_York browser; stored open attendance; Japan-time checkout PATCH; version increment; 480 minutes from the fixture's already Human-approved rule; separate review/approval; no approved edit/cancel; reasoned draft leave cancellation; existing stale-rule and logout checks. No response fabrication. **Not executed locally; native CI remains required and receives no credit yet.**
- Python compile and diff checks PASS. Independent review, exact remote tree, all CI, merge and independent main CI remain pending.

Independent checkout review at4161485b/tree72f7298 found no Critical/Important; **81 passed,16.03s**, diff/JavaScript syntax PASS. Its Minor refresh-failure concern now has a genuine RED regression and accepted-update-specific recovery message. Final combined Node rerun: **82 passed,19.39s**. A fresh isolated full application bootstrap using the native fixture's actual seed also exercised actual checkout PATCH, Human review/approval, approved PATCH409 and separate draft leave cancellation: **PASS**; this HTTP exercise is not Chromium acceptance. Updated delta review and native exact/main CI remain required.

## Internal remainder

Final delta review exercised 7 tests PASS/1.52s and closed the accepted-update recovery concern with no Critical/Important findings. Exact remote CI and independent main acceptance are still required for checkout/cancellation; local native-test skips receive no execution credit.

Chapters25/45/48/54 remain Partial. Teams/work results, roster-to-dispatch-to-work-result/overtime/allowance linkage, balances and expiry reconciliation remain internal. Real institution rule values and real production acceptance require Human approval. No canonical ten-flow E2E or release completion is claimed.
