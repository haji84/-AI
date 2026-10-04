# Phase 5.1 Legal Source Registry Test Evidence

更新日: 2026-10-05

## CI

GitHub Actions run for commit `8024d4ba77d048a75ffd73eee2aafb2bd6742367`: SUCCESS.

Verified:
- Phase 0-5 regression suite
- legal jurisdiction create/list
- fire-department legal profile create/list
- profile-to-jurisdiction attachment
- national/local legal source registration
- unknown jurisdiction rejection
- RBAC for legal source read/manage/sync
- Migration 009 parser smoke through project-checks
- frontend JavaScript syntax regression

## Implemented in Phase 5.1 core

- `legal_jurisdictions`
- `legal_profiles`
- `legal_profile_jurisdictions`
- `legal_sources`
- `legal_source_documents`
- `legal_source_document_versions`
- `legal_sync_runs`
- `legal_update_candidates`
- source legal-document Version link for legal Rule Versions
- source/profile registry API
- national/fire-department/local jurisdiction separation
- online/bundle/manual update modes
- content scope and sync frequency metadata

## Not yet claimed complete

- e-Gov live collector
- e-Gov bulk initial bootstrap
- e-Gov daily delta import
- local regulation-site vendor adapters
- browser-based official regulation collector
- official promulgation-page collector
- signed closed-network Update Bundle
- automatic rule impact analysis from real legal amendments
- real fire-department ordinance full-corpus import

These remain the next Phase 5.1 implementation slice and must not be reported as completed until executed.
