"""Synthetic review copies: visible Japanese, exact source geometry and full failure."""
from copy import deepcopy
from importlib import import_module
from io import BytesIO
import sys

from PIL import Image, ImageDraw
import pymupdf as fitz
import pytest


def review_plan():
    return {'schema_version': 1, 'run_id': '00000000-0000-0000-0000-000000000001',
        'report_version': 4, 'revision_number': 1, 'page_count': 1, 'mode': 'candidate',
        'reading_complete': False, 'as_of': '2026-11-22',
        'fields': [{'field_id': 'sample', 'label': '記載欄', 'state': 'unreadable', 'used': True}],
        'findings': [{'rule_id': 'SYN-1', 'status': 'REVIEW_REQUIRED', 'message': '原本の記載を確認してください。',
            'source_reference': '合成資料 1ページ', 'fields': ['sample'], 'is_ai': False,
            'decision': 'correction_needed', 'decision_reason': 'missing', 'quote': None,
            'locations': [{'page': 1, 'bbox': [.1, .2, .4, .4]}]}]}


def source_pdf(*, rotation=0, crop=False, hidden=False):
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=240)
        page.insert_text((50, 80), 'SYNTHETIC VISIBLE', fontsize=15)
        page.draw_rect(fitz.Rect(40, 48, 160, 96), color=(0, 0, 0), width=1)
        if hidden:
            page.insert_text((50, 140), 'SYNTHETIC_HIDDEN_TEXT', render_mode=3)
            page.insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(40, 48, 160, 96), 'uri': 'https://example.invalid/private'})
            page.add_text_annot((200, 120), 'SYNTHETIC_VISIBLE_ANNOTATION')
        if crop:
            page.set_cropbox(fitz.Rect(20, 30, 380, 210))
        page.set_rotation(rotation)
        return doc.tobytes()


def render(source=None, plan=None):
    return import_module('app.emergency_audit_pdf').render_review_pdf(
        source or source_pdf(), plan or review_plan())


def text_of(data):
    with fitz.open(stream=data, filetype='pdf') as doc:
        return '\n'.join(page.get_text() for page in doc)


def test_review_copy_flattens_original_objects_keeps_original_unchanged_and_embeds_japanese():
    raw = source_pdf(hidden=True); original = bytes(raw)
    result = render(raw)
    assert raw == original and result != raw
    with fitz.open(stream=result, filetype='pdf') as doc:
        assert doc.page_count >= 2
        text = '\n'.join(page.get_text() for page in doc)
        assert '訂正確認用' in text and '要修正（担当者確認）' in text
        assert '候補ルール' in text and 'この検査範囲のみ' in text
        assert '読取不能' in text and '原本の記載を確認してください。' in text
        assert 'SYNTHETIC_HIDDEN_TEXT' not in text and 'SYNTHETIC VISIBLE' not in text
        assert doc.embfile_count() == 0
        assert all(not list(page.annots() or ()) and not list(page.widgets() or ()) and not page.get_links() for page in doc)
        objects = '\n'.join(doc.xref_object(i) for i in range(1, doc.xref_length()))
        assert '/JavaScript' not in objects and '/EmbeddedFile' not in objects and '/OCProperties' not in objects
        assert any(doc.extract_font(font[0])[3] for page in doc for font in page.get_fonts())
        assert doc[0].get_images() and doc[0].get_pixmap().samples


@pytest.mark.parametrize('rotation,crop', [(0, False), (90, False), (180, True), (270, True)])
def test_numbered_boxes_follow_displayed_pdf_rotation_and_crop(rotation, crop):
    raw = source_pdf(rotation=rotation, crop=crop)
    from app.emergency_reader import extract_source, render_page
    reading = extract_source(raw)
    bbox = reading['pages'][0]['words'][0]['bbox']
    plan = review_plan(); plan['findings'][0]['locations'][0]['bbox'] = bbox
    result = render(raw, plan)
    with fitz.open(stream=result, filetype='pdf') as doc:
        page = doc[0]
        source_rect = page.get_image_rects(page.get_images()[0][0])[0]
        want = fitz.Rect(source_rect.x0 + bbox[0] * source_rect.width,
                         source_rect.y0 + bbox[1] * source_rect.height,
                         source_rect.x0 + bbox[2] * source_rect.width,
                         source_rect.y0 + bbox[3] * source_rect.height)
        boxes = [drawing['rect'] for drawing in page.get_drawings() if drawing['color'] == pytest.approx((.75, .12, .12))]
        assert any(tuple(box) == pytest.approx(tuple(want), abs=.02) for box in boxes)
        with Image.open(BytesIO(render_page(raw, 1))) as original:
            assert source_rect.width / source_rect.height == pytest.approx(original.width / original.height, rel=.001)


def test_image_exif_orientation_and_unknown_position_remain_explicit():
    picture = Image.new('RGB', (160, 80), 'white')
    ImageDraw.Draw(picture).rectangle((0, 0, 80, 40), fill='red')
    exif = Image.Exif(); exif[274] = 6
    stream = BytesIO(); picture.save(stream, 'JPEG', exif=exif); picture.close()
    plan = review_plan(); plan['mode'] = 'ai'; plan['findings'][0].update(is_ai=True, locations=[], quote='未確認候補')
    result = render(stream.getvalue(), plan)
    with fitz.open(stream=result, filetype='pdf') as doc:
        source_rect = doc[0].get_image_rects(doc[0].get_images()[0][0])[0]
        assert source_rect.width / source_rect.height == pytest.approx(.5)
        assert not any(drawing['color'] == pytest.approx((.75, .12, .12)) for drawing in doc[0].get_drawings())
    text = text_of(result)
    assert '位置未特定' in text and 'AI候補（未確認）' in text and 'AI文章確認' in text


@pytest.mark.parametrize('status,decision,color', [
    ('REVIEW_REQUIRED', 'correction_needed', (.75, .12, .12)),
    ('REVIEW_REQUIRED', None, (.72, .39, .02)),
    ('REVIEW_REQUIRED', 'unresolved', (.72, .39, .02)),
    ('REVIEW_REQUIRED', 'false_alarm', None),
    ('REVIEW_REQUIRED', 'exception', None),
    ('NO_ISSUE_DETECTED', None, None),
    ('NOT_APPLICABLE', None, None),
    ('NOT_TESTED', None, None),
])
def test_source_page_does_not_mark_cleared_or_untested_findings_as_required_corrections(status, decision, color):
    plan = review_plan(); plan['findings'][0].update(status=status, decision=decision)
    result = render(plan=plan)
    with fitz.open(stream=result, filetype='pdf') as doc:
        drawings = [d for d in doc[0].get_drawings() if d['color'] == pytest.approx((.75, .12, .12))
                    or d['color'] == pytest.approx((.72, .39, .02))]
        assert bool(drawings) == (color is not None)
        if color is not None:
            assert all(d['color'] == pytest.approx(color) for d in drawings)
        assert '赤: 要修正' in doc[0].get_text() and '橙: 要確認' in doc[0].get_text()
    if color is None:
        assert 'ページの番号枠' not in text_of(result)


def test_long_japanese_appendix_paginates_without_dropping_last_finding_or_read_states():
    plan = review_plan()
    plan['fields'] = [dict(field_id=f'f{i}', label=f'未読欄{i}', state=state, used=False)
        for i, state in enumerate(('unreadable', 'unmapped', 'not_printed', 'unconfirmed', 'confirmed'))]
    plan['findings'] = [{**deepcopy(plan['findings'][0]), 'rule_id': f'SYN-{index}',
        'message': ('日本語の長い確認事項。原本と照合してください。' * 15) + f' END_{index}',
        'fields': [], 'locations': [], 'decision': None} for index in range(12)]
    result = render(plan=plan)
    with fitz.open(stream=result, filetype='pdf') as doc:
        assert doc.page_count > 3
    text = text_of(result).replace('\n', '')
    assert all(f'END_{index}' in text for index in range(12))
    for state in ('読取不能', '欄対応なし', '印刷なし', '未確認', '確認済み', 'この検査で未使用'):
        assert state in text


@pytest.mark.parametrize('kind,code', [('pages', 'PAGE_LIMIT_EXCEEDED'), ('pixels', 'PAGE_TOO_LARGE'),
    ('appendix', 'PDF_APPENDIX_LIMIT'), ('bytes', 'PDF_OUTPUT_LIMIT'), ('timeout', 'TOTAL_TIMEOUT')])
def test_resource_limits_fail_the_complete_export_instead_of_returning_partial_pdf(monkeypatch, kind, code):
    module = import_module('app.emergency_audit_pdf')
    from app.emergency_reader import ReaderError
    raw = source_pdf(); plan = review_plan()
    if kind == 'pages':
        with fitz.open() as doc:
            for _ in range(51): doc.new_page(width=100, height=100)
            raw = doc.tobytes()
    elif kind == 'pixels':
        with fitz.open() as doc:
            doc.new_page(width=2000, height=2000); raw = doc.tobytes()
    elif kind == 'appendix': monkeypatch.setattr(module, 'MAX_APPENDIX_PAGES', 0)
    elif kind == 'bytes': monkeypatch.setattr(module, 'MAX_PDF_BYTES', 100)
    else: monkeypatch.setattr(module, 'TOTAL_TIMEOUT_SECONDS', 0)
    with pytest.raises((module.PDFExportError, ReaderError), match=code):
        module.render_review_pdf(raw, plan)


@pytest.mark.parametrize('change', ['unknown_key', 'out_of_page', 'bad_bbox', 'duplicate_rule', 'secret_value'])
def test_only_bounded_allowlisted_plan_can_reach_native_rendering(change):
    module = import_module('app.emergency_audit_pdf'); plan = review_plan()
    if change == 'unknown_key': plan['history'] = ['PRIVATE_SENTINEL']
    elif change == 'out_of_page': plan['findings'][0]['locations'][0]['page'] = 2
    elif change == 'bad_bbox': plan['findings'][0]['locations'][0]['bbox'] = [.8, .3, .2, .4]
    elif change == 'duplicate_rule': plan['findings'] *= 2
    else: plan['fields'][0]['value'] = 'PRIVATE_SENTINEL'
    with pytest.raises(module.PDFExportError, match='PDF_PLAN_INVALID') as caught:
        module.render_review_pdf(source_pdf(), plan)
    assert 'PRIVATE_SENTINEL' not in str(caught.value)


def test_review_pdf_runs_in_existing_killable_worker_and_enforces_output_contract(monkeypatch):
    worker = import_module('app.emergency_audit_worker')
    result = worker.run_isolated('review_pdf', source_pdf(), export_plan=review_plan())
    assert '訂正確認用' in text_of(result)
    monkeypatch.setitem(worker.MODE_TIMEOUTS, 'review_pdf', .001)
    with pytest.raises(worker.WorkerError, match='PROCESS_TIMEOUT'):
        worker.run_isolated('review_pdf', source_pdf(), export_plan=review_plan())


def test_review_pdf_worker_rejects_invalid_or_oversized_native_response(monkeypatch):
    worker = import_module('app.emergency_audit_worker')
    monkeypatch.setattr(worker, '_child_command', lambda: [sys.executable, '-c',
        "print('{\"ok\":true,\"result\":\"UFJJVkFURV9TRU5USU5FTA==\"}')"])
    with pytest.raises(worker.WorkerError, match='PROCESS_RESPONSE_INVALID'):
        worker.run_isolated('review_pdf', source_pdf(), export_plan=review_plan())
    monkeypatch.setitem(worker.OUTPUT_LIMITS, 'review_pdf', 8)
    with pytest.raises(worker.WorkerError, match='PROCESS_OUTPUT_LIMIT'):
        worker.run_isolated('review_pdf', source_pdf(), export_plan=review_plan())
