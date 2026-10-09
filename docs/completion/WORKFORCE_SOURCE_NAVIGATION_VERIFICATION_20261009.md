# Workforce source navigation — implementation checkpoint

This additional Slice is not accepted main evidence. Dependency PR85 is accepted as main e617b7be/treeaaa0517: exact CI37878688575 and independent main CI37879825992 SUCCESS (backend1382/99 skipped; browser-job75; parser/JavaScript). Its main artifact11594855031 SHA256 is d2c18c85f71afed52ff04bc56a2f4962726e2df0cf6d83b018353021886bf7b3. Chapters25/34/36/45/48/54 remain Partial; this source delta still requires its own exact/main native acceptance, not ten-flow or release acceptance.

## Scope

The closed statistics source surfaces open the exact roster, attendance or time entry in the existing workforce modal. Current employee information and source version are displayed as read-only current evidence, not frozen report values or formal salary decisions. No Human approval controls, database migration or permission grants are added.

`workforce_source.py` follows current attendance/roster/original lineage. Individual workforce/personnel rights precede record lookup; current typed/transitive original rights are required independently of aggregate permission. Historical inactive employees remain readable. An inaccessible original returns the same 404 as an unknown record. Module disable prevents detail release. Responses use no-store; read audit contains kind/version and an opaque reference hash, not employee names or record notes.

After payload construction the endpoint checks the originating session, current permissions, original closure and record version again. Concurrent loss blocks both private response and read audit. Normal workforce requests and source requests retain separate generation/view ownership; obsolete successful bodies and obsolete 403 errors cannot erase or repaint a newer Human view. Existing Human controls remain unchanged.

## Local verification

- New inverse Node regression first reproduced obsolete normal GET403 closing a newly displayed source; the generation/view catch fix makes it cancel instead.
- Late payload permission/session/version changes first reproduced three200 disclosures; final release checks now return403/401/409 respectively, without read audit.
- Combined actual API/Node workforce source, existing workforce state, statistics state and observed workforce statistics: **70 passed / 1 native skipped, 28.06s**.
- Fresh isolated full application bootstrap and authenticated HTTP reads for all three exact source kinds: **PASS**. This verifies actual route/module registration, not Chromium.
- After adding native PostgreSQL cases, source API rerun: **7 passed / 3 native skipped, 12.98s**. Held-request browser synchronization waits for the actual route callback, not a fixed delay or a fabricated response.
- Independent review after both fixes: **48 passed / 1 native skipped, 22.71s**, no remaining Critical/Important; git diff check passed. This independent run preceded the additional three native PostgreSQL parametrizations.
- Native PostgreSQL tests use the fully migrated disposable database and a separate writer after payload construction. Chromium journey uses actual statistics→exact source→close and a held actual HTTP request interrupted by the normal workforce view. Both remain unexecuted locally; skips receive no acceptance credit.

## Remaining acceptance

Exact remote parent/tree equality, complete exact-head CI, merge and independent main CI remain required. Actual PostgreSQL/Chromium success and artifact digest must be recorded after execution, never inferred from local tests. Broader all-module statistics/populations/forms, dispatch/workforce linkage, queue providers, ten canonical E2Es, deployment profiles and installable release remain internal requirements. No real personal data or original document was used.
