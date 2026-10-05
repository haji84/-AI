from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


FORMAT_VERSION = "fire-ai-occupancy-classification-worklist-v1"
TARGET_LAW_TITLE = "消防法施行令"
TARGET_APPENDIX_PREFIX = "別表第一"


def _lname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _norm(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"[\s　]+", " ", text).strip()


def _text(node: ET.Element) -> str:
    return _norm("".join(node.itertext()))


def _first_descendant_text(node: ET.Element, local_name: str) -> str:
    for child in node.iter():
        if _lname(child.tag) == local_name:
            value = _text(child)
            if value:
                return value
    return ""


def extract_law_title(root: ET.Element) -> str:
    for node in root.iter():
        if _lname(node.tag) == "LawTitle":
            value = _text(node)
            if value:
                return value
    return ""


def _table_rows(node: ET.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in node.iter():
        if _lname(row.tag) != "TableRow":
            continue
        cells = []
        for cell in row:
            if _lname(cell.tag) == "TableColumn":
                cells.append(_text(cell))
        if not cells:
            cells = [
                _text(cell)
                for cell in row.iter()
                if _lname(cell.tag) == "TableColumn"
            ]
        if any(cells):
            rows.append(cells)
    return rows


def extract_schedule_one(data: bytes) -> dict:
    root = ET.fromstring(data)
    title = extract_law_title(root)
    if title != TARGET_LAW_TITLE:
        raise ValueError(f"unexpected law title: {title!r}")

    matches = []
    for node in root.iter():
        if _lname(node.tag) != "AppdxTable":
            continue
        label = _first_descendant_text(node, "AppdxTableTitle")
        if not label.startswith(TARGET_APPENDIX_PREFIX):
            continue
        rows = _table_rows(node)
        matches.append(
            {
                "label": label,
                "xml_attributes": dict(node.attrib),
                "rows": rows,
                "body_text": _text(node),
            }
        )

    if not matches:
        raise ValueError("消防法施行令の別表第一 AppdxTable が見つかりません")
    if len(matches) > 1:
        raise ValueError(f"別表第一 AppdxTable が複数見つかりました: {len(matches)}")

    schedule = matches[0]
    if not schedule["rows"]:
        raise ValueError("別表第一のTableRowが0件です")

    source_sha = hashlib.sha256(data).hexdigest()
    worklist = []
    for index, cells in enumerate(schedule["rows"], start=1):
        normalized = [c for c in cells if c]
        if not normalized:
            continue
        worklist.append(
            {
                "row_no": index,
                "cells": cells,
                "row_sha256": hashlib.sha256(
                    json.dumps(cells, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "domain": "occupancy_classification",
                "human_review_status": "pending",
                "proposed_rule_code": None,
                "proposed_name": None,
                "proposed_conditions": {},
                "proposed_outcome": {},
                "policy": "No automatic conditions/outcome generation. Human legal authoring required.",
            }
        )

    return {
        "format": FORMAT_VERSION,
        "law_title": title,
        "target_appendix": schedule["label"],
        "source_xml_sha256": source_sha,
        "row_count": len(worklist),
        "rows": worklist,
        "raw_table_body": schedule["body_text"],
        "policy": {
            "auto_approve": False,
            "auto_classification_rule": False,
            "human_review_required": True,
            "purpose": "prepare exact official Schedule 1 rows for occupancy-classification Rule authoring",
        },
    }


def find_target_xml(root_dir: Path) -> tuple[Path, bytes]:
    candidates = sorted(root_dir.rglob("*.xml"))
    if not candidates:
        raise ValueError(f"XML files not found under {root_dir}")
    for path in candidates:
        data = path.read_bytes()
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            continue
        if extract_law_title(root) == TARGET_LAW_TITLE:
            return path, data
    raise ValueError(f"{TARGET_LAW_TITLE} XML not found")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a Human-review worklist from 消防法施行令 別表第一."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--xml", type=Path)
    source.add_argument("--root-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.xml:
        source_path = args.xml
        data = source_path.read_bytes()
    else:
        source_path, data = find_target_xml(args.root_dir)

    result = extract_schedule_one(data)
    result["source_path"] = str(source_path)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
