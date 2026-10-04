from __future__ import annotations

from dataclasses import dataclass


SCANNER_VERSION = "fire-legal-relevance-v1"

CATEGORY_KEYWORDS: dict[str, dict[str, float]] = {
    "equipment_requirement": {
        "消防用設備": 4.0,
        "消火器": 3.0,
        "屋内消火栓": 4.0,
        "屋外消火栓": 4.0,
        "スプリンクラー": 4.0,
        "自動火災報知設備": 4.0,
        "消防機関へ通報する火災報知設備": 4.0,
        "非常警報設備": 3.0,
        "避難器具": 3.0,
        "誘導灯": 3.0,
        "誘導標識": 3.0,
        "連結送水管": 4.0,
        "排煙設備": 3.0,
        "防火水槽": 3.0,
        "無窓階": 3.0,
    },
    "submission_requirement": {
        "届出": 3.0,
        "届出書": 3.0,
        "報告": 2.0,
        "点検結果報告": 4.0,
        "消防計画": 4.0,
        "選任": 2.5,
        "解任": 2.5,
        "使用開始": 3.0,
        "提出": 2.0,
        "申請": 2.0,
    },
    "fire_management": {
        "防火管理者": 4.0,
        "統括防火管理者": 4.0,
        "防災管理者": 4.0,
        "消防計画": 3.0,
        "自衛消防組織": 3.0,
        "訓練": 1.5,
    },
    "inspection_enforcement": {
        "査察": 4.0,
        "立入検査": 4.0,
        "違反": 3.0,
        "命令": 2.5,
        "公表": 2.0,
        "改善": 1.5,
        "是正": 2.5,
    },
    "hazardous_materials": {
        "危険物": 4.0,
        "指定数量": 3.0,
        "製造所": 2.5,
        "貯蔵所": 2.5,
        "取扱所": 2.5,
        "少量危険物": 3.0,
    },
    "fire_prevention_local": {
        "火災予防条例": 4.0,
        "火気": 2.5,
        "喫煙": 2.0,
        "裸火": 2.0,
        "催物": 2.0,
        "露店": 2.0,
        "防炎": 2.5,
    },
}

NEGATIVE_HINTS = {
    "給与", "旅費", "退職手当", "人事", "職員定数", "会計年度任用職員",
}


@dataclass(frozen=True)
class RelevanceHit:
    category: str
    score: float
    reasons: list[str]


def score_fire_service_relevance(
    *,
    title: str | None,
    label: str | None,
    heading: str | None,
    body: str | None,
    provision_type: str | None,
) -> list[RelevanceHit]:
    text = "\n".join(x for x in [title, label, heading, body] if x)
    title_text = title or ""
    hits: list[RelevanceHit] = []

    negative_penalty = 1.5 if any(x in title_text for x in NEGATIVE_HINTS) else 0.0
    type_boost = 0.25 if provision_type in {"article", "paragraph", "item", "document_body"} else 0.0

    for category, weighted in CATEGORY_KEYWORDS.items():
        score = 0.0
        reasons: list[str] = []
        for keyword, weight in weighted.items():
            count = text.count(keyword)
            if count:
                contribution = weight + min(count - 1, 3) * 0.25
                score += contribution
                reasons.append(f"{keyword}×{count}")
        if score:
            score = max(0.0, score + type_boost - negative_penalty)
            if score >= 2.0:
                hits.append(
                    RelevanceHit(
                        category=category,
                        score=round(score, 2),
                        reasons=reasons,
                    )
                )

    hits.sort(key=lambda x: (-x.score, x.category))
    return hits
