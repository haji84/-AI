# Finance queued-write and shared-PC safety

Canonical prerequisite: main7b320db1788008377250726dd6982455d29413ab, PR53. Finance implementation remains PR55; this slice extends its safety checks, not its accounting policy.

All financial POST/PATCH routes acquire the existing transaction account-change lock before financial service locks and revalidate the originating cookie session, active employee/account, password expiry and current permissions. Secondary service permissions run under the same lock. Existing Human review, source hashes, Decimal precision, immutable journal and optimistic versions remain in force. This deliberately serializes Human mutations within one department runtime; production throughput still requires approved-host measurement.

The finance browser surface validates identity, clears modal/drafts/cache on401/403/identity or permission loss, rejects earlier-generation responses and guards export downloads. Losing financial access clears previous budgets even when contract access remains. The remaining permitted surface can reopen after refresh. Attachment downloads retain server document RBAC.

Synthetic evidence: four queued revocation tests failed with201 before repair, then passed; combined financial API regression51passed1skipped43warnings51.59s. Actual Node JavaScript authorization/late-response/read-loss reproductions failed before repair; final five focused tests passed0.46s. No real financial information, official policy or operational host was used. Full CI and merge evidence must be recorded before completion of this slice.

Prerequisite PR53 exact head334b3246937b3d3308e70f1ac2e3d857990f5357: CI37509352367 succeeded, PostgreSQL-enabled backend546passed14skipped249warnings198.43s, seven Chromium cases succeeded. Squash merge7b320db. Main CI37509992617 was still running when this report was opened.

Main verification subsequently failed its workforce browser test: an in-flight warnings response correctly received401 after logout and erased navigation before the test's next click. PR58 changes only the test to invoke the same protected attendance handler regardless of prior clearing. Exact head21279dcd34871303c077142ebb6cb8a52704b63b passed CI37510513248, including seven Chromium cases69.47s. Merged main386582ceeade254aec70fd0adb633b597fda6148 passed CI37511281181. No clearing or authorization checks were relaxed.

One fresh gpt-6-astra review found four Important gaps, all repaired in one pass: legacy common-contract writes now use the same guard; completed API/blob responses revalidate identity; all document anchors inside the finance surface use a guarded download; compound financial/contract menus and contract action controls require their route/service permissions. Synthetic RED evidence: four legacy cases6.50s and four browser cases0.83s; download-time expiry follow-up also failed before repair. Final focused19passed9warnings9.26s. Native Chromium financial workflow now additionally follows a source link after logout and requires private modal/cache removal.

Deferred Minor: a queued financeAction after modal deletion may reject on its missing message element before its try block. Private state is already erased; defer this handler polish to shared-shell UX completion. Node harness removal fidelity does not represent full DOM deletion; native Chromium assertions supplement it.

Review rulings: PostgreSQL/concurrency and Chromium require exact-head CI before merge; production contention/host acceptance remains an External Gate; unrelated canonical modules remain subject to the completion matrix, not this bounded finance review. No production load or real-original acceptance is claimed.

Final local full suite after the one repair pass:519passed60skipped256warnings234.04s. Node syntax and git diff checks passed. Exact-head PostgreSQL/Chromium CI and subsequent main CI are still required.

Initial financial PR59 headb9bbdbbe/CI37512355890 exposed a separate workforce view race: attendance loaded, then the initial roster response overwrote its Human controls. Backend sources were unchanged. Actual-JS reproduction failed before repair; added view generations to all workforce screens, rejecting superseded responses before rendering. Combined workforce/finance actual-JS suite17passed2.17s; syntax/diff checks passed. PostgreSQL/Chromium rerun on the new exact head remains mandatory. No wait-only test workaround and no weakening of Human controls.
