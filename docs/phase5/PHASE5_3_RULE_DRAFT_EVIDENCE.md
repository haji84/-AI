# Phase 5.3 Rule Draft Candidate Evidence

更新日: 2026-10-05

## Purpose

Separate AI/deterministic extraction from formal legal Rule authoring.

Flow:

LegalProvision
→ Rule Draft Candidate
→ Human Review
→ promoted Draft Rule Version
→ separate formal Rule approval
→ Approved Rule Version

No AI-generated candidate can become an Approved Rule directly.

## Implemented

Migration 011:
- `legal_rule_draft_candidates`
- `legal_rule_draft_citations`

Candidate fields include:
- source legal document Version
- proposed domain
- proposed Rule code/name
- proposed conditions
- proposed outcome
- extraction method: manual/deterministic/ai
- model version
- confidence
- rationale
- exact LegalProvision citations
- review status
- optimistic version
- promoted Rule/Rule Version references

API:
- list candidates
- create candidate
- review/reject candidate
- promote reviewed candidate

Promotion behavior:
- requires Human Review
- structured-source candidate requires exact citation
- promotion creates a Rule Version with `status=draft`
- it does NOT approve the Rule
- formal approval remains the separate Phase 5 Rule approval Human Gate

## Verification

Latest main project-checks:
- backend pytest: 46 passed
- AI candidate cannot promote before review
- reviewed candidate can promote
- promoted Rule Version remains `draft`
- source legal document Version and citations are preserved
- Migration 011: 5 statements, parser PASS

## Next step

Generate candidate queues from actual fire-related provisions in:
- e-Gov national laws
- 大島地区消防組合 regulations

Candidate generation remains non-authoritative and review-only.
