# PR61 inquiry integration into canonical main

Canonical base: `027e1d025ea9947ca7ae2d0a015a943c297466f6`, main CI `37520767373` successful. Existing inquiry PR61 head: `a3d4e249662db83cabaaeec6fe6d124442d0fb1a`, based on `ecbd0a7d5e81bbf98100bee19c879df2ba892eac`. The existing implementation is integrated, not recreated. Binding rules: AGENTS.md, RUN_B_CONTRACT.md, task-6-brief.md. No subagents as required by task-6-brief.

## Bounded repair plan and evidence

1. Three-way merge the existing PR using its exact canonical base; preserve violations, finance safety, tenant binding, permissions, source checks and previous browser workflows.
2. Rename the unmerged inquiry migration to 050; canonical 049 violation migration stays unchanged.
3. Reproduce and repair the browser adoption/edit race. Keep backend version checks. Disable controls bound to an old version while mutation and reload execute; preserve controls already disabled by permission/state.
4. Run inquiry, shared integration and full regression tests, migration parser and JavaScript checks; publish onto the existing PR with an exact-head lease. Inspect exact-head CI, repair any failures, then merge and verify main CI.

Original inquiry CI `37519172683`: backend succeeded, browser failed (1 failed, 7 passed). Adoption candidate prose already contained the synthetic answer; checking that prose did not mean adoption/reload had completed. Old edit controls remained usable during the asynchronous mutation. The Node regression independently reproduced this actual UI defect: `1 failed, 1 passed` before repair, `2 passed` after repair. The test additionally checks that existing disabled controls remain disabled.

The main architecture remains common code with separate department DB, app runtime, originals and backups. No actual operational data is introduced. AI candidates remain distinct from Human draft adoption and Human formal approval. Numeric evidence and original source authorization remain mandatory.

This is integration evidence, not a whole-product completion claim. Exact final test counts, CI run/head and main merge evidence must be recorded after execution.

## Concurrent canonical PR refresh

The publish lease check found PR61 advanced to `8d015231a0253ae6bc73ca3a0fc021d4834e0c58`, based on current main027. No stale write was published. Its stronger pending-action controls cover dynamic source controls, close/reopen and late error ownership as well as adoption/edit. That existing correction supersedes the local minimal action-lock implementation. Local commit `4c350a3` tree `e4b054285da5ccca10337a44b4edcf416c62644b` is byte-identical to the refreshed PR61 source tree; synthetic local history must never be pushed.

Local preliminary integration full regression: 586 passed, 69 declared skips, 286 warnings in300.36s. This result precedes adoption of the concurrently refreshed controls and must not be attributed to the final remote head. Refreshed actual source focused regression: 33 passed, 1 native-PostgreSQL declared skip in32.95s. Exact refreshed-head browser CI37522253547/job112470351413: 9 passed in101.98s. Backend/native PostgreSQL CI still pending at this checkpoint.

Final refreshed-head CI37522253547 succeeded: backend/native PostgreSQL639 passed19 declared skips288 warnings in338.32s; actual Chromium9 passed101.98s. PR61 squash merged as main922d292c48fa0d7e4082432116e608825f6fe154, treee4b05428; postmerge main CI37523158483 SUCCESS. This is module integration evidence, not whole-product completion.
