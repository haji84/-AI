"""Deterministic acceptance measurements, never production authorization.

All inputs are independently recorded study observations. No original report,
OCR text, network call, diagnosis, or change to operational data is used here.
The result contains aggregate counts and fixed vocabulary only. Even numerical
target attainment cannot establish privacy, approval, or operational safety.
"""
from math import isfinite
from statistics import mean

from .emergency_acceptance_schemas import EvaluationInput, ReportMeasurement


_EXTERNAL_BLOCKERS = (
    "PRIVACY_EVIDENCE_REQUIRED", "RULE_APPROVAL_REQUIRED",
    "FORM_APPROVAL_REQUIRED", "ENVIRONMENT_APPROVAL_REQUIRED",
    "INDEPENDENT_ACCEPTANCE_REQUIRED",
)
_ACTIVITIES = ("transport", "nontransport", "transfer", "unknown")
_DOCUMENTS = ("text_pdf", "image_pdf", "photo", "mixed", "unknown")


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _reduction(baseline: float | None, assisted: float | None) -> float | None:
    if baseline is None or assisted is None or baseline == 0:
        return None
    result = (baseline - assisted) / baseline * 100
    return result if isfinite(result) else None


def _status(
    measured: bool, *, pending: bool, target_configured: bool,
    sufficient: bool, meets: bool, unsafe: bool = False,
) -> str:
    if unsafe:
        return "NOT_MET"
    if not measured:
        return "NOT_MEASURED"
    if pending:
        return "PENDING"
    if not target_configured:
        return "TARGET_UNSET"
    if not sufficient:
        return "INSUFFICIENT_DATA"
    return "MET" if meets else "NOT_MET"


def _outcome_known(report: ReportMeasurement) -> bool:
    return report.followup_complete and report.corrected_after_submission is not None


def _correction_summary(reports: list[ReportMeasurement]) -> dict:
    completed = [report for report in reports if _outcome_known(report)]
    corrections = sum(report.corrected_after_submission is True for report in completed)
    return {
        "numerator": corrections, "denominator": len(completed),
        "rate": _ratio(corrections, len(completed)),
        "pending": len(reports) - len(completed),
    }


def _time_summary(reports: list[ReportMeasurement]) -> dict:
    values = [
        sum(item.end_seconds - item.start_seconds for item in report.work) / 60
        for report in reports if _outcome_known(report) and report.work_complete
    ]
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    median_value = None
    if ordered:
        # Divide first to avoid an overflow for two individually finite values.
        median_value = ordered[midpoint] if len(ordered) % 2 else (
            ordered[midpoint - 1] / 2 + ordered[midpoint] / 2
        )
    return {
        "reports": len(values), "missing": len(reports) - len(values),
        "mean_minutes": mean(values) if values else None,
        "median_minutes": median_value,
    }


def evaluate_acceptance(payload: EvaluationInput) -> dict:
    """Return descriptive metrics with explicit measurement and approval gaps.

    ``unresolved`` combines unresolved opportunities with one placeholder for
    each unreviewed/empty report. Separate counters expose those components;
    it is a backlog count, never an error denominator. Permanently external
    blockers are present even when ``NUMERIC_TARGETS_MET`` is returned.
    """
    payload = EvaluationInput.model_validate(payload)
    targets = payload.targets
    groups = {
        cohort: [report for report in payload.reports if report.cohort == cohort]
        for cohort in ("baseline", "assisted")
    }
    minimum_reports = targets.minimum_reports_per_cohort
    minimum_errors = targets.minimum_true_errors
    cohort_minimum_set = minimum_reports is not None
    comparison_pending = not payload.comparison_confirmed or payload.followup_days is None

    corrections = {cohort: _correction_summary(reports) for cohort, reports in groups.items()}
    correction_reduction = _reduction(corrections["baseline"]["rate"], corrections["assisted"]["rate"])
    correction_points = None
    if corrections["baseline"]["rate"] is not None and corrections["assisted"]["rate"] is not None:
        correction_points = (corrections["baseline"]["rate"] - corrections["assisted"]["rate"]) * 100
    pending_outcomes = sum(item["pending"] for item in corrections.values())
    corrections.update({
        "reduction_percent": correction_reduction, "percentage_points": correction_points,
        "status": _status(
            correction_reduction is not None,
            pending=comparison_pending or pending_outcomes > 0,
            target_configured=targets.correction_reduction_percent is not None and cohort_minimum_set,
            sufficient=cohort_minimum_set and all(corrections[group]["denominator"] >= minimum_reports for group in groups),
            meets=correction_reduction is not None and targets.correction_reduction_percent is not None
            and correction_reduction >= targets.correction_reduction_percent,
        ),
    })

    assisted = groups["assisted"]
    reviewed = [report for report in assisted if report.independent_review_complete and report.opportunities]
    unreviewed = sum(not report.independent_review_complete for report in assisted)
    empty_reviewed = sum(report.independent_review_complete and not report.opportunities for report in assisted)
    incomplete_reports = unreviewed + empty_reviewed
    opportunities = [item for report in reviewed for item in report.opportunities]
    unknown_truth = sum(item.truth == "unknown" for item in opportunities)
    errors = {item.error_id for item in opportunities if item.truth == "error"}
    detected = {
        item.error_id for item in opportunities
        if item.truth == "error" and item.decision == "warning" and item.before_submission is True
    }
    late = {
        item.error_id for item in opportunities
        if item.truth == "error" and item.decision == "warning" and item.before_submission is False
    }
    late_warning_count = sum(item.decision == "warning" and item.before_submission is False for item in opportunities)
    recall_rate = _ratio(len(detected), len(errors))
    review_pending = incomplete_reports > 0 or unknown_truth > 0 or not payload.held_out_confirmed
    reviewed_sufficient = cohort_minimum_set and len(reviewed) >= minimum_reports
    recall = {
        "detected_errors": len(detected), "actual_errors": len(errors), "rate": recall_rate,
        "unresolved": incomplete_reports + unknown_truth,
        "unreviewed_reports": unreviewed, "empty_reports": empty_reviewed,
        "unknown_opportunities": unknown_truth, "reviewed_reports": len(reviewed),
        "late_errors": len(late - detected), "late_warnings": late_warning_count,
        "status": _status(
            recall_rate is not None, pending=review_pending,
            target_configured=targets.recall is not None and cohort_minimum_set and minimum_errors is not None,
            sufficient=reviewed_sufficient and minimum_errors is not None and len(errors) >= minimum_errors,
            meets=recall_rate is not None and targets.recall is not None and recall_rate >= targets.recall,
        ),
    }

    before_warnings = [item for item in opportunities if item.decision == "warning" and item.before_submission is True]
    false_count = sum(item.truth in ("correct", "not_applicable") for item in before_warnings)
    true_alerts = sum(item.truth == "error" for item in before_warnings)
    unresolved_warnings = sum(item.truth == "unknown" for item in before_warnings)
    per_report = _ratio(false_count, len(reviewed))
    false_alerts = {
        "count": false_count, "reviewed_reports": len(reviewed), "per_report": per_report,
        "true_alerts": true_alerts,
        # This is the fraction of all timely warnings, not only warnings whose
        # truth happens to be resolved. Keep known counts but withhold the
        # fraction while warnings or whole report reviews are unresolved.
        "false_fraction": None if unresolved_warnings or incomplete_reports else _ratio(
            false_count, false_count + true_alerts),
        "unresolved": incomplete_reports + unresolved_warnings,
        "unreviewed_reports": unreviewed, "empty_reports": empty_reviewed,
        "unknown_opportunities": unknown_truth, "unresolved_warnings": unresolved_warnings,
        "late_warnings": late_warning_count,
        "status": _status(
            per_report is not None, pending=review_pending,
            target_configured=targets.false_alerts_per_report is not None and cohort_minimum_set,
            sufficient=reviewed_sufficient,
            meets=per_report is not None and targets.false_alerts_per_report is not None
            and per_report <= targets.false_alerts_per_report,
        ),
    }

    time = {cohort: _time_summary(reports) for cohort, reports in groups.items()}
    time_reduction = _reduction(time["baseline"]["mean_minutes"], time["assisted"]["mean_minutes"])
    missing_time = sum(item["missing"] for item in time.values())
    time.update({
        "reduction_percent": time_reduction,
        "status": _status(
            time_reduction is not None, pending=comparison_pending or missing_time > 0,
            target_configured=targets.time_reduction_percent is not None and cohort_minimum_set,
            sufficient=cohort_minimum_set and all(time[group]["reports"] >= minimum_reports for group in groups),
            meets=time_reduction is not None and targets.time_reduction_percent is not None
            and time_reduction >= targets.time_reduction_percent,
        ),
    })

    verified = [item for item in opportunities if item.verified_read_state is not None]
    matched = sum(item.read_state == item.verified_read_state for item in verified)
    unverified = len(opportunities) - len(verified)
    unsafe_clear = sum(
        item.decision == "clear" and (
            item.read_state != "confirmed"
            or item.verified_read_state in ("unconfirmed", "unreadable", "not_printed", "unmapped")
        ) for item in opportunities
    )
    read_accuracy = _ratio(matched, len(verified))
    read_states = {
        "matched": matched, "verified": len(verified), "accuracy": read_accuracy,
        "unresolved": incomplete_reports + unverified, "unverified_opportunities": unverified,
        "unreviewed_reports": unreviewed, "empty_reports": empty_reviewed,
        "unreadable": sum(item.read_state == "unreadable" for item in opportunities),
        "unchecked": sum(item.decision == "unchecked" for item in opportunities),
        "unsafe_clear": unsafe_clear,
        "status": _status(
            read_accuracy is not None,
            pending=incomplete_reports > 0 or unverified > 0 or not payload.held_out_confirmed,
            target_configured=targets.read_state_accuracy is not None and cohort_minimum_set,
            sufficient=reviewed_sufficient, unsafe=unsafe_clear > 0,
            meets=read_accuracy is not None and targets.read_state_accuracy is not None
            and read_accuracy >= targets.read_state_accuracy,
        ),
    }

    metrics = {
        "corrections": corrections, "recall": recall, "false_alerts": false_alerts,
        "time": time, "read_states": read_states,
    }
    blockers = list(_EXTERNAL_BLOCKERS)
    conditions = (
        (payload.dataset_kind == "synthetic", "DEVELOPMENT_ONLY"),
        (not payload.reports, "NO_MEASUREMENTS"),
        (not payload.comparison_confirmed, "COMPARISON_NOT_CONFIRMED"),
        (not payload.held_out_confirmed, "HOLDOUT_NOT_CONFIRMED"),
        (payload.followup_days is None, "FOLLOWUP_WINDOW_UNSET"),
        (any(value is None for value in (
            targets.correction_reduction_percent, targets.recall, targets.false_alerts_per_report,
            targets.time_reduction_percent, targets.read_state_accuracy,
        )), "TARGETS_UNSET"),
        (not cohort_minimum_set or minimum_errors is None, "SAMPLE_MINIMUMS_UNSET"),
        (pending_outcomes > 0, "PENDING_FOLLOWUP"),
        (incomplete_reports > 0, "INCOMPLETE_INDEPENDENT_REVIEW"),
        (unknown_truth > 0, "UNKNOWN_TRUTH"),
        (unverified > 0, "READ_STATES_UNVERIFIED"),
        (unsafe_clear > 0, "UNSAFE_CLEAR"),
        (missing_time > 0, "WORK_TIME_MISSING"),
        (correction_reduction is None, "CORRECTION_REDUCTION_UNDEFINED"),
        (time_reduction is None, "TIME_REDUCTION_UNDEFINED"),
        (any(item["status"] == "INSUFFICIENT_DATA" for item in metrics.values()), "INSUFFICIENT_SAMPLE"),
        (any(item["status"] == "NOT_MET" for item in metrics.values()), "NUMERIC_TARGETS_NOT_MET"),
    )
    blockers.extend(code for condition, code in conditions if condition)
    numeric_met = all(item["status"] == "MET" for item in metrics.values())
    status = "DEVELOPMENT_ONLY" if payload.dataset_kind == "synthetic" else (
        "NUMERIC_TARGETS_MET" if numeric_met else "INCOMPLETE"
    )
    strata = {
        cohort: {
            "activity_kind": {kind: sum(report.activity_kind == kind for report in reports) for kind in _ACTIVITIES},
            "document_kind": {kind: sum(report.document_kind == kind for report in reports) for kind in _DOCUMENTS},
        } for cohort, reports in groups.items()
    }
    return {
        "dataset_kind": payload.dataset_kind, "production_complete": False, "status": status,
        "completion_scope": "MEASUREMENT_ONLY", "metrics": metrics, "blockers": blockers,
        "counts": {
            "total_reports": len(payload.reports), "baseline_reports": len(groups["baseline"]),
            "assisted_reports": len(assisted), "assisted_reviewed_reports": len(reviewed),
            "assisted_unreviewed_reports": unreviewed, "assisted_empty_reports": empty_reviewed,
            "opportunities": sum(len(report.opportunities) for report in payload.reports),
            "strata": strata,
        },
    }
