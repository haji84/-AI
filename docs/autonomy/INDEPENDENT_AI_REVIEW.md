# Independent local AI review candidate (Issue #140)

This is a **bounded reviewer candidate**, not an independent GitHub APPROVED
actor. It does not install a GitHub App, post PR comments, write GitHub
credentials to an AI prompt, execute PR code, or merge any PR.

## Trust separation

1. Run \`collect\` with a GitHub identity granted **read-only** metadata,
   Actions and repository access. It fetches the immutable PR head, base-main
   policy, all PR patches (fail-closed if missing/truncated), and all four
   exact-head CI streams. No checkout or execution of PR-supplied files.
2. End the collector process. **Do not reuse its shell's GH_TOKEN or
   GITHUB_TOKEN.** Run \`evaluate\` in a different, nonprivileged local OS
   account with no GitHub or external provider secrets. Ollama connects
   to 127.0.0.1 only. A separate account is necessary but not in itself
   sufficient to prove reviewer independence.
3. The review result is immutable head-bound JSON evidence. Neither PASS nor
   needs_changes amounts to an authenticated independent GitHub APPROVED.
   A separate authorized review publisher would need to check identity,
   fresh head/CI and governance before submitting any GitHub review.
   This code intentionally has no such write path.

## PR #133 exact-head test inputs (2026-10-13)

- Repo: haji84/-AI
- PR: 133
- Head: 2dd95b171f7b8e3932b551ff8c01398ec5b70a3c
- Base: main
- CI streams: project 38332629515, security 38332629902,
  dependency 38332629583, release 38332629526. All SUCCESS at inspection.
- Historical CI success is not valid for a later updated PR head.

Read-only collector example on isolated checkout with Python 3.11+ and gh CLI:

~~~powershell
py -3.11 scripts/autonomy/independent_ai_review.py collect --pr 133 --expected-head 2dd95b171f7b8e3932b551ff8c01398ec5b70a3c --output C:\AIOS-review\snapshot-133.json
~~~

On a separate nonprivileged environment, with \`GH_TOKEN\` and
\`GITHUB_TOKEN\` absent, and local \`qwen2.5-coder:7b\` installed:

~~~powershell
py -3.11 scripts/autonomy/independent_ai_review.py evaluate --snapshot C:\AIOS-review\snapshot-133.json --output C:\AIOS-review\review-133.json
~~~

**CAUTION:** A Python process invoking Ollama is not an OS sandbox. Do not
run PR code, use an unrestricted machine with business secrets, or make a
public-repository self-hosted runner execute untrusted PR code. The review
model's prose is a candidate; human/independent operator must verify source
claims. Snapshot and result files may contain source code. Do not publish
these wholesale to GitHub without checking their content.

## Verification gate

- Synthetics: \`python -m pytest backend/tests/test_independent_ai_review.py\`
- Real acceptance: separately operated workstation successfully collects
  exact PR head and gets an actual Ollama JSON review with no credentials,
  records evidence, and independent reviewing authority is verified.
- Even after that, there must be a separate policy-controlled path to submit
  an authenticated GitHub review. No \`APPROVED\`, \`main\` merge,
  auto-approval or unattended development completion is claimed here.
