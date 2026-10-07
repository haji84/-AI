# Personal work list: scope and verification

Base: `c1b684c5c38fc52fe908d2116a21a16ef48dcb34`. This adds a first usable Specification §36 flow. The full chapter remains Partial.

## User flow and permissions

After login, 今日の作業 shows authorized asset deadlines/loan returns, fleet deadlines/faults, corrective-action deadlines and inquiry draft/review work. Users can choose 自分が作成・借用したもの, refresh, paginate and open the existing source detail screen. A newer facility choice takes precedence over delayed automatic Home initialization, and delayed facility loading cannot overwrite a newer Home selection.

The endpoint is read-only and creates no duplicate business records. Counts and pagination follow source permissions, transitive inquiry evidence permissions, module flags and relationship filters. Source IDs and versions identify the underlying records. Creator, borrower, role work and shared deadline labels are distinct; a creator is never presented as an assignee. No general assignment table or assignment inference is introduced.

Dates use the existing asset business-date policy (Asia/Tokyo by default). An undated review item has no invented deadline. Providers are read sequentially under ordinary transaction isolation; the response is not an atomic snapshot across all business modules.

## Verification

Backend tests first failed on the absent endpoint. The source/permission suite includes mixed permitted and forbidden modules, borrower privacy, honest relationships, source retirement/closure, version/date changes, flags, horizon edges, stable pagination and unchanged business row counts. A real restricted inquiry source added between authorization boundaries initially leaked a card; the final closure is now rechecked before emitting any title, ID or count.

The UI tests exercise the real shared-session guard and shell API, escaping, empty/error/loading states, page/scope changes and discarded late responses. Additional navigation regressions cover a removed/replaced source modal, Close followed by reopen, newer module actions during authority checks, and late login initialization.

The dedicated Chromium journey covers a limited-role login, permitted cards, forbidden transitive evidence, source navigation/close, source changes, recoverable API errors and session/permission changes. Actual Chromium execution is a CI gate and was not run locally. PostgreSQL execution is also a CI gate; local SQLite coverage is not PostgreSQL evidence.

Local final integrated backend suite: **743 passed, 92 skipped** (194.81 seconds). The skips include PostgreSQL and actual Chromium gates. Targeted API/UI/shared-session regressions: **77 passed, 1 PostgreSQL skip**. Independent backend review and final UI re-review found no remaining significant findings. All 49 migration files parse, all frontend JavaScript passes syntax checks, and whitespace checks pass.

## Remaining implementation

General assignment, additional providers (including finance, workforce and statistics), full common-dashboard coverage and remaining Specification §54 flows remain internal work. Stranded workforce/statistics source is not included. No migration, legal threshold, AI execution dependency, distributed PC worker, production deployment or new persistent access is part of this slice.
