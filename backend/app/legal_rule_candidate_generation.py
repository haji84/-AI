from __future__ import annotations

from dataclasses import dataclass
import hashlib


GENERATOR_VERSION = "legal-rule-candidate-v1"

EQUIPMENT_TERMS = (
    "消防用設備等",
    "消火器",
    "屋内消火栓",
    "屋外消火栓",
    "スプリンクラー",
    "自動火災報知設備",
    "消防機関へ通報する火災報知設備",
    "非常警報設備",
    "避難器具",
    "誘導灯",
    "誘導標識",
    "連結送水管",
    "連結散水設備",
    "排煙設備",
    "非常コンセント設備",
    "無線通信補助設備",
    "漏電火災警報器",
    "ガス漏れ火災警報設備",
)

SUBMISSION_TERMS = (
    "届出",
    "報告",
    "提出",
    "防火管理者",
    "消防計画",
    "点検結果報告",
    "防火対象物点検",
    "防災管理",
)


@dataclass(frozen=True)
class CandidateSignal:
    domain: str
    matched_terms: tuple[str, ...]
    confidence: float


def _hits(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(term for term in terms if term in text)


def detect_candidate_signals(text: str, title: str | None = None) -> list[CandidateSignal]:
    haystack = "\n".join(x for x in [title or "", text or ""] if x)
    out: list[CandidateSignal] = []

    equipment = _hits(haystack, EQUIPMENT_TERMS)
    if equipment:
        out.append(
            CandidateSignal(
                domain="equipment_requirement",
                matched_terms=equipment,
                confidence=min(0.75, 0.35 + 0.05 * len(equipment)),
            )
        )

    submissions = _hits(haystack, SUBMISSION_TERMS)
    if submissions:
        out.append(
            CandidateSignal(
                domain="submission_requirement",
                matched_terms=submissions,
                confidence=min(0.75, 0.35 + 0.05 * len(submissions)),
            )
        )

    return out


def candidate_fingerprint(
    *,
    source_version_id: str,
    provision_id: str,
    domain: str,
    generator_version: str = GENERATOR_VERSION,
) -> str:
    raw = "|".join([source_version_id, provision_id, domain, generator_version])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
