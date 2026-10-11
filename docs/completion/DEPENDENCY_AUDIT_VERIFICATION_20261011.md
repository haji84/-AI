# Resolved dependency audit verification (2026-10-11 JST)

## Boundary

Issue #98 implements the chapter 43.1 prerequisite gate for the Python
dependencies actually resolved by CI.  It does not produce a Release lock,
wheel bundle, hashes, or a fully offline installation.  The three scopes are:

- `runtime`: dependencies resolved from `backend`;
- `backend-test`: dependencies resolved from `backend[test]`;
- `browser`: `backend[test]` plus `playwright>=1.55,<2`.

Each target is a fresh virtual environment.  CI installs the local project to
resolve its declared dependency graph and then removes only the editable
`fire-ai-local-backend` distribution.  The remaining complete third-party
inventory is the audit target.  Project source remains covered by source,
test, secret, and review gates; it is not a public PyPI package and cannot be
meaningfully queried as one.

The auditor is `pip-audit==2.10.1` in a separate virtual environment.  Version
2.10.1 was rechecked as the latest official PyPA release on 2026-10-10 UTC
(released 2026-06-10).  The gate verifies that exact runtime version before
use.  GitHub Actions has only `contents: read`, checkout credentials are not
persisted, and no secrets are supplied.

## Fail-closed contract

`scripts/audit_dependencies.py` obtains package names, versions, and both
installation paths from the target interpreter itself.  It invokes the pinned
auditor with the PyPI vulnerability service, JSON output, `--strict`, and each
target path.  It accepts success only when the report has exactly one matching
name/version row for every installed package and no additional rows or known
vulnerabilities.  Service failure, malformed output, an omitted package,
duplicate package, version mismatch, unexpected fix output, timeout, or wrong
auditor version fails the gate.

There is no vulnerability ignore baseline, auto-fix, dry-run, editable skip,
shell failure suppression, or workflow `continue-on-error`.  Success writes a
deterministic evidence JSON containing the scope, exact sorted inventory,
inventory SHA-256, auditor version, and service name.  Each scope is uploaded
as a separate Actions artifact.  On a vulnerability RED, CI prints only
escaped package names, versions, advisory identifiers, and published fix
versions; descriptions and arbitrary scanner text are excluded.

This detects published Python-package advisories.  In accordance with the
auditor's own security model, it does not establish that resolving or
installing an arbitrary malicious package is safe, and it does not cover a
native library hidden behind a Python package unless the advisory service maps
that issue to the Python distribution.

## TDD and local evidence

Canonical base before the slice:

- commit `99db53947e222f2d9554af7131b0555cc3280078`;
- tree `7377d759df60af225ff2fc87f4768adb116ef238`.

Observed RED stages:

1. Eleven tests failed because the audit implementation did not exist.  These
   covered a synthetic advisory, service/report failure, missing package,
   explicit skipped row, mismatched/extra/duplicate report rows, command
   waivers, auditor version, and environment separation.
2. The workflow contract test then failed because the dedicated workflow did
   not exist.
3. A real target rehearsal exposed that resolving the target executable's
   symlink selected the base interpreter instead of the virtual environment.
   A dedicated symlink-preservation regression failed before the single path
   normalization repair.

Focused GREEN after the repair:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend python -m pytest \
  backend/tests/test_dependency_audit.py -q
15 passed in 0.04s
```

A local real browser-superset environment resolved 51 third-party packages
after upgrading to `pip 26.2.1` and removing the local project distribution.
The audit then failed closed with `findings=unknown` because this execution
environment could not resolve the vulnerability service hostname.  Direct
boundary diagnostics showed the correct target path and inventory, exact
auditor version, and a DNS failure before any JSON response.  This is not a
clean vulnerability verdict and is not counted as GREEN; the network-enabled
exact PR CI matrix is required.

The base backend suite was also run locally without the required pinned
Gitleaks environment variable: `1345 passed, 303 skipped, 327 warnings`, with
three failures and thirteen setup errors all confined to the existing secret
scanner tests requiring `FIRE_AI_GITLEAKS_BIN`.  No unrelated product failure
was observed, but this is not a replacement for configured CI, PostgreSQL, or
Chromium evidence.

## Exact-PR RED and remediation

PR head `9ff56081b1e9a8ffa4c8a3b3e823f8194f88a34e` (tree
`8edff5d6e85340db019de74740ae336296297968`) reached the public advisory
service in dependency workflow run `38080702298`.  All three jobs failed
closed.  The distinct public findings, retained in Issue #111, were:

- `cryptography 48.0.1`: `PYSEC-2026-3552`, `PYSEC-2026-3553`, and
  `PYSEC-2026-3554`; the highest required fix version is `50.0.0`;
- `pytest 8.4.2`: `PYSEC-2026-1845`, fixed in `9.0.3`;
- `setuptools 79.0.1`: `PYSEC-2026-3447`, fixed in `83.0.0`.

The upstream report repeated identical advisory rows, producing displayed
counts of eight for runtime and ten for test/browser.  The gate still blocked.
A regression now collapses only identical advisory facts while failing closed
if the same package/version/advisory identifier reports conflicting fix
versions.  No finding is waived.

The minimal remediation raises the declared `cryptography` range to
`>=50,<51`, the test-only `pytest` range to `>=9.0.3,<10`, and upgrades the
target environment's bootstrap `setuptools` before inventory capture.  A fresh
local environment resolved `cryptography 50.0.2`, `pytest 9.1.1`, and
`setuptools 84.0.0`.  With the repository's pinned Gitleaks binary configured,
the complete backend regression in that upgraded environment passed:
`1375 passed, 303 skipped, 327 warnings, 31 subtests passed` in 409.59 seconds.
The skips are the existing environment-gated PostgreSQL/browser/external
groups; exact-head CI remains required before acceptance.

## Acceptance still required

- independent exact-tree review;
- all three dependency matrix jobs on the exact PR head, with retained
  inventory artifacts and no findings;
- existing backend, PostgreSQL, browser, parser/JavaScript, and secret gates on
  the same PR head;
- merge without weakening repository conditions, followed by independent
  `main` runs of the same gates;
- parent Issue #93 checkpoint with exact SHAs, run/job/artifact identities,
  verified results, remaining Release lock/hash/wheel/offline work, and lease
  release.
