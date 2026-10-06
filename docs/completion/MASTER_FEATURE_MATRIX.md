# Fire AIOS Master Feature Matrix

Audit date: 2026-10-06
Canonical specification: docs/SPECIFICATION.md v2.0
Audited main base: 922d292c48fa0d7e4082432116e608825f6fe154 (PR61; main CI37523158483 SUCCESS). Shared session/body guards are under implementation and do not yet change main classification.

This matrix compares all 57 Master Specification chapters against the actual repository: models, migrations, routers, services, frontend surfaces, tests, deployment files and current CI evidence.

Status meanings:

- Completed: the chapter's internal code foundation and required core workflow are implemented in main. Production-site acceptance may still exist as a separate External Gate.
- Partial: meaningful implementation exists, but one or more specification requirements remain internally implementable.
- Missing: no adequate implementation for the chapter's primary workflow was found.
- External Gate: the internal framework exists and the remaining decisive acceptance requires real infrastructure, real reference data, official originals or Human authority that cannot be fabricated in code.

## Summary

| Status | Count |
|---|---:|
| Completed | 14 |
| Partial | 37 |
| Missing | 5 |
| External Gate | 1 |
| Total | 57 |

## 57-chapter matrix

| # | Specification chapter | Status | Main evidence | Remaining internal work / gate |
|---:|---|---|---|---|
| 1 | Product Vision | Partial | shared FastAPI app, common browser shell, DB-backed modules | whole-system DoD not yet met |
| 2 | Canonical Architecture | Completed | tenant_context.py, storage.py, db.py, deploy/tenants, tenant tests | real production host acceptance is external |
| 3 | Deployment Profiles | Partial | local deployment assets, tenant generator, Windows/Linux deployment material | cloud / closed / fully-offline / LGWAN profiles are not all packaged and acceptance-tested |
| 4 | Update, Release and Rollback | Partial | Module registry, Feature Flag/Change Request foundation, signed legal Update Bundle | full application Release updater, staged rollout and rollback across all deployment profiles |
| 5 | Common Data Principles | Completed | UUID records, optimistic versions, audit, logical lifecycle patterns across core models | module-specific exceptions must continue to follow these rules |
| 6 | Employee, Organization and Account | Partial | PR44, Migration041, personnel.py, routers/administration.py, admin UI/tests | Document-driven personnel transfer/import flow; remaining account lifecycle polish |
| 7 | Authorization | Partial | authz.py, RBAC, backend permission dependencies, effective-dated appointment roles | PR56 customRole/RoleRule/timed/acting and own explanation are merged with PG/browser CI; qualification/duty-derived selector extension remains internal; production role acceptance is external |
| 8 | Audit | Completed | audit.py; administration audit API/UI keyset paging and action/entity filters; test_personnel keyset regression; real PostgreSQL tenant application-role DELETE denial test included in Green main CI37520767373 | production-site operator acceptance remains external; preserve append-only application-role grants |
| 9 | Document Platform | Completed | Document model, managed storage, SHA-256, source/original separation, document router | continue module adapters without duplicating originals |
| 10 | Document Intake and OCR | Partial | document_intake.py, intake router/UI, PDF/image/DOCX/XLSX/text paths | HEIC path, multi-image document assembly, correction/quality pipeline and all target-module adapters |
| 11 | Facility Registry | Completed | facility models/router/UI, details/contacts/floors, legacy import, optimistic conflict flow | real LAN user acceptance external |
| 12 | Inspection | Partial | inspection/finding models/router/UI and tests | richer workflow, scheduled follow-up, direct violation/correction lifecycle integration |
| 13 | Violations and Corrective Actions | Partial | PR60 merged: API/UI/Migration049, immutable correction history, source-bound Human confirmation; CI37519910509 backend605/browser8 and main CI37520767373 SUCCESS | common AI candidate producer remains internal integration work |
| 14 | Submission and Application | Partial | submission type master, receipt records, document links, intake apply and facility UI | complete configurable review flows, attachment requirements and all official submission families |
| 15 | Submission Requirement Tracking | Partial | Rule engine evaluates submission requirements; facility dashboard has submission state | durable required/received/next-due lifecycle and full approved-Rule coverage |
| 16 | Hazardous Materials | Missing | legal authoring category exists | operational hazardous-material facility/case/permit/inspection/document module |
| 17 | Legal and Rule Engine | Partial | migrations008-015, legal source/version/provision/rule/draft/review queue, signed update bundle | Human authoring/approval coverage of production Rule set; remaining official-source adapters |
| 18 | Equipment Requirement and Installed Equipment | Partial | FacilityEquipment, equipment types, requirement/placement engines, Human review/regression tooling | complete approved Rule/placement corpus and operational acceptance |
| 19 | Drawing AI | Partial | drawing analyses, Annotation, edit/QA/revision, benchmark core/run registry/UI | actual Local Vision execution quality and real drawing Baseline/threshold acceptance |
| 20 | Occupancy Classification and Drawing Consultation | Partial | consultation APIs/UI, occupancy authoring/regression, equipment evaluation/response review | complete Human-approved occupancy/rule corpus and production consultation acceptance |
| 21 | Emergency Module | Partial | import/normalized Case/Patient/Crew, PR39/40 reports/edit/treatment/clinical review, UI | masters/mappings, full dated time checks, corrections/history, structured official forms, remaining reports |
| 22 | Incident and Dispatch | Completed | PR42, Migration040, operations models/service/router/UI/tests | cross-module dashboard/statistics integration only |
| 23 | Fleet and Vehicle | Completed | PR42 vehicle registry/trip/fuel/inspection/service/fault/cost workflows | production acceptance and cross-module statistics only |
| 24 | Operational Assets and Inventory | Completed | PR46, Migration042, asset/lot/balance/movement/loan/service/import/export/UI/tests | production acceptance and dashboard/statistics integration only |
| 25 | Workforce and Duty Management | Partial | Migration044, workforce models/service/router/UI, existing personnel reuse, explicit Human working intervals, CAS/provenance, serialized balance/placement and session guards, browser and PG regressions | team/work-result, checkout/cancel/correction/balance/crew UI, explicit expiry/reconciliation policy; actual Human staffing rules and physical PC acceptance external |
| 26 | Contract and Procurement | Partial | PR55 / Migration048 common Contract/Counterparty/Document, quote/commitment/invoice/inspection/payment/amendment/renewal UI and native PG evidence | PR59 mutation and identity clearing merged; common AI/STT adapter and post-response same-user permission checks remain internal; real originals/formal policy external |
| 27 | Budget and Finance | Partial | PR55 / Migration048, exact Decimal, Human policy/year/account hierarchy, immutable journal, proposal review/posting/reversal, budgets/transfers/commitments/payments/requests, native PG races and browser CI | PR59 mutation/identity guard merged; shared-shell post-response same-user permission revocation checks remain internal; production policy/formal adoption external |
| 28 | Council, Assembly and Inquiry Support | Partial | PR61/Migration050 evidence-linked questions, revisions, Decimal numeric/source lineage, year/lexical search, source-gated exchanges/templates and Human review/approval; PR CI37522253547 backend639/browser9 and main CI37523158483 SUCCESS | shared production local-model worker adapter and common statistics/dashboard integration remain internal; deterministic evidence extraction is explicitly labelled |
| 29 | Fire Investigation | Partial | Migration019+, fire case/evidence/statement/timeline/cause/report APIs/UI | complete local-model worker/adapters, video path and full operational audit |
| 30 | Fire Photo Intelligence | Partial | Migration023/024, photo metadata/quality/duplicate and drawing links | production classifier/description worker and real labeled accuracy acceptance |
| 31 | Voice, Statement and Evidence Comparison | Partial | Migration025/026, transcript semantics, statement/evidence comparison workflow and benchmark | actual STT/diarization worker and real audio baseline |
| 32 | Fire Report Drafting | Partial | report Draft, Evidence Snapshot provenance, formal cause separation and export path | complete local AI drafting worker, all official original forms and real workflow acceptance |
| 33 | Official Form Platform | Partial | FormTemplate, official_form_renderer.py, PDF/XLSX/DOCX support, fire export | adapters and registered official originals for remaining modules |
| 34 | Cross-module Statistics, Annual Reports and Surveys | Missing | emergency-specific reports exist only | unified statistics service across all modules, prior-year comparison, snapshot lineage, official surveys |
| 35 | Unified Search | Partial | permission-aware routers/search.py, facilities/fire/legal/docs/contracts/operations/assets integration | add all remaining modules, filters/pagination quality and production performance evidence |
| 36 | Dashboard and Personal Work Queue | Missing | facility dashboard exists, no system-wide personal work queue | permission-aware today/unprocessed/review/deadline/task aggregation across modules |
| 37 | Learning Platform | Partial | PR52: eight correction targets, frozen Human references, server comparison, immutable dictionary Candidate, Human Champion promotion/current-tip rollback, PostgreSQL and Chromium CI | model/worker adapters and actual-model integration are internal; real quality acceptance is external |
| 38 | Autonomous Task and Self-extension Platform | Partial | ChangeRequest/extensibility models and review concepts | bounded task runner, sandbox execution, test/evidence orchestration, approved deployment/rollback loop |
| 39 | AI Decision Levels | Partial | Human Gate patterns exist across legal/drawing/fire/emergency | central machine-readable level/policy enforcement and coverage audit across all modules |
| 40 | AI Failure Mode | Completed | core CRUD/API modules do not require LLM availability; deterministic/manual paths exist | ensure all new modules preserve this contract |
| 41 | Import Framework | Partial | facility/emergency/assets imports, dry-run/hash/idempotency patterns, extension framework | common typed import registry and adapters for remaining modules |
| 42 | Backup and Restore | Completed | PR43/47, backup/restore scripts, maintenance locking, manifest/identity checks, tests | real production restore drill remains external |
| 43 | Security | Partial | tenant middleware, runtime role checks, storage isolation, signed bundles, session/RBAC tests | real TLS/OS ACL/network hardening acceptance and complete security review |
| 44 | External Integration and Network Policy | Partial | deployment configs, online legal collectors, closed-network update path | explicit integration adapters and acceptance for every deployment profile/LGWAN constraints |
| 45 | User Experience | Partial | shared main shell plus administration/emergency reports/operations/assets surfaces | one coherent navigation/dashboard/review experience for remaining modules and usability acceptance |
| 46 | Module Configuration per Department | Partial | ModuleDefinition/feature flags and department-bound runtime | complete per-department module/config enablement, approved configuration history and UI |
| 47 | Formal Evidence Model | Completed | Document SHA, source versions, reviewed snapshots, AI Manifest, Rule citations, benchmark provenance | all future modules must use the same evidence contract |
| 48 | Testing | Partial | broad backend suite, migration parser, PostgreSQL and Chromium CI slices | required full cross-module E2E, performance/load and complete deployment-profile testing |
| 49 | AI Benchmark and Acceptance | External Gate | drawing/audio/evidence benchmark engines and run registries exist | first real datasets, measured baselines and Human-set production thresholds |
| 50 | Data Migration | Partial | facility and emergency legacy imports, raw evidence retention, migration framework | remaining legacy datasets, correction history and production migration rehearsal |
| 51 | Operational Hosting | Partial | nginx/systemd/tenant render assets, runtime validation, maintenance/backup controls | real approved host, TLS, monitoring, log rotation and multi-client acceptance |
| 52 | Release Artifacts | Missing | scattered deployment/phase docs only | complete release package and required final manuals/reports listed by v2.0 |
| 53 | Definition of Done | Partial | DoD is now canonical and many foundations pass | Missing/Partial chapters and required E2E/release package remain |
| 54 | Required Cross-module E2E | Missing | module-level E2E tests exist | implement and execute all ten canonical cross-module flows |
| 55 | Development Governance | Completed | AGENTS.md, append-only migrations, PR/CI conventions, current main refresh rules | continue enforcing during completion |
| 56 | Priority Rule | Completed | v2.0 defines authoritative priority and obsolete wording handling | no internal implementation gap |
| 57 | Completion Principle | Completed | Human decision / AI assistance boundary is implemented as project governance | final operational acceptance still follows DoD |

## Internal implementation backlog derived from the matrix

### P0: missing operational domains with foundations already available

1. Workforce and Duty Management (#25)
2. Budget and Finance (#27) plus completion of Contract/Procurement (#26)
3. Violations and Corrective Actions (#13)
4. Hazardous Materials (#16)
5. Council / Inquiry Support (#28)
6. Cross-module Statistics (#34)
7. Dashboard / Personal Work Queue (#36)
8. Learning Platform (#37)

### P1: completion of strong Partial domains

9. Emergency completion (#21)
10. Fire investigation/photo/voice/report worker and workflow completion (#29-32)
11. Document intake + official form adapters (#10/#33/#41)
12. Submission/requirement tracking (#14/#15)
13. Legal/equipment/occupancy production-authoring completion (#17/#18/#20)
14. Search/UX/module-configuration completion (#35/#45/#46)
15. Autonomous task/self-extension completion (#38/#39)

### P2: system completion and release

16. Deployment-profile/network/security completion (#3/#4/#43/#44/#51)
17. Data migration rehearsal (#50)
18. Full cross-module E2E (#48/#54)
19. Final Release Artifacts (#52)
20. Definition of Done audit (#53)

## External Gate inventory

These do not excuse internal Missing/Partial work.

- real approved production host / LAN / TLS / multiple physical clients
- real drawing/audio/photo reference datasets and Human-set accuracy thresholds
- Human legal Rule approval and organization-specific formal decisions
- official original forms not yet supplied
- final operational user acceptance in the deployment organization

## Next implementation rule

Development must continue from this matrix rather than Phase numbering.
A single PR or module completion is not a stopping condition.
After every merged slice, refresh main and update only the affected matrix rows.
The stopping condition is the Master Specification v2.0 Definition of Done, with External Gates reported separately.

Audit correction after code inspection: chapter7 was previously marked Completed too broadly. Existing appointment/permanent role selection does not provide Human-managed custom permissions/Role Rules and dedicated temporary/acting grant administration. These are internal Partial work, not an External Gate.

Workforce integration safety evidence: docs/completion/WORKFORCE_INTEGRATION.md. Existing PR53 repaired rather than reimplemented; chapter25 remains Partial. No claims of actual PostgreSQL/Chromium or main merge until corresponding exact-head CI evidence is recorded.

Count correction: summary is derived by recounting all57 chapter rows (13Completed/36Partial/7Missing/1External after this workforce slice). Earlier summaries inherited a one-chapter Partial/Missing mismatch. Canonical0feb main before PR53 has13Completed/35Partial/8Missing/1External; unmerged workforce remains Missing in the main-only count.
