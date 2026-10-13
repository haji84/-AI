# Exact changed-line ID review (ZBook acceptance, Issue #140)

**Scope:** draft PR #141 changes the AI reviewer protocol after four of four
Qwen2.5-Coder 3B citations for PR #133 were not exact changed lines.
The earlier raw candidate is not trusted. Never overwrite it or
upgrade it into a verified review.

## Stage 1: model chooses a bounded line ID, not text

`review_line_anchors.py` enumerates each changed line of every immutable
exact-head file diff with a deterministic per-file ID such as `F01L0001`.
The model sees the change as `[F01L0001] +source text` in an annotated
patch. It must return `anchor_id` plus `path`, `severity`, `evidence`,
and `recommendation`. The trusted evaluator independently regenerates
the catalog from the original immutable snapshot and resolves the ID
into the *exact* `source_line`. It refuses missing IDs, unknown IDs, IDs
from another path, and malformed findings. A guessed but valid ID does
not prove that the claimed bug is real. Output is not a GitHub approval.

## Stage 2: semantic review stays separate

`semantic_review_gate.py` independently checks snapshot, PR/head, CI,
source ID and the exact derived changed line again. The deterministic
Python AST layer can reject a few contradictory claims. All other
findings remain `unverified`; context completeness and operator
independence remain unproven. The publisher is COMMENT-only, requires
an authenticated independent reviewer, and has no merge permission.

## ZBook test with no production credentials

Check out this feature's exact GitHub PR #141 head in an isolated,
nonprivileged OS account. Do not execute a development branch with
privileged GitHub tokens, personal files or operational data.
Use an existing pinned PR #133 snapshot only if its head, base and
CI remain current; recollect if they changed.

~~~powershell
py -3.11 scripts/autonomy/zbook_review_preflight.py --model qwen2.5-coder:3b
py -3.11 scripts/autonomy/independent_ai_review.py evaluate --snapshot C:\AIOS-review\snapshot-133.json --output C:\AIOS-review\review-133-v4.json --candidate-output C:\AIOS-review\candidate-133-v4.json --model qwen2.5-coder:3b --num-ctx 8192
~~~

If the trusted review JSON exists, run stage 2:

~~~powershell
py -3.11 scripts/autonomy/semantic_review_gate.py --snapshot C:\AIOS-review\snapshot-133.json --review C:\AIOS-review\review-133-v4.json --output C:\AIOS-review\semantic-133-v4.json
~~~

If the model candidate was rejected, do not run semantic review.
Classify its anchor IDs offline, never post raw model prose:

~~~powershell
py -3.11 scripts/autonomy/diagnose_local_candidate.py --snapshot C:\AIOS-review\snapshot-133.json --candidate C:\AIOS-review\candidate-133-v4.json --output C:\AIOS-review\grounding-133-v4.json
~~~

**Acceptance:** 4 exact-head CI jobs SUCCESS, real ZBook execution
evidence, all reported anchors proven exact, separate semantic results,
and a genuine independent actor's review. A source-line match alone
is not an independent GitHub APPROVED and never authorizes merge.
