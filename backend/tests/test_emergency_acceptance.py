"""Hand-derived, synthetic-only acceptance measurement examples."""
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.emergency_acceptance import evaluate_acceptance
from app.emergency_acceptance_schemas import EvaluationInput, Opportunity, ReportMeasurement, Targets, WorkInterval


def uid(number):
    return str(UUID(int=number))


def opportunity(number, truth="correct", decision="clear", **updates):
    item = {
        "opportunity_id": uid(number), "truth": truth, "decision": decision,
        "read_state": "confirmed", "verified_read_state": "confirmed",
    }
    if truth == "error":
        item["error_id"] = uid(100_000 + number)
    if decision == "warning":
        item["before_submission"] = True
    item.update(updates)
    return item


def interval(worker=900, start=0, end=60, **updates):
    return {"worker_id": uid(worker), "stage": "check", "start_seconds": start, "end_seconds": end, **updates}


def report(number, cohort="assisted", **updates):
    return {
        "report_id": uid(10_000 + number), "report_version": 1, "cohort": cohort,
        "followup_complete": True, "corrected_after_submission": False,
        "independent_review_complete": True, "work_complete": True,
        "opportunities": [opportunity(number)], "work": [interval()], **updates,
    }


def evaluation(reports=None, **updates):
    return EvaluationInput.model_validate({
        "dataset_kind": "internal_trial", "comparison_confirmed": True,
        "held_out_confirmed": True, "followup_days": 30,
        "targets": {
            "correction_reduction_percent": 50, "recall": 1,
            "false_alerts_per_report": 0, "time_reduction_percent": 50,
            "read_state_accuracy": 1, "minimum_reports_per_cohort": 1,
            "minimum_true_errors": 1,
        }, "reports": reports or [], **updates,
    })


def passing_input(**updates):
    return evaluation([
        report(1, "baseline", corrected_after_submission=True, work=[interval(end=120)]),
        report(2, opportunities=[opportunity(2, "error", "warning")]),
    ], **updates)


def test_empty_dataset_never_passes_or_produces_zero_denominator_success():
    result = evaluate_acceptance(evaluation())
    assert result["production_complete"] is False
    assert result["status"] == "INCOMPLETE"
    for metric in result["metrics"].values():
        assert metric["status"] == "NOT_MEASURED"
    assert result["metrics"]["recall"]["rate"] is None
    assert result["metrics"]["false_alerts"]["per_report"] is None


def test_numeric_targets_met_is_never_production_completion():
    result = evaluate_acceptance(passing_input())
    assert result["status"] == "NUMERIC_TARGETS_MET"
    assert result["production_complete"] is False
    assert all(item["status"] == "MET" for item in result["metrics"].values())
    assert "PRIVACY_EVIDENCE_REQUIRED" in result["blockers"]
    assert "RULE_APPROVAL_REQUIRED" in result["blockers"]
    assert "FORM_APPROVAL_REQUIRED" in result["blockers"]
    assert "ENVIRONMENT_APPROVAL_REQUIRED" in result["blockers"]


def test_synthetic_data_remains_development_only_even_when_targets_met():
    result = evaluate_acceptance(passing_input(dataset_kind="synthetic"))
    assert result["status"] == "DEVELOPMENT_ONLY"
    assert result["production_complete"] is False
    assert "DEVELOPMENT_ONLY" in result["blockers"]


def test_correction_rate_difference_and_relative_reduction_are_distinct():
    records = [
        report(1, "baseline", corrected_after_submission=True), report(2, "baseline"),
        report(3), report(4), report(5), report(6, corrected_after_submission=True),
    ]
    metric = evaluate_acceptance(evaluation(records))["metrics"]["corrections"]
    assert metric["baseline"]["numerator"] == 1
    assert metric["baseline"]["denominator"] == 2
    assert metric["baseline"]["rate"] == 0.5
    assert metric["assisted"]["rate"] == 0.25
    assert metric["percentage_points"] == 25
    assert metric["reduction_percent"] == 50


def test_zero_baseline_correction_rate_has_no_relative_reduction():
    metric = evaluate_acceptance(evaluation([report(1, "baseline"), report(2)]))["metrics"]["corrections"]
    assert metric["reduction_percent"] is None
    assert metric["percentage_points"] == 0
    assert metric["status"] != "MET"


@pytest.mark.parametrize("updates", [
    {"followup_complete": False, "corrected_after_submission": True},
    {"followup_complete": True, "corrected_after_submission": None},
])
def test_unfinished_outcomes_are_pending_even_if_a_correction_is_known(updates):
    data = passing_input().model_dump(mode="json")
    data["reports"].append(report(3, **updates))
    result = evaluate_acceptance(EvaluationInput.model_validate(data))
    assert result["metrics"]["corrections"]["assisted"]["pending"] == 1
    assert result["metrics"]["corrections"]["assisted"]["denominator"] == 1
    assert result["metrics"]["corrections"]["status"] == "PENDING"
    assert result["metrics"]["time"]["assisted"]["missing"] == 1
    assert result["status"] == "INCOMPLETE"


def test_duplicate_warnings_for_one_error_are_one_detection():
    ops = [opportunity(1, "error", "warning"), opportunity(2, "error", "warning", error_id=uid(100_001))]
    result = evaluate_acceptance(evaluation([report(1, opportunities=ops)]))["metrics"]
    assert result["recall"]["actual_errors"] == 1
    assert result["recall"]["detected_errors"] == 1
    assert result["recall"]["rate"] == 1
    assert result["false_alerts"]["true_alerts"] == 2


def test_unreadable_unchecked_real_error_is_a_miss_not_excluded():
    ops = [opportunity(1, "error", "warning"), opportunity(2, "error", "unchecked", read_state="unreadable", verified_read_state="unreadable")]
    result = evaluate_acceptance(evaluation([report(1, opportunities=ops)]))["metrics"]
    assert result["recall"]["actual_errors"] == 2
    assert result["recall"]["detected_errors"] == 1
    assert result["recall"]["rate"] == 0.5
    assert result["read_states"]["unreadable"] == 1
    assert result["read_states"]["unchecked"] == 1
    assert result["read_states"]["accuracy"] == 1


def test_late_warning_is_never_pre_submission_detection():
    ops = [opportunity(1, "error", "warning", before_submission=False)]
    metric = evaluate_acceptance(evaluation([report(1, opportunities=ops)]))["metrics"]["recall"]
    assert metric["detected_errors"] == 0
    assert metric["rate"] == 0
    assert metric["late_errors"] == 1


def test_false_alerts_count_correct_and_not_applicable_truth_separately_from_recall():
    ops = [
        opportunity(1, "error", "warning"),
        opportunity(2, "error", "warning", error_id=uid(100_001)),
        opportunity(3, "correct", "warning"),
        opportunity(4, "not_applicable", "warning"),
        opportunity(5, "correct", "warning", before_submission=False),
    ]
    result = evaluate_acceptance(evaluation([report(1, opportunities=ops)]))["metrics"]
    assert result["recall"]["detected_errors"] == 1
    assert result["false_alerts"]["count"] == 2
    assert result["false_alerts"]["reviewed_reports"] == 1
    assert result["false_alerts"]["per_report"] == 2
    assert result["false_alerts"]["false_fraction"] == 0.5


def test_no_warnings_is_not_perfect_recall_or_a_defined_false_fraction():
    result = evaluate_acceptance(evaluation([report(1)]))["metrics"]
    assert result["false_alerts"]["per_report"] == 0
    assert result["false_alerts"]["false_fraction"] is None
    assert result["recall"]["rate"] is None
    assert result["recall"]["status"] == "NOT_MEASURED"


@pytest.mark.parametrize("unresolved_report", [
    report(2, opportunities=[opportunity(2, "unknown", "warning")]),
    report(2, independent_review_complete=False),
    report(2, opportunities=[]),
])
def test_false_fraction_waits_for_all_timely_warning_truth_and_report_reviews(unresolved_report):
    records = [report(1, opportunities=[opportunity(1, "correct", "warning")]), unresolved_report]
    metric = evaluate_acceptance(evaluation(records))["metrics"]["false_alerts"]
    assert metric["count"] == 1
    assert metric["true_alerts"] == 0
    assert metric["unresolved"] == 1
    # Known false warnings remain visible, but unknown warnings/reports cannot
    # silently disappear from an apparent fraction of all timely warnings.
    assert metric["false_fraction"] is None


def test_late_unknown_warning_is_excluded_from_the_timely_false_fraction():
    records = [report(1, opportunities=[
        opportunity(1, "correct", "warning"),
        opportunity(2, "unknown", "warning", before_submission=False),
    ])]
    metric = evaluate_acceptance(evaluation(records))["metrics"]["false_alerts"]
    assert metric["count"] == 1
    assert metric["unresolved_warnings"] == 0
    assert metric["late_warnings"] == 1
    assert metric["false_fraction"] == 1


@pytest.mark.parametrize("updates", [
    {"independent_review_complete": False},
    {"opportunities": []},
    {"opportunities": [opportunity(50, "unknown", "warning")]},
])
def test_incomplete_review_cannot_be_hidden_by_other_successes(updates):
    data = passing_input().model_dump(mode="json")
    data["reports"].append(report(3, **updates))
    result = evaluate_acceptance(EvaluationInput.model_validate(data))
    assert result["metrics"]["recall"]["unresolved"] >= 1
    assert result["metrics"]["recall"]["status"] == "PENDING"
    assert result["metrics"]["false_alerts"]["status"] != "MET"
    assert result["status"] == "INCOMPLETE"


def test_total_time_counts_different_workers_and_all_stages():
    records = [
        report(1, "baseline", work=[interval(end=60), interval(worker=901, end=120, stage="post_submission")]),
        report(2, "baseline", work=[interval(end=60)]),
        report(3, work=[interval(end=60)]),
    ]
    metric = evaluate_acceptance(evaluation(records))["metrics"]["time"]
    assert metric["baseline"]["mean_minutes"] == 2
    assert metric["baseline"]["median_minutes"] == 2
    assert metric["assisted"]["mean_minutes"] == 1
    assert metric["reduction_percent"] == 50


def test_measured_zero_time_differs_from_missing_time():
    records = [report(1, "baseline", work=[]), report(2, work=[]), report(3, work_complete=False)]
    metric = evaluate_acceptance(evaluation(records))["metrics"]["time"]
    assert metric["baseline"]["reports"] == 1
    assert metric["baseline"]["mean_minutes"] == 0
    assert metric["assisted"]["reports"] == 1
    assert metric["assisted"]["missing"] == 1
    assert metric["reduction_percent"] is None
    assert metric["status"] != "MET"


@pytest.mark.parametrize("reported,verified", [
    ("unreadable", "unreadable"), ("unconfirmed", "unconfirmed"),
    ("not_printed", "not_printed"), ("unmapped", "unmapped"),
    ("confirmed", "unreadable"),
])
def test_unsafe_clear_cannot_pass_even_if_accuracy_target_is_low(reported, verified):
    data = passing_input().model_dump(mode="json")
    data["targets"]["read_state_accuracy"] = 0
    data["reports"][1]["opportunities"].append(opportunity(3, read_state=reported, verified_read_state=verified))
    result = evaluate_acceptance(EvaluationInput.model_validate(data))
    assert result["metrics"]["read_states"]["unsafe_clear"] == 1
    assert result["metrics"]["read_states"]["status"] == "NOT_MET"
    assert result["status"] == "INCOMPLETE"


def test_unverified_read_state_is_pending_not_correct():
    data = passing_input().model_dump(mode="json")
    data["reports"][1]["opportunities"].append(opportunity(3, verified_read_state=None))
    metric = evaluate_acceptance(EvaluationInput.model_validate(data))["metrics"]["read_states"]
    assert metric["verified"] == 1
    assert metric["matched"] == 1
    assert metric["unresolved"] == 1
    assert metric["status"] == "PENDING"


def test_targets_have_no_manufactured_defaults():
    result = evaluate_acceptance(passing_input(targets={}))
    assert all(metric["status"] == "TARGET_UNSET" for metric in result["metrics"].values())
    assert result["status"] == "INCOMPLETE"


@pytest.mark.parametrize("field,value", [("minimum_reports_per_cohort", 2), ("minimum_true_errors", 2)])
def test_sample_minimum_is_a_real_gate(field, value):
    data = passing_input().model_dump(mode="json")
    data["targets"][field] = value
    result = evaluate_acceptance(EvaluationInput.model_validate(data))
    assert result["status"] == "INCOMPLETE"
    assert result["metrics"]["recall"]["status"] == "INSUFFICIENT_DATA"


@pytest.mark.parametrize("field,value", [("comparison_confirmed", False), ("held_out_confirmed", False), ("followup_days", None)])
def test_missing_evaluation_prerequisite_blocks_numerical_readiness(field, value):
    result = evaluate_acceptance(passing_input(**{field: value}))
    assert result["status"] == "INCOMPLETE"
    assert any(metric["status"] == "PENDING" for metric in result["metrics"].values())


def test_result_has_no_report_opportunity_error_or_worker_id_and_does_not_mutate_input():
    data = passing_input()
    before = data.model_dump(mode="json")
    result = evaluate_acceptance(data)
    serialized = json.dumps(result, allow_nan=False)
    for item in before["reports"]:
        assert item["report_id"] not in serialized
        for op in item["opportunities"]:
            assert op["opportunity_id"] not in serialized
            if op["error_id"]:
                assert op["error_id"] not in serialized
        for work in item["work"]:
            assert work["worker_id"] not in serialized
    assert data.model_dump(mode="json") == before


def test_counts_expose_cohorts_and_case_mix():
    data = passing_input().model_dump(mode="json")
    data["reports"][0]["activity_kind"] = "transport"
    data["reports"][1]["activity_kind"] = "transfer"
    data["reports"][1]["document_kind"] = "image_pdf"
    counts = evaluate_acceptance(EvaluationInput.model_validate(data))["counts"]
    assert counts["baseline_reports"] == 1
    assert counts["assisted_reports"] == 1
    assert counts["strata"]["baseline"]["activity_kind"]["transport"] == 1
    assert counts["strata"]["assisted"]["document_kind"]["image_pdf"] == 1


@pytest.mark.parametrize("updates", [{"error_id": None}, {"error_id": uid(1), "truth": "correct"}])
def test_error_identity_matches_truth(updates):
    with pytest.raises(ValidationError):
        Opportunity.model_validate({**opportunity(1, "error", "warning"), **updates})


@pytest.mark.parametrize("updates", [
    {"before_submission": None}, {"decision": "clear", "before_submission": True},
])
def test_submission_timing_is_explicit_for_warnings_only(updates):
    with pytest.raises(ValidationError):
        Opportunity.model_validate({**opportunity(1, "error", "warning"), **updates})


def test_same_report_id_with_another_version_is_rejected():
    with pytest.raises(ValidationError):
        evaluation([report(1), report(1, report_version=2)])


def test_opportunity_id_must_be_unique_across_reports():
    with pytest.raises(ValidationError):
        evaluation([report(1), report(2, opportunities=[opportunity(1)])])


def test_error_id_cannot_move_between_reports():
    with pytest.raises(ValidationError):
        evaluation([
            report(1, opportunities=[opportunity(1, "error", "warning")]),
            report(2, opportunities=[opportunity(2, "error", "warning", error_id=uid(100_001))]),
        ])


def test_same_person_overlapping_work_is_rejected():
    with pytest.raises(ValidationError):
        ReportMeasurement.model_validate(report(1, work=[interval(end=90), interval(start=60, end=120, stage="correction")]))


def test_same_person_adjacent_and_zero_intervals_are_valid():
    ReportMeasurement.model_validate(report(1, work=[interval(end=60), interval(start=60, end=120), interval(start=30, end=30)]))


def test_worker_relative_timelines_are_scoped_per_report():
    evaluation([report(1), report(2)])


@pytest.mark.parametrize("updates", [{"start_seconds": -1}, {"end_seconds": -1}, {"start_seconds": 2, "end_seconds": 1}, {"start_seconds": True}, {"end_seconds": "60"}, {"end_seconds": 60.5}])
def test_invalid_work_intervals_are_rejected(updates):
    with pytest.raises(ValidationError):
        WorkInterval.model_validate(interval(**updates))


@pytest.mark.parametrize("field,value", [
    ("recall", float("nan")), ("recall", float("inf")), ("recall", -0.1), ("recall", 1.1),
    ("recall", "0.9"), ("recall", True), ("false_alerts_per_report", -1),
    ("correction_reduction_percent", 101), ("time_reduction_percent", -1),
    ("minimum_reports_per_cohort", True), ("minimum_true_errors", 0),
])
def test_invalid_targets_are_rejected(field, value):
    with pytest.raises(ValidationError):
        Targets.model_validate({field: value})


@pytest.mark.parametrize("field,value", [("comparison_confirmed", "true"), ("held_out_confirmed", 1), ("followup_days", True)])
def test_strict_evaluation_types_are_enforced(field, value):
    with pytest.raises(ValidationError):
        evaluation(**{field: value})


@pytest.mark.parametrize("field,value", [("report_version", 1.0), ("report_version", 0), ("followup_complete", 1), ("corrected_after_submission", "false"), ("independent_review_complete", "yes"), ("work_complete", 1)])
def test_strict_report_types_are_enforced(field, value):
    with pytest.raises(ValidationError):
        ReportMeasurement.model_validate(report(1, **{field: value}))


@pytest.mark.parametrize("factory,extra", [
    (lambda: {"dataset_kind": "synthetic"}, {"patient_name": "SYNTHETIC_PRIVATE_MARKER"}),
])
def test_arbitrary_fields_are_rejected_without_reflecting_input_values_in_exception_text(factory, extra):
    with pytest.raises(ValidationError) as exc:
        EvaluationInput.model_validate({**factory(), **extra})
    assert "SYNTHETIC_PRIVATE_MARKER" not in str(exc.value)


def test_nested_arbitrary_fields_are_rejected():
    with pytest.raises(ValidationError):
        evaluation([report(1, opportunities=[{**opportunity(1), "raw_ocr": "SYNTHETIC_PRIVATE_MARKER"}])])


def test_batch_resource_limits():
    with pytest.raises(ValidationError):
        evaluation([report(i) for i in range(1001)])
    with pytest.raises(ValidationError):
        evaluation([report(1, opportunities=[opportunity(i) for i in range(1001)])])
    with pytest.raises(ValidationError):
        evaluation([report(1, work=[interval(start=i, end=i) for i in range(1001)])])
    with pytest.raises(ValidationError):
        evaluation([report(i, opportunities=[opportunity(i * 1000 + j) for j in range(1000)]) for i in range(21)])


def test_oversized_raw_batch_is_rejected_before_nested_item_validation():
    # Reject the request as a whole before expanding thousands of item errors.
    with pytest.raises(ValidationError) as exc:
        EvaluationInput.model_validate({
            "dataset_kind": "synthetic",
            "reports": [{"opportunities": [{}] * 1000}] * 21,
        })
    assert exc.value.error_count() == 1
    assert "Evaluation opportunity limit exceeded." in str(exc.value)


def test_mutated_models_are_revalidated_before_evaluation():
    data = passing_input()
    data.reports.append(data.reports[0])
    with pytest.raises(ValidationError):
        evaluate_acceptance(data)


def test_excessive_integer_duration_is_rejected_without_overflow():
    with pytest.raises(ValidationError):
        ReportMeasurement.model_validate(report(1, work=[interval(end=10 ** 400)]))


def test_large_finite_durations_never_produce_nonfinite_aggregates():
    data = evaluation([
        report(1, "baseline", work=[interval(end=10 ** 310)]),
        report(2, "baseline", work=[interval(end=10 ** 310)]),
        report(3, work=[interval(end=10 ** 310)]),
    ])
    result = evaluate_acceptance(data)
    json.dumps(result, allow_nan=False)
    assert result["metrics"]["time"]["reduction_percent"] == 0


def test_extreme_reduction_is_unmeasured_instead_of_infinity():
    result = evaluate_acceptance(evaluation([
        report(1, "baseline", work=[interval(end=1)]),
        report(2, work=[interval(end=10 ** 310)]),
    ]))
    assert result["metrics"]["time"]["reduction_percent"] is None
    assert result["metrics"]["time"]["status"] == "NOT_MEASURED"
    json.dumps(result, allow_nan=False)
