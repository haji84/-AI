# Workforce search current-source boundary

Canonical main PR85 e617b7b/treeaaa0517 is accepted; exact CI37878688575 and independent main CI37879825992 SUCCESS (1382 backend/99 skipped;75 browser-job; parser/JavaScript). Exact source-navigation PR86 is a separate unmerged dependency. Publish this search delta only after that dependency's exact/main acceptance and fresh actual remote parent/tree equality.

Audit reproduced risk: common workforce search currently selects employee names and roster notes with workforce.read alone, without personnel.read, current original rights or module disable. It limits candidates before source filtering and opens the generic workforce page rather than the exact original. Close these existing source-boundary gaps without granting privileges or changing Human decisions.

1. RED actual HTTP search with baseline individual rights missing, protected original revoked, disabled module and an inaccessible early row occupying a limited page.
2. Reuse current workforce original closure and configured module boundary before projection/count/limit. Current actor/session rights must be verified again before private response release. Preserve historical inactive employee rows.
3. Reuse closed read-only source navigation in the shared search shell; owner-based late response protections and current permissions are retained. No server URL/function dispatch, no Human business mutation from search.
4. Independent review, existing search/source/Node regressions and actual Chromium protected query→exact source journey; exact-head CI, merge, independent main and evidence carry-forward.

Chapters7/25/34/35/43/45/48 remain Partial. No ten-flow/release/production completion claim, no new migration or permission grant.
