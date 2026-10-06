# Specification v2.0 gap resolution

Date: 2026-10-07

This document records the consolidation performed in `docs/SPECIFICATION.md`.
The Master Specification remains the Source of Truth defined by `AGENTS.md`.

## Conflict resolutions

- Production database changed from "PostgreSQL preferred" to PostgreSQL required. SQLite is development/test only.
- "Shared folder" wording was replaced by server-managed Document Storage and separate Backup Storage.
- User-selectable fire-department switching was removed. Each production runtime is bound to one immutable department UUID.
- Tenant and legal jurisdiction are explicitly separate concepts.
- Client update behavior is fixed to server-side Web application updates by default. Per-PC installation/update is not required for normal releases.
- One common release does not imply forced simultaneous rollout to every department.

## Previously scattered or conversation-defined requirements added to the Master Specification

- Five deployment profiles: cloud, connected local, closed-network local, fully offline, LGWAN/constrained-network.
- Server-side update, department-by-department release approval, rollback and signed offline update path.
- Human personnel/organization/assignment/account administration.
- Shared incident/dispatch operations.
- Fleet/vehicle operations.
- Operational assets, inventory, consumables, drugs and lot/batch history.
- Workforce roster, staffing, leave, attendance, overtime and support placement.
- Procurement, expenditure and configurable budget-account hierarchy.
- Council/inquiry evidence-backed answer drafting.
- Cross-module monthly/annual statistics and surveys with source lineage.
- Violation correction and hazardous-materials domains.
- Permission-aware shared dashboard, notifications and expanded unified search.
- Complete Document intake and original-template output integration.
- Emergency completion requirements including post-review/lifesaving forms and correction history.
- Fire-investigation completion requirements including local AI worker/adapters and official output lineage.
- Learning platform with Champion/Candidate/benchmark/Human promotion/rollback.
- Human Change Request and bounded autonomous change workflow.
- Backup/restore/maintenance/security requirements.
- Common-data reuse rules preventing duplicate masters and duplicate entry.
- Cross-module Full E2E acceptance flows.
- Release artifacts and system-level Definition of Done.

## Non-negotiable safety boundaries retained

- AI candidates do not directly become official records.
- Legal rules, permissions, security, source evidence, audit logs, formal violations, formal cause and formal financial values require authoritative non-AI controls and/or Human Gate.
- Original documents and evidence remain immutable.
- AI failure must not disable core manual CRUD/intake/search workflows.
- Actual production/LAN/model-accuracy/Human legal acceptance remains explicitly separated as External Gates.

## Implementation note

Older Phase sections are retained for historical implementation detail.
If an older section conflicts with the v2.0 integrated requirements, the v2.0 "仕様優先順位・確定事項" section governs.
