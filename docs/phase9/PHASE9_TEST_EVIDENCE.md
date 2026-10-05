# Phase 9 Test Evidence

更新日: 2026-10-05

## Last verified green checkpoint

GitHub Actions run: `37254735014`
Conclusion: SUCCESS

- backend pytest: 83 passed
- Migration 025: 5 statements PASS
- Migration 026: 2 statements PASS
- frontend JavaScript syntax: PASS

Canonical Phase 9 API is consolidated under `/fire-investigations`.
The temporary duplicate `fire_audio` router was removed after consolidation.

## Verified behaviors

- uncertainty marker positions are deterministic
- transcript text SHA-256 is stable
- transcript search can restrict to Human-accepted segments
- transcript search can restrict to uncertain segments
- statement Draft inherits source uncertainty markers
- uncertain statement cannot become reviewed without explicit Human uncertainty confirmation
- evidence comparison accepts only Human-reviewed/confirmed evidence
- same Evidence cannot be compared with itself
- evidence comparison AI Manifest is idempotent
- comparison candidates remain pending until Human review
- optimistic version conflict prevents double review
- accepted comparison remains a separate candidate record

## Additional hardening after the checkpoint

- Phase 9 UI added for transcript search and evidence-comparison review
- UI warns when comparison Evidence contains uncertainty markers
- explicit regression assertion added that accepting a comparison must not mutate:
  - reviewed statement text
  - confirmed timeline status
  - official fire cause

These latest changes require their current HEAD CI result before being reported as the new final green checkpoint.

## Safety boundary

An accepted evidence-comparison candidate is not an established fact.
It cannot directly:
- rewrite transcript text
- rewrite a reviewed statement
- rewrite a confirmed timeline
- select/approve a fire cause
- approve a formal report
