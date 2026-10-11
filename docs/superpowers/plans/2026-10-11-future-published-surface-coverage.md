# Future Published-Surface Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every repository workflow family other than the audit workflow itself triggers the existing private exact-run published-surface audit after completion.

**Architecture:** Keep the existing fail-closed collector unchanged. Expand only the `workflow_run.workflows` allowlist in `security-checks.yml`, and protect it with a contract test that derives the expected workflow names from the checked-in workflow files so later additions fail until explicitly covered.

**Tech Stack:** GitHub Actions YAML, Python 3.11, pytest.

**Spec:** `docs/SPECIFICATION.md` §43.1 and GitHub Issue #97.

## Global Constraints

- Never print or upload downloaded GitHub surface bytes or raw scanner findings.
- Preserve exact completed-run selection, bounded download/extraction, private temporary storage, and fail-closed behavior.
- Do not trigger `security-checks` from itself.
- Do not change Push Protection, repository administration, credentials, RBAC, production state, or Human policy.
- This slice proves future workflow-family trigger coverage only; it does not prove historical coverage or operational PII closure.

## Review Focus

- A newly added workflow must cause the contract test to fail until added to the watcher.
- The audit workflow must not watch itself and create a recursive workflow chain.
- Workflow names must match each file's top-level `name:` exactly.
- Manual exact-ID dispatch must remain available.
- The published-surface job must retain least-privilege Actions/issues/pull-request reads and no artifact upload.

---

### Task 1: Cover every future workflow family

**Files:**
- Modify: `backend/tests/test_github_published_surface_audit.py`
- Modify: `.github/workflows/security-checks.yml`

**Interfaces:**
- Consumes: top-level `name:` values from every checked-in `.github/workflows/*.yml` except `security-checks.yml`.
- Produces: exact `workflow_run.workflows` set that matches those names and continues passing the completed run ID to `audit_github_published_surfaces.py`.

- [x] **Step 1: Write the failing workflow coverage test**

Replace the single `project-checks` assertion with a test that extracts all top-level workflow names, extracts the watched quoted names from the `workflow_run` block, and asserts exact set equality excluding `security-checks`. Retain assertions for manual dispatch, completed events, permissions, token, exact run ID, scanner invocation, and absence of artifact uploads.

- [x] **Step 2: Run the focused test to verify RED**

Run: `pytest -q backend/tests/test_github_published_surface_audit.py::test_security_workflow_has_manual_private_published_surface_gate`

Expected: FAIL because the watched set contains only `project-checks`.

- [x] **Step 3: Expand the workflow-run watcher minimally**

Update `.github/workflows/security-checks.yml` so `workflow_run.workflows` lists the exact top-level names of every other checked-in workflow. Do not change jobs, permissions, audit inputs, timeouts, or scanner behavior.

- [x] **Step 4: Verify focused and full regression GREEN**

Run: `pytest -q backend/tests/test_github_published_surface_audit.py`

Expected: PASS.

Run: `pytest -q`

Expected: the complete project test suite passes; report every skip and failure exactly.

- [x] **Step 5: Verify syntax and diff**

Run: `python -m compileall -q scripts backend/app backend/tests`

Run: `git diff --check && git diff -- .github/workflows/security-checks.yml backend/tests/test_github_published_surface_audit.py`

Expected: no syntax or whitespace errors and only the planned watcher/test changes.

- [x] **Step 6: Commit**

Commit the plan, test, and workflow change together with an Issue #97-scoped message after GREEN.
