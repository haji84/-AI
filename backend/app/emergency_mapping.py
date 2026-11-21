"""Explicit, versionable form definitions; no guessed coordinates or codes."""
from datetime import date, datetime, time
import math
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Scalar = str | int | float | bool | None
Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')]
Label = Annotated[str, Field(min_length=1, max_length=100)]
NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', re.ASCII)
DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', re.ASCII)
TIME = re.compile(r'[0-9]{2}:[0-9]{2}(?::[0-9]{2})?', re.ASCII)
DATETIME = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2})?(?:Z|[+-][0-9]{2}:[0-9]{2})?', re.ASCII)
MAX_VALUE_CHARS = 2_000
MAX_EVIDENCE_WORDS_TOTAL = 25_000


def _bbox(value):
    if (not isinstance(value, list) or len(value) != 4 or any(type(x) not in (int, float)
            or not math.isfinite(x) or not 0 <= x <= 1 for x in value)
            or value[0] >= value[2] or value[1] >= value[3]):
        raise ValueError('INVALID_REGION')
    return value


def _valid_value(kind, value, options):
    if value is None:
        return None
    valid = False
    if kind == 'number':
        valid = type(value) in (int, float)
        try:
            valid = valid and math.isfinite(value) and abs(value) <= 1e15
        except (OverflowError, TypeError):
            valid = False
    elif kind == 'boolean':
        valid = type(value) is bool
    elif type(value) is str and len(value) <= MAX_VALUE_CHARS:
        valid = kind == 'text' or (kind == 'enum' and value in options)
        try:
            if kind == 'date':
                valid = DATE.fullmatch(value) is not None and date.fromisoformat(value) is not None
            elif kind == 'time':
                valid = TIME.fullmatch(value) is not None and time.fromisoformat(value) is not None
            elif kind == 'datetime':
                valid = DATETIME.fullmatch(value) is not None and datetime.fromisoformat(value.replace('Z', '+00:00')) is not None
        except ValueError:
            valid = False
    if not valid:
        raise ValueError('VALUE_FORMAT_INVALID')
    return value


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    field_id: Identifier
    label: Label
    value_type: Literal['text', 'number', 'boolean', 'date', 'datetime', 'time', 'enum']
    page: int = Field(ge=1, le=50)
    bbox: list[float] | None = None
    extraction: Literal['region', 'manual', 'not_printed']
    unit: str | None = Field(default=None, max_length=30)
    phase: str | None = Field(default=None, max_length=30)
    code_map: dict[str, Scalar] = Field(default_factory=dict, max_length=200)
    options: list[Label] = Field(default_factory=list, max_length=200)

    @field_validator('bbox', mode='before')
    @classmethod
    def region(cls, value):
        return _bbox(value) if value is not None else None

    @model_validator(mode='after')
    def explicit_mapping(self):
        if (self.extraction == 'region') != (self.bbox is not None):
            raise ValueError('REGION_REQUIRED_ONLY_FOR_REGION_EXTRACTION')
        if len(set(self.options)) != len(self.options) or (self.options and self.value_type != 'enum'):
            raise ValueError('INVALID_ENUM_OPTIONS')
        if self.value_type == 'enum' and not self.options:
            raise ValueError('ENUM_OPTIONS_REQUIRED')
        if self.extraction == 'region' and self.value_type in {'boolean', 'enum'} and not self.code_map:
            raise ValueError('EXPLICIT_CODE_MAP_REQUIRED')
        for key, value in self.code_map.items():
            if not key.strip() or len(key) > MAX_VALUE_CHARS or value is None:
                raise ValueError('INVALID_CODE_MAP')
            _valid_value(self.value_type, value, self.options)
        return self


class ProfileDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    label: Label
    form_key: Identifier
    valid_from: date
    valid_to: date | None = None
    fields: list[FieldMapping] = Field(min_length=1, max_length=200)

    @field_validator('valid_from', 'valid_to', mode='before')
    @classmethod
    def exact_date(cls, value):
        if type(value) is str:
            if not DATE.fullmatch(value):
                raise ValueError('INVALID_PROFILE_DATE')
            return date.fromisoformat(value)
        return value

    @model_validator(mode='after')
    def unique_fields_and_dates(self):
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError('REVERSED_PROFILE_DATES')
        if len({item.field_id for item in self.fields}) != len(self.fields):
            raise ValueError('DUPLICATE_FIELD_ID')
        return self


def confirm_value(mapping: FieldMapping, value: Scalar) -> Scalar:
    """Validate a human-supplied scalar. None means a deliberately confirmed blank.

    Authorization, source evidence, version guards and review attribution belong
    to the calling service; invoking this function alone confirms no record.
    """
    if not isinstance(mapping, FieldMapping):
        raise ValueError('INVALID_FIELD_MAPPING')
    return _valid_value(mapping.value_type, value, mapping.options)


def _pages(artifact):
    try:
        if not isinstance(artifact, dict) or type(artifact.get('schema_version')) is not int or artifact['schema_version'] != 1:
            raise ValueError()
        pages = artifact['pages']
        if not isinstance(pages, list) or not 1 <= len(pages) <= 50 or type(artifact.get('page_count')) is not int or artifact['page_count'] != len(pages):
            raise ValueError()
        result = {}
        total_words = 0
        for page in pages:
            number = page['page']
            if type(number) is not int or not 1 <= number <= 50 or number in result:
                raise ValueError()
            if page['status'] not in {'TEXT_EXTRACTED', 'OCR_CANDIDATE', 'OCR_UNAVAILABLE', 'UNREADABLE'}:
                raise ValueError()
            if page['method'] not in {'none', 'pdf_text', 'tesseract'}:
                raise ValueError()
            for key in ('width', 'height'):
                if type(page[key]) not in (int, float) or not math.isfinite(page[key]) or page[key] <= 0:
                    raise ValueError()
            if not isinstance(page['issues'], list) or len(page['issues']) > 30 or any(
                    not isinstance(issue, str) or not re.fullmatch(r'[A-Z_]{1,80}', issue) for issue in page['issues']):
                raise ValueError()
            if not isinstance(page['words'], list) or len(page['words']) > 5_000:
                raise ValueError()
            total_words += len(page['words'])
            for word in page['words']:
                if not isinstance(word['text'], str) or not word['text'].strip() or len(word['text']) > 50_000:
                    raise ValueError()
                _bbox(word['bbox'])
                confidence = word['confidence']
                if confidence is not None and (type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
                    raise ValueError()
            result[number] = page
        if total_words > 25_000:
            raise ValueError()
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('INVALID_READING_ARTIFACT') from None


def _candidate(mapping, raw):
    if raw in mapping.code_map:
        return confirm_value(mapping, mapping.code_map[raw])
    if mapping.value_type in {'boolean', 'enum'}:
        raise ValueError('UNKNOWN_CODE')
    value = raw
    if mapping.value_type == 'number':
        if len(raw) > 64 or NUMBER.fullmatch(raw) is None:
            raise ValueError('VALUE_FORMAT_INVALID')
        value = float(raw) if '.' in raw else int(raw)
    return confirm_value(mapping, value)


def map_fields(artifact: dict, profile: ProfileDefinition) -> dict:
    """Map only explicitly chosen regions, retaining exact word provenance."""
    if not isinstance(profile, ProfileDefinition):
        raise ValueError('INVALID_PROFILE_DEFINITION')
    pages = _pages(artifact)
    result = {}
    remaining_evidence = MAX_EVIDENCE_WORDS_TOTAL
    for definition in profile.fields:
        item = {'state': 'unmapped', 'candidate': None, 'value': None, 'evidence': [], 'issues': []}
        result[definition.field_id] = item
        if definition.extraction == 'not_printed':
            item.update(state='not_printed', issues=['NOT_PRINTED'])
            continue
        if definition.extraction == 'manual':
            item['issues'] = ['MANUAL_ENTRY_REQUIRED']
            continue
        page = pages.get(definition.page)
        if page is None:
            item['issues'] = ['PAGE_UNAVAILABLE']
            continue
        item['issues'] = list(page['issues'])
        if page['status'] in {'UNREADABLE', 'OCR_UNAVAILABLE'}:
            item['state'] = 'unreadable'
            if not item['issues']: item['issues'].append('SOURCE_UNREADABLE')
            continue
        left, top, right, bottom = definition.bbox
        selected, ambiguous, limited = [], False, False
        for word in page['words']:
            x0, y0, x1, y1 = word['bbox']
            if x1 <= left or x0 >= right or y1 <= top or y0 >= bottom:
                continue
            if remaining_evidence <= 0:
                limited = True
                break
            item['evidence'].append({'page': definition.page, 'bbox': list(word['bbox']), 'text': word['text'],
                                     'method': page['method'], 'confidence': word['confidence']})
            remaining_evidence -= 1
            if x0 < left or y0 < top or x1 > right or y1 > bottom:
                ambiguous = True
            else:
                selected.append(word['text'])
        if limited or ambiguous or not selected:
            item['state'] = 'unreadable'
            item['issues'].append('EVIDENCE_LIMIT_REACHED' if limited else 'REGION_BOUNDARY_AMBIGUOUS' if ambiguous else 'EMPTY_REGION')
            continue
        item['state'] = 'unconfirmed'
        try:
            item['candidate'] = _candidate(definition, ' '.join(selected))
        except ValueError as error:
            item['issues'].append('UNKNOWN_CODE' if str(error) == 'UNKNOWN_CODE' else 'VALUE_FORMAT_INVALID')
    return result
