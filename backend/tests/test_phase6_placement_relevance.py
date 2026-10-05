from __future__ import annotations

import json
from pathlib import Path

from app.legal_authoring_import import KNOWN_REVIEW_CATEGORIES
from app.legal_relevance import SCANNER_VERSION, score_fire_service_relevance


def _categories(body: str, *, provision_type: str = "paragraph") -> set[str]:
    return {
        x.category
        for x in score_fire_service_relevance(
            title="消防法施行規則",
            label=None,
            heading=None,
            body=body,
            provision_type=provision_type,
        )
    }


def test_phase6_placement_relevance_requires_equipment_and_placement_cooccurrence():
    categories = _categories(
        "消火器は、各階において歩行距離が二十メートル以下となるよう設置場所を定める。"
    )
    assert "equipment_requirement" in categories
    assert "equipment_placement" in categories

    equipment_only = _categories("当該防火対象物には消火器を設けなければならない。")
    assert "equipment_requirement" in equipment_only
    assert "equipment_placement" not in equipment_only

    placement_only = _categories("出入口付近の見やすい箇所を設置場所とする。")
    assert "equipment_placement" not in placement_only


def test_phase6_placement_relevance_supports_citable_table_rows():
    categories = _categories(
        "自動火災報知設備の表示灯は床面から高さを考慮した見やすい箇所に設置する。",
        provision_type="table_row",
    )
    assert "equipment_placement" in categories


def test_phase6_placement_category_is_importable_and_has_own_authoring_lane():
    assert SCANNER_VERSION == "fire-legal-relevance-v3"
    assert "equipment_placement" in KNOWN_REVIEW_CATEGORIES

    config_path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "legal-rule-authoring"
        / "core-sources.json"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["version"] == "phase6-core-sources-v2"
    assert config["authoring_lanes"]["placement_rules"]["categories"] == [
        "equipment_placement"
    ]
