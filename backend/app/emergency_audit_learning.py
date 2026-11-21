"""Read-only operational feedback counts, never automatic rules or model training.

Warning counts include every historical check, including rechecks. Independent
truth identifies actual errors; a correction or false-alarm disposition never
creates that truth. Per-group error totals are intentionally non-additive: one
actual error can be associated with both a rule and an AI candidate. Only the
top-level error total deduplicates identities across all groups.

No original, field value, quotation, finding message, source fingerprint or
person identifier is returned. Labels come only from static core definitions or
the immutable rule configuration; AI and unknown items have fixed labels.
"""
from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from . import emergency_audit_service as svc
from . import emergency_vault as vault
from .emergency_audit_models import AuditConfiguration, AuditReport, AuditRun
from .emergency_audit_workflow import active_events, all_runs
from .emergency_review_core import evaluate_confirmed_fields
from .emergency_rule_schemas import RuleSetDefinition
from .models import User


DECISIONS = ('correction_needed', 'false_alarm', 'exception', 'unresolved')
REASONS = ('missing', 'inconsistent', 'code_selection', 'format', 'reading_error', 'local_rule', 'unknown')
READ_STATES = {'confirmed', 'unconfirmed', 'unreadable', 'not_printed', 'unmapped'}
CORE_LABELS = {finding.rule_id: finding.message for finding in evaluate_confirmed_fields({})}
KNOWN_TRUTHS = {'error', 'correct', 'not_applicable'}


def _error_id(item: dict) -> str | None:
    if item.get('truth') != 'error' or not item.get('error_id'):
        return None
    try:
        return str(UUID(str(item['error_id'])))
    except (ValueError, TypeError, AttributeError):
        return None


def _labels(db: Session, identity: str, cache: dict) -> dict[str, str]:
    if identity not in cache:
        row = db.get(AuditConfiguration, identity)
        if row is None or row.kind != 'rules':
            cache[identity] = {}
        else:
            try:
                definition = RuleSetDefinition.model_validate(
                    vault.open_json('config', row.config_id, row.definition_cipher))
            except ValidationError:
                # Never expose a rejected definition or source reference.
                svc.failure(503, '集計に必要な確認項目の設定を読み込めません。')
            cache[identity] = {rule.rule_id: rule.label for rule in definition.rules}
    return cache[identity]


def _group(db: Session, run: AuditRun, rule_id: str, labels: dict) -> tuple[str | None, str, str]:
    if run.mode in {'ai', 'vision'}:
        # Stored AI rule IDs contain a source-dependent candidate fingerprint.
        # Keep those private; group only by the fixed mode identifier.
        return None, 'AI-TEXT' if run.mode == 'ai' else 'AI-VISION', 'AIによる確認候補'
    known = _labels(db, run.rule_set_id, labels) if run.rule_set_id else CORE_LABELS
    if rule_id in known:
        return run.rule_set_id, rule_id, known[rule_id]
    return run.rule_set_id, 'UNKNOWN', '確認項目'


def _feedback(db: Session, parent: AuditReport, run_ids: set[str]) -> tuple[dict, dict, dict]:
    dispositions: dict[str, dict] = defaultdict(dict)
    truths: dict[str, dict] = {}
    for event in active_events(db, parent):
        payload = event.payload
        identity = payload.get('run_id')
        if identity not in run_ids:
            continue
        if event.kind == 'dispositions':
            # Saving a subset edits only those decisions, retaining earlier
            # active decisions for the other findings in that same run.
            for decision in payload.get('decisions', []):
                dispositions[identity][decision['rule_id']] = decision
        elif event.kind == 'truth_review':
            # A truth event is a whole review snapshot, not a partial patch.
            truths[identity] = payload
    linked: dict[tuple[str, str], list] = defaultdict(list)
    for review in truths.values():
        for item in review.get('items', []):
            if _error_id(item) is not None:
                for identity in item.get('detected_in_run_ids', []):
                    if identity in run_ids:
                        linked[(identity, item['rule_id'])].append(item)
    return dispositions, truths, linked


def _truth_for(run_id: str, rule_id: str, adjudicated: dict, linked: dict) -> dict:
    known = adjudicated.get(rule_id)
    if known is not None:
        return known
    candidates = linked.get((run_id, rule_id), [])
    if candidates and len({_error_id(item) for item in candidates}) == 1:
        return candidates[-1]
    return {}


def _complete_review(review: dict, findings: list[dict], adjudicated: dict) -> bool:
    if review.get('complete') is not True or review.get('whole_report_checked') is not True:
        return False
    return all(
        adjudicated.get(item['rule_id'], {}).get('truth') in KNOWN_TRUTHS
        and adjudicated[item['rule_id']].get('verified_read_state') in READ_STATES
        for item in findings
    )


def summarize_patterns(db: Session, user: User, report_ids: list[UUID]) -> dict:
    """Summarize only explicitly selected visible reports, without any writes.

    ``unreviewed_run_count`` counts runs without complete independent review of
    their original and every finding. ``unresolved_truth_count`` is per finding,
    including untested findings; it is separate from unresolved warning actions.
    Reasons, decisions and each group's affected report count cover warnings
    only. Explicit independently recorded
    missed errors contribute to the global error count without inventing a rule
    or cause for them. These are operational counts, not a recall estimate.
    """
    if not isinstance(report_ids, list) or not 1 <= len(report_ids) <= 1000:
        svc.failure(422, '対象の報告書を1件から1000件まで選択してください。')
    try:
        selected = {str(UUID(str(identity))) for identity in report_ids}
    except (ValueError, TypeError, AttributeError):
        svc.failure(422, '対象の報告書を確認してください。')

    result = {'report_count': len(selected), 'run_count': 0, 'unreviewed_run_count': 0,
              'verified_error_count': 0, 'items': [], 'group_totals_additive': False,
              'automatic_rule_updates': False, 'model_training_performed': False}
    groups: dict[tuple[str | None, str], dict] = {}
    actual_errors: set[str] = set()
    configuration_labels: dict = {}
    # This helper must remain read-only even if its caller has pending changes.
    with db.no_autoflush:
        parents = list(db.scalars(svc.reports_query(db, user).where(AuditReport.report_id.in_(selected))
                                  .order_by(AuditReport.report_id)))
        if len(parents) != len(selected):
            # Reject the whole selection before decrypting any run. Missing and
            # unauthorized identities have exactly the same response.
            svc.failure(404, '対象の報告書を参照できません。')
        for dataset in {parent.dataset_kind for parent in parents}:
            svc.allow_dataset(dataset)
        for parent in parents:
            runs = all_runs(db, parent)
            result['run_count'] += len(runs)
            decisions, truths, linked = _feedback(db, parent, {run.run_id for run in runs})
            for run in runs:
                snapshot = vault.open_json('run', run.run_id, run.payload_cipher)
                findings = snapshot['findings']
                review = truths.get(run.run_id, {})
                adjudicated = {item['rule_id']: item for item in review.get('items', [])}
                if not _complete_review(review, findings, adjudicated):
                    result['unreviewed_run_count'] += 1
                for finding in findings:
                    rule_id = finding['rule_id']
                    configuration, output_rule, label = _group(db, run, rule_id, configuration_labels)
                    key = (configuration, output_rule)
                    if key not in groups:
                        groups[key] = {'rule_id': output_rule, 'rule_set_id': configuration, 'label': label,
                            'warning_count': 0, 'report_count': 0,
                            'decision_counts': dict.fromkeys(DECISIONS, 0), 'reason_counts': dict.fromkeys(REASONS, 0),
                            'verified_error_count': 0, 'unresolved_truth_count': 0,
                            '_reports': set(), '_errors': set()}
                    group = groups[key]
                    known = _truth_for(run.run_id, rule_id, adjudicated, linked)
                    error = _error_id(known)
                    if error is not None:
                        group['_errors'].add(error); actual_errors.add(error)
                    if known.get('truth') not in KNOWN_TRUTHS or (known.get('truth') == 'error' and error is None):
                        group['unresolved_truth_count'] += 1
                    if finding['status'] != 'REVIEW_REQUIRED':
                        continue
                    group['warning_count'] += 1
                    group['_reports'].add(parent.report_id)
                    feedback = decisions.get(run.run_id, {}).get(rule_id, {})
                    decision = feedback.get('decision', 'unresolved')
                    reason = feedback.get('reason_code', 'unknown')
                    group['decision_counts'][decision if decision in DECISIONS else 'unresolved'] += 1
                    group['reason_counts'][reason if reason in REASONS else 'unknown'] += 1
                for missed in review.get('missed_errors', []):
                    identity = _error_id({**missed, 'truth': 'error'})
                    if identity is not None:
                        actual_errors.add(identity)
    for group in groups.values():
        group['report_count'] = len(group.pop('_reports'))
        group['verified_error_count'] = len(group.pop('_errors'))
    result['items'] = sorted(groups.values(), key=lambda group: (
        -group['warning_count'], group['rule_set_id'] or '', group['rule_id']))
    result['verified_error_count'] = len(actual_errors)
    return result
