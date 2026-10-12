# Exact Reviewed Workflow Log Finding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept only the privately reviewed synthetic UUIDv4 false positive in immutable workflow run `37493709157`, while every changed, duplicated, relocated, differently ruled, or differently sourced finding remains fail-closed.

**Architecture:** Reuse the scanner's existing seven-field finding identity instead of adding a rule or UUID allowlist. For the one immutable run, derive that identity only when exactly one regular log file contains the UUIDv4 line inside the exact reviewed import-preview traceback context, and accept it only when a SHA-256 commitment to the entire seven-field identity matches the reviewed constant. This pins content hash, rule, path, and reported position without exposing those private identity fields. Artifact scans and every other run keep the existing reviewed dependency identities only.

**Tech Stack:** Python 3.11, pytest, pinned Gitleaks 8.30.1.

**Spec:** `docs/SPECIFICATION.md` sections 43, 43.1, 48, and 55.1; Issue #97 and parent Issue #93 checkpoint `6123042015`.

## Global Constraints

- Never print or publish matched values, raw scanner reports, private paths, file digests, or positions.
- Do not accept all UUIDs, all `generic-api-key` findings, all findings from the run, or all workflow logs.
- Keep the accepted history cursor at workflow run `37393414922` until the fixed batch is independently GREEN with `findings=0`.
- Preserve fixed snapshot PR/run `122`/`38175688221` and snapshot SHA-256 `d101123b1529a46efb99b4842b13c8bc3ebbd95bc5f2257a99b16d91e840237d`.
- Do not change Human gates, permissions, production data, secrets, keys, or Push Protection administration.

## Review Focus

- Another run with the same traceback must remain blocked.
- Another UUID elsewhere in the reviewed run must remain blocked.
- A duplicated reviewed traceback occurrence must remain blocked.
- A UUID with wrong RFC 4122 version/variant bits must remain blocked.
- A changed source hash, traceback line, detector rule, file path, or reported position must remain blocked by the scanner identity.

---

### Task 1: Pin the exact reviewed log identity

**Files:**
- Modify: `backend/tests/test_github_published_surface_audit.py`
- Modify: `scripts/audit_github_published_surfaces.py`

**Interfaces:**
- Consumes: extracted private workflow-run directory and exact integer run ID.
- Produces: `reviewed_workflow_log_findings(run_id: int, source_root: Path) -> frozenset[tuple]` containing zero or one existing seven-field scanner identity.

- [x] **Step 1: Write failing tests**

Add tests that require one exact reviewed-context fixture to return one identity and that require different run, missing/changed context, duplicate occurrence, and non-v4 UUID fixtures to return no identity. Add an actual pinned-Gitleaks assertion that the derived identity changes the exact fixture from one finding to zero without accepting an extra unrelated UUID.

- [x] **Step 2: Run tests to verify RED**

Run: `FIRE_AI_GITLEAKS_BIN=/tmp/fire-ai-gitleaks.pYiOCq/gitleaks pytest -q backend/tests/test_github_published_surface_audit.py -k reviewed_workflow_log_finding`

Expected: FAIL because `reviewed_workflow_log_findings` does not exist.

- [x] **Step 3: Implement the minimal identity derivation**

Implement the exact immutable-run/context/uniqueness validator. Build the existing `(relative_path, sha256, rule_id, start_line, end_line, start_column, end_column)` tuple from the validated regular log file and UUIDv4 match. Return an empty frozen set for nonmatches; fail closed on unsafe filesystem state.

- [x] **Step 4: Integrate only the exact workflow source scan**

Union the derived identity with `REVIEWED_PUBLIC_DEPENDENCY_FINDINGS` only while scanning that workflow run's collected source root. Keep streamed artifact scanning unchanged.

- [x] **Step 5: Verify GREEN and regression**

Run the focused test command, all published-surface/secret scanner tests, then the full backend suite with the repository's documented `PYTHONPATH` and pinned Gitleaks environment.

- [ ] **Step 6: Commit**

Commit only the plan, audit script, and audit tests with a bounded security-fix message.

### Task 2: Independent acceptance and GitHub integration

**Files:**
- Modify: Issue #97 and Issue #93 evidence only after observed results.

**Interfaces:**
- Consumes: exact branch commit/tree and fixed historical workflow inputs.
- Produces: reviewed PR, exact-head CI, merged main, independent main CI, and one fixed-batch rerun result.

- [ ] **Step 1: Obtain independent exact-tree review**

Review for broad suppression, path traversal/symlink behavior, line/column mismatch, Unicode/newline behavior, duplicate candidate ambiguity, and private-data output.

- [ ] **Step 2: Publish bounded PR and wait for exact-head CI**

Require project, security, dependency, and release workflows to succeed at the exact head before merge.

- [ ] **Step 3: Merge without bypass and verify independent main CI**

Recheck latest main and protection/ruleset state, merge only the reviewed expected head, then require all independent main workflows to succeed.

- [ ] **Step 4: Rerun the locked historical batch exactly once**

Use the unchanged accepted cursor/snapshot inputs. Advance to the candidate boundary only if both secret-scan and published-surface-audit are GREEN with `findings=0`; otherwise keep the old boundary and stop.

- [ ] **Step 5: Record checkpoint and release lease**

Record exact SHA/tree, changed files, PR/head CI/main CI, fixed-batch result, verified/unverified scope, remaining work, and next execution in Issue #97 and parent Issue #93.
