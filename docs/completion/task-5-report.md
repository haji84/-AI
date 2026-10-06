> Current integration/safety evidence supersedes unmerged estimates below: [WORKFORCE_INTEGRATION.md](WORKFORCE_INTEGRATION.md). Chapter25 remains Partial; existing PR53 was CI-failing and is being repaired, not treated as canonical completion.

# Completion Run B Task 5 — Workforce and Duty Management

Status: implementation candidate on latest main after Learning PR52.
Migration: 044_run_b_workforce.sql.

## Canonical reuse

This module does not create a second personnel master.

It references:
- employees
- organization_units
- employee_assignments
- documents
- app_users

Roster entries snapshot the effective primary assignment ID/version for the work date.
Normal placement must match that assignment. Explicit support placement may target another organization.
If source assignment evidence changes before Human review, review is rejected.

## Implemented

- shift type registry with explicit timezone, cross-midnight declaration and Human-configured payable minutes
- employee qualification evidence with effective dates and optional source Document
- Human-gated staffing rules with minimum headcount and optional qualification requirement
- staffing rule source version binding to Organization and Shift Type
- roster Draft / Human review / Human approval / cancellation
- overlapping placement rejection
- support placement
- exact leave-use time intervals
- annual / special / compensatory leave immutable ledger
- leave grant/use/adjustment/expiry entries
- approved-only leave balance and negative-balance rejection
- attendance Draft / review / approval
- timezone-aware check-in/out and deterministic elapsed/planned/overtime-candidate calculation
- one attendance per linked roster
- overtime and compensatory-time ledger with nonnegative compensatory balance
- minimum staffing warnings using only approved rules and approved rosters
- approved leave overlap exclusion
- stale approved staffing-rule detection when its configuration source changes
- available-crew view with current qualification codes
- monthly/yearly workforce statistics
- roster CSV/XLSX preview-confirm import with SHA-256 and source Document option
- formula-safe CSV/XLSX roster export
- backend RBAC and dedicated workforce roles
- audit logging for mutations/Human decisions/imports
- Module Registry registration
- permission-aware unified search of roster evidence only
- private leave reason excluded without personnel.read and never indexed by unified search
- shared PC-browser modal UI for roster, staffing, leave, attendance, overtime/comp time, settings, statistics and exchange
- AI is not required for any core workforce workflow

## Human boundaries

The system does not invent:
- minimum staffing counts
- qualification requirements
- payable work minutes
- leave grants
- overtime approval
- compensatory-time entitlement

Those are configured or approved by authorized Humans.

Draft/review state does not change official leave/compensatory balances or approved staffing availability.

## Deliberate boundaries

- Workforce qualifications are explicit Human-managed evidence. Unknown qualifications are not inferred from job title.
- A leave-use interval overlapping a shift makes that employee unavailable for that staffing rule's shift-level availability calculation. Finer intra-shift coverage can be added later without changing the ledger.
- Cross-module Incident/Dispatch → work-result reconciliation belongs to the canonical Full E2E/System Integration work (#54), not a duplicate Incident implementation inside Workforce.
- Real production staffing policy acceptance and physical-client use remain External/hosting acceptance.

## Verification contract

Synthetic regressions cover:
- explicit cross-midnight rules
- stale optimistic writes
- effective primary assignment and support placement
- overlapping roster rejection
- stale assignment evidence
- qualification-gated staffing
- Human rule review/approval
- partial leave overlap and leave balance
- negative leave/compensatory balance rejection
- timezone-aware attendance
- Human review vs approval permissions
- overtime evidence
- CSV/XLSX preview-confirm/export
- formula injection neutralization
- unified search privacy
- shared UI/bootstrap registration
- audit evidence

Project CI additionally parses and applies all migrations on PostgreSQL and runs the repository-wide backend/frontend checks.

