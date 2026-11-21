"""Synthetic-only examples for the candidate emergency report review core."""
import pytest

from app.emergency_review_core import Observation, confirmed, evaluate_confirmed_fields


def sample(**overrides):
    data = dict(
        transported=confirmed(True), transfer_transport=confirmed(False),
        urgency=confirmed("準緊急（黄）"), form_version=confirmed("new"),
        incident_type_first=confirmed("急病"), incident_type_second=confirmed("急病"),
        place_major=confirmed("住宅"), place_minor=confirmed("一般住宅"),
        occurrence_floor=confirmed("地上2階"), vital_phase=confirmed("initial"),
        age_band=confirmed("age_7_plus"), pulse=confirmed(90),
        respirations=confirmed(20), systolic=confirmed(120), spo2=confirmed(98), jcs=confirmed(0),
    )
    data.update(overrides)
    return data


def finding(values, rule):
    return next(x for x in evaluate_confirmed_fields(values) if x.rule_id == rule)


@pytest.mark.parametrize('value', [False, 123, 1.5])
def test_invalid_place_category_type_stays_untested(value):
    assert finding(sample(place_minor=confirmed(value)), 'ER-PLACE-MINOR').status == 'NOT_TESTED'


def test_nontransport_blank_urgency_is_not_flagged():
    a = sample(transported=confirmed(False), urgency=confirmed(None), transfer_transport=confirmed(True))
    assert finding(a, "ER-NONTRANSPORT-URGENCY").status == "NO_ISSUE_DETECTED"
    assert finding(a, "ER-TRANSFER-URGENCY").status == "NOT_APPLICABLE"
    assert finding(a, "ER-RED-TRIGGER-PULSE").status == "NOT_APPLICABLE"


def test_nontransport_with_urgency_needs_review():
    assert finding(sample(transported=confirmed(False)), "ER-NONTRANSPORT-URGENCY").status == "REVIEW_REQUIRED"


def test_pdf_not_printed_is_not_assumed_blank():
    assert finding(sample(transported=confirmed(False), urgency=Observation("not_printed")), "ER-NONTRANSPORT-URGENCY").status == "NOT_TESTED"


def test_unconfirmed_is_not_silently_used():
    assert finding(sample(transported=Observation("unconfirmed")), "ER-NONTRANSPORT-URGENCY").status == "NOT_TESTED"


@pytest.mark.parametrize("urgency,expected", [
    ("準緊急（黄）", "NO_ISSUE_DETECTED"), ("緊急（赤）", "REVIEW_REQUIRED"),
    (None, "REVIEW_REQUIRED")
])
def test_transfer_yellow_override(urgency, expected):
    a = sample(transfer_transport=confirmed(True), urgency=confirmed(urgency), pulse=confirmed(150))
    assert finding(a, "ER-TRANSFER-URGENCY").status == expected
    assert finding(a, "ER-RED-TRIGGER-PULSE").status == "NOT_APPLICABLE"


@pytest.mark.parametrize("major,minor,floor,result_minor,result_floor", [
    ("住宅", "一般住宅", "地上2階", "NO_ISSUE_DETECTED", "NOT_APPLICABLE"),
    ("住宅", "", None, "REVIEW_REQUIRED", "NOT_APPLICABLE"),
    ("公衆出入場所", None, None, "NO_ISSUE_DETECTED", "NO_ISSUE_DETECTED"),
    ("仕事場", "作業場", None, "REVIEW_REQUIRED", "NO_ISSUE_DETECTED"),
    ("道路", None, "地上1階", "NO_ISSUE_DETECTED", "REVIEW_REQUIRED"),
    ("その他", None, None, "NO_ISSUE_DETECTED", "NO_ISSUE_DETECTED"),
])
def test_places(major,minor,floor,result_minor,result_floor):
    v = sample(place_major=confirmed(major), place_minor=confirmed(minor), occurrence_floor=confirmed(floor))
    assert finding(v, "ER-PLACE-MINOR").status == result_minor
    assert finding(v, "ER-PLACE-FLOOR").status == result_floor


def test_missing_place_cannot_be_assumed_nonresidential():
    v = sample(place_major=Observation("unreadable"))
    assert finding(v, "ER-PLACE-FLOOR").status == "NOT_TESTED"


@pytest.mark.parametrize("form,left,right,expected", [
    ("new", "急病", "急病", "NO_ISSUE_DETECTED"),
    ("new", "急病", "一般負傷", "REVIEW_REQUIRED"),
    ("old", "急病", "一般負傷", "NOT_APPLICABLE"),
])
def test_form_two_accident_kinds(form,left,right,expected):
    v = sample(form_version=confirmed(form), incident_type_first=confirmed(left),incident_type_second=confirmed(right))
    assert finding(v, "ER-FORM-ACCIDENT-TWO").status == expected


def test_form_unmapped_is_not_checked():
    v=sample(form_version=Observation("unmapped"))
    assert finding(v, "ER-FORM-ACCIDENT-TWO").status == "NOT_TESTED"


@pytest.mark.parametrize("age_band,metric,value", [
    ("newborn", "pulse", 99), ("newborn", "pulse", 150),
    ("infant", "pulse", 120), ("toddler", "pulse", 110),
    ("age_7_plus", "pulse", 120), ("newborn", "respirations", 29),
    ("infant", "respirations", 30), ("age_7_plus", "respirations", 30),
    ("newborn", "systolic", 69), ("infant", "systolic", 79),
    ("age_7_plus", "systolic", 200),
    ("age_7_plus", "spo2", 89), ("age_7_plus", "jcs", 100),
])
def test_regional_red_thresholds_trigger_review_for_yellow(age_band,metric,value):
    v=sample(age_band=confirmed(age_band), **{metric:confirmed(value)})
    assert finding(v,"ER-RED-TRIGGER-"+metric.upper()).status == "REVIEW_REQUIRED"


def test_normal_range_is_not_inferred_from_red_threshold():
    v=sample(age_band=confirmed("infant"), pulse=confirmed(100))
    f=finding(v, "ER-RED-TRIGGER-PULSE")
    assert f.status == "NO_ISSUE_DETECTED"
    assert "正常値判定ではない" in f.message
    assert f.rule_approval == "PROVISIONAL_NOT_APPROVED"


def test_red_can_be_justified_by_clinical_judgment_beyond_numbers():
    v=sample(urgency=confirmed("緊急（赤）"), pulse=confirmed(100))
    assert finding(v, "ER-RED-TRIGGER-PULSE").status == "NO_ISSUE_DETECTED"


@pytest.mark.parametrize("field,obs", [( "age_band",Observation("unreadable")), ("vital_phase", confirmed("after_intervention")), ("pulse",Observation("unconfirmed"))])
def test_uncertain_vitals_do_not_create_false_certainty(field,obs):
    v=sample(**{field:obs})
    assert finding(v, "ER-RED-TRIGGER-PULSE").status == "NOT_TESTED"


def test_spo2_can_be_checked_without_age_if_confirmed():
    v=sample(age_band=Observation("unmapped"), spo2=confirmed(89))
    assert finding(v, "ER-RED-TRIGGER-SPO2").status == "REVIEW_REQUIRED"
    assert finding(v, "ER-RED-TRIGGER-PULSE").status == "NOT_TESTED"


def test_numeric_strings_not_coerced_without_value_confirmation():
    v=sample(pulse=confirmed("120"))
    assert finding(v, "ER-RED-TRIGGER-PULSE").status == "NOT_TESTED"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_spo2_is_not_used(value):
    v=sample(spo2=confirmed(value))
    assert finding(v,"ER-RED-TRIGGER-SPO2").status == "NOT_TESTED"


def test_no_personal_values_are_echoed_in_findings():
    secret="PRIVATE_TEST_PERSON_MARKER"
    v=sample(incident_type_first=confirmed(secret))
    res=evaluate_confirmed_fields(v)
    assert secret not in repr(res)
    assert all(item.rule_approval=="PROVISIONAL_NOT_APPROVED" for item in res)


def test_unverified_values_rejected_at_boundary():
    with pytest.raises(ValueError):
        Observation("unreadable", "PRIVATE_TEST_PERSON_MARKER")
    with pytest.raises(ValueError):
        Observation("wrong_state", None)


def test_missing_all_fields_never_produces_pass():
    res=evaluate_confirmed_fields({})
    assert all(f.status in ("NOT_TESTED","NOT_APPLICABLE") for f in res)


def test_unknown_place_category_needs_mapping_before_evaluation():
    v=sample(place_major=confirmed("分類コード未確定"), occurrence_floor=confirmed("地上2階"))
    assert finding(v, "ER-PLACE-FLOOR").status == "NOT_TESTED"


@pytest.mark.parametrize("metric,age,value", [
    ("pulse", "newborn", 100), ("pulse", "newborn", 149),
    ("pulse", "infant", 119), ("pulse", "toddler", 109),
    ("pulse", "age_7_plus", 119), ("respirations", "newborn", 30),
    ("respirations", "newborn", 49), ("systolic", "age_7_plus", 199),
    ("spo2", "age_7_plus", 90), ("jcs", "age_7_plus", 99),
])
def test_threshold_edges_do_not_create_false_red_candidates(metric,age,value):
    v=sample(age_band=confirmed(age), **{metric:confirmed(value)})
    assert finding(v, "ER-RED-TRIGGER-"+metric.upper()).status == "NO_ISSUE_DETECTED"


def test_both_missing_accident_types_are_not_false_pass():
    v=sample(incident_type_first=confirmed(""), incident_type_second=confirmed(""))
    assert finding(v, "ER-FORM-ACCIDENT-TWO").status == "NOT_TESTED"


def test_massive_integer_does_not_crash_or_make_rule_pass():
    v=sample(pulse=confirmed(10**500))
    assert finding(v, "ER-RED-TRIGGER-PULSE").status == "NOT_TESTED"
