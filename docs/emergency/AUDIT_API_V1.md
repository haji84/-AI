# Emergency audit API v1 — implementation contract

Status: implementation, 2026-11-22. All examples/fixtures are synthetic. These
interfaces implement the accepted report-audit scope. They do not certify
unapproved source rules, actual report accuracy, or target-machine readiness.

Base `/emergency/audit`. Session authentication, same-origin mutations, no-store
on every response, sanitized errors. All private endpoints require
`emergency.case.read`, `emergency.patient.read`, `emergency.report.read`.
Create/update additionally require `emergency.report.create`. Report owner sees
their reports; `emergency.audit.read_all` permits department-wide access. An
explicit report reviewer assignment grants that reviewer access; no generic
document, drawing, search, learning, or file ID can expose these originals.
Configuration management requires `emergency.audit.configure`; approval requires
`emergency.audit.approve` and a different linked employee. New rights are not
automatically granted to any role. Internal data require server enablement,
department binding, production PostgreSQL, secure cookies, and private key.

## Common shapes

Identifiers are UUIDs. Dates are ISO dates; event instants are timezone-aware
ISO datetimes. `expected_version` is the report's optimistic-lock version, not
the immutable PDF revision number. Every mutating response returns updated
report detail unless stated otherwise. All JSON errors use a fixed Japanese
message and optional fixed `code`, never submitted data. All file uploads use
multipart, one file per request, with total capped at 25MiB + 64KiB overhead.

ReportSummary: `report_id, version, current_revision_id, revision_number,
dataset_kind, created_at, status, job_status, owner, reviewer_id, submitted_at`.
No patient name or original file name appears in lists.

ReportDetail extends summary with `revisions, revision, last_run, initial_run,
runs, events, measurement, measurement_pending, measurement_scope`.
`runs` lists immutable run metadata. Events include `event_id, kind, payload,
supersedes_event_id, can_correct, created_at`; private value fields are not
copied into workflow event notes. `revision` contains `revision_id, number, media_type, page_count,
profile_id, processing_status, error_code, reading, fields, ai_result`.
`reading` has per-page provenance; may be null while queued. `fields` keyed by
field ID contain `label, value_type, state, value, candidate, evidence, issues`.
Evidence: `{page:1-based,bbox:[x0,y0,x1,y1] normalized,text,method,confidence}`.
States: confirmed/unconfirmed/unreadable/not_printed/unmapped. Only explicit
human confirmation supplies `value`; uncertain text remains `candidate`.

Run: `run_id, revision_id, report_version, created_at, mode, approval,
rule_set_id, findings, counts, stale, changes, decisions, decision_reasons`.
Findings: `rule_id,status,message,fields,source_reference,rule_approval,
reason_code?`. Status REVIEW_REQUIRED/NO_ISSUE_DETECTED/NOT_TESTED/NOT_APPLICABLE.
Changes: `resolved,persistent,new,untested` arrays of rule IDs. No result is a
submission permit; a no-issue result applies only to its tested scope.

## Reports and sources

* `GET /capabilities`: `{enabled,storage_ready,internal_enabled,ocr,ai,
  worker,limits:{max_file_bytes,max_pages},permissions}`. No internal paths.
* `GET /reports?limit=30&offset=0`: array of ReportSummary, access scoped.
* `GET /reviewers`: active linked employees with the required detail/review
  permissions, for explicit reviewer assignment. No role grant is performed.
* `POST /reports`: multipart `file,request_id,dataset_kind,profile_id?`.
  Returns ReportDetail (201; identical idempotent retry 200). Autoqueues reading.
* `GET /reports/{report_id}`: ReportDetail including current run and metadata
  of old revisions; separate old-revision selection below.
* `POST /reports/{report_id}/revisions`: multipart
  `file,request_id,expected_version,profile_id?`. Creates immutable replacement,
  leaves previous PDF/checks/decisions intact, queues reading. Changes are made
  in the existing OA system; this API never rewrites that original system.
* `GET /revisions/{revision_id}`: private revision detail and its latest run.
* `GET /revisions/{revision_id}/pages/{page}.png`: bounded PNG; no active PDF.
* `GET /revisions/{revision_id}/original`: attachment-only exact original.
* `POST /reports/{report_id}/annotated-pdf`: `{run_id,expected_version}`.
  Requires the three detail permissions, `emergency.report.export`, and the
  existing report scope. Accepts only the current original revision's latest
  non-stale inspection; mismatched version, old run, or invalidated approval
  is a conflict. Returns `application/pdf`, attachment `emergency-review.pdf`,
  with the private response headers. After isolated rendering, the server
  rechecks session, linked employee, permissions, report scope/version,
  current revision, latest run, and configuration validity before release.
  The UI also rejects changed selection/authority/version before saving.
  A new rasterized copy has numbered regions and a Japanese review appendix.
  It preserves unreadable, untested, and unknown-location states and current
  same-run human dispositions. It does not merge old inspections or invent
  corrected values. The mode and limited inspection scope remain explicit.
  Frozen same-run input fields/findings supply an allowlisted render plan;
  full report histories and unrelated AI payloads are not sent to rendering.
  Original bytes/hash stay unchanged; original active objects, attachments,
  links, and hidden text are not copied. The review copy is not a replacement
  signed original or a submission permit. Native generation stays in the
  bounded Linux child: source <=50 pages, <=12M pixels per rendered page,
  <=120 seconds, output <=32MiB, appendix <=50 pages. Exceeding a limit fails
  the export rather than silently omitting pages/findings.
* `POST /revisions/{revision_id}/retry`: `{expected_version}`; failed/current
  reading only, retained attempts, no concurrent double execution.
* `POST /revisions/{revision_id}/mapping`:
  `{expected_version,profile_id}`; maps existing extraction, clears prior
  confirmations and marks prior checks stale. Current revision only.
* `POST /revisions/{revision_id}/fields`: `{expected_version,
  confirmed_from_original:true,fields:[{field_id,state,value}]}`. Known mapped
  fields only; explicit null represents human-confirmed blank. Nonconfirmed
  states require null value. Current revision only; invalidates old checks.
* `POST /revisions/{revision_id}/checks`: `{expected_version,
  rule_set_id:null|UUID,mode:'candidate'|'approved',as_of:'YYYY-MM-DD'}`.
  Null rule set is the existing ten provisional candidates, candidate mode
  only. Configured rule sets use explicit effective date/form scope. Results
  persist as immutable snapshots. Historical run remains available.
* `POST /revisions/{revision_id}/ai`: `{expected_version}` queues optional
  local-model review. Returns normal detail. No cloud, remote URL, model
  download or model auto-promotion. Unavailable remains explicit.
* `POST /revisions/{revision_id}/vision`: `{expected_version,page:1-based}`
  queues optional local image recognition for one bounded page. Printed,
  handwritten and strikeout candidates remain unconfirmed. It never invents
  before/after correction pairs or a correction reason.
* `GET /runs/{run_id}`: the immutable protected result for that run, with
  current staleness and current human dispositions. Old runs are accessible
  only through the report's current scope.
* `POST /runs/{run_id}/decisions`: `{expected_version,decisions:[{rule_id,
  decision:'correction_needed'|'false_alarm'|'exception'|'unresolved',
  reason_code:'missing'|'inconsistent'|'code_selection'|'format'|'reading_error'|
  'local_rule'|'unknown'}]}`. Requires create or review right plus report scope.
  Omitted reasons remain unknown. Human disposition is not independent truth.
* `POST /reports/{report_id}/reviewer`: `{expected_version,reviewer_id:UUID}`;
  owner or read_all; active linked employee with detail + report.review rights.

## Profiles, rule sets, and approval

`kind` is `profile` or `rules`. Config records are immutable definitions with
separate versioned review status. List/detail include
`config_id,kind,label,form_key,status,version,definition,source_id,created_by,
created_employee_id,approved_by,approval_version,impact`.

* `GET /profiles`, `GET /rule-sets`: arrays of configs visible to audit users.
* `POST /profiles`, `POST /rule-sets`: `{request_id,definition,source_id:null|UUID,
  supersedes_id:null|UUID}`. Returns config. New version is always draft.
* `GET /configurations/{id}`: config detail.
* `POST /sources`: multipart `file,request_id` -> `{source_id,media_type,
  page_count,sha256}`. Internal formal manuals/blank templates live in the
  private encrypted store; no general Document registration.
* `GET /sources/{id}/pages/{page}.png`: private source preview.
* `GET /sources`: retained source ID/hash/media/page-count/date for authorized
  configuration editors/approvers; no filename. Reuse sources without upload.
* `POST /configurations/{id}/impact`: `{report_ids:[UUID,...]}`; bounded <=100
  visible fixed report revisions; counts and baseline comparison are saved.
  No automatic source verification. Reports changed since validation make
  approval stale. A report set is required; empty cannot pass validation.
* `POST /configurations/{id}/approve`: `{expected_version,
  source_verified:true,mapping_verified:true}`. Requires retained source,
  completed impact with no invalid cases, independent linked employee and
  appropriate permission; records the officer's attestation, not AI authority.
  No automatic grants. Effective periods cannot overlap approved versions of
  the same kind/form. Every distinct rule source hash must match a retained
  verified private source; one rule set may cite multiple manuals. Profile
  approval requires at least one usable tested extraction region; a wholly
  manual profile remains draft in this release. Deactivation preserves history.
* `POST /configurations/{id}/retire`: `{expected_version}`. Explicit authorized
  rollback disables future approved-mode selection; old snapshots remain.
  Existing approved runs become stale when their profile or rule set retires.
* `GET /rule-candidates?group=&query=&limit=50&offset=0`: `{total,items}` from
  the existing 433-row provenance ledger. All remain candidates, HOLD and
  EXAMPLE status retained; not 433 executable approved rules.

ProfileDefinition: `{label,form_key,valid_from,valid_to:null|date,fields:[
{field_id,label,value_type:'text'|'number'|'boolean'|'date'|'datetime'|'time'|'enum',
page:1,bbox:[0,0,1,1]|null,extraction:'region'|'manual'|'not_printed',unit:null,
phase:null,code_map:{},options:[]}]}`. Region selected on original, no invented
production field mapping. Version supplied by server config record.

RuleSetDefinition: `{label,form_key,valid_from,valid_to:null|date,rules:[
{rule_id,label,message,severity:'error'|'warning'|'review',
source:{document_title,version,page,section,sha256:null|hex},candidate_ids:[],
applies_when:null|Expression,exceptions:[],assertion:Expression}]}`.
Expression: `{kind:'all'|'any',expressions:[Expression,...]}` or
`{kind:'not',expression:Expression}` or
`{kind:'field',field,operator:'eq'|'ne'|'lt'|'le'|'gt'|'ge'|'in'|'blank'|
'not_blank'|'compare_field',value?:scalar|scalar[],right_field?:fieldID,unit?:str}`.
Unknown inputs propagate; exceptions are evaluated before assertion.

Shared configuration definitions are not a grant to private reports. `impact`
is suppressed unless the caller can configure/approve and still sees every
report included in that validation. Approval checks both user and employee
identities, frozen source/content versions, and unchanged tested reports.

## Measurement events and export

`POST /reports/{report_id}/events` body
`{event_id:UUID,expected_version,kind,payload,supersedes_event_id:null|UUID}`.
Identical retries return the existing result; conflicting event IDs reject.
No free patient text. Work/submission correction is append-only: only the same
currently linked employee can supersede their own current same-kind event.
Forked corrections fail; the original remains in history. Other event kinds
record a new state without modifying stored events.

* `kind:'study'`, payload `{cohort:'baseline'|'assisted',activity_kind:
  'transport'|'nontransport'|'transfer'|'unknown'}`. Set before any check;
  cohort changes freeze after any run, AI/vision job or submission. Baseline
  does not permit automated checks (avoid contaminated controls).
* `kind:'submitted'`, payload `{occurred_at:ISO datetime}`. Human confirmation
  of actual OA submission; never inferred from pressing check.
* `kind:'followup'`, payload `{complete:bool,corrected_after_submission:
  true|false|null,work_complete:bool}`. Must follow submission; incomplete
  outcomes remain unknown, not zero.
* `kind:'work_interval'`, payload `{stage:'import'|'read_review'|'check'|
  'correction'|'recheck'|'second_review'|'post_submission',started_at,ended_at}`.
  Authenticated employee supplies worker identity; no overlap across reports,
  future or negative time. Assigned review-only users may record their work.
  Capture active work with pause; external correction time
  may be entered explicitly. No elapsed-page-time masquerading as work time.
* `kind:'truth_review'`, payload `{run_id:UUID,complete:bool,whole_report_checked:
  bool,items:[{rule_id,truth:'error'|'correct'|'unknown'|'not_applicable',
  error_id:null|UUID,verified_read_state:null|'confirmed'|'unconfirmed'|
  'unreadable'|'not_printed'|'unmapped'}],missed_errors:[{opportunity_id:UUID,
  error_id:UUID,read_state,verified_read_state}]}`. Requires assigned reviewer
  or department scope + report.review; different linked employee from owner.
  May address any report-owned immutable rule/AI/vision run; the UI requires
  opening that run's original before marking whole-report review complete.
  The reviewer may reuse the same error UUID across runs only by explicit
  matching, not by automatic text similarity.
  Extra missed errors represent independent whole-report review, not only
  errors already suggested by the engine. Unknowns block completeness.

`GET /reports/{id}/measurement`: existing `ReportMeasurement` schema, no source
values. Its `report_version` means base original revision, not a claim that all
opportunities derive from a single physical PDF. All runs of originals created
by the recorded actual submission instant are eligible. Late checks on those
originals remain late warnings; new originals created after submission are
excluded from this pre-submission opportunity scope. All history, work and
followup remain retained. Each displayed eligible warning is an opportunity;
actual errors deduplicate by independently assigned UUID. Followup/complete
work become incomplete when later activity invalidates them.

If submission has not been recorded and warnings require timing,
`measurement` remains null with `SUBMISSION_NOT_RECORDED`; no inferred timing.
An over-limit report returns `MEASUREMENT_LIMIT_EXCEEDED`, never truncation.
`measurement_scope` explains eligible runs and excluded post-submission new
original runs. Export refuses pending reports with a fixed conflict response.

`POST /measurement-export`: `{report_ids:[UUID,...]}` (<=100 reports per export) ->
`{dataset_kind,comparison_confirmed:false,held_out_confirmed:false,
followup_days:null,targets:{},reports:[...]}` accepted by the existing
`/emergency/acceptance/preview` and measurement console. Homogeneous dataset,
strict count limits, zero fabricated truths/outcomes/targets.

`POST /correction-patterns`: `{report_ids:[UUID,...]}` (<=1000 distinct visible
reports) gives read-only warning/decision/reason/independent-truth counts over
all retained runs, including post-submission work. Counts of repeated warnings
and affected reports are separate. Reasons not recorded remain unknown.
AI groups use fixed labels; no quote, source hash, patient/employee ID or
source-dependent finding fingerprint is returned. Global verified errors are
deduplicated; group totals are explicitly non-additive. It returns
`automatic_rule_updates:false` and `model_training_performed:false`.
This improvement dashboard is not itself the five-indicator comparison.

## Worker, encryption, and operations

Dedicated PostgreSQL job table: atomic claim, lease, max3 attempts, heartbeat,
stale publication CAS, bounded subprocess, durable retry after restart.
Linux process-group isolation and private temporary storage are required;
native Windows processing is refused by this release. A configured model is
not proof of inference, quality or network isolation. Failed/unavailable AI
never blocks deterministic checking of confirmed fields.
AES-GCM private source files and private DB payloads bind tenant/kind/UUID in
AAD. Key file is an external server secret, not in repository, public endpoint,
or backups. Backups retain ciphertext plus DB; restore needs separately held
key. No plaintext originals/reading in generic audit logs.

Deployment, health checks, update/rollback and restore sequence are specified
in [AUDIT_OPERATIONS.md](AUDIT_OPERATIONS.md). Target hardware, actual model,
real handwritten records and real-data effectiveness require separate evidence.
