# Issue 97: bounded secret scanning verification

This evidence covers the Lane 2 CLI, its synthetic tests, and root-owned
CI/pre-push wiring. It does not mark specification chapter 43 complete.
The final integrated full suite and exact PR/independent main CI execution
remain required before acceptance.

## Design and invocation

The caller fetches the refs that must be covered, installs the verified official
Linux x64 Gitleaks binary, then runs:

```sh
python scripts/security_scan.py --repository . --gitleaks "$FIRE_AI_GITLEAKS_BIN"
FIRE_AI_GITLEAKS_BIN=/absolute/path/to/gitleaks python -m pytest backend/tests/test_security_scan.py -q
```

Pin: Gitleaks 8.30.1. Official release archive:
`https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz`.
The root owner independently verified the archive SHA256 as
`551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`.
The CLI independently requires the extracted binary SHA256
`88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509`
and exact version output `8.30.1`. It neither downloads nor accepts a hash override.

Two actual scanner invocations cover all locally available refs through
`git --log-opts '--all --full-history --text --no-ext-diff --no-textconv'`
and a separate directory scan of the current working tree. Untracked and
Git-ignored regular text files are included by the directory scan, as verified
with synthetic fixtures. `--text` prevents repository binary diff attributes
from hiding historical text credentials. Git replace objects are disabled.
The subprocess environment uses a trusted minimal system PATH, disables global
and system Git config, and inherits no caller-provided scanner configuration,
Git routing variables, or loader injection variables.

Each scan receives an external private temporary `[extend] useDefault = true`
configuration, an empty explicit ignore file, and `--ignore-gitleaks-allow`.
Both trusted files are checked unchanged afterward. No baseline, suppression,
skip option, or continue-on-error path exists. The pinned default rules still
have their own documented detection and exclusion behavior.

Raw stdout, stderr and redacted JSON reports stay inside a private `/tmp`
directory outside the target repository and are removed on completion.
The terminal receives only a generic status, scope and count, including on
argument errors, exceptions and scanner failures. Counts sum the two passes;
the same credential can count more than once. Return codes: 0 clean, 1 findings,
2 inability to establish a clean result. Missing/wrong binary, version mismatch,
unexpected scanner exit, missing/malformed/inconsistent report, modified trusted
config/ignore, timeout and output limits all fail closed.

Each scan has a 300-second external deadline and scanner timeout; version
verification has a 10-second deadline. Stream capture plus reports have a
16 MiB budget per invocation. Linux `RLIMIT_FSIZE` additionally caps each
report file at 16 MiB. Scanner and Git process groups are terminated when the
deadline or capture budget is exceeded. Report rotation during active scanning
is tolerated; a valid final report is required after completion.

## RED / GREEN

RED before implementation: 7 failures / 1 pass because the CLI did not exist.
Actual-tool tests used the verified pinned binary in isolated temporary Git
repositories. Tokens were generated at runtime with random synthetic content;
no complete token literal or operational data was committed.

Final focused GREEN: **18 passed in 7.97 seconds**, using
`FIRE_AI_GITLEAKS_BIN=/tmp/fire-aios-gitleaks-probe-YrxQnE/gitleaks`.
Coverage includes clean repository; untracked and Git-ignored dirty secrets;
deleted credentials retained only in another fetched ref's history; historical
binary attributes and replacement refs; repository config, environment config,
ignore and inline-allow attempts; missing/wrong binary; wrong version; scanner
exception; output/report budgets and timeout; report rotation; missing/malformed
reports, inconsistent exit/report, and trusted-file modification; argument
privacy and environment routing. Actual-tool readiness fails rather than skips
when `FIRE_AI_GITLEAKS_BIN` is absent.

The lane worktree also passed the actual CLI over locally fetched history and
the working tree with zero findings before final integration. Root performs
the final integrated-head scan and full suite.

## Scope and limitations

This Linux-only gate detects patterns supported by the pinned default rules.
It covers available fetched refs and scanner-supported current regular files;
it cannot prove that remote refs were fetched completely. Git metadata,
unfetched/unreachable history, symlink targets, binary/document extraction,
archives (default archive traversal remains disabled), remote PR logs and
artifacts, operational PII, and GitHub Push Protection are outside this evidence.
Passing this gate is not evidence that those surfaces contain no sensitive data.
No remote issue/PR/push/merge action was performed by this lane.

## Root-owned CI and pre-push integration

The dedicated `security-checks` job runs on PRs and main pushes, with
`contents: read`, immutable official checkout/setup-python refs, full fetched
history, and credentials removed after checkout. The composite installer
verifies both the official archive and extracted binary SHA256 before exporting
`FIRE_AI_GITLEAKS_BIN`; no credential or raw scanner report is uploaded.
Existing backend tests also install the same pinned binary so actual-tool
regressions execute rather than skip. Existing PostgreSQL/browser gates remain.
This is a development CI check; no branch protection setting is altered and
untrusted changes to workflows/scanner source still require independent review.

The actual `.githooks/pre-push` entry point was tested against generated clean,
dirty-secret and absent-scanner repositories: three REDs without the hook, then
the combined scanner/hook suite passed21 tests with the actual pinned tool.
Existing hooks are not replaced or silently installed. On a Linux development
host, first inspect `git config --local --get core.hooksPath` and existing
pre-push logic. Only if there is no existing hook arrangement, enable the
provided hook with `git config --local core.hooksPath .githooks`, and export
`FIRE_AI_GITLEAKS_BIN` to the verified absolute binary path. Otherwise preserve
the existing hook and incorporate this gate there. Git/API writes can bypass a
local hook; root must invoke the CLI explicitly before connector publication.
This hook is not a replacement for remote CI or GitHub Push Protection.

## Independent review correction

Independent review of integrated commit `deb68b80` reproduced a process-group
cleanup defect: a scanner parent could exit before its descendant, leaving that
descendant alive after the capture deadline. The new synthetic regression
failed before repair. Cleanup now attempts to terminate the entire group
regardless of the parent's exit status, tolerates an already absent group,
and reaps the parent. The combined actual-tool scanner/hook suite then passed
**22 tests in 9.78 seconds**. Independent final review also ran 22 tests in
10.38 seconds. The final descendant fixture uses a namespace-safe Linux pidfd;
the former `/proc/<pid>` observation was invalid in the local PID namespace.
With this corrected fixture, the old implementation failed and the repaired
implementation passed. Interrupted pre-final suites are not acceptance evidence.

## Local integration verification

Final scanner source at local `272674a` on base `75673ba` completed the full
backend suite with exit 0: **1287 passed, 295 skipped, 287 warnings in 388.82s**.
Explicit `PYTHONPATH` resolved the application into this worktree. These local
skips do not establish PostgreSQL or Chromium acceptance.

After PR101 merged, this unpublished branch rebased without conflicts onto
main `adfede71a22e23f44faa6c53208a84cabcb433c5` (tree
`12358e2f14e554287e03d5a2aa36f5426a1ce4bc`). Scanner source is unchanged.
The integrated scanner, hook and violation state regressions passed
**32 tests in 11.66s** at local `90726ed`. The actual CLI scan over fetched
refs and the integrated working tree returned zero findings. Dedicated secret
CI, native PR CI and independent main CI remain pending; no remote acceptance
or chapter completion is inferred from these local checks.
