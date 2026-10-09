# Workforce observed statistics continuation

Accepted dependency checkpoint: PR84 is merged as maina3ae2e37b2bebba95bd107c8abe5ee6501b51d59/tree9c5c3fdd545657f88b2ad715cecd51ba3bc30ee6. Exact CI37876067326 and independent main CI37877280792 succeeded. The pending sentence below records the initial planning checkpoint; workforce delta remains unmerged.

Base dependency: PR84 head69257631649831f47fc1d408966b6a59e1aea8d5, tree9c5c3fdd545657f88b2ad715cecd51ba3bc30ee6, native CI37876067326 pending. Publish only after dependency merge/main acceptance with actual-parent tree identity. Current canonical main07b8545 already independently accepted. No migration.

§34 explicitly requires workforce as a source. Add bounded approved-roster counts, approved attendance worked minutes and approved overtime minutes, using stored explicit DATE and integer minutes. Exclude draft/review/cancelled and distinguish unavailable minutes from observed zero. Historic employee retirement does not erase past activity. These are observed records, not salary/allowance or complete headcount/populations.

1. RED selector tests for explicit period boundaries, approved-only, zero/unknown coverage, missing minutes, private lineage and source-change fingerprints.
2. Add closed catalog/schema metrics, aggregate/export rights and read-only selectors; old seven metric semantics remain identical. Disabled workforce flag fails closed for new capture/release.
3. Actual API aggregate-only save/confirm/replace/export and source-right revocation; source pointers require separate workforce/personnel/original rights. No private row/name/reason in aggregate or audit. Existing frontend catalog renders new metrics; no forced unsafe navigation.
4. Existing statistics and workforce regression, independent review, native PostgreSQL/coherent snapshot and Chromium actual query/report/export; exact-head CI → merge → independent main CI/evidence → next internal slice.

Full annual reports, official templates, populations, other module adapters, safe workforce pointer UI navigation, ten canonical E2Es and chapter34/36 completion remain internal requirements, not External.
