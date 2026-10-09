"""Shared legal authoring must retain a hazardous candidate-only contract."""
import pytest

from app.legal_rule_validation import validate_rule_conditions
from app.legal_outcome_validation import validate_rule_outcome_references
from app.schemas import LegalRuleCreate, LegalRuleDraftCandidateCreate


CONDITIONS = {'all': [{'field': 'quantity', 'op': 'gte', 'value': '100', 'unit': 'L'}]}
OUTCOME = {'decision': 'hazardous_requirement_candidate', 'requirement': 'Synthetic Human requirement',
    'human_review_required': True}


def test_existing_authoring_accepts_separate_hazardous_domain():
    rule = LegalRuleCreate(rule_code='SYN-HZ', name='Synthetic rule', domain='hazardous_requirement')
    assert rule.domain == 'hazardous_requirement'
    draft = LegalRuleDraftCandidateCreate(domain=rule.domain, proposed_name=rule.name,
        proposed_conditions=CONDITIONS, proposed_outcome=OUTCOME, extraction_method='manual')
    assert draft.domain == rule.domain
    validate_rule_conditions(CONDITIONS, domain=rule.domain)
    validate_rule_outcome_references(None, domain=rule.domain, outcome=OUTCOME)


def test_hazardous_fields_do_not_enter_facility_condition_language():
    with pytest.raises(ValueError):
        validate_rule_conditions(CONDITIONS)
    with pytest.raises(ValueError):
        validate_rule_conditions({'all': [{'field': 'building_area', 'op': 'gte', 'value': 100}]},
            domain='hazardous_requirement')
    validate_rule_conditions({'all': [{'field': 'building_area', 'op': 'gte', 'value': 100}]})


@pytest.mark.parametrize('changes', [{'decision': 'formal_violation'}, {'decision': 'permit_approved'},
    {'human_review_required': False}, {'human_review_required': 1}, {'human_review_required': 'true'},
    {'requirement': ''}, {'requirement': ' '}, {'requirement': {}}, {'automatic_apply': True}])
def test_hazardous_outcome_cannot_request_formal_or_automatic_decision(changes):
    with pytest.raises(ValueError):
        validate_rule_outcome_references(None, domain='hazardous_requirement', outcome={**OUTCOME, **changes})


def test_hazardous_outcome_requires_explicit_human_gate():
    for field in OUTCOME:
        with pytest.raises(ValueError):
            validate_rule_outcome_references(None, domain='hazardous_requirement',
                outcome={key: value for key, value in OUTCOME.items() if key != field})
