# Workforce search exact source — unmerged checkpoint

Canonical dependency PR86 is accepted as main a2586a6a8d4426e3f79966f437a3bb6e46161fee/tree db2d44c136cdcf9accc948ad937871cca839f29c. Exact CI37882703445 SUCCESS (backend1400/99 skipped/783.07s; browser75/765.16s) and independent main CI37883890162 SUCCESS (backend1400/99 skipped/774.84s; browser75/716.32s; parser/JS). Main artifact11595692705 SHA256 f659fa647874a323f42324f163cf09ab68adf6f5cd77cd1870fc52927ccdc969. D18 carries original D17 evidence. This search delta remains unmerged; its own native/main acceptance is pending.

## Existing gaps reproduced and scope

Actual HTTP RED2 returned employee names and roster notes with workforce.read alone and returned an inaccessible protected newest row within limit1. Search now additionally requires existing personnel.read, reuses current typed/transitive original rights before projection/count/limit, and checks the current workforce module configuration. It retains historical inactive employees, selects visible records past inaccessible early candidates, and returns the closed exact roster source pointer rather than a generic workforce page.

After source search completes, the endpoint expires cached state and verifies the originating session, current search/individual rights, original closure and source version again. Lost baseline rights/session or changed source version deny release without accepted query audit; inaccessible original or disabled source removes its private hits before response counts. Query audit remains hashed and excludes raw query, names and notes.

Independent review also reproduced an existing missing response cache policy:200 containing private names had no Cache-Control. A further RED2 confirmed both200 and403 lacked the header. Search-limited PrivateSearchRoute now sets no-store for successful replies and preserves existing HTTPException headers while adding no-store for rejection. No new privilege grant or formal decision policy is introduced.

The shared search shell calls a closed exact-roster handoff. Source generation, current session, header/navigation interruption and workforce modal ownership reject obsolete body/403 effects. The source screen remains read-only, with fresh rights, version and current employee data; no Human approval controls or source data copies are added. Current source errors clear old private results and return to search only while the handoff owns the view.

## Local evidence

- After merging the independently accepted source navigation test repair, exact source/search API and Node handoff rerun: **27 passed / 8 native skipped,26.60s**. Native skips receive no acceptance credit; protected search Chromium/PostgreSQL must execute on this delta's own exact and main CI.

- Initial authorization/original/limit regression:2 failures8.02s, then2 passes6.71s.
- Source/query/state suite:26 passed /8 native skips22.59s; independent first focused run26 passed /8 native skips38.56s. The latter identified the existing no-store gap; it is not final acceptance of that repair.
- Header RED2 failed6.58s; repaired header regression2 passed7.72s.
- Dependent new_human_error Node regression reproduced old403 reopening the search modal over newer Human content. Source detail now cancels obsolete errors before caller recovery; source/search Node13 passed2.97s. Final independent search/source/hazardous review **32 passed /12 native skipped32.77s**, no remaining Critical/Important; separate independent source38 passed/3 native skipped21.33s. Source assertion fix is carried by dependency PR86.
- Existing workforce/search/hazardous API regression21 passed /4 native skips40.10s. Existing workforce Human/state/statistics plus new handoff Node regression66 passed12.02s. Existing whole-module/reviewed-fire unified search regression2 passed8.81s.
- Inline and all frontend JavaScript syntax and git diff check PASS.
- Native PostgreSQL tests use all migrations and a separate writer for session, individual permission, original permission, version and disable changes. Extended actual Chromium journey opens the exact roster from common search and checks readonly content/version. Both are unexecuted locally; native skips are not PASS.

## Required continuation

Final independent review, dependency acceptance, actual remote parent/tree equality, exact-head full CI, merge, independent main CI and artifact digests remain required. Chapters7/25/34/35/43/45/48 stay Partial. All-module source/search/work queue coverage, workforce work results/dispatch linkage, ten canonical E2Es, deployment profiles and installable release remain internal work. No production or real-data acceptance is claimed.
