from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


FORMAT_VERSION = "fire-ai-evidence-comparison-benchmark-v1"


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _comparisons(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("comparisons"), list):
        return payload["comparisons"]
    raise ValueError("benchmark payload must be a list or an object with comparisons[]")


def _normalized_ref(ref: dict) -> str:
    if not isinstance(ref, dict):
        raise ValueError("evidence ref must be an object")
    ref_type = str(ref.get("type", "")).strip()
    ref_id = str(ref.get("id", "")).strip()
    if not ref_type or not ref_id:
        raise ValueError("evidence ref requires non-empty type and id")
    return f"{ref_type}:{ref_id}"


def comparison_key(row: dict) -> tuple[str, str, str]:
    issue_type = str(row.get("issue_type", "")).strip()
    if not issue_type:
        raise ValueError("comparison requires non-empty issue_type")
    left = _normalized_ref(row.get("left_ref", {}))
    right = _normalized_ref(row.get("right_ref", {}))
    if left == right:
        raise ValueError("left_ref and right_ref must differ")
    first, second = sorted((left, right))
    return issue_type, first, second


def _prf(true_positive: int, false_positive: int, false_negative: int) -> dict:
    predicted = true_positive + false_positive
    expected = true_positive + false_negative
    precision = true_positive / predicted if predicted else 1.0
    recall = true_positive / expected if expected else 1.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _key_rows(counter: Counter) -> list[dict]:
    rows = []
    for (issue_type, left_ref, right_ref), count in sorted(counter.items()):
        rows.append(
            {
                "issue_type": issue_type,
                "left_ref": left_ref,
                "right_ref": right_ref,
                "count": count,
            }
        )
    return rows


def score_comparisons(reference_rows: list[dict], hypothesis_rows: list[dict]) -> dict:
    reference = Counter(comparison_key(row) for row in reference_rows)
    hypothesis = Counter(comparison_key(row) for row in hypothesis_rows)

    matched = reference & hypothesis
    false_positive = hypothesis - reference
    false_negative = reference - hypothesis

    result = _prf(
        sum(matched.values()),
        sum(false_positive.values()),
        sum(false_negative.values()),
    )
    result.update(
        {
            "reference_count": sum(reference.values()),
            "hypothesis_count": sum(hypothesis.values()),
            "false_positive_candidates": _key_rows(false_positive),
            "false_negative_candidates": _key_rows(false_negative),
        }
    )

    issue_types = sorted(
        {key[0] for key in reference.keys()} | {key[0] for key in hypothesis.keys()}
    )
    by_issue_type = {}
    for issue_type in issue_types:
        ref_count = Counter(
            {key: count for key, count in reference.items() if key[0] == issue_type}
        )
        hyp_count = Counter(
            {key: count for key, count in hypothesis.items() if key[0] == issue_type}
        )
        issue_matched = ref_count & hyp_count
        issue_fp = hyp_count - ref_count
        issue_fn = ref_count - hyp_count
        metrics = _prf(
            sum(issue_matched.values()),
            sum(issue_fp.values()),
            sum(issue_fn.values()),
        )
        metrics["reference_count"] = sum(ref_count.values())
        metrics["hypothesis_count"] = sum(hyp_count.values())
        by_issue_type[issue_type] = metrics

    result["by_issue_type"] = by_issue_type
    return result


def score_pair(
    reference_path: Path,
    hypothesis_path: Path,
    *,
    case_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    reference_payload = _load_json(reference_path)
    hypothesis_payload = _load_json(hypothesis_path)
    metrics = score_comparisons(
        _comparisons(reference_payload),
        _comparisons(hypothesis_payload),
    )
    return {
        "case_id": case_id or reference_path.stem,
        "metadata": metadata or {},
        "reference": str(reference_path),
        "reference_sha256": _sha256_path(reference_path),
        "hypothesis": str(hypothesis_path),
        "hypothesis_sha256": _sha256_path(hypothesis_path),
        "metrics": metrics,
    }


def _aggregate_case_metrics(cases: list[dict]) -> dict:
    tp = sum(x["metrics"]["true_positive"] for x in cases)
    fp = sum(x["metrics"]["false_positive"] for x in cases)
    fn = sum(x["metrics"]["false_negative"] for x in cases)
    aggregate = _prf(tp, fp, fn)
    aggregate["case_count"] = len(cases)
    aggregate["reference_count"] = sum(
        x["metrics"]["reference_count"] for x in cases
    )
    aggregate["hypothesis_count"] = sum(
        x["metrics"]["hypothesis_count"] for x in cases
    )

    issue_types = sorted(
        {
            issue_type
            for case in cases
            for issue_type in case["metrics"]["by_issue_type"].keys()
        }
    )
    by_issue_type = {}
    for issue_type in issue_types:
        issue_tp = issue_fp = issue_fn = issue_ref = issue_hyp = 0
        for case in cases:
            row = case["metrics"]["by_issue_type"].get(issue_type)
            if not row:
                continue
            issue_tp += row["true_positive"]
            issue_fp += row["false_positive"]
            issue_fn += row["false_negative"]
            issue_ref += row["reference_count"]
            issue_hyp += row["hypothesis_count"]
        metrics = _prf(issue_tp, issue_fp, issue_fn)
        metrics["reference_count"] = issue_ref
        metrics["hypothesis_count"] = issue_hyp
        by_issue_type[issue_type] = metrics
    aggregate["by_issue_type"] = by_issue_type
    return aggregate


def score_manifest(manifest_path: Path) -> dict:
    manifest = _load_json(manifest_path)
    rows = manifest.get("cases", [])
    if not isinstance(rows, list) or not rows:
        raise ValueError("manifest requires non-empty cases[]")

    base = manifest_path.parent
    cases = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("manifest cases[] entries must be objects")
        reference = row.get("reference")
        hypothesis = row.get("hypothesis")
        if not reference or not hypothesis:
            raise ValueError("each manifest case requires reference and hypothesis")
        cases.append(
            score_pair(
                (base / reference).resolve(),
                (base / hypothesis).resolve(),
                case_id=str(row.get("id") or f"case-{index + 1}"),
                metadata=row.get("metadata") or {},
            )
        )

    return {
        "benchmark_format": FORMAT_VERSION,
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256_path(manifest_path),
        "cases": cases,
        "aggregate": _aggregate_case_metrics(cases),
        "policy": (
            "Benchmark evidence only. Human review decides usefulness and acceptance "
            "thresholds; benchmark output cannot promote formal evidence or fire cause."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark fire-investigation evidence-comparison candidates."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest", type=Path)
    mode.add_argument("--reference", type=Path)
    parser.add_argument("--hypothesis", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.manifest:
        result = score_manifest(args.manifest)
    else:
        if not args.hypothesis:
            parser.error("--hypothesis is required with --reference")
        pair = score_pair(args.reference, args.hypothesis)
        result = {
            "benchmark_format": FORMAT_VERSION,
            "cases": [pair],
            "aggregate": _aggregate_case_metrics([pair]),
            "policy": (
                "Benchmark evidence only. Human review decides usefulness and "
                "acceptance thresholds."
            ),
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
