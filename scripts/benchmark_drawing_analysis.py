from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.drawing_benchmark_core import (  # noqa: E402
    FORMAT_VERSION,
    aggregate_drawings,
    require_human_accepted_reference,
    require_same_source_drawing,
    score_drawing,
    score_payload_pair,
)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_human_accepted_reference(payload: dict) -> None:
    require_human_accepted_reference(payload)


def _require_same_source_drawing(
    reference: dict,
    hypothesis: dict,
) -> None:
    require_same_source_drawing(reference, hypothesis)


def score_pair(
    reference_path: Path,
    hypothesis_path: Path,
    *,
    drawing_id: str | None = None,
    metadata: dict | None = None,
    iou_threshold: float = 0.5,
) -> dict:
    reference = _load_json(reference_path)
    hypothesis = _load_json(hypothesis_path)
    pair = score_payload_pair(
        reference,
        hypothesis,
        drawing_id=drawing_id or reference_path.stem,
        metadata=metadata,
        iou_threshold=iou_threshold,
    )
    pair["reference"] = str(reference_path)
    pair["reference_sha256"] = _sha256_path(reference_path)
    pair["hypothesis"] = str(hypothesis_path)
    pair["hypothesis_sha256"] = _sha256_path(
        hypothesis_path
    )
    return pair


def _aggregate(
    drawings: list[dict],
    iou_threshold: float,
) -> dict:
    return aggregate_drawings(
        drawings,
        iou_threshold,
    )


def score_manifest(manifest_path: Path) -> dict:
    manifest = _load_json(manifest_path)
    drawings = manifest.get("drawings")
    if not isinstance(drawings, list) or not drawings:
        raise ValueError(
            "manifest requires non-empty drawings[]"
        )
    threshold = float(
        manifest.get("iou_threshold", 0.5)
    )
    if not 0 < threshold <= 1:
        raise ValueError(
            "iou_threshold must be > 0 and <= 1"
        )

    base = manifest_path.parent
    results = []
    for index, row in enumerate(drawings):
        if (
            not isinstance(row, dict)
            or not row.get("reference")
            or not row.get("hypothesis")
        ):
            raise ValueError(
                "each drawings[] entry requires "
                "reference and hypothesis"
            )
        results.append(
            score_pair(
                (base / row["reference"]).resolve(),
                (base / row["hypothesis"]).resolve(),
                drawing_id=str(
                    row.get("id")
                    or f"drawing-{index + 1}"
                ),
                metadata=row.get("metadata") or {},
                iou_threshold=threshold,
            )
        )
    return {
        "benchmark_format": FORMAT_VERSION,
        "manifest": str(manifest_path),
        "manifest_sha256":
            _sha256_path(manifest_path),
        "iou_threshold": threshold,
        "drawings": results,
        "aggregate":
            aggregate_drawings(results, threshold),
        "policy": (
            "Benchmark evidence only. Human review "
            "sets acceptance thresholds and controls "
            "any production use."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark Local AI architectural "
            "drawing analysis."
        )
    )
    mode = parser.add_mutually_exclusive_group(
        required=True
    )
    mode.add_argument("--manifest", type=Path)
    mode.add_argument("--reference", type=Path)
    parser.add_argument("--hypothesis", type=Path)
    parser.add_argument(
        "--iou-threshold",
        type=float,
        default=0.5,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    if args.manifest:
        result = score_manifest(args.manifest)
    else:
        if not args.hypothesis:
            parser.error(
                "--hypothesis is required "
                "with --reference"
            )
        pair = score_pair(
            args.reference,
            args.hypothesis,
            iou_threshold=args.iou_threshold,
        )
        result = {
            "benchmark_format": FORMAT_VERSION,
            "iou_threshold": args.iou_threshold,
            "drawings": [pair],
            "aggregate": aggregate_drawings(
                [pair],
                args.iou_threshold,
            ),
            "policy": (
                "Benchmark evidence only. Human "
                "review sets acceptance thresholds."
            ),
        }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
