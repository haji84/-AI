# Phase 6 Drawing Benchmark Hypothesis

This directory is for Local Vision / AI Hypothesis JSON exported from a `DrawingAnalysis`.

## Export

After a DrawingAnalysis has:

- `analysis_method=ai`
- status `analyzed` or `reviewed`
- a non-empty `model_version`

export:

```
GET /drawing-analyses/{analysis_id}/benchmark-hypothesis
```

The export includes:

- source Document ID / filename / SHA-256
- model version
- DrawingAnalysis version/status
- elements
- equipment candidates
- Facility fact candidates
- stable element references

## Baseline pairing

The Human Reference must come from:

```
GET /drawing-annotations/{annotation_id}/benchmark-reference
```

or a repository Reference that has passed the explicit Human acceptance gate.

The evaluator rejects:

- pending Human Reference Drafts
- Reference/Hypothesis source drawing SHA-256 mismatch

For `house-plan-001`, save the AI export as:

```
benchmarks/phase6/hypothesis/house-plan-001.hypothesis.json
```

and use the manifest template at:

```
benchmarks/phase6/house-plan-001.baseline-manifest.template.json
```
