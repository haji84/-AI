from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


FORMAT_VERSION = "fire-ai-occupancy-classification-worklist-v2"
TARGET_LAW_TITLE = "消防法施行令"
TARGET_APPENDIX_PREFIX = "別表第一"
KANA_RE = re.compile(
    r"^([イロハニホヘトチリヌルヲワカヨタレソツネナラムウヰノオクヤマケフコエテアサキユメミシヱヒモセス])(?:[\s　]+)(.+)$"
)


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


def extract_law_number(root: ET.Element) -> str:
    for node in root.iter():
        if _lname(node.tag) == "LawNum":
            value = _text(node)
            if value:
                return value
    return ""


def _direct_column_sentences(column: ET.Element) -> list[dict]:
    rows: list[dict] = []
    for child in column.iter():
        if _lname(child.tag) != "Sentence":
            continue
        value = _text(child)
        if not value:
            continue
        rows.append(
            {
                "sentence_no": child.attrib.get("Num"),
                "text": value,
            }
        )
    return rows


def _table_rows(node: ET.Element) -> list[dict]:
    rows: list[dict] = []
    for row in node.iter():
        if _lname(row.tag) != "TableRow":
            continue
        columns = [x for x in list(row) if _lname(x.tag) == "TableColumn"]
        if len(columns) < 2:
            columns = [x for x in row.iter() if _lname(x.tag) == "TableColumn"]
        if len(columns) < 2:
            continue

        item_label = _text(columns[0])
        sentences = _direct_column_sentences(columns[1])
        if not item_label or not sentences:
            continue
        rows.append(
            {
                "item_label": item_label,
                "sentences": sentences,
                "cells": [
                    item_label,
                    " ".join(x["text"] for x in sentences),
                ],
            }
        )
    return rows


def _classification_entries(row_no: int, row: dict) -> list[dict]:
    sentences = row["sentences"]
    groups: list[dict] = []
    current: dict | None = None
    has_kana = any(KANA_RE.match(x["text"]) for x in sentences)

    if not has_kana:
        official_text = " ".join(x["text"] for x in sentences)
        classification_code = row["item_label"]
        return [
            {
                "entry_no": 1,
                "classification_code": classification_code,
                "classification_label": sentences[0]["text"],
                "official_text": official_text,
                "detail_sentences": [x["text"] for x in sentences[1:]],
                "source_sentence_numbers": [x["sentence_no"] for x in sentences],
                "proposed_rule_code": f"OCC-S1-R{row_no:02d}-E01",
                "proposed_name": f"令別表第一 {classification_code}",
                "proposed_conditions": {},
                "proposed_outcome": {
                    "decision": "classification_candidate",
                    "classification_code": classification_code,
                    "classification_label": sentences[0]["text"],
                },
                "human_review_status": "pending",
                "conditions_authoring_status": "required",
                "policy": (
                    "Classification identity is copied mechanically from the official table. "
                    "Applicability conditions require Human legal authoring."
                ),
            }
        ]

    for sentence in sentences:
        match = KANA_RE.match(sentence["text"])
        if match:
            if current:
                groups.append(current)
            current = {
                "kana": match.group(1),
                "main_text": match.group(2),
                "sentences": [sentence],
            }
        else:
            if current is None:
                # Defensive preservation for malformed source structure.
                current = {
                    "kana": None,
                    "main_text": sentence["text"],
                    "sentences": [sentence],
                }
            else:
                current["sentences"].append(sentence)
    if current:
        groups.append(current)

    entries = []
    for entry_no, group in enumerate(groups, start=1):
        kana = group["kana"]
        suffix = kana or f"補助{entry_no}"
        classification_code = f'{row["item_label"]}{suffix}'
        source_sentences = group["sentences"]
        official_text = " ".join(x["text"] for x in source_sentences)
        entries.append(
            {
                "entry_no": entry_no,
                "classification_code": classification_code,
                "classification_label": group["main_text"],
                "official_text": official_text,
                "detail_sentences": [x["text"] for x in source_sentences[1:]],
                "source_sentence_numbers": [x["sentence_no"] for x in source_sentences],
                "proposed_rule_code": f"OCC-S1-R{row_no:02d}-E{entry_no:02d}",
                "proposed_name": f"令別表第一 {classification_code}",
                "proposed_conditions": {},
                "proposed_outcome": {
                    "decision": "classification_candidate",
                    "classification_code": classification_code,
                    "classification_label": group["main_text"],
                },
                "human_review_status": "pending",
                "conditions_authoring_status": "required",
                "policy": (
                    "Classification identity is copied mechanically from the official table. "
                    "Applicability conditions require Human legal authoring."
                ),
            }
        )
    return entries


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
    entry_count = 0
    for index, row in enumerate(schedule["rows"], start=1):
        entries = _classification_entries(index, row)
        for entry in entries:
            entry["entry_sha256"] = hashlib.sha256(
                json.dumps(
                    {
                        "classification_code": entry["classification_code"],
                        "official_text": entry["official_text"],
                        "source_sentence_numbers": entry["source_sentence_numbers"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        entry_count += len(entries)

        row_payload = {
            "row_no": index,
            "item_label": row["item_label"],
            "cells": row["cells"],
            "sentences": row["sentences"],
            "classification_entries": entries,
            "domain": "occupancy_classification",
            "human_review_status": "pending",
        }
        row_payload["row_sha256"] = hashlib.sha256(
            json.dumps(
                {
                    "item_label": row_payload["item_label"],
                    "sentences": row_payload["sentences"],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        worklist.append(row_payload)

    return {
        "format": FORMAT_VERSION,
        "law_title": title,
        "law_number": extract_law_number(root),
        "target_appendix": schedule["label"],
        "source_xml_sha256": source_sha,
        "row_count": len(worklist),
        "classification_entry_count": entry_count,
        "rows": worklist,
        "policy": {
            "auto_approve": False,
            "auto_conditions": False,
            "classification_identity_from_official_table": True,
            "human_review_required": True,
            "purpose": (
                "prepare exact official Schedule 1 classification identities and source text "
                "for Human-authored occupancy-classification Rules"
            ),
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
