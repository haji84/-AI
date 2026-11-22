"""Three-valued, declarative report checks; approval is supplied by the service.

No observation values are copied into findings. Empty result sets are not a
completion certificate; the caller must retain rule and field coverage gaps.
"""
from collections.abc import Mapping
from datetime import date

from pydantic import ValidationError

from .emergency_review_core import Observation
from .emergency_rule_schemas import FieldExpression, GroupExpression, NotExpression, RuleObservation, RuleSetDefinition, TemporalValue


UNKNOWN = None


def _observation(observations, field):
    value = observations.get(field)
    if isinstance(value, Observation):
        value = {"state": value.state, "value": value.value}
    if not isinstance(value, (dict, RuleObservation)):
        return None
    try:
        parsed = RuleObservation.model_validate(value)
    except ValidationError:
        return None
    return parsed if parsed.state == "confirmed" else None


def _kind(value):
    if isinstance(value, TemporalValue):
        return value.type
    if type(value) in (int, float):
        return "number"
    return type(value).__name__


def _equal(left, right):
    if left is None or right is None:
        return left is None and right is None
    if _kind(left) != _kind(right):
        return UNKNOWN
    if isinstance(left, TemporalValue):
        return left.parsed() == right.parsed()
    return left == right


def _leaf(expression, observations):
    item = _observation(observations, expression.field)
    if item is None:
        return UNKNOWN
    actual, op = item.value, expression.operator
    if op in {"blank", "not_blank"}:
        blank = actual is None or (isinstance(actual, str) and not actual.strip())
        return blank if op == "blank" else not blank
    if op == "compare_field":
        other = _observation(observations, expression.right_field)
        if other is None or item.unit != other.unit:
            return UNKNOWN
        if expression.unit is not None and item.unit != expression.unit:
            return UNKNOWN
        return _equal(actual, other.value)
    if item.unit != expression.unit:
        return UNKNOWN
    expected = expression.value
    if op == "in":
        outcomes = [_equal(actual, choice) for choice in expected]
        return True if True in outcomes else UNKNOWN if UNKNOWN in outcomes else False
    if op in {"eq", "ne"}:
        matched = _equal(actual, expected)
        return matched if matched is UNKNOWN or op == "eq" else not matched
    if _kind(actual) != _kind(expected) or _kind(actual) not in {"number", "date", "datetime"}:
        # A time of day has no date: never infer rollover for chronology.
        return UNKNOWN
    if isinstance(actual, TemporalValue):
        actual, expected = actual.parsed(), expected.parsed()
    if op == "lt":
        return actual < expected
    if op == "le":
        return actual <= expected
    if op == "gt":
        return actual > expected
    return actual >= expected


def _evaluate(expression, observations):
    if isinstance(expression, FieldExpression):
        return _leaf(expression, observations)
    if isinstance(expression, NotExpression):
        value = _evaluate(expression.expression, observations)
        return UNKNOWN if value is UNKNOWN else not value
    values = [_evaluate(child, observations) for child in expression.expressions]
    if expression.kind == "all":
        return False if False in values else UNKNOWN if UNKNOWN in values else True
    return True if True in values else UNKNOWN if UNKNOWN in values else False


def _fields(expression):
    if expression is None:
        return set()
    if isinstance(expression, FieldExpression):
        return {expression.field} | ({expression.right_field} if expression.right_field else set())
    if isinstance(expression, NotExpression):
        return _fields(expression.expression)
    return set().union(*(_fields(child) for child in expression.expressions))


def evaluate_rules(definition, observations, *, approval="draft", as_of: date, form_key: str) -> list[dict]:
    definition = RuleSetDefinition.model_validate(definition)
    if not isinstance(observations, Mapping) or type(as_of) is not date or approval not in {"draft", "approved"}:
        raise ValueError("Explicit rule context and observation mapping are required.")
    result = []
    for rule in definition.rules:
        fields = _fields(rule.applies_when) | _fields(rule.assertion)
        for exception in rule.exceptions:
            fields |= _fields(exception)
        if form_key != definition.form_key:
            status, reason = "NOT_TESTED", "FORM_NOT_MATCHED"
        elif as_of < definition.valid_from or (definition.valid_to is not None and as_of > definition.valid_to):
            status, reason = "NOT_APPLICABLE", "OUTSIDE_EFFECTIVE_PERIOD"
        else:
            applies = _evaluate(rule.applies_when, observations) if rule.applies_when else True
            if applies is False:
                status, reason = "NOT_APPLICABLE", "APPLICABILITY_FALSE"
            elif applies is UNKNOWN:
                status, reason = "NOT_TESTED", "APPLICABILITY_UNRESOLVED"
            else:
                exceptions = [_evaluate(item, observations) for item in rule.exceptions]
                if True in exceptions:
                    status, reason = "NOT_APPLICABLE", "EXCEPTION_APPLIES"
                elif UNKNOWN in exceptions:
                    status, reason = "NOT_TESTED", "EXCEPTION_UNRESOLVED"
                else:
                    assertion = _evaluate(rule.assertion, observations)
                    if assertion is UNKNOWN:
                        status, reason = "NOT_TESTED", "ASSERTION_UNRESOLVED"
                    elif assertion:
                        status, reason = "NO_ISSUE_DETECTED", "ASSERTION_SATISFIED"
                    else:
                        status, reason = "REVIEW_REQUIRED", "ASSERTION_FAILED"
        source = rule.source
        reference = f"{source.document_title} / {source.version} / {source.page}"
        if source.section:
            reference += f" / {source.section}"
        result.append({
            "rule_id": rule.rule_id, "status": status, "message": rule.message,
            "fields": sorted(fields), "source_reference": reference,
            "rule_approval": "APPROVED_RULE" if approval == "approved" else "PROVISIONAL_NOT_APPROVED",
            "reason_code": reason, "severity": rule.severity,
        })
    return result
