# Independent local AI review: specificity gate

2026-10-13 ZBook real PR #133 review with qwen2.5-coder:3b on
commit `2dd95b171f7b8e3932b551ff8c01398ec5b70a3c`:
the model completed with 588 generated tokens, valid JSON and 6 anchored
findings. Semantic v7 returned `needs_changes`, `contradicted=0`,
`unverified=6`, `APPROVED=false`. All six pointed to consecutive changed
lines F04L0055-F04L0060 in `scripts/autonomy/backlog.py`.

Review text had `evidence` consisting of a copied source-code line and
`recommendation` consisting of generic `Ensure...`/`Validate the
output... expected and properly formatted` phrases. The model did not
identify a concrete exploit, observable malfunction, violated invariant,
missing check, failing test or reproduction. Its high/medium scores
are not substantiated by those descriptions.

Manual source inspection confirmed:

- Repository identity is checked against `haji84/-AI` before issue operations.
- The candidate proposal builder checks 57 canonical chapters, status
  identity and audited base before producing bounded chapter proposals.
- Subprocess receives an argument list, `check=True`, `timeout=70`;
  subprocess and other enumerated operational errors are handled in main.
- `gh issue list` JSON is parsed, constrained to a list shorter than 1000,
  and entries must be dictionaries. There can be further type-hardening
  opportunities for individual fields, but the six model findings
  identify no particular malformed input or security exploit.

## Machine gate

`semantic_review_gate.py` now marks a candidate
`insufficient_specificity` if BOTH:

1. The alleged evidence is **only an exact copy** of its changed source
   line after normalizing whitespace, with no failure explanation;
2. The advice starts with one of the observed generic Ensure/Validate
   templates and contains generic expected/properly/formatted language.

This label denotes **inadequate evidence**, not that the allegation is
false or code is secure. Specific allegations still remain `unverified`
unless an extremely narrow deterministic contradiction is proven.
`review_evidence_publisher.py` now refuses to publish an
`insufficient_specificity` candidate as an actionable GitHub review.
Nothing changes credentials, required reviewer identity, or merge policy.

To reclassify existing ZBook evidence offline without another model run,
check out the current PR #141 head on an isolated unprivileged system,
then use a NEW output name:

~~~powershell
py -3.11 scripts/autonomy/semantic_review_gate.py --snapshot C:\AIOS-review\snapshot-133.json --review C:\AIOS-review\review-133-v7.json --output C:\AIOS-review\semantic-133-v8-quality.json
~~~

Do not overwrite the original v7 semantic JSON. Check status counts,
not sensitive model prose. Formal independent GitHub APPROVED and merge
remain blocked even if all six are low specificity. CI and review on
the updated PR #141 exact head are independent acceptance gates.
