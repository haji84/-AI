# Offline candidate grounding diagnosis

Input: snapshot-133.json and untrusted candidate-133-v3.json produced on the isolated
ZBook. This diagnosis does not contact GitHub or Ollama and does not accept a review.

After checking out the reviewed PR #141 head on a nonprivileged system:

~~~powershell
py -3.11 scripts/autonomy/diagnose_local_candidate.py --snapshot C:\AIOS-review\snapshot-133.json --candidate C:\AIOS-review\candidate-133-v3.json --output C:\AIOS-review\grounding-133-v3.json
~~~

Summary status is printed without the quoted line or model's interpretation.
Inspect index/path/status only:

~~~powershell
$d = Get-Content C:\AIOS-review\grounding-133-v3.json -Raw | ConvertFrom-Json
$d | Select-Object pr,head,total_findings,counts,accepted_review,independent_github_approval | Format-List
$d.findings | Format-Table finding_index,known_path,quote_status -AutoSize
~~~

Possible statuses: exact_match, quoted_from_other_changed_file,
surrounding_whitespace_mismatch, addition_deletion_sign_mismatch,
not_an_exact_changed_line, missing_source_line, unknown_path, invalid_record.

Even exact_match proves only that the cited line occurs in a changed hunk;
it does not prove the claimed vulnerability. All statuses remain untrusted.
Never automatically normalize/repair quotes, overwrite a valid review or
publish raw candidate model prose to GitHub. The diagnostic report itself
is non-sensitive metadata by design, but inspect its paths before sharing.

If no accepted review JSON exists, do not run semantic_review_gate.py.

Regression command:

~~~powershell
py -3.11 -m pytest backend/tests/test_diagnose_local_candidate.py
~~~
