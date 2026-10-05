# Phase 9 Evidence Comparison Benchmark Contract

Updated: 2026-10-05  
Format: `fire-ai-evidence-comparison-benchmark-v1`

## Purpose

Measure whether Local AI evidence-comparison candidates are useful enough to review without flooding investigators with false positives.

This benchmark evaluates candidate detection only. It must not:

- edit Human-reviewed statements
- alter confirmed timeline events
- select or promote an official fire cause
- turn an AI candidate into formal evidence automatically

## Human Reference

For each investigation case, a Human reviewer creates the expected comparison set.

Each comparison contains:

- `issue_type`
- `left_ref.type`
- `left_ref.id`
- `right_ref.type`
- `right_ref.id`

The left/right order is not semantically significant. A candidate comparing A to B is the same pair as B to A when `issue_type` is identical.

Example:

```json
{
  "comparisons": [
    {
      "issue_type": "time_conflict",
      "left_ref": {"type": "statement", "id": "statement-a"},
      "right_ref": {"type": "timeline_event", "id": "timeline-1"}
    }
  ]
}
```

## Hypothesis

The Local AI output uses the same minimal comparison identity fields. Extra fields such as summary, confidence, evidence refs, or model metadata may be present but do not affect exact candidate matching in v1.

## Metrics

The evaluator performs one-to-one multiset matching on:

```
(issue_type, unordered(left_ref, right_ref))
```

It reports:

- true positives
- false positives
- false negatives
- precision
- recall
- F1
- reference count
- hypothesis count
- metrics by `issue_type`
- false-positive candidate keys
- false-negative candidate keys

Duplicate AI predictions are not collapsed away. Extra duplicates count as false positives.

## Dataset Manifest

```json
{
  "cases": [
    {
      "id": "fire-case-001",
      "reference": "reference/fire-case-001.json",
      "hypothesis": "hypothesis/fire-case-001.json",
      "metadata": {
        "case_kind": "interview-plus-timeline"
      }
    }
  ]
}
```

Paths are relative to the Manifest.

The result records SHA-256 for:

- Manifest
- each Human Reference
- each Hypothesis

## Tool

`scripts/benchmark_fire_evidence_comparison.py`

Single case:

```bash
python scripts/benchmark_fire_evidence_comparison.py \
  --reference reference.json \
  --hypothesis hypothesis.json \
  --output result.json
```

Dataset:

```bash
python scripts/benchmark_fire_evidence_comparison.py \
  --manifest benchmark-manifest.json \
  --output benchmark-result.json
```

## Acceptance Gate

No production threshold is hard-coded in v1.

After a real Human-labeled dataset is collected, Human review must set:

- minimum Precision
- minimum Recall
- minimum F1
- acceptable false positives per case
- issue types allowed in production
- required case-count and case-mix coverage

Until that gate is completed, the system may report benchmark measurements but must not claim production-quality evidence-comparison accuracy.
