# Phase 6 Drawing Analysis Test Evidence

更新日: 2026-10-05

## CI checkpoint

GitHub Actions run: `37251037051`
Conclusion: SUCCESS

- backend pytest: 70 passed
- Migration 017 parser: PASS (11 statements)
- Migration 018 parser: PASS (1 statement)
- frontend JavaScript syntax: PASS
- operational script syntax: PASS

## Verified flows

### Drawing upload and state

- drawing registration creates `pending`
- candidate generation changes analysis to `analyzed`
- reviewed analysis is locked against new candidate creation
- analysis review is blocked while pending equipment/fact candidates exist

### Equipment candidate

- AI equipment candidate starts `pending`
- direct promotion before Human acceptance: rejected
- Human accepted candidate can promote
- promotion creates FacilityEquipment with:
  - verification_status = `ai_candidate`
  - source_kind = `drawing_ai`
  - original drawing Document linkage
- `ai_candidate` does not satisfy equipment Rule comparison
- independent equipment verification changes it to `verified`
- only `verified` equipment satisfies presence comparison

### Facility fact candidate

- pending fact cannot apply
- accepted fact can apply only for allowlisted target paths
- invalid target path: HTTP 422
- stale Facility Version: HTTP 409
- successful apply increments Facility Version
- normalized FacilityDetail value is updated
- apply audit stores AI model Version and before/after values
- Decimal audit serialization is handled safely
- duplicate apply: rejected

### Local AI manifest

- normalized manifest can contain:
  - drawing elements
  - equipment candidates
  - Facility fact candidates
- manifest content is SHA-256 fingerprinted
- exact same manifest resubmission is idempotent
- duplicate elements/candidates are not created
- different result cannot overwrite an attached result with stale Version
- manifest candidates remain pending after ingestion

### RBAC

- drawing.read
- drawing.analyze
- drawing.review

Prevention role has the drawing workflow permissions.
System admin inherits all permissions.

## UI verification

Frontend syntax PASS after:
- drawing upload
- drawing analysis list
- candidate review modal
- equipment accept/reject/promote
- fact accept/reject/apply
- analysis review completion
- equipment verification and Rule comparison

## Intentional non-claims

Not yet claimed as PASS:
- a production Local Vision model actually interpreting real architectural drawings
- symbol recognition accuracy
- room/door/stair/fire-compartment geometry accuracy
- floor-plan vectorization
- real PDF/image drawing E2E against production examples
- approved LAN PostgreSQL Phase 6 migration
- two-client drawing review concurrency on physical clients

Phase 6 establishes the safe data contract and Human-Gated application path. Model-quality E2E remains a separate gate.
