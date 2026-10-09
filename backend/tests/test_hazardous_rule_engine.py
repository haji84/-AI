"""Synthetic thresholds test arithmetic mechanics, never Japanese legal policy."""
import pytest

from app.hazardous_rule_engine import evaluate_conditions, validate_conditions


def threshold(value='100', unit='L', op='gte'):
    return {'all': [{'field': 'quantity', 'op': op, 'value': value, 'unit': unit}]}


@pytest.mark.parametrize('actual,state', [('99.999999', 'not_matched'), ('100', 'matched'),
    ('100.000001', 'matched'), ('999999999999999999.999999', 'matched')])
def test_exact_quantity_boundaries(actual, state):
    result = evaluate_conditions(threshold(), {'quantity': actual, 'quantity_unit': 'L'})
    assert result['state'] == state
    assert result['all'][0]['actual'] == actual


def test_large_decimal_values_do_not_round_to_equal():
    result = evaluate_conditions(threshold('999999999999999999.999999', op='eq'),
        {'quantity': '999999999999999999.999998', 'quantity_unit': 'L'})
    assert result['state'] == 'not_matched'


@pytest.mark.parametrize('facts', [{}, {'quantity': '100'},
    {'quantity': '100', 'quantity_unit': 'kg'}, {'quantity': 100, 'quantity_unit': 'L'},
    {'quantity': 'NaN', 'quantity_unit': 'L'}])
def test_missing_or_incompatible_measurement_is_unresolved(facts):
    result = evaluate_conditions(threshold(), facts)
    assert result['state'] == 'unresolved'
    assert result['all'][0]['reason']


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '1e2', '-1', '01', '0.1234567',
    '1000000000000000000', 100, True])
def test_rule_numbers_require_existing_exact_material_contract(value):
    with pytest.raises(ValueError):
        validate_conditions(threshold(value))


@pytest.mark.parametrize('conditions', [{}, {'all': []}, {'all': {}}, {'all': 'invalid'},
    {'any': [True]}, {'all': [{'field': 'quantity', 'op': 'gte', 'value': '100'}]},
    {'all': [{'field': 'quantity', 'op': 'gte', 'value': '100', 'unit': 'L', 'execute': 'permit'}]},
    {'all': [{'field': 'quantity_unit', 'op': 'eq', 'value': 'L'}]},
    {'all': [{'field': 'material_name', 'op': 'contains', 'value': 'synthetic'}]},
    {'all': [{'field': 'material_name', 'op': 'in', 'value': []}]},
    {'all': [{'field': 'material_name', 'op': 'eq', 'value': ''}]},
    {'all': [{'field': 'material_name', 'op': 'eq', 'value': 'synthetic'}], 'script': 'unsafe'}])
def test_closed_bounded_rule_language(conditions):
    with pytest.raises(ValueError):
        validate_conditions(conditions)


def test_unknown_label_never_matches_negative_condition():
    rule = {'all': [{'field': 'material_category_label', 'op': 'ne', 'value': 'synthetic category'}]}
    assert evaluate_conditions(rule, {})['state'] == 'unresolved'
    assert evaluate_conditions(rule, {'material_category_label': ''})['state'] == 'unresolved'


def test_any_and_all_retain_three_valued_logic():
    unknown = {'field': 'material_name', 'op': 'eq', 'value': 'synthetic'}
    known = threshold()['all'][0]
    facts = {'quantity': '100', 'quantity_unit': 'L'}
    assert evaluate_conditions({'all': [unknown, known]}, facts)['state'] == 'unresolved'
    assert evaluate_conditions({'any': [unknown, known]}, facts)['state'] == 'matched'
    facts['quantity'] = '99'
    assert evaluate_conditions({'all': [unknown, known]}, facts)['state'] == 'not_matched'
    assert evaluate_conditions({'any': [unknown, known]}, facts)['state'] == 'unresolved'


def test_labels_are_exact_and_never_inferred_from_partial_name():
    rule = {'all': [{'field': 'material_name', 'op': 'in', 'value': ['synthetic A', 'synthetic B']}]}
    assert evaluate_conditions(rule, {'material_name': 'synthetic A'})['state'] == 'matched'
    assert evaluate_conditions(rule, {'material_name': 'synthetic'})['state'] == 'not_matched'


@pytest.mark.parametrize('op,actual,state', [('eq', '100', 'matched'), ('ne', '100', 'not_matched'),
    ('gte', '100', 'matched'), ('lte', '100', 'matched'), ('gt', '100', 'not_matched'),
    ('lt', '100', 'not_matched'), ('gt', '100.000001', 'matched'), ('lt', '99.999999', 'matched')])
def test_capacity_uses_its_own_exact_unit_and_all_comparators(op, actual, state):
    conditions = {'all': [{'field': 'capacity', 'op': op, 'value': '100', 'unit': 'L'}]}
    assert evaluate_conditions(conditions, {'capacity': actual, 'capacity_unit': 'L'})['state'] == state
    assert evaluate_conditions(conditions, {'capacity': actual, 'quantity_unit': 'L'})['state'] == 'unresolved'


def test_clause_and_membership_bounds_are_enforced():
    clause = {'field': 'material_name', 'op': 'eq', 'value': 'synthetic'}
    validate_conditions({'all': [clause] * 64})
    with pytest.raises(ValueError):
        validate_conditions({'all': [clause] * 64, 'any': [clause]})
    clause = {'field': 'material_name', 'op': 'in', 'value': ['synthetic'] * 100}
    validate_conditions({'all': [clause]})
    clause['value'].append('synthetic')
    with pytest.raises(ValueError):
        validate_conditions({'all': [clause]})


@pytest.mark.parametrize('clause', [{'field': {}, 'op': 'eq', 'value': 'synthetic'},
    {'field': [], 'op': 'eq', 'value': 'synthetic'},
    {'field': 'quantity', 'op': {}, 'value': '100', 'unit': 'L'},
    {'field': 'quantity', 'op': [], 'value': '100', 'unit': 'L'},
    {'field': 'quantity', 'op': 'gte', 'value': {}, 'unit': 'L'},
    {'field': 'quantity', 'op': 'gte', 'value': '100', 'unit': []},
    {'field': 'material_name', 'op': 'in', 'value': [{}]}])
def test_malformed_unhashable_values_fail_closed(clause):
    with pytest.raises(ValueError):
        validate_conditions({'all': [clause]})
