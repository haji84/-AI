# Independent local AI review candidate (Issue #140)

This is a **bounded reviewer candidate**, not an independent GitHub APPROVED
actor. It does not install a GitHub App, post PR comments, write GitHub
credentials to an AI prompt, execute PR code, or merge any PR.

## Trust separation

1. Run `collect` with a GitHub identity granted **read-only** metadata,
   Actions and repository access. It fetches the immutable PR head, base-main
   policy, all PR patches (fail-closed if missing/truncated), and all four
   exact-head CI streams. No checkout or execution of PR-supplied files.
2. End the collector process. **Do not reuse its shell's GH_TOKEN or
   GITHUB_TOKEN.** Run `evaluate` in a different, nonprivileged local OS
   account with no GitHub or external provider secrets. Ollama connects
   to 127.0.0.1 only. A separate account is necessary but not in itself
   sufficient to prove reviewer independence.
3. The review result is head-bound JSON with a SHA-256 integrity check (not a signature or authenticated attestation). Neither PASS nor
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

On a separate nonprivileged environment, with `GH_TOKEN` and
`GITHUB_TOKEN` absent, and local `qwen2.5-coder:7b` installed:

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

- Synthetics: `python -m pytest backend/tests/test_independent_ai_review.py`
- Real acceptance: separately operated workstation successfully collects
  exact PR head and gets an actual Ollama JSON review with no credentials,
  records evidence, and independent reviewing authority is verified.
- Even after that, there must be a separate policy-controlled path to submit
  an authenticated GitHub review. No `APPROVED`, `main` merge,
  auto-approval or unattended development completion is claimed here.


## GitHub comment publisher under a different identity

The AI reviewer does not get credentials. A **separate authenticated operator**
may turn the local JSON review into an auditable GitHub review with state
COMMENTED, not APPROVED. This path fails closed if the publisher login matches
the PR author or the live PR head, CI or patch digest changed.

Render a candidate comment without publishing:

~~~powershell
py -3.11 scripts/autonomy/review_evidence_publisher.py --snapshot C:\AIOS-review\snapshot-133.json --result C:\AIOS-review\review-133.json --output C:\AIOS-review\comment-133.md
~~~

The same command with `--publish-comment` requires a different GitHub login
with reviewer write permissions, rechecks exact live evidence, and prompts an
explicit terminal YES. Do not run this with the PR author's login. Check the
rendered candidate for secrets before publication.

This creates GitHub COMMENTED only. True independent GitHub APPROVED requires
separate governance and a review authority, not the local model output.

## ZBook/isolated reviewer evaluation gate

Use a separate nonprivileged checkout of PR #141. Do not run a candidate
branch on a privileged or confidential machine. Never connect a public PR
self-hosted runner to ZBook. Check current PR #133 head before collection.

1. Collector identity (GitHub read-only): run the collect command shown
   above with a read-only GitHub identity. Transfer its snapshot to an
   isolated evaluator with integrity verification.
2. Evaluator OS identity: a separate low-privilege Windows account with
   no GH CLI credential store and no external provider keys. With Ollama
   qwen2.5-coder:7b installed, run:

~~~powershell
py -3.11 scripts/autonomy/zbook_review_preflight.py
~~~

Only if ready_for_isolated_inference_trial=true, run the evaluate command
shown earlier. A preflight success is NOT actual model inference.
3. Independent review publisher: verify the JSON, fresh head and CI as an
   authenticated reviewer different from the PR author. A COMMENTED event
   is not an APPROVED event. The author must not impersonate a reviewer.

Synthetic regression: python -m pytest backend/tests/test_zbook_review_preflight.py

This probe checks common GH CLI credential locations and environment keys;
it does not certify OS isolation, operator independence, real model output
or GitHub approval. All such claims require external execution evidence.

## Collector when GitHub CLI is absent

If the collector operating system does not have the `gh` executable, the
read-only collector now falls back to **unauthenticated public GitHub REST**
over HTTPS, restricted to haji84/-AI. It sends no Authorization header,
does not install software, and does not post anything. This only works
while the repository is public and GitHub permits anonymous API reads.
Anonymous API rate limiting or network restrictions cause a safe failure.

The **independent publisher is different**: it still requires a distinct
authenticated GitHub CLI identity for any COMMENTED review and never
creates an APPROVED review. The isolated model evaluator must not have
GitHub tokens or credential stores.

For the ZBook's previous `SAFE_STOP: FileNotFoundError`, collect again
after obtaining this updated, reviewed PR #141 head. Do not change the
PR #133 expected-head value without fetching its latest actual head.

## 4GB VRAM: smaller-model option (2026-10-13)

A ZBook trial showed `qwen2.5-coder:7b` on 100% CPU and 0% NVIDIA GPU
utilization with a 4GB RTX A2000. Ollama's published 3B model is approximately
1.9GB on disk, versus 4.7GB for the standard 7B model. Runtime usage
includes context/KV cache and overhead, so GPU residency is NOT guaranteed.

The reviewer now accepts an explicitly allowlisted 3B model with a smaller
context while leaving 7B as the default. First stop any still-running
7B evaluation with Ctrl+C in the original terminal and verify that it has
stopped. From PowerShell, with Ollama installed, download:

~~~powershell
ollama pull qwen2.5-coder:3b
ollama stop qwen2.5-coder:7b
~~~

Only in the credential-free evaluator OS account, after the isolated preflight command
`py -3.11 scripts/autonomy/zbook_review_preflight.py --model qwen2.5-coder:3b`, evaluate the already pinned PR #133 snapshot:

~~~powershell
py -3.11 scripts/autonomy/independent_ai_review.py evaluate --snapshot C:\AIOS-review\snapshot-133.json --output C:\AIOS-review\review-133-3b.json --model qwen2.5-coder:3b --num-ctx 8192
~~~

The runtime emits a start marker before the blocking Ollama request and a
response marker when an Ollama response has been received; this is NOT
token-level live progress. Confirm actual GPU placement via `ollama ps`
and `nvidia-smi`. If `ollama ps` still says 100% CPU, GPU acceleration
did not occur. If the prompt exceeds 8K context and may have been truncated,
do NOT accept the review as complete. A compact model is a preliminary
candidate reviewer, not security approval or evidence of reviewer independence.
