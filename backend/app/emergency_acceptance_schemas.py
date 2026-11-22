"""Typed, original-free inputs for internal acceptance measurement.

The limits below bound an evaluation request; they are not server capacity
claims. UUIDs are study identities, never source case identifiers.
"""
from collections import defaultdict
from math import isfinite
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


ReadState = Literal["confirmed", "unconfirmed", "unreadable", "not_printed", "unmapped"]
PositiveInt = Annotated[StrictInt, Field(ge=1)]
NonnegativeInt = Annotated[StrictInt, Field(ge=0)]
Proportion = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
ReductionPercent = Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)]
NonnegativeFinite = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class StrictMeasurement(BaseModel):
    model_config = ConfigDict(
        extra="forbid", hide_input_in_errors=True, allow_inf_nan=False,
        revalidate_instances="always",
    )


class Opportunity(StrictMeasurement):
    opportunity_id: UUID
    truth: Literal["error", "correct", "unknown", "not_applicable"]
    error_id: UUID | None = None
    decision: Literal["warning", "clear", "unchecked", "not_applicable"]
    before_submission: StrictBool | None = None
    read_state: ReadState
    verified_read_state: ReadState | None = None

    @model_validator(mode="after")
    def consistent_identity_and_timing(self) -> Self:
        if (self.truth == "error") != (self.error_id is not None):
            raise ValueError("Error identity must match the adjudicated truth.")
        if (self.decision == "warning") != (self.before_submission is not None):
            raise ValueError("Submission timing is required for warnings only.")
        return self


class WorkInterval(StrictMeasurement):
    worker_id: UUID
    stage: Literal[
        "import", "read_review", "check", "correction", "recheck",
        "second_review", "post_submission",
    ]
    start_seconds: NonnegativeInt
    end_seconds: NonnegativeInt

    @model_validator(mode="after")
    def ordered_interval(self) -> Self:
        if self.end_seconds < self.start_seconds:
            raise ValueError("Work interval end must not precede its start.")
        return self


class ReportMeasurement(StrictMeasurement):
    report_id: UUID
    report_version: PositiveInt
    cohort: Literal["baseline", "assisted"]
    activity_kind: Literal["transport", "nontransport", "transfer", "unknown"] = "unknown"
    document_kind: Literal["text_pdf", "image_pdf", "photo", "mixed", "unknown"] = "unknown"
    followup_complete: StrictBool = False
    corrected_after_submission: StrictBool | None = None
    independent_review_complete: StrictBool = False
    work_complete: StrictBool = False
    opportunities: list[Opportunity] = Field(default_factory=list, max_length=1000)
    work: list[WorkInterval] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def no_double_counted_work(self) -> Self:
        by_worker = defaultdict(list)
        total_seconds = 0
        for item in self.work:
            total_seconds += item.end_seconds - item.start_seconds
            if item.end_seconds != item.start_seconds:
                by_worker[item.worker_id].append((item.start_seconds, item.end_seconds))
        for intervals in by_worker.values():
            intervals.sort()
            previous_end = -1
            for start, end in intervals:
                if start < previous_end:
                    raise ValueError("Work intervals for the same worker must not overlap.")
                previous_end = end
        # Strict integers cannot contain NaN, but an unbounded integer total
        # can still overflow the floating-point output representation.
        try:
            finite_total = isfinite(total_seconds / 60)
        except OverflowError:
            finite_total = False
        if not finite_total:
            raise ValueError("Work duration exceeds the numeric representation.")
        return self


class Targets(StrictMeasurement):
    correction_reduction_percent: ReductionPercent | None = None
    recall: Proportion | None = None
    false_alerts_per_report: NonnegativeFinite | None = None
    time_reduction_percent: ReductionPercent | None = None
    read_state_accuracy: Proportion | None = None
    minimum_reports_per_cohort: PositiveInt | None = None
    minimum_true_errors: PositiveInt | None = None


class EvaluationInput(StrictMeasurement):
    dataset_kind: Literal["synthetic", "internal_trial"]
    comparison_confirmed: StrictBool = False
    held_out_confirmed: StrictBool = False
    followup_days: PositiveInt | None = None
    targets: Targets = Field(default_factory=Targets)
    reports: list[ReportMeasurement] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="before")
    @classmethod
    def bound_raw_collections(cls, value):
        # Bound nested parsing/error expansion before constructing all models.
        if not isinstance(value, dict):
            return value
        reports = value.get("reports")
        if not isinstance(reports, (list, tuple)):
            return value
        if len(reports) > 1000:
            raise ValueError("Evaluation report limit exceeded.")
        opportunity_count = 0
        for report in reports:
            if not isinstance(report, dict):
                continue
            opportunities = report.get("opportunities")
            if isinstance(opportunities, (list, tuple)):
                if len(opportunities) > 1000:
                    raise ValueError("Report opportunity limit exceeded.")
                opportunity_count += len(opportunities)
                if opportunity_count > 20_000:
                    raise ValueError("Evaluation opportunity limit exceeded.")
            work = report.get("work")
            if isinstance(work, (list, tuple)) and len(work) > 1000:
                raise ValueError("Report work interval limit exceeded.")
        return value

    @model_validator(mode="after")
    def identity_and_resource_boundaries(self) -> Self:
        reports: set[UUID] = set()
        opportunities: set[UUID] = set()
        error_owners: dict[UUID, UUID] = {}
        count = 0
        for report in self.reports:
            if report.report_id in reports:
                raise ValueError("A report may occur only once at one fixed version.")
            reports.add(report.report_id)
            for item in report.opportunities:
                count += 1
                if count > 20_000:
                    raise ValueError("Evaluation opportunity limit exceeded.")
                if item.opportunity_id in opportunities:
                    raise ValueError("Opportunity identities must be unique.")
                opportunities.add(item.opportunity_id)
                if item.error_id is not None:
                    previous = error_owners.setdefault(item.error_id, report.report_id)
                    if previous != report.report_id:
                        raise ValueError("An error identity must belong to one report.")
        return self
