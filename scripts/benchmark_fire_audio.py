from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Iterable


FORMAT_VERSION = "fire-ai-japanese-stt-benchmark-v2"


def levenshtein(ref: list[str], hyp: list[str]) -> tuple[int, int, int]:
    n, m = len(ref), len(hyp)
    previous = [(j, 0, j, 0) for j in range(m + 1)]
    for i in range(1, n + 1):
        current = [(i, 0, 0, i)]
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                current.append(previous[j - 1])
                continue
            sub = previous[j - 1]
            ins = current[j - 1]
            dele = previous[j]
            candidates = [
                (sub[0] + 1, sub[1] + 1, sub[2], sub[3]),
                (ins[0] + 1, ins[1], ins[2] + 1, ins[3]),
                (dele[0] + 1, dele[1], dele[2], dele[3] + 1),
            ]
            current.append(min(candidates, key=lambda x: x[0]))
        previous = current
    _, substitutions, insertions, deletions = previous[m]
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
        "hypothesis_chars": len(hyp),
        "substitutions": s,
        "insertions": i,
        "deletions": d,
        "errors": errors,
        "cer": (errors / len(ref)) if ref else (0.0 if not hyp else 1.0),
    }


def _normalized_segments(rows: Iterable[dict]) -> list[dict]:
    out = []
    for row in rows:
        start = int(row.get("start_ms", 0))
        end = int(row.get("end_ms", 0))
        if end <= start:
            continue
        out.append(
            {
                "start_ms": start,
                "end_ms": end,
                "speaker": str(row.get("speaker", "")),
            }
        )
    return out


def _speaker_at(segments: list[dict], start: int, end: int) -> str | None:
    best = None
    best_overlap = 0
    for row in segments:
        overlap = max(0, min(end, row["end_ms"]) - max(start, row["start_ms"]))
        if overlap > best_overlap:
            best_overlap = overlap
            best = row["speaker"]
    return best


def _speaker_overlap_matrix(reference: list[dict], hypothesis: list[dict]) -> dict[tuple[str, str], int]:
    boundaries = sorted(
        {
            x
            for row in [*reference, *hypothesis]
            for x in (row["start_ms"], row["end_ms"])
        }
    )
    matrix: dict[tuple[str, str], int] = {}
    for a, b in zip(boundaries, boundaries[1:]):
        if b <= a:
            continue
        rs = _speaker_at(reference, a, b)
        hs = _speaker_at(hypothesis, a, b)
        if rs is None or hs is None:
            continue
        matrix[(rs, hs)] = matrix.get((rs, hs), 0) + (b - a)
    return matrix


def _best_speaker_mapping(reference: list[dict], hypothesis: list[dict]) -> dict[str, str]:
    ref_labels = sorted({x["speaker"] for x in reference if x["speaker"]})
    hyp_labels = sorted({x["speaker"] for x in hypothesis if x["speaker"]})
    if not ref_labels or not hyp_labels:
        return {}

    matrix = _speaker_overlap_matrix(reference, hypothesis)
    n_ref = len(ref_labels)
    n_hyp = len(hyp_labels)

    # Exact DP assignment for ordinary interview sizes. Extra hypothesis speakers remain unmapped.
    if max(n_ref, n_hyp) <= 12:
        if n_hyp <= n_ref:
            # Assign each hypothesis speaker to a unique reference speaker.
            dp: dict[tuple[int, int], tuple[int, tuple[int, ...]]] = {(0, 0): (0, ())}
            for hi, h in enumerate(hyp_labels):
                nxt: dict[tuple[int, int], tuple[int, tuple[int, ...]]] = {}
                for (_idx, mask), (score, assignment) in dp.items():
                    for ri, r in enumerate(ref_labels):
                        if mask & (1 << ri):
                            continue
                        key = (hi + 1, mask | (1 << ri))
                        value = (score + matrix.get((r, h), 0), assignment + (ri,))
                        if key not in nxt or value[0] > nxt[key][0]:
                            nxt[key] = value
                dp = nxt
            best = max(dp.values(), key=lambda x: x[0], default=(0, ()))
            return {
                hyp_labels[hi]: ref_labels[ri]
                for hi, ri in enumerate(best[1])
            }

        # More hypothesis speakers than reference speakers: assign each reference
        # speaker to one unique hypothesis speaker and leave extra hypothesis labels unmapped.
        dp2: dict[int, tuple[int, tuple[int, ...]]] = {0: (0, ())}
        for ri, r in enumerate(ref_labels):
            nxt2: dict[int, tuple[int, tuple[int, ...]]] = {}
            for mask, (score, assignment) in dp2.items():
                for hi, h in enumerate(hyp_labels):
                    if mask & (1 << hi):
                        continue
                    new_mask = mask | (1 << hi)
                    value = (
                        score + matrix.get((r, h), 0),
                        assignment + (hi,),
                    )
                    if new_mask not in nxt2 or value[0] > nxt2[new_mask][0]:
                        nxt2[new_mask] = value
            dp2 = nxt2
        best = max(dp2.values(), key=lambda x: x[0], default=(0, ()))
        return {
            hyp_labels[hi]: ref_labels[ri]
            for ri, hi in enumerate(best[1])
        }

    # Large-speaker fallback: deterministic greedy maximum-overlap matching.
    pairs = sorted(
        (
            (ms, r, h)
            for (r, h), ms in matrix.items()
        ),
        reverse=True,
    )
    used_r: set[str] = set()
    used_h: set[str] = set()
    mapping: dict[str, str] = {}
    for _ms, r, h in pairs:
        if r in used_r or h in used_h:
            continue
        mapping[h] = r
        used_r.add(r)
        used_h.add(h)
    return mapping


def diarization_score(
    reference: list[dict],
    hypothesis: list[dict],
    *,
    auto_map_speakers: bool = True,
) -> dict:
    ref = _normalized_segments(reference)
    hyp = _normalized_segments(hypothesis)
    mapping = _best_speaker_mapping(ref, hyp) if auto_map_speakers else {
        x["speaker"]: x["speaker"] for x in hyp
    }

    boundaries = sorted(
        {
            x
            for row in [*ref, *hyp]
            for x in (row["start_ms"], row["end_ms"])
        }
    )
    reference_ms = 0
    correct = 0
    confusion = 0
    missed = 0
    false_alarm = 0

    for a, b in zip(boundaries, boundaries[1:]):
        duration = b - a
        if duration <= 0:
            continue
        rs = _speaker_at(ref, a, b)
        hs_raw = _speaker_at(hyp, a, b)
        hs = mapping.get(hs_raw) if hs_raw is not None else None

        if rs is not None:
            reference_ms += duration
            if hs_raw is None:
                missed += duration
            elif hs == rs:
                correct += duration
            else:
                confusion += duration
        elif hs_raw is not None:
            false_alarm += duration

    error_ms = confusion + missed + false_alarm
    return {
        "reference_ms": reference_ms,
        "correct_speaker_ms": correct,
        "speaker_confusion_ms": confusion,
        "missed_ms": missed,
        "false_alarm_ms": false_alarm,
        "speaker_error_ms": error_ms,
        "speaker_error_rate": (error_ms / reference_ms) if reference_ms else (0.0 if not hyp else 1.0),
        "speaker_mapping": mapping,
        "speaker_mapping_mode": "auto_overlap" if auto_map_speakers else "identity",
    }


def _marker_match(a: dict, b: dict, tolerance_ms: int) -> bool:
    return (
        str(a.get("type", "")) == str(b.get("type", ""))
        and abs(int(a.get("start_ms", -1)) - int(b.get("start_ms", -1))) <= tolerance_ms
        and abs(int(a.get("end_ms", -1)) - int(b.get("end_ms", -1))) <= tolerance_ms
    )


def marker_metrics(
    reference: list[dict],
    hypothesis: list[dict],
    *,
    tolerance_ms: int = 0,
) -> dict:
    ref = list(reference)
    hyp = list(hypothesis)

    # Maximum bipartite matching prevents one hypothesis marker from satisfying several references.
    edges = {
        ri: [hi for hi, h in enumerate(hyp) if _marker_match(r, h, tolerance_ms)]
        for ri, r in enumerate(ref)
    }
    matched_h: dict[int, int] = {}

    def augment(ri: int, seen: set[int]) -> bool:
        for hi in edges.get(ri, []):
            if hi in seen:
                continue
            seen.add(hi)
            if hi not in matched_h or augment(matched_h[hi], seen):
                matched_h[hi] = ri
                return True
        return False

    tp = sum(1 for ri in range(len(ref)) if augment(ri, set()))
    fp = len(hyp) - tp
    fn = len(ref) - tp
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "reference_markers": len(ref),
        "hypothesis_markers": len(hyp),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tolerance_ms": tolerance_ms,
    }


def validate_payload(payload: dict, label: str) -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    if "transcript_text" not in payload:
        raise ValueError(f"{label}.transcript_text is required")
    for key in ("speaker_segments", "uncertainty_markers"):
        value = payload.get(key, [])
        if not isinstance(value, list):
            raise ValueError(f"{label}.{key} must be an array")
        for index, row in enumerate(value):
            if not isinstance(row, dict):
                raise ValueError(f"{label}.{key}[{index}] must be an object")
            start = int(row.get("start_ms", -1))
            end = int(row.get("end_ms", -1))
            if start < 0 or end <= start:
                raise ValueError(f"{label}.{key}[{index}] has invalid time range")


def score_recording(
    reference: dict,
    hypothesis: dict,
    *,
    marker_tolerance_ms: int = 0,
    auto_map_speakers: bool = True,
) -> dict:
    validate_payload(reference, "reference")
    validate_payload(hypothesis, "hypothesis")
    return {
        "text": score_text(
            str(reference.get("transcript_text", "")),
            str(hypothesis.get("transcript_text", "")),
        ),
        "diarization": diarization_score(
            reference.get("speaker_segments") or [],
            hypothesis.get("speaker_segments") or [],
            auto_map_speakers=auto_map_speakers,
        ),
        "uncertainty_markers": marker_metrics(
            reference.get("uncertainty_markers") or [],
            hypothesis.get("uncertainty_markers") or [],
            tolerance_ms=marker_tolerance_ms,
        ),
    }


def aggregate_results(results: list[dict]) -> dict:
    text_ref = sum(x["text"]["reference_chars"] for x in results)
    text_errors = sum(x["text"]["errors"] for x in results)
    text_s = sum(x["text"]["substitutions"] for x in results)
    text_i = sum(x["text"]["insertions"] for x in results)
    text_d = sum(x["text"]["deletions"] for x in results)

    ref_ms = sum(x["diarization"]["reference_ms"] for x in results)
    confusion = sum(x["diarization"]["speaker_confusion_ms"] for x in results)
    missed = sum(x["diarization"]["missed_ms"] for x in results)
    false_alarm = sum(x["diarization"]["false_alarm_ms"] for x in results)
    correct = sum(x["diarization"]["correct_speaker_ms"] for x in results)

    marker_tp = sum(x["uncertainty_markers"]["true_positive"] for x in results)
    marker_fp = sum(x["uncertainty_markers"]["false_positive"] for x in results)
    marker_fn = sum(x["uncertainty_markers"]["false_negative"] for x in results)
    precision = marker_tp / (marker_tp + marker_fp) if marker_tp + marker_fp else 1.0
    recall = marker_tp / (marker_tp + marker_fn) if marker_tp + marker_fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    diar_errors = confusion + missed + false_alarm
    return {
        "recording_count": len(results),
        "text_micro": {
            "reference_chars": text_ref,
            "substitutions": text_s,
            "insertions": text_i,
            "deletions": text_d,
            "errors": text_errors,
            "cer": (text_errors / text_ref) if text_ref else 0.0,
        },
        "diarization_micro": {
            "reference_ms": ref_ms,
            "correct_speaker_ms": correct,
            "speaker_confusion_ms": confusion,
            "missed_ms": missed,
            "false_alarm_ms": false_alarm,
            "speaker_error_ms": diar_errors,
            "speaker_error_rate": (diar_errors / ref_ms) if ref_ms else 0.0,
        },
        "uncertainty_markers_micro": {
            "true_positive": marker_tp,
            "false_positive": marker_fp,
            "false_negative": marker_fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        },
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def score_manifest(
    manifest_path: Path,
    *,
    marker_tolerance_ms: int | None = None,
    auto_map_speakers: bool = True,
) -> dict:
    manifest = _read_json(manifest_path)
    records = manifest.get("recordings")
    if not isinstance(records, list) or not records:
        raise ValueError("manifest.recordings must be a non-empty array")
    base = manifest_path.parent
    tolerance = (
        int(marker_tolerance_ms)
        if marker_tolerance_ms is not None
        else int(manifest.get("marker_tolerance_ms", 0))
    )
    output = []
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            raise ValueError(f"manifest.recordings[{index}] must be an object")
        ref_path = (base / str(item["reference"])).resolve()
        hyp_path = (base / str(item["hypothesis"])).resolve()
        result = score_recording(
            _read_json(ref_path),
            _read_json(hyp_path),
            marker_tolerance_ms=tolerance,
            auto_map_speakers=auto_map_speakers,
        )
        output.append(
            {
                "recording_id": str(item.get("id") or f"recording-{index + 1}"),
                "reference": str(item["reference"]),
                "hypothesis": str(item["hypothesis"]),
                **result,
            }
        )
    return {
        "benchmark_format": FORMAT_VERSION,
        "marker_tolerance_ms": tolerance,
        "speaker_mapping": "auto_overlap" if auto_map_speakers else "identity",
        "recordings": output,
        "aggregate": aggregate_results(output),
        "policy": (
            "Benchmark metrics are evidence only. They do not promote transcript, "
            "statement, timeline, cause, or report evidence to formal status."
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Score Japanese fire-investigation STT benchmark output.")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest")
    source.add_argument("--reference")
    p.add_argument("--hypothesis")
    p.add_argument("--marker-tolerance-ms", type=int)
    p.add_argument("--no-auto-speaker-map", action="store_true")
    p.add_argument("--output")
    args = p.parse_args()

    auto_map = not args.no_auto_speaker_map
    if args.manifest:
        result = score_manifest(
            Path(args.manifest),
            marker_tolerance_ms=args.marker_tolerance_ms,
            auto_map_speakers=auto_map,
        )
    else:
        if not args.hypothesis:
            p.error("--hypothesis is required with --reference")
        tolerance = args.marker_tolerance_ms or 0
        reference = _read_json(Path(args.reference))
        hypothesis = _read_json(Path(args.hypothesis))
        result = {
            "benchmark_format": FORMAT_VERSION,
            "marker_tolerance_ms": tolerance,
            "speaker_mapping": "auto_overlap" if auto_map else "identity",
            **score_recording(
                reference,
                hypothesis,
                marker_tolerance_ms=tolerance,
                auto_map_speakers=auto_map,
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
