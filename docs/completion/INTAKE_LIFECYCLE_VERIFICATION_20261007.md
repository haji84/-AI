# Document intake lifecycle verification

Base: `c1b684c5c38fc52fe908d2116a21a16ef48dcb34`. This is a bounded repair toward Specification §54(2), not whole-product completion.

## Behavior

Human review, receipt confirmation and an explicitly accepted facility change now consume an atomic revision of the same analysis. A receipt-confirmed analysis cannot be reviewed or confirmed again. A later review supersedes earlier pending proposals, preserving their original target and change evidence even when the new review has no differences. Application rejects a proposal that no longer matches the current review. Conflicting or invalid transactions roll back their receipt, link, proposal and facility side effects.

All four intake mutations revalidate current session and permission through the existing mutation guard. Original document bytes and audit history are preserved. The existing browser prompt flow stops on cancelled or invalid facility selection and cancelled official number; an explicitly empty official number is still allowed.

## Executed local checks

- The new integrity tests first reproduced repeated receipt, stale proposal, lost review evidence and queued authority defects. Additional stale-transaction tests failed before application consumed the analysis revision.
- The actual browser prompt function is exercised in Node. Five cancellation/index cases failed before the shell correction; all seven contract cases pass afterward.
- Complete local backend suite: **706 passed, 138 skipped**. The skips include PostgreSQL and actual-browser gates; they are not passing evidence for those environments.
- Independent lifecycle review found no significant backend issue. JavaScript syntax and whitespace checks passed.

## Required CI gates

The existing CI PostgreSQL service executes nine real transaction-interleaving cases, including exactly one HTTP receipt winner and no orphan document/specialized receipt records. Explicit barriers exercise the lifecycle compare-and-swap independently of the global authority lock.

The browser job explicitly includes `test_intake_browser.py`. Its ten Chromium cases cover original upload, analysis, Human selection, receipt, address-only application, unified search, cancellation, failed-upload retry, stale facility version and shared-session changes. Browser results must be read from the exact PR head; these cases were not executed locally.

## Remaining internal scope

The existing native prompt chain has no resumable review screen. Searching a facility-linked original currently opens the facility because the shared search routes `building_id` first; the acceptance test separately verifies original bytes through the supported download API. This repair does not redesign those shared adapters, implement stranded work, or complete every §54 flow. No database migration, real operational data, legal rule, deployment or new access is included.
