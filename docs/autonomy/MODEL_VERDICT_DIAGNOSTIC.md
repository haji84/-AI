# Offline verdict-shape diagnosis before retrying local inference

The isolated ZBook's first deterministic-line-ID review for PR #133
returned an Ollama JSON response but was rejected with
`SAFE_STOP: ReviewStop: model verdict invalid`. Thus the old candidate
is **not** an accepted review, and no semantic triage can run on it.

Do NOT rerun Ollama merely to learn the previous response shape.
Analyze the existing untrusted `candidate-133-v4.json` offline.

~~~powershell
py -3.11 scripts/autonomy/diagnose_review_format.py --snapshot C:\AIOS-review\snapshot-133.json --candidate C:\AIOS-review\candidate-133-v4.json --output C:\AIOS-review\format-133-v4.json
~~~

The output reports the JSON response type, verdict status/type, summary
type, findings type and count. It never quotes model text or even the
literal untrusted verdict value. This preserves the raw candidate without
misrepresenting it as an accepted reviewer result.

Interpret `verdict_status` as follows: `accepted_enum` means only that
the verdict string has correct spelling; `wrong_case` means capitalization
differs; `other_string`, `missing`, or `wrong_type` are invalid.
An accepted enum **does not** prove findings true, grounded or comprehensive.

## Future inference, only after latest-head CI and source review

The local Ollama API supports passing a JSON schema to `format`, rather
than just `format=json`. The reviewer now asks the model for
`verdict` restricted to `pass` or `needs_changes`, and requires
`summary` and a list of bounded findings with `path`, `anchor_id`,
`severity`, `evidence`, `recommendation`. Its own Python fail-closed
validation and non-author independent approval gate remain unchanged.

Structured output may still fail on a resource-limited model or when
input context is truncated. If it does, record evidence and stop instead
of converting an arbitrary verdict into pass or an approval.

Never upload complete raw candidate/source data to GitHub. Only the
offline diagnostic category summary may be shared after inspection.
