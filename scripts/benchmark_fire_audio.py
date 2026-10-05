from __future__ import annotations

import argparse
import json
from pathlib import Path


def levenshtein(ref: list[str], hyp: list[str]) -> tuple[int, int, int]:
    n, m = len(ref), len(hyp)
    dp = [[(0, 0, 0, 0) for _ in range(m + 1)] for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = (i, 0, 0, i)
    for j in range(1, m + 1):
        dp[0][j] = (j, 0, j, 0)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
                continue
            sub = dp[i - 1][j - 1]
            ins = dp[i][j - 1]
            dele = dp[i - 1][j]
            candidates = [
                (sub[0] + 1, sub[1] + 1, sub[2], sub[3]),
                (ins[0] + 1, ins[1], ins[2] + 1, ins[3]),
                (dele[0] + 1, dele[1], dele[2], dele[3] + 1),
            ]
            dp[i][j] = min(candidates, key=lambda x: x[0])
    _, substitutions, insertions, deletions = dp[n][m]
    return substitutions, insertions, deletions


def chars(text: str) -> list[str]:
    return [c for c in text if not c.isspace()]


def score_text(reference: str, hypothesis: str) -> dict:
    ref = chars(reference)
    hyp = chars(hypothesis)
    s, i, d = levenshtein(ref, hyp)
    errors = s + i + d
    return {
        "reference_chars": len(ref),
        "substitutions": s,
        "insertions": i,
        "deletions": d,
        "errors": errors,
        "cer": (errors / len(ref)) if ref else (0.0 if not hyp else 1.0),
    }


def overlap_ms(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def diarization_score(reference: list[dict], hypothesis: list[dict]) -> dict:
    total = 0
    correct = 0
    confusion = 0
    missed = 0
    for ref in reference:
        duration = max(0, int(ref["end_ms"]) - int(ref["start_ms"]))
        total += duration
        covered = 0
        for hyp in hypothesis:
            ov = overlap_ms(
                int(ref["start_ms"]), int(ref["end_ms"]),
                int(hyp["start_ms"]), int(hyp["end_ms"]),
            )
            if not ov:
                continue
            covered += ov
            if str(ref.get("speaker")) == str(hyp.get("speaker")):
                correct += ov
            else:
                confusion += ov
        missed += max(0, duration - min(duration, covered))
    return {
        "reference_ms": total,
        "correct_speaker_ms": correct,
        "speaker_confusion_ms": confusion,
        "missed_ms": missed,
        "speaker_error_rate": ((confusion + missed) / total) if total else 0.0,
    }


def marker_metrics(reference: list[dict], hypothesis: list[dict]) -> dict:
    def key(x: dict) -> tuple:
        return (
            int(x.get("start_ms", -1)),
            int(x.get("end_ms", -1)),
            str(x.get("type", "")),
        )
    ref = {key(x) for x in reference}
    hyp = {key(x) for x in hypothesis}
    tp = len(ref & hyp)
    fp = len(hyp - ref)
    fn = len(ref - hyp)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Score Japanese fire-investigation STT benchmark output.")
    p.add_argument("--reference", required=True)
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--output")
    args = p.parse_args()

    reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
    hypothesis = json.loads(Path(args.hypothesis).read_text(encoding="utf-8"))

    result = {
        "benchmark_format": "fire-ai-japanese-stt-benchmark-v1",
        "text": score_text(
            str(reference.get("transcript_text", "")),
            str(hypothesis.get("transcript_text", "")),
        ),
        "diarization": diarization_score(
            reference.get("speaker_segments") or [],
            hypothesis.get("speaker_segments") or [],
        ),
        "uncertainty_markers": marker_metrics(
            reference.get("uncertainty_markers") or [],
            hypothesis.get("uncertainty_markers") or [],
        ),
        "policy": (
            "Benchmark metrics are evidence only. They do not promote transcript, "
            "statement, timeline, cause, or report evidence to formal status."
        ),
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
