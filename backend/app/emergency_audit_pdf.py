"""Bounded review-copy DTO and child-only raster PDF rendering.

Importing this module does not import a native PDF/image library. The renderer
is called only by emergency_reader_process in production. No source PDF object,
current AI result, generated answer or arbitrary history enters the new PDF.
"""
from contextlib import contextmanager
from datetime import date
from io import BytesIO
import math
import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator


MAX_PDF_BYTES = 32 * 1024 * 1024
MAX_APPENDIX_PAGES = 50
MAX_PLAN_BYTES = 2 * 1024 * 1024
TOTAL_TIMEOUT_SECONDS = 120
ERROR_CODES = frozenset({'PDF_PLAN_INVALID', 'PDF_SOURCE_MISMATCH', 'PDF_APPENDIX_LIMIT',
    'PDF_OUTPUT_LIMIT', 'PDF_FONT_UNAVAILABLE', 'PDF_LAYOUT_LIMIT', 'PDF_EXPORT_FAILED'})


class PDFExportError(ValueError):
    def __init__(self, code):
        self.code = code if code in ERROR_CODES else 'PDF_EXPORT_FAILED'
        super().__init__(self.code)


class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True, allow_inf_nan=False)


Identifier = Annotated[StrictStr, Field(min_length=1, max_length=64)]
ReadState = Literal['confirmed', 'unconfirmed', 'unreadable', 'not_printed', 'unmapped']


class ReviewLocation(_Strict):
    page: Annotated[StrictInt, Field(ge=1, le=50)]
    bbox: list[float] = Field(min_length=4, max_length=4)

    @field_validator('bbox', mode='before')
    @classmethod
    def explicit_bounds(cls, value):
        if (not isinstance(value, list) or len(value) != 4 or any(type(v) not in (float, int)
                or not math.isfinite(v) or not 0 <= v <= 1 for v in value)
                or value[0] >= value[2] or value[1] >= value[3]):
            raise ValueError('Bounded source location required.')
        return [float(v) for v in value]


class ReviewField(_Strict):
    field_id: Identifier
    label: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    state: ReadState
    used: StrictBool


class ReviewFinding(_Strict):
    rule_id: Identifier
    status: Literal['REVIEW_REQUIRED', 'NO_ISSUE_DETECTED', 'NOT_TESTED', 'NOT_APPLICABLE']
    message: Annotated[StrictStr, Field(min_length=1, max_length=2000)]
    source_reference: Annotated[StrictStr, Field(max_length=1000)]
    fields: list[Identifier] = Field(max_length=200)
    is_ai: StrictBool
    decision: Literal['correction_needed', 'false_alarm', 'exception', 'unresolved'] | None
    decision_reason: Literal['missing', 'inconsistent', 'code_selection', 'format', 'reading_error', 'local_rule', 'unknown'] | None
    quote: Annotated[StrictStr, Field(max_length=2000)] | None
    locations: list[ReviewLocation] = Field(max_length=25_000)


class ReviewPlan(_Strict):
    schema_version: Literal[1]
    run_id: Annotated[StrictStr, Field(pattern=r'^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$')]
    report_version: Annotated[StrictInt, Field(ge=1)]
    revision_number: Annotated[StrictInt, Field(ge=1)]
    page_count: Annotated[StrictInt, Field(ge=1, le=50)]
    mode: Literal['candidate', 'approved', 'ai', 'vision']
    reading_complete: StrictBool
    as_of: Annotated[StrictStr, Field(min_length=10, max_length=10)] | None
    fields: list[ReviewField] = Field(max_length=500)
    findings: list[ReviewFinding] = Field(max_length=500)

    @field_validator('as_of')
    @classmethod
    def exact_date(cls, value):
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError('Exact date required.')
        return value

    @model_validator(mode='after')
    def bounded_context(self):
        if (len({item.rule_id for item in self.findings}) != len(self.findings)
                or len({item.field_id for item in self.fields}) != len(self.fields)
                or sum(len(item.locations) for item in self.findings) > 25_000
                or any(location.page > self.page_count for item in self.findings for location in item.locations)):
            raise ValueError('Distinct bounded source context required.')
        return self


def validate_plan(value):
    try:
        return ReviewPlan.model_validate(value)
    except (ValueError, TypeError, RecursionError):
        raise PDFExportError('PDF_PLAN_INVALID') from None


MODE_LABELS = {'candidate': '候補ルール（未承認）', 'approved': '承認済みルール',
               'ai': 'AI文章確認（未確認候補）', 'vision': 'AI画像確認（未確認候補）'}
READ_LABELS = {'confirmed': '確認済み', 'unconfirmed': '未確認', 'unreadable': '読取不能',
               'not_printed': '印刷なし', 'unmapped': '欄対応なし'}
STATUS_LABELS = {'REVIEW_REQUIRED': '要確認（未確認）', 'NOT_TESTED': '未検査',
                 'NO_ISSUE_DETECTED': 'この条件では指摘なし', 'NOT_APPLICABLE': 'この条件は対象外'}
DECISION_LABELS = {'correction_needed': '要修正（担当者確認）', 'false_alarm': '誤警告として確認',
                   'exception': '例外として確認', 'unresolved': '未解決（要確認）'}
REASON_LABELS = {'missing': '記載不足', 'inconsistent': '不整合', 'code_selection': '選択コード',
                 'format': '書式', 'reading_error': '読取誤り', 'local_rule': '地域の運用', 'unknown': '理由未確定'}
MARKER_COLORS = {'correction': (.75, .12, .12), 'review': (.72, .39, .02)}


def _marker_kind(finding):
    if finding.decision == 'correction_needed':
        return 'correction'
    if finding.decision not in {'false_alarm', 'exception'} and finding.status == 'REVIEW_REQUIRED':
        return 'review'
    return None


def _wrapped(text, font, width, size):
    """Character wrapping supports Japanese and long unbroken identifiers."""
    line = ''; length = 0.0
    for character in text:
        if character == '\r':
            continue
        if character == '\n':
            yield line; line = ''; length = 0.0; continue
        if character == '\t':
            character = ' '
        if not font.has_glyph(ord(character)):
            raise PDFExportError('PDF_FONT_UNAVAILABLE')
        advance = font.text_length(character, fontsize=size)
        if advance > width:
            raise PDFExportError('PDF_LAYOUT_LIMIT')
        if line and length + advance > width:
            yield line; line = ''; length = 0.0
        line += character; length += advance
    if line:
        yield line


def _number_ranges(numbers):
    groups = []; start = end = numbers[0]
    for number in numbers[1:]:
        if number == end + 1:
            end = number
        else:
            groups.append(str(start) if start == end else f'{start}-{end}'); start = end = number
    groups.append(str(start) if start == end else f'{start}-{end}')
    return ','.join(groups)


@contextmanager
def _export_source(data):
    from .emergency_reader import _source
    failure = None
    with _source(data) as opened:
        try:
            yield opened
        except Exception as error:
            # The reader normalizes exceptions crossing its source context.
            # Close that context normally so the exporter retains its own
            # bounded, public error codes (e.g. appendix/output exhaustion).
            failure = error
    if failure is not None:
        raise failure


def render_review_pdf(data: bytes, raw_plan: dict) -> bytes:
    """Produce all source pages plus a full Japanese appendix, or fail entirely."""
    plan = validate_plan(raw_plan)
    import pymupdf as fitz
    from .emergency_reader import ReaderError, _deadline, _render_pdf

    deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS
    try:
        _deadline(deadline)
        # This font is distributed with PyMuPDF. Embed its original glyph IDs;
        # do not depend on the viewer's CJK substitution or a system font path.
        font = fitz.Font('cjk')
        if not font.has_glyph(ord('訂')) or not font.buffer:
            raise PDFExportError('PDF_FONT_UNAVAILABLE')
        with _export_source(data) as (media, source), fitz.open() as output:
            source_count = source.page_count if media == 'application/pdf' else 1
            if source_count != plan.page_count:
                raise PDFExportError('PDF_SOURCE_MISMATCH')

            def write(page, text, x, y, *, size=10, color=(.12, .15, .2)):
                _deadline(deadline)
                page.insert_font(fontname='ReviewJapanese', fontbuffer=font.buffer)
                # Font glyph checks cover headings as well as supplied text.
                if any(not font.has_glyph(ord(char)) for char in text):
                    raise PDFExportError('PDF_FONT_UNAVAILABLE')
                page.insert_text((x, y), text, fontname='ReviewJapanese', fontsize=size, color=color)

            def header(page, subtitle):
                write(page, '訂正確認用', 24, 29, size=18)
                write(page, f'検査種別: {MODE_LABELS[plan.mode]} / この検査範囲のみ', 24, 47, size=10)
                write(page, f'原本版 {plan.revision_number} / 報告書版 {plan.report_version} / {subtitle}', 24, 63, size=9)
                write(page, '原本の表示写しと確認結果です。正式な訂正版・提出許可ではありません。', 24, 79, size=9)
                page.draw_line((24, 87), (page.rect.width-24, 87), color=(.65, .69, .72), width=.5)

            def footer(page, text):
                write(page, text, 24, page.rect.height-18, size=8)

            for number in range(1, source_count+1):
                _deadline(deadline)
                native = source.load_page(number-1) if media == 'application/pdf' else None
                picture = _render_pdf(native) if native is not None else source.copy()
                try:
                    # Canonical displayed image geometry is shared with the
                    # reader: PDF crop/rotation and JPEG EXIF have been applied.
                    width, height = picture.size
                    page = output.new_page(width=842 if width > height else 595,
                                           height=595 if width > height else 842)
                    header(page, f'原本 {number}/{source_count} ページ')
                    area = fitz.Rect(24, 97, page.rect.width-24, page.rect.height-38)
                    scale = min(area.width/width, area.height/height)
                    left = area.x0 + (area.width-width*scale)/2
                    top = area.y0 + (area.height-height*scale)/2
                    displayed = fitz.Rect(left, top, left+width*scale, top+height*scale)
                    image = BytesIO(); picture.save(image, format='PNG')
                    page.insert_image(displayed, stream=image.getvalue(), keep_proportion=False)
                finally:
                    picture.close()
                groups = {}
                for index, finding in enumerate(plan.findings, 1):
                    kind = _marker_kind(finding)
                    if kind is None:
                        continue
                    for location in finding.locations:
                        if location.page == number:
                            groups.setdefault(tuple(location.bbox), {}).setdefault(kind, set()).add(index)
                for bounds, markers in groups.items():
                    _deadline(deadline)
                    x0, y0, x1, y1 = bounds
                    box = fitz.Rect(displayed.x0+x0*displayed.width, displayed.y0+y0*displayed.height,
                                    displayed.x0+x1*displayed.width, displayed.y0+y1*displayed.height)
                    # Shared evidence can support different decisions. Keep
                    # each numbered badge's state visible rather than merging
                    # a pending candidate into a confirmed correction.
                    outline = MARKER_COLORS['correction' if 'correction' in markers else 'review']
                    page.draw_rect(box, color=outline, width=1.1, overlay=True)
                    badges = [(kind, _number_ranges(sorted(indices))) for kind, indices in sorted(markers.items())]
                    label_width = sum(font.text_length(label, fontsize=8)+8 for _, label in badges)
                    if label_width > displayed.width:
                        raise PDFExportError('PDF_LAYOUT_LIMIT')
                    label_x = min(box.x0, displayed.x1-label_width)
                    label_y = max(area.y0, box.y0-12)
                    for kind, label in badges:
                        badge_width = font.text_length(label, fontsize=8)+6
                        color = MARKER_COLORS[kind]
                        badge = fitz.Rect(label_x, label_y, label_x+badge_width, label_y+12)
                        page.draw_rect(badge, color=color, fill=(1, 1, 1), width=.6, overlay=True)
                        write(page, label, label_x+3, label_y+9, size=8, color=color)
                        label_x += badge_width+2
                write(page, '番号の色  赤: 要修正（担当者確認） / 橙: 要確認（未確認・AI候補を含む）',
                      24, page.rect.height-31, size=8)
                footer(page, '番号枠は付録の同じ番号に対応します。位置未特定の事項は付録に記載します。')

            appendix_count = 0; page = None; cursor = 0

            def new_appendix():
                nonlocal appendix_count, page, cursor
                _deadline(deadline)
                if appendix_count >= MAX_APPENDIX_PAGES:
                    raise PDFExportError('PDF_APPENDIX_LIMIT')
                appendix_count += 1
                page = output.new_page(width=595, height=842)
                header(page, f'確認一覧 {appendix_count}')
                footer(page, f'確認一覧 {appendix_count} / 原本の電子署名の効力はこの写しへ引き継がれません。')
                cursor = 106

            def paragraph(text, *, size=10, gap=5):
                nonlocal cursor
                for line in _wrapped(text, font, 547, size):
                    if page is None or cursor + size*1.5 > 803:
                        new_appendix()
                    write(page, line, 24, cursor, size=size)
                    cursor += size*1.5
                cursor += gap

            new_appendix()
            paragraph(f'対象検査: {plan.run_id}', size=8)
            if plan.as_of:
                paragraph(f'適用確認日: {plan.as_of}', size=9)
            paragraph('読取の完全性: ' + ('読取処理上は完了（内容の正しさは別途確認）' if plan.reading_complete
                      else '未完了・未確認。読取不能、未確認、未対応の範囲が残る可能性があります。'))
            paragraph('出力対象は指定した検査1件だけです。別の検査・別のAI結果は含みません。'
                      '記載のない欄・ページ・検査種別は未検査です。正しい修正文は生成していません。')
            if plan.mode in {'ai', 'vision'}:
                paragraph('AI候補は担当者の確認結果が付いても、読取値や記載内容の自動確定にはなりません。')
            if not plan.findings:
                paragraph('検査項目なし。この検査で報告書の正しさを確認したことにはなりません。')
            for index, finding in enumerate(plan.findings, 1):
                # Keep the heading with at least its first detail line.
                if cursor > 754:
                    new_appendix()
                decision = DECISION_LABELS.get(finding.decision, STATUS_LABELS[finding.status])
                paragraph(f'{index}. {decision} / {finding.rule_id}', size=11, gap=2)
                paragraph(f'検査結果: {STATUS_LABELS[finding.status]}' + (' / AI候補（未確認）' if finding.is_ai else ''), size=9)
                if finding.decision_reason:
                    paragraph(f'確認理由: {REASON_LABELS[finding.decision_reason]}', size=9)
                paragraph(finding.message)
                if finding.quote:
                    paragraph(f'未確認の引用・読取候補: {finding.quote}')
                if finding.fields:
                    paragraph('対象欄: ' + ', '.join(finding.fields), size=9)
                if finding.locations:
                    pages = ', '.join(str(n) for n in sorted({loc.page for loc in finding.locations}))
                    paragraph('位置: 原本 ' + pages + (' ページの番号枠' if _marker_kind(finding)
                              else ' ページ（訂正対象の枠なし）'), size=9)
                else:
                    paragraph('位置未特定。原本上の座標は推測していません。', size=9)
                if finding.source_reference:
                    paragraph('根拠: ' + finding.source_reference, size=9)
                cursor += 4
            paragraph('検査時点の欄の読取状態', size=12)
            if not plan.fields:
                paragraph('欄対応データなし。原本全体の読取・検査は確認できません。')
            for field in plan.fields:
                paragraph(f'{field.label} ({field.field_id}): {READ_LABELS[field.state]}' +
                          (' / この検査で未使用' if not field.used else ''), size=9, gap=2)
            _deadline(deadline)
            output.set_metadata({'title': '訂正確認用', 'producer': 'Fire AI review export'})
            result = output.tobytes(garbage=4, deflate=True)
            _deadline(deadline)
            if len(result) > MAX_PDF_BYTES:
                raise PDFExportError('PDF_OUTPUT_LIMIT')
            return result
    except (PDFExportError, ReaderError):
        raise
    except Exception:
        raise PDFExportError('PDF_EXPORT_FAILED') from None
