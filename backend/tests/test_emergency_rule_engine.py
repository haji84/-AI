"""Synthetic rules only; no source policy is approved by these tests."""
from datetime import date
import json

import pytest
from pydantic import ValidationError

from app.emergency_rule_schemas import RuleSetDefinition
from app.emergency_rule_engine import evaluate_rules
from app.emergency_review_core import confirmed


def leaf(field="count", operator="ge", **extra):
    return {"kind": "field", "field": field, "operator": operator, **extra}


def definition(**rule_updates):
    rule = {
        "rule_id": "SYN-001", "label": "Synthetic comparison", "message": "記載内容を確認してください。",
        "severity": "warning", "source": {"document_title": "Synthetic manual", "version": "test-v1", "page": "1", "section": "test"},
        "candidate_ids": [], "assertion": leaf(value=1), **rule_updates,
    }
    return RuleSetDefinition.model_validate({"label": "Synthetic rules", "form_key": "synthetic-v1",
        "valid_from": "2026-01-01", "valid_to": "2026-12-31", "rules": [rule]})


def run(defn=None, values=None, **kwargs):
    return evaluate_rules(defn or definition(), values or {}, as_of=date(2026, 6, 1), form_key="synthetic-v1", **kwargs)[0]


def test_known_pass_and_mismatch_remain_provisional():
    assert run(values={"count": confirmed(1)})["status"] == "NO_ISSUE_DETECTED"
    result = run(values={"count": confirmed(0)})
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["rule_approval"] == "PROVISIONAL_NOT_APPROVED"
    assert "Synthetic manual" in result["source_reference"]


@pytest.mark.parametrize("state", ["unconfirmed", "unreadable", "not_printed", "unmapped"])
def test_unverified_values_are_never_used(state):
    assert run(values={"count": {"state": state, "value": 99}})["status"] == "NOT_TESTED"


def test_absent_confirmed_value_is_not_a_confirmed_blank():
    rule = definition(assertion=leaf("name", "blank"))
    assert run(rule, {"name": {"state": "confirmed"}})["status"] == "NOT_TESTED"
    assert run(rule, {"name": confirmed(None)})["status"] == "NO_ISSUE_DETECTED"


def test_known_false_applicability_short_circuits_unknown_assertion():
    rule = definition(applies_when=leaf("transport", "eq", value=True))
    result = run(rule, {"transport": confirmed(False)})
    assert result["status"] == "NOT_APPLICABLE"
    assert result["reason_code"] == "APPLICABILITY_FALSE"


def test_unknown_applicability_and_exception_never_clear():
    assert run(definition(applies_when=leaf("transport", "eq", value=True)), {"count": confirmed(1)})["status"] == "NOT_TESTED"
    assert run(definition(exceptions=[leaf("exception", "eq", value=True)]), {"count": confirmed(1)})["status"] == "NOT_TESTED"


def test_known_exception_short_circuits_unknown_target_and_other_exception():
    rule = definition(exceptions=[leaf("unknown", "eq", value=True), leaf("exception", "eq", value=True)])
    assert run(rule, {"exception": confirmed(True)})["status"] == "NOT_APPLICABLE"


@pytest.mark.parametrize("kind,value,expected", [("all", False, "REVIEW_REQUIRED"), ("any", True, "NO_ISSUE_DETECTED")])
def test_three_valued_groups_keep_decisive_known_branch(kind, value, expected):
    expression = {"kind": kind, "expressions": [leaf("known", "eq", value=True), leaf("unknown", "eq", value=True)]}
    assert run(definition(assertion=expression), {"known": confirmed(value)})["status"] == expected


def test_not_preserves_unknown():
    rule = definition(assertion={"kind": "not", "expression": leaf("missing", "eq", value=True)})
    assert run(rule)["status"] == "NOT_TESTED"


@pytest.mark.parametrize("value", [True, "1"])
def test_incompatible_types_do_not_become_numeric_comparisons(value):
    assert run(values={"count": confirmed(value)})["status"] == "NOT_TESTED"


def test_blank_and_nonblank_and_membership_are_explicit():
    assert run(definition(assertion=leaf("name", "blank")), {"name": confirmed(" ")})["status"] == "NO_ISSUE_DETECTED"
    assert run(definition(assertion=leaf("name", "not_blank")), {"name": confirmed(None)})["status"] == "REVIEW_REQUIRED"
    assert run(definition(assertion=leaf("kind", "in", value=["A", "B"])), {"kind": confirmed("B")})["status"] == "NO_ISSUE_DETECTED"


def test_field_equality_requires_two_confirmed_compatible_values():
    rule = definition(assertion=leaf("first", "compare_field", right_field="second"))
    assert run(rule, {"first": confirmed("A"), "second": confirmed("A")})["status"] == "NO_ISSUE_DETECTED"
    assert run(rule, {"first": confirmed("A"), "second": confirmed("B")})["status"] == "REVIEW_REQUIRED"
    assert run(rule, {"first": confirmed("A")})["status"] == "NOT_TESTED"


def test_units_are_exact_without_implicit_conversion():
    rule = definition(assertion=leaf(value=1, unit="mg"))
    assert run(rule, {"count": {"state": "confirmed", "value": 1, "unit": "mg"}})["status"] == "NO_ISSUE_DETECTED"
    assert run(rule, {"count": {"state": "confirmed", "value": 1000, "unit": "microgram"}})["status"] == "NOT_TESTED"
    assert run(rule, {"count": confirmed(1)})["status"] == "NOT_TESTED"


def test_two_field_units_must_match():
    rule = definition(assertion=leaf("first", "compare_field", right_field="second"))
    values = {"first": {"state": "confirmed", "value": 1, "unit": "mg"},
              "second": {"state": "confirmed", "value": 1, "unit": "g"}}
    assert run(rule, values)["status"] == "NOT_TESTED"


def test_explicit_dates_compare_without_parsing_plain_text():
    rule = definition(assertion=leaf("day", "ge", value={"type": "date", "value": "2026-01-01"}))
    assert run(rule, {"day": {"state": "confirmed", "value": {"type": "date", "value": "2026-01-02"}}})["status"] == "NO_ISSUE_DETECTED"
    assert run(rule, {"day": confirmed("2026-01-02")})["status"] == "NOT_TESTED"


def test_clock_order_does_not_guess_day_rollover():
    rule = definition(assertion=leaf("clock", "ge", value={"type": "time", "value": "23:50:00"}))
    assert run(rule, {"clock": {"state": "confirmed", "value": {"type": "time", "value": "00:10:00"}}})["status"] == "NOT_TESTED"


def test_explicit_datetimes_cross_midnight_correctly():
    rule = definition(assertion=leaf("instant", "gt", value={"type": "datetime", "value": "2026-01-01T23:50:00+09:00"}))
    obs = {"instant": {"state": "confirmed", "value": {"type": "datetime", "value": "2026-01-02T00:10:00+09:00"}}}
    assert run(rule, obs)["status"] == "NO_ISSUE_DETECTED"


def test_effective_period_and_form_are_checked():
    rule = definition()
    assert evaluate_rules(rule, {}, as_of=date(2025, 12, 31), form_key="synthetic-v1")[0]["reason_code"] == "OUTSIDE_EFFECTIVE_PERIOD"
    assert evaluate_rules(rule, {}, as_of=date(2026, 6, 1), form_key="unknown")[0]["status"] == "NOT_TESTED"
    assert run(values={"count": confirmed(1)}, approval="approved")["rule_approval"] == "APPROVED_RULE"


def test_no_observation_values_are_reflected_in_findings():
    marker = "SYNTHETIC_PRIVATE_VALUE"
    rule = definition(assertion=leaf("name", "eq", value="expected"))
    assert marker not in json.dumps(run(rule, {"name": confirmed(marker)}))


@pytest.mark.parametrize("expression", [
    {"kind": "all", "expressions": []},
    leaf(operator="eq"), leaf(operator="blank", value=1), leaf(operator="compare_field"),
    leaf(operator="in", value="A"), leaf(operator="in", value=[]),
    leaf(operator="ge", value=True), leaf(operator="eq", value=float("nan")),
    leaf(operator="regex", value=".*"),
    leaf(operator="eq", value=1, script="forbidden"),
    leaf(operator="ge", value={"type": "datetime", "value": "2026-01-01T00:00:00"}),
])
def test_invalid_or_executable_expressions_are_rejected(expression):
    with pytest.raises(ValidationError):
        definition(assertion=expression)


def test_depth_and_duplicate_rules_are_bounded():
    expression = leaf(value=1)
    for _ in range(10):
        expression = {"kind": "not", "expression": expression}
    with pytest.raises(ValidationError):
        definition(assertion=expression)
    data = definition().model_dump(mode="json")
    data["rules"].append(data["rules"][0])
    with pytest.raises(ValidationError):
        RuleSetDefinition.model_validate(data)


def test_round_trip_and_empty_rule_set_are_explicit():
    first = definition()
    assert RuleSetDefinition.model_validate(first.model_dump(mode="json")) == first
    data = first.model_dump(mode="json")
    data["rules"] = []
    empty = RuleSetDefinition.model_validate(data)
    assert evaluate_rules(empty, {}, as_of=date(2026, 6, 1), form_key="synthetic-v1") == []


def test_invalid_dates_or_source_metadata_cannot_be_saved():
    data = definition().model_dump(mode="json")
    data["valid_to"] = "2025-12-31"
    with pytest.raises(ValidationError):
        RuleSetDefinition.model_validate(data)
    data["valid_to"] = None
    data["rules"][0]["source"]["sha256"] = "not-a-hash"
    with pytest.raises(ValidationError):
        RuleSetDefinition.model_validate(data)


@pytest.mark.parametrize('raw', ['1704067200', '2026-01-01T00:00:00', '20260101'])
def test_effective_date_strings_cannot_be_coerced_from_epoch_or_datetime(raw):
    data = definition().model_dump(mode='json')
    data['valid_from'] = raw
    with pytest.raises(ValidationError):
        RuleSetDefinition.model_validate(data)
