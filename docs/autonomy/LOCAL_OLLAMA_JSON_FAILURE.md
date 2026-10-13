# Local Ollama JSON parse failure: safe metadata acceptance

On ZBook with reviewer PR #141 head b446599aeb8475e31879dd9c74c9fc7590c47d55,
the PR #133 model evaluation produced LOCAL_AI_REVIEW_RESPONSE_RECEIVED
then SAFE_STOP: JSONDecodeError. No candidate/review file was created.
The error occurs when JSON decoding the Ollama message content,
NOT when authenticating with GitHub or comparing diff anchors.

## Read-only, no-prose failure diagnostics

A reviewer on an isolated nonprivileged machine can run:

~~~powershell
py -3.11 scripts/autonomy/independent_ai_review.py evaluate --snapshot C:\AIOS-review\snapshot-133.json --output C:\AIOS-review\review-133-v6.json --candidate-output C:\AIOS-review\candidate-133-v6.json --inference-metadata-output C:\AIOS-review\inference-133-v6.json --model qwen2.5-coder:3b --num-ctx 8192
~~~

The optional inference metadata is written immediately after receiving
the Ollama response (even if JSON decoding fails). Its fields are limited
to model, context token setting, whether Ollama marked itself done,
classified done_reason (stop, length, other), bounded prompt_eval_count
and eval_count, response bytes, SHA-256 of response and JSON parse position.
It contains **no generated text**, no diff content, and no credentials.

To inspect without revealing raw source or model response:

~~~powershell
if (Test-Path C:\AIOS-review\inference-133-v6.json) {
    Get-Content C:\AIOS-review\inference-133-v6.json -Raw | ConvertFrom-Json |
    Select-Object model,context_tokens,done,done_reason_class,prompt_eval_count,eval_count,content_bytes,parse_status,parse_error_position,accepted_review,independent_github_approval | Format-List
}
~~~

Interpretation:

- parse_status=invalid_json: Ollama message content was not valid JSON;
  no trusted candidate/review output is allowed.
- done_reason_class=length: Ollama generation was cut by its output limit;
  reject even if its remaining JSON happens to parse.
- done_reason_class=stop with invalid_json: the model completed but
  generated syntactically invalid JSON; investigate schema compatibility
  and prompt size, not simply increasing a timeout.
- prompt_eval_count near context_tokens can indicate a context budget
  problem, but cannot alone prove or disprove input truncation.
- parse_status=valid_json alone does not establish source-grounded
  findings, review quality, independent operator status or GitHub APPROVED.

Do not increase model context/output size blindly on a 4GB GPU.
Before making changes, compare these diagnostics with the exact-head
snapshot and original PR/CI. Do not upload raw untrusted output to GitHub.
Both JSON outputs use no-overwrite semantics. Use a new filename per trial.
