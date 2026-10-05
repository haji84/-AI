# Phase 5.5 Core Legal Authoring Worklist Evidence

更新日: 2026-10-05

## Purpose

全関連Provisionを一度にHuman Reviewへ送らず、
現在の設備・届出Rule作成に必要な中核法令・大島地区例規をExact Titleで固定して
優先作業パックを生成する。

## Core sources

National exact titles: 5 / 5 found
- 消防法
- 消防法施行令
- 消防法施行規則
- 危険物の規制に関する政令
- 危険物の規制に関する規則

大島地区消防組合 exact titles: 13 / 13 found

## Verified worklist

Workflow run: `37248400904`
Result: SUCCESS
Artifact ID: `11320435391`
Artifact name: `core-legal-authoring-worklist`
Artifact size: 2,037,491 bytes
Artifact SHA-256: `39688473f87fa888ae9db6840ec6f2f41a880a500f72c97f05dc4c96582221ec`

Worklist items: 7,854

Authoring lane counts:
- requirement_rules: 1,602
- management_review: 803
- hazardous_materials: 5,093
- local_fire_prevention: 1,223

Lane counts overlap when the same Provision belongs to multiple legal review categories.

## Hash binding

Each worklist item contains:
- source scope
- exact document title
- source reference
- Provision Key
- Provision content SHA-256
- Provision context
- source priority
- relevance hits

Baseline source evidence is embedded in the inventory:
- e-Gov acquisition run/artifact/source Archive Hash
- 大島地区消防組合 acquisition run/artifact/Hash/content-current date

## Local AI importer

`scripts/import_core_legal_authoring_worklist.py`

Default behavior: dry-run.

Persistent import requires `--apply`.

Importer requires:
1. exact source external ID
2. exact Provision Key
3. exact Provision SHA-256
4. exact document title

Any mismatch is rejected as missing/stale.
Reviewed/ignored/drafted terminal queue rows are not silently overwritten.
Repeated import is idempotent.

## UI/API operationalization

Legal Review supports:
- status
- equipment/submission/etc category
- national_core/local_core/normal
- main/supplementary/document body
- legal title/text search
- minimum relevance
- minimum total review priority
- 50-item pagination
- total/status counts
- reviewed Provision → incomplete Rule Draft handoff

## Interpretation policy

The worklist is a Human authoring queue.
It does not mean 1,602 Rules are required, because multiple Provisions may combine into one Rule,
and one Provision may participate in multiple Rules.

No Rule condition or outcome is inferred merely from worklist membership.
