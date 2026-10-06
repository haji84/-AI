# Violation and correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans, native implementation with one fresh whole-branch review.

**Goal:** Provide a usable, separately gated formal violation and corrective-action lifecycle.
**Architecture:** Reuse Facility/InspectionFinding/Document and structured approved legal sources. New case/measure/action/event tables preserve candidate/official separation and immutable evidence. Shared mutation authority guard precedes row locks/CAS.
**Tech Stack:** Existing FastAPI/SQLAlchemy/PostgreSQL/Pydantic/browser JavaScript.
**Spec:** docs/superpowers/specs/2026-10-06-violation-correction-design.md; docs/SPECIFICATION.md§13.

## Global Constraints
- No operational data or originals in Git; synthetic fixtures only.
- No AI formal violation/order/disposition confirmation.
- Tenant runtime/DB/original/backup separation fixed; canonical main is sole base.
- Human source, permission, audit and CAS checks cannot be weakened.

## Review Focus
- Source reparse/change during Human review; stale facility/finding or missing files must block confirmation.
- Permission/session loss while queued or during browser responses; no source leakage or stale drafts.
- Concurrent confirmations/responses/completions and task closure; one winner and immutable events.
- Historical legal versions and revision/withdrawal; preserve past evidence while blocking new stale decisions.
- Exhausted paging, cancelled tasks, no-task completion and cross-facility links; no misleading completion/counts.

### Task1: Case provenance and separate formal Human gate
Files: app/violation_models.py, violation_schemas.py, violation_service.py, routers/violations.py; Migration049; bootstrap/main/rbac/module registration; tests/test_violations.py.
Interfaces: create_case(db,user,payload), case_action(db,user,id,payload,action), case_dict(db,user,row); REST /violations and /violations/{id}/review|confirm|withdraw|revisions.
- [ ] Write tests: create→confirm409; missing evidence409; successful review/confirm; stale expected409; changed rule/source/finding/doc bytes409; AI candidate leaves inspection unchanged; revoked originating session401; no source permission403; confirmed edit409 and revision keeps original.
- [ ] Run `PYTHONPATH=.:backend /tmp/fire-ai-venv/bin/python -m pytest -q backend/tests/test_violations.py`; Expected RED before implementation.
- [ ] Implement four tables and canonical source snapshot/CAS/audit/Human APIs, seed module permissions.
- [ ] Run same test command; Expected PASS; commit.

### Task2: Measures and correction lifecycle
Files: same bounded domain, tests/test_violation_corrections.py.
Interfaces: measure_action(...), create_correction(...), correction_event(...); REST /violations/{id}/measures, /corrections and task transitions.
- [ ] Write tests: guidance/order/disposition require explicit review/confirm; procedure originals mandatory; response→positive verification→completion; negative/no verification blocked; overdue filtering; immutable ordered events; outstanding/no-task case completion blocked.
- [ ] Run focused tests; Expected RED. Implement permission-aware records/immutable events/Human closure; rerun Expected PASS; commit.

### Task3: Browser, search, export and PostgreSQL integration
Files: frontend/violations.js/index; search.py; tests/test_violation_browser.py/test_violation_concurrency.py; workflow; completion evidence.
Interfaces: identity/generation-safe UI; protected candidate versus confirmed navigation; paged source selectors; exact-head native Chromium and PG tests.
- [ ] Write failing actual-JS state tests and native workflow; add PG concurrent confirm/close tests. Expected RED for unimplemented UI; PG/browser locally skipped explicitly.
- [ ] Implement forms, evidence/Rule selection and transitions, source/status/history UI, permission-aware search/export, CI coverage.
- [ ] Full suite, one fresh review and one TDD repair pass; exact-head CI success; merge; main Green; update completion matrix only against canonical code. Expected no remaining internal§13 primary workflow gaps; genuine Human operational acceptance external.
