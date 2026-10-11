# Release Artifact Private Scan Repair Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing private published-surface audit inspect the legitimate source bundle and wheels inside the release artifact without weakening archive safety.

**Architecture:** Keep logs and direct artifact archive-name masquerading fail-closed. For downloaded Actions artifacts only, permit two bounded container layers after the outer artifact so legitimate wheel-embedded DOCX resources are inspected. Named containers require complete structural coverage; the pinned PyMuPDF ELF wrapper is accepted only by exact internal path and whole-file SHA-256 before its embedded ZIP is expanded. Retain every raw container beside its private expansion, reserve expansion namespaces against cross-layer overwrites, and apply one aggregate entry/raw-byte budget across the outer artifact and every expanded member.

**Tech Stack:** Python 3.11 standard-library `zipfile`/`tarfile`, pytest, GitHub Actions.

**Spec:** `docs/SPECIFICATION.md` §43.1; Issue #97; real RED run `38144546785`.

## Global Constraints

- Never print or upload downloaded bytes, extracted content, or raw scanner reports.
- Reject traversal, links, special files, duplicates, cross-layer path collisions, unsupported direct artifact formats, third-level nesting, excessive files, excessive entries/metadata, or aggregate expansion overflow.
- Preserve absolute network deadlines, token redirect stripping, completed-run validation, exact-ID selection, and private temporary deletion.
- Do not change release artifacts, security administration, credentials, RBAC, production data, or Human policy.

## Review Focus

- Source `.tar.gz` and wheel ZIP contents must actually reach the private Gitleaks directory.
- Archives beyond the bounded wheel/source resource depth must still fail closed.
- Aggregate limits must not reset per nested archive.
- Tar traversal/link/special-file cases must fail before escaping the private tree.
- Logs must retain the original no-nesting rule.
- Real pinned python-docx/PyMuPDF wheel containers must reach Gitleaks without allowing overwrite or unbounded TAR metadata.

---

### Task 1: Bounded release artifact expansion

**Files:**
- Modify: `backend/tests/test_github_published_surface_audit.py`
- Modify: `backend/tests/test_security_scan.py`
- Modify: `scripts/audit_github_published_surfaces.py`
- Modify: `scripts/security_scan.py`

**Interfaces:**
- Consumes: downloaded outer Actions artifact ZIP.
- Produces: privately expanded regular files from bounded ZIP/wheel/tar-family resource layers for the existing pinned Gitleaks scan, with only exact file-hash-bound reviewed public dependency findings accepted.

- [x] Add failing release-artifact tests for wheel + source tar expansion, deeper nesting, unsafe tar members, and shared aggregate budgets.
- [x] Run the focused tests and confirm failure comes from the current nested-archive rejection.
- [x] Implement one-level private expansion with shared counters; retain default no-nesting behavior for logs.
- [x] Run focused tests, the full backend suite with pinned Gitleaks, compileall, YAML parse, and diff-check.
- [x] Reproduce independent-review REDs for expansion overwrite, legitimate nested wheel resources, and unbudgeted TAR metadata/headers.
- [x] Redesign expansion namespaces, bounded embedded-container handling, raw-container retention, and TAR raw-byte/entry accounting; rerun focused/full tests.
- [x] Obtain independent exact-tree security review and repair Critical/Important findings in one RED→GREEN pass.
- [ ] Publish a fresh PR from current main, require exact-head CI, merge only when all checks are green, then require independent main CI and release-triggered audit GREEN.
