from __future__ import annotations

import hashlib
import re


UNCERTAINTY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("probability", re.compile(r"たぶん|多分|おそらく|恐らく|かもしれ(?:ない|ません)")),
    ("approximation", re.compile(r"\d+時(?:\d+分)?頃|\d+時(?:\d+分)?ごろ|\d+分くらい|\d+分ぐらい|頃|ごろ|くらい|ぐらい")),
    ("belief", re.compile(r"と思う|と思います|気がする|ような気がする")),
    ("memory", re.compile(r"記憶がない|記憶にない|覚えていない|覚えてません|はっきり覚えていない")),
    ("unknown", re.compile(r"分からない|わからない|分かりません|不明|はっきりしない|確かではない")),
]


def extract_uncertainty_markers(text: str) -> list[dict]:
    markers: list[dict] = []
    seen: set[tuple[int, int, str]] = set()
    for kind, pattern in UNCERTAINTY_PATTERNS:
        for match in pattern.finditer(text or ""):
            key = (match.start(), match.end(), kind)
            if key in seen:
                continue
            seen.add(key)
            markers.append(
                {
                    "type": kind,
                    "text": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    markers.sort(key=lambda x: (x["start"], x["end"], x["type"]))
    return markers


def transcript_text_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def transcript_search_text(*, speaker_label: str | None, text: str) -> str:
    return "\n".join(x.strip() for x in [speaker_label or "", text or ""] if x and x.strip())


def unique_uncertainty_labels(markers: list[dict]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for marker in markers:
        value = str(marker.get("text") or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
