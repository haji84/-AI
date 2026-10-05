# Phase 10 Unified Search Evidence

更新日: 2026-10-05

## Result

Latest Phase 10 UI checkpoint:
- commit: `9482d2fd83978446be236f696a30dccdaf117c43`
- GitHub Actions run: `37255300365`
- conclusion: SUCCESS
- backend pytest: 85 passed
- migrations 001-026 parser smoke: PASS
- frontend JavaScript syntax: PASS
- operational Python script syntax: PASS

## Implemented

Permission-aware unified search across:
- facilities
- inspections/findings
- submissions
- installed equipment
- drawing elements
- fire investigation cases
- accepted transcript evidence
- reviewed statement evidence
- accepted photo annotations
- legal documents
- legal Rules
- documents
- contracts
- form templates
- change requests/extensions

## Safety

- `search.use` permission is required.
- Module search is further restricted by each module's read permission.
- Explicit request for an unauthorized module returns 403.
- Fire transcript search includes accepted transcript segments only.
- Fire statement search includes reviewed statements only.
- Fire photo search includes accepted annotations only.
- Search results retain source IDs, navigation targets, required permission and evidence metadata.
- Raw search query is not written to audit log; only SHA-256 and query length are recorded.
- Emergency personal records are intentionally excluded from this Phase 10 slice.

## Search behavior

- deterministic lexical scoring
- bounded overall and per-module limits
- permission-filtered module selection
- provenance-linked navigation metadata
- UI supports global search and module filtering

## Not claimed

- semantic/vector search quality benchmark
- production-scale PostgreSQL query latency benchmark
- emergency-record search
- approved LAN physical-client search E2E
- production search index or FTS tuning
