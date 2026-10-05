# Phase 9 Test Evidence

更新日: 2026-10-05

## Current green checkpoint

GitHub Actions run: `37257011265`
Conclusion: SUCCESS

- backend pytest: 91 passed
- Phase 9 audio benchmark v2 tests: PASS
- migrations parser smoke: PASS
- frontend JavaScript syntax: PASS

## Phase 9 voice / statement intelligence already verified

- uncertainty marker positions are deterministic
- transcript text SHA-256 is stable
- transcript search can restrict to Human-accepted segments
- transcript search can restrict to uncertain segments
- statement Draft inherits source uncertainty markers
- uncertain statement cannot become reviewed without explicit Human uncertainty confirmation
- evidence comparison accepts only Human-reviewed/confirmed evidence
- same Evidence cannot be compared with itself
- evidence comparison AI Manifest is idempotent
- comparison candidates remain pending until Human review
- optimistic version conflict prevents double review
- accepted comparison remains a separate candidate record
- accepted comparison cannot mutate reviewed statement text
- accepted comparison cannot mutate confirmed timeline status
- accepted comparison cannot select/approve official fire cause

## Japanese Audio Benchmark v2 verified

Tool:
`scripts/benchmark_fire_audio.py`

Format:
`fire-ai-japanese-stt-benchmark-v2`

Verified features:
- Japanese Character Error Rate
- substitutions / insertions / deletions
- memory-reduced Levenshtein row implementation
- speaker diarization scoring on non-double-counted timeline intervals
- automatic Hypothesis speaker-label -> Reference speaker-label mapping
- rectangular speaker assignment handling
- speaker confusion / missed / false-alarm time
- Speaker Error Rate
- uncertainty marker exact scoring
- uncertainty marker time-tolerance scoring
- bipartite marker matching to prevent duplicate matches
- multi-recording Dataset Manifest
- per-recording results
- micro aggregate CER
- micro aggregate diarization error
- micro aggregate uncertainty Precision/Recall/F1
- Reference/Hypothesis SHA-256 provenance
- Manifest SHA-256 provenance
- per-recording environment/condition metadata passthrough
- payload/time-range validation

## Benchmark interpretation policy

The benchmark is evidence only.

It cannot directly:
- mark a transcript accepted
- mark a statement reviewed
- confirm a timeline
- select or approve a fire cause
- approve a formal report

No production-quality STT claim is allowed until a real Japanese audio Dataset is benchmarked.

## Still unexecuted external benchmark gate

1. Prepare real Japanese interview/fire-investigation-like audio recordings.
2. Create Human Reference transcripts, speaker segments, and uncertainty markers.
3. Generate Local STT/diarization Hypothesis JSON.
4. Build Dataset Manifest with recording-condition metadata.
5. Run Benchmark v2.
6. Save Baseline result and all input hashes as Evidence.
7. Human Gate sets acceptance thresholds after seeing the Baseline.

Until this gate is executed, do not report production-quality STT/diarization or validated uncertainty-marker accuracy.


## Persistent Benchmark Run Registry verified

Migration 027:
- `fire_audio_benchmark_runs`

Verified:
- Benchmark v2 result registration
- canonical result JSON SHA-256
- duplicate result idempotency
- Dataset label / Manifest SHA / recording count persistence
- pending Human Review state
- Human baseline decision:
  - accepted_baseline
  - rejected_baseline
- optimistic review conflict protection
- benchmark-run list API
- baseline comparison API
- CER delta
- Speaker Error Rate delta
- uncertainty-marker F1 delta
- dataset-comparability caution in comparison result
- static benchmark routes registered before dynamic fire-investigation case routes

Safety:
- accepted_baseline is comparison-baseline approval only
- it does not mean STT production-quality PASS
- Benchmark Run review does not mutate transcript, statement, timeline, cause, or report state
