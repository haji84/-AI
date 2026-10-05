# Phase 5.4 Legal Review Queue Evidence

更新日: 2026-10-05

## Purpose

全国法令・指定消防本部例規の全Provisionを直接Rule化せず、
消防業務関連度を決定的にスコアリングしてHuman Review Queueへ絞り込む。

Rule条件・Rule結論はこの段階では生成しない。

## Real-corpus verification

Workflow run: `37243458396`
Result: SUCCESS
Artifact ID: `11318361994`
Artifact name: `fire-legal-review-queue-verification`
Artifact SHA-256: `da71ca8137b248cc0d97dd328e349d890d19c996d106c413528db231d557623a`

### e-Gov

Matched provisions: 15,065

Category counts:
- equipment_requirement: 1,900
- submission_requirement: 1,688
- fire_management: 522
- inspection_enforcement: 729
- hazardous_materials: 9,294
- fire_prevention_local: 2,009

Priority lanes:
- national_core: 6,184
- local_core: 2,945
- normal: 5,936

Provision context:
- main: 12,520
- supplementary_transition: 2,545

### 大島地区消防組合

Matched provisions: 2,226

Category counts:
- equipment_requirement: 69
- submission_requirement: 601
- fire_management: 72
- inspection_enforcement: 524
- hazardous_materials: 240
- fire_prevention_local: 1,129

Priority lanes:
- local_core: 1,650
- normal: 576

Provision context:
- main: 2,226

Category counts may overlap because one Provision may be relevant to multiple categories.

## Review workflow

LegalProvision
→ relevance candidate
→ Human reviewed / ignored
→ reviewed requirement candidate only
→ incomplete Rule Draft Candidate
→ Human fills conditions/outcome
→ Human reviews Rule Draft
→ Draft Rule Version
→ separate formal approval
→ Approved Rule Version

## Safety

- relevance score is not a legal conclusion
- supplementary/transitional provisions are retained but deprioritized
- reviewed Provision cannot create an Approved Rule directly
- only equipment/submission categories currently hand off to the requirement Rule engine
- optimistic version checks protect concurrent review
- UI shows exact source text and Provision context

## DB

- Migration 013: review queue
- Migration 014: source priority
- Migration 015: Provision context priority
