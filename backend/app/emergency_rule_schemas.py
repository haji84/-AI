"""Bounded declarative rules; no executable code or inferred source policy."""
from datetime import date, datetime, time
from math import isfinite
import re
from typing import Annotated, Literal, Self, Union

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator, model_serializer, model_validator


Identifier = Annotated[StrictStr, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.:-]*$")]
Unit = Annotated[StrictStr, Field(min_length=1, max_length=40)]
TextValue = Annotated[StrictStr, Field(max_length=4000)]
Scalar = Union[StrictBool, StrictInt, StrictFloat, TextValue, None]
MAX_EXPRESSION_DEPTH = 8
MAX_EXPRESSION_NODES = 20_000


class StrictRuleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, allow_inf_nan=False, revalidate_instances="always")


class TemporalValue(StrictRuleModel):
    type: Literal["date", "datetime", "time"]
    value: Annotated[StrictStr, Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def validate_explicit_temporal(self) -> Self:
        try:
            parsed = self.parsed()
            if self.type == "datetime" and parsed.utcoffset() is None:
                raise ValueError("timezone required")
        except (ValueError, TypeError, OverflowError):
            raise ValueError("An explicit valid temporal value is required.") from None
        return self

    def parsed(self):
        if self.type == "date":
            return date.fromisoformat(self.value)
        if self.type == "datetime":
            return datetime.fromisoformat(self.value)
        return time.fromisoformat(self.value)


RuleValue = Union[Scalar, TemporalValue]


class FieldExpression(StrictRuleModel):
    kind: Literal["field"]
    field: Identifier
    operator: Literal["eq", "ne", "lt", "le", "gt", "ge", "in", "blank", "not_blank", "compare_field"]
    value: RuleValue | list[RuleValue] = None
    right_field: Identifier | None = None
    unit: Unit | None = None

    @model_validator(mode="after")
    def operator_shape(self) -> Self:
        if self.operator in {"blank", "not_blank", "compare_field"}:
            if "value" in self.model_fields_set:
                raise ValueError("This operator does not accept a literal value.")
        elif "value" not in self.model_fields_set:
            raise ValueError("An explicit comparison value is required.")
        if (self.operator == "compare_field") != (self.right_field is not None):
            raise ValueError("Only field comparison requires a right field.")
        if self.operator == "in":
            if not isinstance(self.value, list) or not 1 <= len(self.value) <= 100:
                raise ValueError("Membership requires a bounded nonempty value list.")
        elif isinstance(self.value, list):
            raise ValueError("This operator requires one literal value.")
        if self.operator in {"lt", "le", "gt", "ge"} and (
            type(self.value) not in (int, float) and not isinstance(self.value, TemporalValue)
        ):
            raise ValueError("Ordered comparisons require numeric or explicit temporal values.")
        if self.operator in {"blank", "not_blank"} and self.unit is not None:
            raise ValueError("Blank checks do not use a unit.")
        values = self.value if isinstance(self.value, list) else [self.value]
        for value in values:
            if type(value) in (int, float):
                try:
                    finite = isfinite(value)
                except OverflowError:
                    finite = False
                if not finite:
                    raise ValueError("Finite literal values are required.")
        return self

    @model_serializer(mode="wrap")
    def serialize_operator(self, handler):
        result = handler(self)
        if self.operator in {"blank", "not_blank", "compare_field"}:
            result.pop("value", None)
        if self.right_field is None:
            result.pop("right_field", None)
        if self.unit is None:
            result.pop("unit", None)
        return result


class GroupExpression(StrictRuleModel):
    kind: Literal["all", "any"]
    expressions: list["Expression"] = Field(min_length=1, max_length=64)


class NotExpression(StrictRuleModel):
    kind: Literal["not"]
    expression: "Expression"


Expression = Annotated[Union[FieldExpression, GroupExpression, NotExpression], Field(discriminator="kind")]
GroupExpression.model_rebuild()
NotExpression.model_rebuild()


class SourceReference(StrictRuleModel):
    document_title: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    version: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    page: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    section: Annotated[StrictStr, Field(max_length=200)] = ""
    sha256: Annotated[StrictStr, Field(pattern=r"^[a-fA-F0-9]{64}$")] | None = None

    @field_validator("document_title", "version", "page")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Explicit source metadata is required.")
        return value


class RuleDefinition(StrictRuleModel):
    rule_id: Identifier
    label: Annotated[StrictStr, Field(min_length=1, max_length=150)]
    message: Annotated[StrictStr, Field(min_length=1, max_length=300)]
    severity: Literal["error", "warning", "review"]
    source: SourceReference
    candidate_ids: list[Annotated[StrictStr, Field(pattern=r"^(ER|CR|EX)-[0-9]{3}$")]] = Field(default_factory=list, max_length=30)
    applies_when: Expression | None = None
    exceptions: list[Expression] = Field(default_factory=list, max_length=30)
    assertion: Expression

    @model_validator(mode="after")
    def candidate_identities(self) -> Self:
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("Candidate references must be unique.")
        bounds = {"ER": 202, "CR": 64, "EX": 167}
        if any(not 1 <= int(item.split("-")[1]) <= bounds[item[:2]] for item in self.candidate_ids):
            raise ValueError("Candidate reference is outside the known ledger.")
        return self


def _expression_children(expression):
    if isinstance(expression, dict):
        kind = expression.get("kind")
        if kind in {"all", "any"}:
            children = expression.get("expressions")
            return children if isinstance(children, list) else []
        if kind == "not":
            return [expression.get("expression")]
    elif isinstance(expression, GroupExpression):
        return expression.expressions
    elif isinstance(expression, NotExpression):
        return [expression.expression]
    return []


def _bound_expressions(rules):
    nodes = 0
    for rule in rules:
        if isinstance(rule, dict):
            exceptions = rule.get("exceptions", [])
            roots = [rule.get("applies_when"), rule.get("assertion")]
            if isinstance(exceptions, list):
                roots += exceptions
        elif isinstance(rule, RuleDefinition):
            roots = [rule.applies_when, rule.assertion, *rule.exceptions]
        else:
            continue
        pending = [(root, 1) for root in roots if root is not None]
        while pending:
            expression, depth = pending.pop()
            nodes += 1
            if depth > MAX_EXPRESSION_DEPTH or nodes > MAX_EXPRESSION_NODES:
                raise ValueError("Rule expression resource limit exceeded.")
            pending.extend((child, depth + 1) for child in _expression_children(expression))


class RuleSetDefinition(StrictRuleModel):
    label: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    form_key: Identifier
    valid_from: date
    valid_to: date | None = None
    rules: list[RuleDefinition] = Field(default_factory=list, max_length=500)

    @field_validator("valid_from", "valid_to", mode="before")
    @classmethod
    def explicit_date(cls, value):
        if value is not None and type(value) not in (str, date):
            raise ValueError("Use an explicit date.")
        if type(value) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
            raise ValueError("Use an explicit YYYY-MM-DD date.")
        return value

    @model_validator(mode="before")
    @classmethod
    def bound_raw_expressions(cls, value):
        if isinstance(value, dict) and isinstance(value.get("rules"), list):
            if len(value["rules"]) > 500:
                raise ValueError("Rule count limit exceeded.")
            _bound_expressions(value["rules"])
        return value

    @model_validator(mode="after")
    def ordered_and_bounded(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("Rule validity end precedes its start.")
        if len({rule.rule_id for rule in self.rules}) != len(self.rules):
            raise ValueError("Rule identifiers must be unique within a set.")
        _bound_expressions(self.rules)
        return self


class RuleObservation(StrictRuleModel):
    state: Literal["confirmed", "unconfirmed", "unreadable", "not_printed", "unmapped"]
    value: RuleValue = None
    unit: Unit | None = None

    @model_validator(mode="after")
    def explicit_confirmed_value(self) -> Self:
        if self.state == "confirmed" and "value" not in self.model_fields_set:
            raise ValueError("Confirmed observations require an explicit value, including null for blank.")
        if type(self.value) in (int, float):
            try:
                finite = isfinite(self.value)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError("Finite observations are required.")
        return self
