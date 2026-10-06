# Department maintenance and automatic backup completion plan

Spec: SPECIFICATION section4 automatic backup/restore test; user-approved per-department DB/runtime/originals/backup contract. Canonical main00f128cdc includes PR45 signed legal updates. Run B operational modules remain independent.

1. Add PostgreSQL maintenance exclusion shared by every BoundSession transaction and exclusive server maintenance. Identity mismatch refuses before work. Normal runtime requests/CLI fail closed during maintenance; HTTP503 gives human retry guidance. Existing owner migration/restore still possible through explicit maintenance context. No live server commands run during development.
2. Add scheduled-backup orchestrator. Fixed slug derives own service names; preflight validates UUID/config/path/release, snapshots service activity, stops own app and configured own writer services, acquires DB exclusion, executes existing validated paired backup, releases exclusion, restores only previously active units. Refuse overlap, unknown/wrong department, unsupported live targets. No automatic data/backup deletion.
3. Generate per-department backup service/timer and writer-sync service configuration. Linux/systemd timezone-aware schedule; scripts fixed and protected env files; root orchestrates service stop but backup uses dedicated department credentials. No cross-department inferred paths. Explicit administrative registration of other writers required.
4. TDD fake service order/failure/restart/own scope and real disposable PostgreSQL shared-vs-exclusive/race/identity tests. Migration/restore/backup keep existing safety confirmations and evidence. Full tests, browser/PG CI, review, PR/merge.
5. Publish backup/operator/manual recovery acceptance details and remaining External Gate. Continue final package and remaining Missing/Partial; this plan does not end overall completion task.

Ruling: automatic backup will not simulate stopped writers with a flag. Service stop plus database exclusion protects standard runtime/CLI; administrator-level bypass tools remain serialized maintenance operations. Recovery never auto-runs from a timer.
