# Phase 6 Drawing Analysis / Human-Gated Facility Updates

更新日: 2026-10-05

## Goal

PDF/画像の図面をLocal AI等で解析し、設備・建物情報を候補化する。
AI解析結果を正式台帳へ直接書き込まず、Human Reviewを必須とする。

## State flow

### Drawing analysis

```
drawing upload
-> pending
-> Local AI / import manifest
-> analyzed
-> all candidates reviewed
-> reviewed
```

### Equipment candidate

```
AI observation
-> pending
-> Human accepted / rejected
-> accepted
-> promote
-> FacilityEquipment(verification_status=ai_candidate, source_kind=drawing_ai)
-> independent field/document verification
-> FacilityEquipment(verification_status=verified)
```

Rule compliance only treats `verified` installed equipment as satisfying a requirement.
`ai_candidate`, `legacy_only`, and `unverified` remain evidence only.

### Facility fact candidate

```
AI observation
-> pending
-> Human accepted / rejected
-> accepted
-> apply with candidate Version + Facility Version
-> allowlisted normalized FacilityDetail field only
```

Application uses optimistic locking. A stale Facility Version returns HTTP 409.

## Allowlisted fact targets

- detail.classification_code
- detail.classification_detail_1
- detail.classification_detail_2
- detail.structure
- detail.zoning
- detail.article8_partition
- detail.above_ground_floors
- detail.basement_floors
- detail.building_area
- detail.total_floor_area
- detail.occupancy_total
- detail.employee_total

Unknown target paths are rejected with 422.

## Data model

Migration 017:
- drawing_analyses
- drawing_elements
- drawing_equipment_candidates
- drawing_fact_candidates

Migration 018:
- applied_by
- applied_at
- applied_facility_version

Equipment registry from Phase 5.8:
- equipment_types
- facility_equipment

## APIs

- GET /facilities/{building_id}/drawing-analyses
- POST /facilities/{building_id}/drawing-analyses
- GET /drawing-analyses/{analysis_id}
- POST /drawing-analyses/{analysis_id}/elements
- POST /drawing-analyses/{analysis_id}/equipment-candidates
- PATCH /drawing-equipment-candidates/{candidate_id}
- POST /drawing-equipment-candidates/{candidate_id}/promote
- POST /drawing-analyses/{analysis_id}/fact-candidates
- PATCH /drawing-fact-candidates/{candidate_id}
- POST /drawing-fact-candidates/{candidate_id}/apply
- POST /drawing-analyses/{analysis_id}/review

## Local AI manifest contract

Local AI implementations can submit one normalized result manifest:

`POST /drawing-analyses/{analysis_id}/manifest`

Manifest contains:
- expected analysis Version
- model Version
- page count/confidence
- analysis summary/evidence
- elements
- equipment candidates
- Facility fact candidates

The manifest is SHA-256 fingerprinted. Resubmitting the exact same content is idempotent.
A different result cannot overwrite an already attached result; use a new DrawingAnalysis Version/record.

No manifest ingestion automatically accepts candidates.

## UI

Facility detail supports:
- installed equipment registry
- equipment requirement comparison
- drawing upload
- drawing analysis list
- drawing candidate review modal
- equipment candidate accept/reject/promote
- Facility fact accept/reject/apply
- analysis review completion

Drawing upload itself produces `pending`, not `analyzed`.

## RBAC

- drawing.read
- drawing.analyze
- drawing.review

The permissions are separate from equipment verification.
Promotion from drawing evidence creates `ai_candidate`, never `verified`.

## Safety rules

1. AI cannot create verified equipment directly.
2. AI cannot write arbitrary DB paths.
3. Facility fact application is allowlisted and optimistic-locked.
4. Drawing evidence remains linked to original Document.
5. Candidate rejection never mutates facility/equipment truth.
6. Analysis cannot be marked reviewed while pending equipment/fact candidates remain.
7. Rule evaluation remains deterministic and uses only approved legal Rule Versions.
