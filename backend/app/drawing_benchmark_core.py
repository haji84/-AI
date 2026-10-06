from __future__ import annotations

import hashlib
import json
from collections import Counter


FORMAT_VERSION = "fire-ai-drawing-benchmark-v1"


def canonical_json_sha(payload) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def require_human_accepted_reference(payload: dict) -> None:
    fmt = payload.get("reference_format")
    if not isinstance(fmt, str) or not fmt.startswith(
        "fire-ai-drawing-human-reference"
    ):
        return

    status = str(payload.get("reference_status") or "").strip()
    human_review = payload.get("human_review")
    reviewed_export = bool(
        isinstance(human_review, dict)
        and human_review.get("status") == "reviewed"
    )
    accepted = status == "human_accepted" or reviewed_export
    human_gate = payload.get("human_gate")
    if (
        status == "human_accepted"
        and isinstance(human_gate, dict)
        and human_gate.get("required") is True
        and human_gate.get("accepted") is not True
    ):
        accepted = False

    if not accepted:
        raise ValueError(
            "Human-accepted drawing reference is required before benchmark "
            "execution; current reference_status="
            f"{status or 'missing'}"
        )


def source_sha(payload: dict) -> str | None:
    source = payload.get("source")
    if not isinstance(source, dict):
        return None
    value = source.get("sha256")
    return str(value).strip() if value else None


def require_same_source_drawing(
    reference: dict,
    hypothesis: dict,
) -> None:
    ref_sha = source_sha(reference)
    hyp_sha = source_sha(hypothesis)
    if ref_sha and hyp_sha and ref_sha != hyp_sha:
        raise ValueError(
            "Reference/Hypothesis source drawing SHA-256 mismatch: "
            f"{ref_sha} != {hyp_sha}"
        )


def _rows(payload: dict, key: str) -> list[dict]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _bbox(
    geometry: dict,
) -> tuple[float, float, float, float] | None:
    if not isinstance(geometry, dict):
        return None
    if all(k in geometry for k in ("x", "y", "width", "height")):
        x = float(geometry["x"])
        y = float(geometry["y"])
        w = float(geometry["width"])
        h = float(geometry["height"])
        if w <= 0 or h <= 0:
            return None
        return x, y, x + w, y + h
    if all(k in geometry for k in ("x1", "y1", "x2", "y2")):
        x1, y1, x2, y2 = map(
            float,
            (
                geometry["x1"],
                geometry["y1"],
                geometry["x2"],
                geometry["y2"],
            ),
        )
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2
    bbox = geometry.get("bbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        x, y, w, h = map(float, bbox)
        if w <= 0 or h <= 0:
            return None
        return x, y, x + w, y + h
    points = geometry.get("points")
    if isinstance(points, list) and points:
        coords = []
        for point in points:
            if (
                isinstance(point, dict)
                and "x" in point
                and "y" in point
            ):
                coords.append(
                    (float(point["x"]), float(point["y"]))
                )
            elif (
                isinstance(point, (list, tuple))
                and len(point) >= 2
            ):
                coords.append(
                    (float(point[0]), float(point[1]))
                )
        if coords:
            xs = [p[0] for p in coords]
            ys = [p[1] for p in coords]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            if x2 > x1 and y2 > y1:
                return x1, y1, x2, y2
    return None


def bbox_iou(left: dict, right: dict) -> float:
    a = _bbox(left)
    b = _bbox(right)
    if a is None or b is None:
        return 0.0
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def _prf(tp: int, fp: int, fn: int) -> dict:
    if tp == 0 and fp == 0 and fn == 0:
        return {
            "true_positive": 0,
            "false_positive": 0,
            "false_negative": 0,
            "precision": None,
            "recall": None,
            "f1": None,
            "applicable": False,
        }

    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    if precision is None or recall is None:
        f1 = 0.0
    else:
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "applicable": True,
    }


def _match_elements(
    reference: list[dict],
    hypothesis: list[dict],
    iou_threshold: float,
):
    candidates: dict[int, list[tuple[int, float]]] = {}
    for ri, ref in enumerate(reference):
        page = int(ref.get("page_no", 1))
        hits = []
        for hi, hyp in enumerate(hypothesis):
            if int(hyp.get("page_no", 1)) != page:
                continue
            score = bbox_iou(
                ref.get("geometry") or {},
                hyp.get("geometry") or {},
            )
            if score >= iou_threshold:
                hits.append((hi, score))
        hits.sort(key=lambda x: (-x[1], x[0]))
        candidates[ri] = hits

    hyp_to_ref: dict[int, int] = {}

    def assign(ri: int, seen: set[int]) -> bool:
        for hi, _score in candidates[ri]:
            if hi in seen:
                continue
            seen.add(hi)
            old = hyp_to_ref.get(hi)
            if old is None or assign(old, seen):
                hyp_to_ref[hi] = ri
                return True
        return False

    for ri in sorted(
        candidates,
        key=lambda x: (len(candidates[x]), x),
    ):
        assign(ri, set())

    ref_to_hyp = {
        ri: hi for hi, ri in hyp_to_ref.items()
    }
    pairs = []
    for ri, hi in sorted(ref_to_hyp.items()):
        pairs.append(
            (
                ri,
                hi,
                bbox_iou(
                    reference[ri].get("geometry") or {},
                    hypothesis[hi].get("geometry") or {},
                ),
            )
        )
    return pairs


def _symbol_code(row: dict) -> str | None:
    direct = row.get("symbol_code")
    if direct not in (None, ""):
        return str(direct)
    data = row.get("extracted_data")
    if (
        isinstance(data, dict)
        and data.get("symbol") not in (None, "")
    ):
        return str(data["symbol"])
    return None


def _ref_id(row: dict, index: int) -> str:
    for key in ("client_ref", "id", "element_id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return f"index:{index}"


def _canonical_value(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _candidate_metrics(
    reference_payload: dict,
    hypothesis_payload: dict,
    element_pairs: list[tuple[int, int, float]],
) -> tuple[dict, dict]:
    ref_elements = _rows(reference_payload, "elements")
    hyp_elements = _rows(hypothesis_payload, "elements")
    hyp_to_ref_index = {
        hi: ri for ri, hi, _ in element_pairs
    }
    ref_id_to_index = {
        _ref_id(row, i): i
        for i, row in enumerate(ref_elements)
    }
    hyp_id_to_index = {
        _ref_id(row, i): i
        for i, row in enumerate(hyp_elements)
    }

    def equipment_keys(
        payload: dict,
        is_hyp: bool,
    ) -> Counter:
        out = Counter()
        rows = _rows(payload, "equipment_candidates")
        index_map = (
            hyp_id_to_index
            if is_hyp
            else ref_id_to_index
        )
        for row in rows:
            code = str(
                row.get("suggested_equipment_type_code")
                or ""
            ).strip()
            if not code:
                code = str(
                    row.get("equipment_type_code")
                    or ""
                ).strip()
            ref = row.get("drawing_element_ref")
            if ref is None:
                ref = row.get("element_ref")
            if (
                ref is not None
                and str(ref) in index_map
            ):
                idx = index_map[str(ref)]
                if is_hyp:
                    idx = hyp_to_ref_index.get(
                        idx,
                        -(idx + 1),
                    )
                key = ("element", idx, code)
            else:
                key = (
                    "fallback",
                    int(row.get("floor_number", 0) or 0),
                    str(
                        row.get("location_text")
                        or ""
                    ).strip(),
                    code,
                )
            out[key] += 1
        return out

    def fact_keys(payload: dict) -> Counter:
        out = Counter()
        for row in _rows(payload, "fact_candidates"):
            target = str(
                row.get("target_path") or ""
            ).strip()
            proposed = row.get("proposed_value")
            out[
                (target, _canonical_value(proposed))
            ] += 1
        return out

    ref_eq = equipment_keys(
        reference_payload,
        False,
    )
    hyp_eq = equipment_keys(
        hypothesis_payload,
        True,
    )
    eq_match = ref_eq & hyp_eq
    equipment = _prf(
        sum(eq_match.values()),
        sum((hyp_eq - ref_eq).values()),
        sum((ref_eq - hyp_eq).values()),
    )

    ref_fact = fact_keys(reference_payload)
    hyp_fact = fact_keys(hypothesis_payload)
    fact_match = ref_fact & hyp_fact
    facts = _prf(
        sum(fact_match.values()),
        sum((hyp_fact - ref_fact).values()),
        sum((ref_fact - hyp_fact).values()),
    )
    return equipment, facts


def score_drawing(
    reference_payload: dict,
    hypothesis_payload: dict,
    iou_threshold: float = 0.5,
) -> dict:
    if not 0 < iou_threshold <= 1:
        raise ValueError(
            "iou_threshold must be > 0 and <= 1"
        )
    reference = _rows(
        reference_payload,
        "elements",
    )
    hypothesis = _rows(
        hypothesis_payload,
        "elements",
    )
    pairs = _match_elements(
        reference,
        hypothesis,
        iou_threshold,
    )

    geometry = _prf(
        len(pairs),
        len(hypothesis) - len(pairs),
        len(reference) - len(pairs),
    )
    geometry["iou_threshold"] = iou_threshold
    geometry["mean_iou"] = (
        sum(x[2] for x in pairs) / len(pairs)
        if pairs
        else None
    )

    type_correct = sum(
        1
        for ri, hi, _ in pairs
        if str(
            reference[ri].get("element_type") or ""
        )
        == str(
            hypothesis[hi].get("element_type") or ""
        )
    )
    geometry["element_type_correct"] = type_correct
    geometry["element_type_accuracy"] = (
        type_correct / len(pairs)
        if pairs
        else None
    )

    symbol_total = 0
    symbol_correct = 0
    for ri, hi, _ in pairs:
        ref_symbol = _symbol_code(reference[ri])
        if ref_symbol is None:
            continue
        symbol_total += 1
        if (
            ref_symbol
            == _symbol_code(hypothesis[hi])
        ):
            symbol_correct += 1
    symbols = {
        "reference_scored": symbol_total,
        "correct": symbol_correct,
        "accuracy": (
            symbol_correct / symbol_total
            if symbol_total
            else None
        ),
        "applicable": symbol_total > 0,
    }

    equipment, facts = _candidate_metrics(
        reference_payload,
        hypothesis_payload,
        pairs,
    )
    return {
        "geometry_detection": geometry,
        "symbol_classification": symbols,
        "equipment_candidates": equipment,
        "fact_candidates": facts,
    }


def aggregate_drawings(
    drawings: list[dict],
    iou_threshold: float,
) -> dict:
    gtp = sum(
        x["metrics"]["geometry_detection"][
            "true_positive"
        ]
        for x in drawings
    )
    gfp = sum(
        x["metrics"]["geometry_detection"][
            "false_positive"
        ]
        for x in drawings
    )
    gfn = sum(
        x["metrics"]["geometry_detection"][
            "false_negative"
        ]
        for x in drawings
    )
    geometry = _prf(gtp, gfp, gfn)
    geometry["iou_threshold"] = iou_threshold
    weighted_iou = sum(
        (
            x["metrics"]["geometry_detection"][
                "mean_iou"
            ]
            or 0.0
        )
        * x["metrics"]["geometry_detection"][
            "true_positive"
        ]
        for x in drawings
    )
    geometry["mean_iou"] = (
        weighted_iou / gtp
        if gtp
        else None
    )
    type_correct = sum(
        x["metrics"]["geometry_detection"][
            "element_type_correct"
        ]
        for x in drawings
    )
    geometry["element_type_correct"] = type_correct
    geometry["element_type_accuracy"] = (
        type_correct / gtp
        if gtp
        else None
    )

    symbol_total = sum(
        x["metrics"]["symbol_classification"][
            "reference_scored"
        ]
        for x in drawings
    )
    symbol_correct = sum(
        x["metrics"]["symbol_classification"][
            "correct"
        ]
        for x in drawings
    )

    def sum_prf(key: str):
        tp = sum(
            x["metrics"][key]["true_positive"]
            for x in drawings
        )
        fp = sum(
            x["metrics"][key]["false_positive"]
            for x in drawings
        )
        fn = sum(
            x["metrics"][key]["false_negative"]
            for x in drawings
        )
        return _prf(tp, fp, fn)

    return {
        "drawing_count": len(drawings),
        "geometry_detection": geometry,
        "symbol_classification": {
            "reference_scored": symbol_total,
            "correct": symbol_correct,
            "accuracy": (
                symbol_correct / symbol_total
                if symbol_total
                else None
            ),
            "applicable": symbol_total > 0,
        },
        "equipment_candidates":
            sum_prf("equipment_candidates"),
        "fact_candidates":
            sum_prf("fact_candidates"),
    }


def score_payload_pair(
    reference: dict,
    hypothesis: dict,
    *,
    drawing_id: str,
    metadata: dict | None = None,
    iou_threshold: float = 0.5,
) -> dict:
    require_human_accepted_reference(reference)
    require_same_source_drawing(
        reference,
        hypothesis,
    )
    return {
        "drawing_id": drawing_id,
        "metadata": metadata or {},
        "reference_sha256":
            canonical_json_sha(reference),
        "hypothesis_sha256":
            canonical_json_sha(hypothesis),
        "metrics": score_drawing(
            reference,
            hypothesis,
            iou_threshold,
        ),
    }
