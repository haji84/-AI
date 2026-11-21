"""User-defined synthetic mappings: no real form coordinates or inferred codes."""
from importlib import import_module
import math

from pydantic import ValidationError
import pytest


def mapping():
    return import_module('app.emergency_mapping')


def field(**changes):
    return {'field_id': 'example_value', 'label': '合成の確認欄', 'value_type': 'text',
            'page': 1, 'bbox': [0.1, 0.1, 0.6, 0.4], 'extraction': 'region', **changes}


def profile(fields=None, **changes):
    return mapping().ProfileDefinition.model_validate({'label': '合成様式', 'form_key': 'synthetic-v1',
        'valid_from': '2026-01-01', 'fields': fields if fields is not None else [field()], **changes})


def artifact(words=None, **page_changes):
    return {'schema_version': 1, 'page_count': 1, 'complete': True, 'issues': [], 'pages': [
        {'page': 1, 'width': 400, 'height': 200, 'status': 'TEXT_EXTRACTED', 'method': 'pdf_text',
         'text': '123 Neighbor', 'words': words if words is not None else [
             {'text': '123', 'bbox': [.2, .2, .3, .3], 'confidence': None},
             {'text': 'Neighbor', 'bbox': [.7, .2, .9, .3], 'confidence': None}],
         'issues': [], **page_changes}]}


def test_region_returns_only_exact_selected_evidence_and_never_confirms():
    m = mapping(); result = m.map_fields(artifact(), profile([field(value_type='number')]))
    observed = result['example_value']
    assert observed['state'] == 'unconfirmed' and observed['candidate'] == 123 and observed['value'] is None
    assert observed['evidence'] == [{'page': 1, 'bbox': [.2, .2, .3, .3], 'text': '123', 'method': 'pdf_text', 'confidence': None}]


@pytest.mark.parametrize('definition,expected', [
    (field(extraction='manual', bbox=None), ('unmapped', 'MANUAL_ENTRY_REQUIRED')),
    (field(extraction='not_printed', bbox=None), ('not_printed', 'NOT_PRINTED')),
    (field(page=2), ('unmapped', 'PAGE_UNAVAILABLE')),
])
def test_nonread_states_remain_distinct(definition, expected):
    result = mapping().map_fields(artifact(), profile([definition]))['example_value']
    assert result['state'] == expected[0] and expected[1] in result['issues']
    assert result['candidate'] is None and result['value'] is None


def test_unavailable_ocr_and_empty_region_never_become_confirmed_blank():
    m = mapping()
    unread = m.map_fields(artifact(status='OCR_UNAVAILABLE', words=[], text='', issues=['OCR_LANGUAGE_UNAVAILABLE']), profile())['example_value']
    assert unread['state'] == 'unreadable' and unread['candidate'] is None
    assert 'OCR_LANGUAGE_UNAVAILABLE' in unread['issues']
    empty = m.map_fields(artifact(words=[]), profile())['example_value']
    assert empty['state'] == 'unreadable' and 'EMPTY_REGION' in empty['issues']


def test_partial_word_crossing_region_is_ambiguous_not_truncated_or_guessed():
    value = mapping().map_fields(artifact(words=[{'text': '1234', 'bbox': [.5, .2, .7, .3], 'confidence': .8}]), profile())['example_value']
    assert value['candidate'] is None and value['state'] == 'unreadable'
    assert 'REGION_BOUNDARY_AMBIGUOUS' in value['issues']
    assert value['evidence'][0]['text'] == '1234'


@pytest.mark.parametrize('kind,text,codes,options,want', [
    ('boolean', '有', {'有': True, '無': False}, [], True),
    ('boolean', '無', {'有': True, '無': False}, [], False),
    ('enum', 'Y', {'Y': 'yellow'}, ['yellow', 'red'], 'yellow'),
])
def test_boolean_and_enum_use_only_explicit_code_map(kind, text, codes, options, want):
    m = mapping(); raw = artifact(words=[{'text': text, 'bbox': [.2, .2, .3, .3], 'confidence': .9}])
    definition = profile([field(value_type=kind, code_map=codes, options=options)])
    result = m.map_fields(raw, definition)['example_value']
    assert result['candidate'] == want and type(result['candidate']) is type(want)
    raw['pages'][0]['words'][0]['text'] = 'unknown abbreviation'
    result = m.map_fields(raw, definition)['example_value']
    assert result['candidate'] is None and 'UNKNOWN_CODE' in result['issues']


@pytest.mark.parametrize('value', ['1,234', '12mg', '1e3', '１２３', 'NaN', 'true'])
def test_number_mapping_refuses_implicit_unit_or_locale_conversion(value):
    raw = artifact(words=[{'text': value, 'bbox': [.2, .2, .3, .3], 'confidence': None}])
    result = mapping().map_fields(raw, profile([field(value_type='number')]))['example_value']
    assert result['candidate'] is None and 'VALUE_FORMAT_INVALID' in result['issues']


@pytest.mark.parametrize('kind,value', [
    ('number', True), ('number', '123'), ('number', float('inf')), ('number', float('nan')),
    ('boolean', 1), ('boolean', 'true'), ('text', 123), ('date', '2026-02-30'),
    ('date', '2026/01/01'), ('datetime', '2026-01-01'), ('time', '24:00'),
])
def test_human_confirmation_validates_exact_types_and_formats(kind, value):
    m = mapping(); definition = m.FieldMapping.model_validate(field(value_type=kind, extraction='manual', bbox=None))
    with pytest.raises(ValueError, match='VALUE_FORMAT_INVALID'):
        m.confirm_value(definition, value)


@pytest.mark.parametrize('kind,value', [
    ('number', 0), ('number', -1.5), ('boolean', False), ('text', ''), ('text', '確認済み'),
    ('date', '2026-02-28'), ('datetime', '2026-01-01T12:30'), ('time', '23:59:59'),
])
def test_human_confirmation_returns_same_canonical_scalar_and_explicit_null(kind, value):
    m = mapping(); definition = m.FieldMapping.model_validate(field(value_type=kind, extraction='manual', bbox=None))
    assert m.confirm_value(definition, value) == value
    assert m.confirm_value(definition, None) is None


@pytest.mark.parametrize('changes', [
    {'bbox': [0.1, 0.2, 0.1, 0.3]}, {'bbox': [-.1, 0, 1, 1]}, {'bbox': [0, 0, math.nan, 1]},
    {'bbox': None}, {'bbox': [0, False, 1, 1]}, {'page': True}, {'page': '1'}, {'page': 51},
    {'field_id': '../secret'}, {'field_id': '日本語'}, {'extra': 1},
    {'extraction': 'manual'}, {'value_type': 'boolean'}, {'value_type': 'enum', 'options': ['yes']},
    {'value_type': 'boolean', 'code_map': {'Y': 'true'}},
    {'value_type': 'enum', 'code_map': {'Y': 'not-an-option'}, 'options': ['yes']},
])
def test_invalid_mapping_cannot_be_registered(changes):
    with pytest.raises(ValidationError):
        profile([field(**changes)])


def test_profile_rejects_ambiguous_identity_duplicates_and_reversed_dates():
    for changes in ({'fields': [field(), field()]}, {'valid_to': '2025-12-31'}, {'form_key': 'a/b'}, {'unexpected': True}):
        with pytest.raises(ValidationError): profile(**changes)


def test_page_review_issues_follow_each_candidate_evidence():
    result = mapping().map_fields(artifact(issues=['PDF_ANNOTATIONS_REVIEW_REQUIRED']), profile())['example_value']
    assert result['state'] == 'unconfirmed' and result['value'] is None
    assert 'PDF_ANNOTATIONS_REVIEW_REQUIRED' in result['issues']


def test_duplicate_page_or_invalid_provenance_fails_closed():
    m = mapping(); data = artifact(); data['pages'].append(data['pages'][0])
    with pytest.raises(ValueError, match='INVALID_READING_ARTIFACT'): m.map_fields(data, profile())
    data = artifact(); data['pages'][0]['words'][0]['bbox'] = [0, 0, 2, 3]
    with pytest.raises(ValueError, match='INVALID_READING_ARTIFACT'): m.map_fields(data, profile())


def test_overlapping_large_regions_cannot_multiply_evidence_without_bound():
    m = mapping()
    words = [{'text': 'A', 'bbox': [.2, .2, .3, .3], 'confidence': None} for _ in range(1000)]
    definitions = [field(field_id=f'field_{number}') for number in range(200)]
    result = m.map_fields(artifact(words=words), profile(definitions))
    assert result['field_0']['state'] == 'unconfirmed'
    assert sum(len(item['evidence']) for item in result.values()) <= 25_000
    assert result['field_199']['state'] == 'unreadable'
    assert result['field_199']['candidate'] is None
    assert 'EVIDENCE_LIMIT_REACHED' in result['field_199']['issues']
