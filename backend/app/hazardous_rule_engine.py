"""Deterministic candidate conditions; no unit conversion or formal decisions.

Rule approval, source authorization, effective dates and Human review belong to
the calling service. This module never writes business data or infers a label.
"""
from decimal import Decimal
import re


TEXT_FIELDS = frozenset({'installation_category_label', 'material_name', 'material_category_label'})
NUMBER_FIELDS = frozenset({'quantity', 'capacity'})
DECIMAL_PATTERN = re.compile(r'(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,6})?\Z')
COMPARATORS = {'eq': lambda a, b: a == b, 'ne': lambda a, b: a != b,
    'gte': lambda a, b: a >= b, 'lte': lambda a, b: a <= b,
    'gt': lambda a, b: a > b, 'lt': lambda a, b: a < b}


def exact_decimal(value):
    if not isinstance(value, str) or len(value) > 25 or not DECIMAL_PATTERN.fullmatch(value):
        raise ValueError('use the exact nonnegative material decimal-string contract')
    return Decimal(value)


def label(value, maximum=500):
    return isinstance(value, str) and 0 < len(value) <= maximum and bool(value.strip())


def validate_conditions(conditions):
    if not isinstance(conditions, dict) or set(conditions) - {'all', 'any'}:
        raise ValueError('unsupported hazardous condition groups')
    clauses = []
    for group in ('all', 'any'):
        values = conditions.get(group, [])
        if not isinstance(values, list):
            raise ValueError('condition group must be a list')
        clauses.extend(values)
    if not 1 <= len(clauses) <= 64:
        raise ValueError('require 1 to 64 explicit condition clauses')
    for clause in clauses:
        if not isinstance(clause, dict):
            raise ValueError('condition clause must be an object')
        field, op, value = clause.get('field'), clause.get('op'), clause.get('value')
        if not isinstance(field, str) or not isinstance(op, str):
            raise ValueError('field and operator must be explicit strings')
        if field in NUMBER_FIELDS:
            if set(clause) != {'field', 'op', 'value', 'unit'} or op not in COMPARATORS:
                raise ValueError('numeric condition requires explicit operator, decimal value and unit')
            exact_decimal(value)
            if not label(clause['unit'], 80):
                raise ValueError('numeric condition requires a bounded explicit unit')
        elif field in TEXT_FIELDS:
            if set(clause) != {'field', 'op', 'value'} or op not in {'eq', 'ne', 'in'}:
                raise ValueError('labels require exact equality or membership')
            if op == 'in':
                if not isinstance(value, list) or not 1 <= len(value) <= 100 or not all(label(x) for x in value):
                    raise ValueError('membership requires 1 to 100 bounded explicit labels')
            elif not label(value):
                raise ValueError('condition requires a bounded explicit label')
        else:
            raise ValueError('unsupported hazardous field')


def evaluate_clause(clause, facts):
    field, op = clause['field'], clause['op']
    actual, expected = facts.get(field), clause['value']
    result = {'field': field, 'op': op, 'actual': actual, 'expected': expected,
        'state': 'unresolved', 'reason': None}
    if field in NUMBER_FIELDS:
        result.update(actual_unit=facts.get(field + '_unit'), expected_unit=clause['unit'])
        if facts.get(field + '_unit') != clause['unit']:
            result['reason'] = 'missing_or_incompatible_unit'
            return result
        try:
            value = exact_decimal(actual)
        except ValueError:
            result['reason'] = 'missing_or_invalid_exact_quantity'
            return result
        matched = COMPARATORS[op](value, exact_decimal(expected))
    else:
        if not label(actual):
            result['reason'] = 'missing_or_invalid_explicit_label'
            return result
        matched = actual in expected if op == 'in' else COMPARATORS[op](actual, expected)
    result['state'] = 'matched' if matched else 'not_matched'
    return result


def evaluate_conditions(conditions, facts):
    validate_conditions(conditions)
    if not isinstance(facts, dict):
        raise ValueError('material facts must be an object')
    groups = {group: [evaluate_clause(clause, facts) for clause in conditions.get(group, [])]
        for group in ('all', 'any')}
    all_states = [row['state'] for row in groups['all']]
    any_states = [row['state'] for row in groups['any']]
    all_state = ('not_matched' if 'not_matched' in all_states else
        'unresolved' if 'unresolved' in all_states else 'matched')
    any_state = ('matched' if not any_states or 'matched' in any_states else
        'unresolved' if 'unresolved' in any_states else 'not_matched')
    state = ('not_matched' if 'not_matched' in (all_state, any_state) else
        'unresolved' if 'unresolved' in (all_state, any_state) else 'matched')
    return {'state': state, **groups}
