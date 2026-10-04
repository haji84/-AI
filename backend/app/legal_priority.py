from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourcePriority:
    lane: str
    score: float
    reasons: tuple[str, ...]


NATIONAL_CORE_EXACT = {
    "消防法": 20.0,
    "消防法施行令": 20.0,
    "消防法施行規則": 20.0,
    "危険物の規制に関する政令": 18.0,
    "危険物の規制に関する規則": 18.0,
}

LOCAL_CORE_KEYWORDS = {
    "火災予防条例": 15.0,
    "火災予防条例施行規則": 15.0,
    "火災予防査察": 14.0,
    "建築同意": 13.0,
    "消防用設備等": 14.0,
    "防火対象物点検": 13.0,
    "危険物": 12.0,
    "違反対象物": 12.0,
    "公表": 8.0,
    "喫煙": 8.0,
    "裸火": 8.0,
}


def classify_source_priority(title: str | None) -> SourcePriority:
    value = (title or "").strip()
    if value in NATIONAL_CORE_EXACT:
        return SourcePriority(
            lane="national_core",
            score=NATIONAL_CORE_EXACT[value],
            reasons=(f"national core law: {value}",),
        )

    matches = [
        (keyword, score)
        for keyword, score in LOCAL_CORE_KEYWORDS.items()
        if keyword in value
    ]
    if matches:
        best = max(score for _, score in matches)
        return SourcePriority(
            lane="local_core",
            score=best,
            reasons=tuple(f"title keyword: {keyword}" for keyword, _ in matches),
        )

    return SourcePriority(lane="normal", score=0.0, reasons=())


@dataclass(frozen=True)
class ProvisionContextPriority:
    context: str
    score: float
    reason: str | None = None


def classify_provision_context(provision_key: str | None, provision_type: str | None) -> ProvisionContextPriority:
    key=(provision_key or "").lower()
    ptype=(provision_type or "").lower()
    if "supplementary" in key or ptype == "supplementary":
        return ProvisionContextPriority(
            context="supplementary_transition",
            score=-10.0,
            reason="supplementary or transitional provision",
        )
    if ptype in {"document_body"}:
        return ProvisionContextPriority(
            context="document_body",
            score=-1.0,
            reason="article-less official document body",
        )
    return ProvisionContextPriority(context="main",score=0.0,reason=None)
