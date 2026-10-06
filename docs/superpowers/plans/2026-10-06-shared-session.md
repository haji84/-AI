# Shared Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans, native implementation with one fresh whole-branch review. Steps use checkbox syntax.

**Goal:** Prevent old private responses and cached actions from surviving a session or permission change in the shared shell.
**Architecture:** One no-store authority context endpoint; one shell fetch/body/event guard reusing current auth, permission and renewal behavior. Reset cached private DOM/data on invalidation.
**Tech Stack:** Existing FastAPI, SQLAlchemy, native browser JavaScript, pytest/Node and Chromium CI.
**Spec:** docs/superpowers/specs/2026-10-06-shared-session-design.md.

## Global Constraints
- No new paid/external dependency; synthetic fixtures only.
- Keep department DB/runtime/original/backup isolation and backend Human/RBAC/CAS/audit controls.
- No tokens or digests in context responses; fixed password renewal destination remains unchanged.
- Continuous user authorization supersedes routine plan approval; genuine external gates still require Human action.

## Review Focus
- Same-user relogin/session UUID changes during a response body.
- Same-session effective permission loss after data or blob fetch; no old cache render.
- Initial signed-out/login failures and expired-password renewal must not loop.
- Cloned responses, parse failures, rejected context probes and late old403 must preserve generation ownership.
- Cached form click, dynamic modal, focus and close/reset must not revive old private data or double-submit.

### Task1: Nonsecret authority context
Files: backend/app/routers/auth.py; backend/tests/test_shared_session_context.py. Interface GET /auth/context -> user_id/session_id/tenant_id/permissions.
- [ ] Write actual-session tests for no-store, secret exclusion, relogin UUID change, permission change and revoked/expired rejection.
- [ ] Run pytest focused and verify RED.
- [ ] Implement endpoint using canonical session digest lookup internally and sorted permission_codes.
- [ ] Run focused pytest and verify GREEN; commit.

### Task2: Shell body and cached action guard
Files: frontend/shared-session.js, frontend/index.html; backend/tests/test_shared_session_browser_state.py and actual browser workflow. Interface guarded window.fetch with unchanged Response identity plus FireAISession.install(reset).
- [ ] Write Node delayed JSON/blob, changed session/permissions, clone, initial401, stale error ownership, event/reset/renewal tests; verify meaningful RED.
- [ ] Implement common context/generation/body guard and initial private DOM/state reset in the shell.
- [ ] Run Node/focused integration tests; verify GREEN.
- [ ] Add actual Chromium shared-PC permission/relogin late-response flow; preserve previous9 workflows.
- [ ] Run full regression/migration parser/JS/diff checks, one fresh whole-branch review and one TDD repair pass if needed.
- [ ] Publish exact tree via leased GitHub commit/ref; exact-head backend/Chromium CI Green; merge; verify main Green and carry evidence onward.
