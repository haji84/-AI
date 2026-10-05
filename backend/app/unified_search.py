from __future__ import annotations

import hashlib
import re


SEARCH_VERSION = "unified-search-v1"


def normalize_query(value: str) -> str:
    return re.sub(r"[\s　]+", " ", (value or "").strip()).lower()


def query_terms(value: str) -> list[str]:
    q = normalize_query(value)
    if not q:
        return []
    parts = [x for x in re.split(r"[\s,、/]+", q) if x]
    # Keep the full phrase first so Japanese phrases without spaces remain useful.
    out = [q]
    for item in parts:
        if item not in out:
            out.append(item)
    return out


def query_sha256(value: str) -> str:
    return hashlib.sha256(normalize_query(value).encode("utf-8")).hexdigest()


def lexical_score(query: str, *, title: str = "", body: str = "") -> float:
    q = normalize_query(query)
    if not q:
        return 0.0
    title_n = (title or "").lower()
    body_n = (body or "").lower()
    score = 0.0

    if q in title_n:
        score += 10.0
    if q in body_n:
        score += 5.0

    terms = query_terms(q)
    for term in terms[1:] if len(terms) > 1 else terms:
        if term in title_n:
            score += 3.0
        if term in body_n:
            score += 1.0
    return score


def make_snippet(query: str, text: str, *, limit: int = 280) -> str:
    value = re.sub(r"[\s　]+", " ", (text or "").strip())
    if len(value) <= limit:
        return value
    q = normalize_query(query)
    lower = value.lower()
    pos = lower.find(q)
    if pos < 0:
        for term in query_terms(q):
            pos = lower.find(term)
            if pos >= 0:
                break
    if pos < 0:
        return value[: limit - 1] + "…"
    half = max(20, limit // 2)
    start = max(0, pos - half)
    end = min(len(value), start + limit)
    if end - start < limit:
        start = max(0, end - limit)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(value) else ""
    return prefix + value[start:end] + suffix
