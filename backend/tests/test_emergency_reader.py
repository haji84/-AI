"""Synthetic in-memory originals exercise the private reader, never patient files."""
from importlib import import_module
from io import BytesIO
import os
import shutil

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont
import pytest


def reader():
    return import_module('app.emergency_reader')


def png(width=300, height=160, text='SYNTHETIC 123'):
    image = Image.new('RGB', (width, height), 'white')
    ImageDraw.Draw(image).text((15, 30), text, fill='black', font=ImageFont.load_default(size=28))
    stream = BytesIO(); image.save(stream, 'PNG'); image.close()
    return stream.getvalue()


def pdf(*, scanned=False, mixed=False, rotation=0, annotations=False):
    with fitz.open() as document:
        page = document.new_page(width=400, height=200)
        if scanned:
            page.insert_image(page.rect, stream=png())
        else:
            page.insert_text((40, 40), 'SYNTHETIC REPORT 123', fontsize=12)
        if annotations:
            page.add_text_annot((15, 15), 'Synthetic correction note')
        page.set_rotation(rotation)
        if mixed:
            page = document.new_page(width=400, height=200)
            page.insert_image(page.rect, stream=png(text='SCANNED 456'))
        return document.tobytes()


def test_text_pdf_has_page_local_normalized_evidence_and_no_ocr(monkeypatch):
    r = reader()
    monkeypatch.setattr(r, '_available_languages', lambda: (_ for _ in ()).throw(AssertionError('text page must not run OCR')))
    data = pdf()
    assert r.inspect_source(data) == {'media_type': 'application/pdf', 'page_count': 1}
    result = r.extract_source(data)
    assert result['schema_version'] == 1 and result['complete'] is True
    page = result['pages'][0]
    assert (page['page'], page['width'], page['height'], page['status']) == (1, 400, 200, 'TEXT_EXTRACTED')
    assert 'SYNTHETIC REPORT 123' in page['text']
    assert page['words'][0]['text'] == 'SYNTHETIC'
    x0, y0, x1, y1 = page['words'][0]['bbox']
    assert x0 == pytest.approx(.1) and .12 < y0 < .16 and .19 < y1 < .23
    assert .1 < x1 < .4
    assert page['words'][0]['confidence'] is None


def test_mixed_pdf_does_not_let_text_page_hide_unavailable_scanned_page(monkeypatch):
    r = reader(); monkeypatch.setattr(r, '_available_languages', lambda: {'eng', 'osd'})
    result = r.extract_source(pdf(mixed=True))
    assert [p['status'] for p in result['pages']] == ['TEXT_EXTRACTED', 'OCR_UNAVAILABLE']
    assert result['complete'] is False and result['page_count'] == 2
    assert 'OCR_LANGUAGE_UNAVAILABLE' in result['pages'][1]['issues']
    assert result['pages'][1]['words'] == []


def test_rotation_keeps_word_boxes_in_displayed_page_coordinates():
    r = reader(); data = pdf(rotation=90)
    page = r.extract_source(data)['pages'][0]
    assert (page['width'], page['height']) == (200, 400)
    x0, y0, x1, y1 = page['words'][0]['bbox']
    assert .77 < x0 < .82 and .84 < x1 < .88
    assert y0 == pytest.approx(.1) and .1 < y1 < .4
    with Image.open(BytesIO(r.render_page(data, 1))) as image:
        assert image.width < image.height
        assert image.width * image.height <= 12_000_000


def test_annotations_keep_rendered_marks_and_require_review():
    r = reader(); data = pdf(annotations=True)
    result = r.extract_source(data)
    assert result['complete'] is False
    assert 'PDF_ANNOTATIONS_REVIEW_REQUIRED' in result['pages'][0]['issues']
    assert r.render_page(data, 1).startswith(b'\x89PNG\r\n\x1a\n')


def test_hidden_text_is_flagged_as_untrusted_overlay():
    r = reader()
    with fitz.open() as document:
        page = document.new_page(width=300, height=200)
        page.insert_text((20, 30), 'VISIBLE', fontsize=16)
        page.insert_text((20, 70), 'HIDDEN', fontsize=16, render_mode=3)
        result = r.extract_source(document.tobytes())
    assert result['complete'] is False
    assert 'PDF_HIDDEN_TEXT_REVIEW_REQUIRED' in result['pages'][0]['issues']


@pytest.mark.parametrize('source', [b'', b'not a PDF\nsynthetic-private-sentinel', b'%PDF-1.7\nbroken', b'GIF89a'])
def test_invalid_sources_fail_with_only_fixed_safe_codes(source):
    r = reader()
    with pytest.raises(r.ReaderError) as caught:
        r.inspect_source(source)
    assert str(caught.value) == caught.value.code
    assert 'synthetic-private-sentinel' not in str(caught.value)
    assert caught.value.code in {'SOURCE_EMPTY', 'SOURCE_UNSUPPORTED', 'SOURCE_INVALID'}


@pytest.mark.parametrize('kind', ['encrypted', 'embedded', 'javascript'])
def test_unsafe_pdf_objects_are_rejected_before_reading(kind):
    r = reader()
    with fitz.open() as document:
        document.new_page(width=100, height=100).insert_text((10, 20), 'SYNTHETIC')
        if kind == 'embedded':
            document.embfile_add('synthetic.txt', b'synthetic-only')
        if kind == 'javascript':
            xref = document.get_new_xref()
            document.update_object(xref, r'<< /Type /Action /S /JavaScript /JS (app.alert\(1\)) >>')
            document.xref_set_key(document.pdf_catalog(), 'OpenAction', f'{xref} 0 R')
        kwargs = {'encryption': fitz.PDF_ENCRYPT_AES_256, 'owner_pw': 'synthetic-owner', 'user_pw': 'synthetic-user'} if kind == 'encrypted' else {}
        data = document.tobytes(**kwargs)
    with pytest.raises(r.ReaderError) as caught:
        r.inspect_source(data)
    assert caught.value.code == ('SOURCE_ENCRYPTED' if kind == 'encrypted' else 'PDF_UNSAFE_CONTENT')


def test_limits_reject_oversized_bytes_pages_and_render_dimensions():
    r = reader()
    with pytest.raises(r.ReaderError, match='SOURCE_TOO_LARGE'):
        r.inspect_source(b'x' * (25 * 1024 * 1024 + 1))
    with fitz.open() as document:
        for _ in range(51): document.new_page(width=100, height=100)
        with pytest.raises(r.ReaderError, match='PAGE_LIMIT_EXCEEDED'):
            r.inspect_source(document.tobytes())
    with fitz.open() as document:
        document.new_page(width=100_000, height=100_000)
        with pytest.raises(r.ReaderError, match='PAGE_TOO_LARGE'):
            r.inspect_source(document.tobytes())


def test_image_dimensions_checked_before_decode_and_exif_rotation_is_preserved():
    r = reader()
    image = Image.new('RGB', (80, 40), 'red')
    exif = Image.Exif(); exif[274] = 6
    out = BytesIO(); image.save(out, 'JPEG', exif=exif); image.close()
    assert r.inspect_source(out.getvalue()) == {'media_type': 'image/jpeg', 'page_count': 1}
    with Image.open(BytesIO(r.render_page(out.getvalue(), 1))) as preview:
        assert preview.size == (40, 80)
        assert not preview.getexif()
    image = Image.new('1', (4000, 4000)); out = BytesIO(); image.save(out, 'PNG'); image.close()
    with pytest.raises(r.ReaderError, match='PAGE_TOO_LARGE'):
        r.inspect_source(out.getvalue())


def test_ocr_timeout_is_unreadable_without_exception_text(monkeypatch):
    r = reader(); monkeypatch.setattr(r, '_available_languages', lambda: {'jpn', 'eng'})
    calls = []
    def timeout(*args, **kwargs):
        calls.append(kwargs)
        assert 0 < kwargs['timeout'] <= 15
        raise RuntimeError('Tesseract process timeout synthetic-private-sentinel')
    monkeypatch.setattr(r.pytesseract, 'image_to_data', timeout)
    result = r.extract_source(png())
    assert result['complete'] is False
    assert result['pages'][0]['status'] == 'UNREADABLE'
    assert result['pages'][0]['issues'] == ['OCR_TIMEOUT']
    assert 'synthetic-private-sentinel' not in repr(result)
    assert len(calls) == 1


def test_empty_automatic_segmentation_retries_sparse_text_with_same_language_and_remaining_budget(monkeypatch):
    from types import SimpleNamespace
    r = reader(); now = [100.0]; calls = []
    monkeypatch.setattr(r, '_available_languages', lambda: {'jpn', 'eng'})
    monkeypatch.setattr(r, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    def recognize(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            now[0] += 9
            return {'text': ['', '  ']}
        return {'text': ['救急'], 'left': [10], 'top': [20], 'width': [60], 'height': [40], 'conf': [95]}
    monkeypatch.setattr(r.pytesseract, 'image_to_data', recognize)
    page = r.extract_source(png())['pages'][0]
    assert page['status'] == 'OCR_CANDIDATE' and page['text'] == '救急'
    assert page['issues'] == [] and page['method'] == 'tesseract'
    assert page['words'][0]['confidence'] == .95
    assert page['words'][0]['bbox'] == pytest.approx([10/300, 20/160, 70/300, 60/160])
    assert len(calls) == 2 and [call['lang'] for call in calls] == ['jpn+eng', 'jpn+eng']
    assert calls[0].get('config', '') == '' and calls[1]['config'] == '--psm 11'
    assert [call['timeout'] for call in calls] == pytest.approx([15, 6])


def test_usable_automatic_segmentation_is_not_replaced_by_an_extra_ocr_attempt(monkeypatch):
    r = reader(); calls = []
    monkeypatch.setattr(r, '_available_languages', lambda: {'jpn', 'eng'})
    def recognize(*args, **kwargs):
        calls.append(kwargs)
        return {'text': ['Synthetic'], 'left': [10], 'top': [20], 'width': [60], 'height': [40], 'conf': [95]}
    monkeypatch.setattr(r.pytesseract, 'image_to_data', recognize)
    page = r.extract_source(png())['pages'][0]
    assert page['status'] == 'OCR_CANDIDATE' and page['text'] == 'Synthetic'
    assert len(calls) == 1


@pytest.mark.parametrize('elapsed,issue', [(15, 'OCR_TIMEOUT'), (95, 'TOTAL_TIMEOUT')])
def test_empty_ocr_cannot_start_a_retry_after_its_existing_deadline(monkeypatch, elapsed, issue):
    from types import SimpleNamespace
    r = reader(); now = [100.0]; calls = []
    monkeypatch.setattr(r, '_available_languages', lambda: {'jpn', 'eng'})
    monkeypatch.setattr(r, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    def recognize(*args, **kwargs):
        calls.append(kwargs); now[0] += elapsed
        return {'text': []}
    monkeypatch.setattr(r.pytesseract, 'image_to_data', recognize)
    result = r.extract_source(png()); page = result['pages'][0]
    assert result['complete'] is False and page['status'] == 'UNREADABLE'
    assert page['issues'] == [issue] and page['words'] == []
    assert len(calls) == 1


def test_two_empty_segmentation_attempts_remain_unreadable_without_more_retries(monkeypatch):
    r = reader(); calls = []
    monkeypatch.setattr(r, '_available_languages', lambda: {'jpn', 'eng'})
    def recognize(*args, **kwargs):
        calls.append(kwargs)
        return {'text': ['']}
    monkeypatch.setattr(r.pytesseract, 'image_to_data', recognize)
    result = r.extract_source(png()); page = result['pages'][0]
    assert result['complete'] is False and page['status'] == 'UNREADABLE'
    assert page['issues'] == ['NO_TEXT_FOUND'] and page['words'] == []
    assert len(calls) == 2


def test_total_deadline_marks_remaining_pages_unreadable(monkeypatch):
    r = reader()
    ticks = iter([0, 0, 0, 10_000])
    monkeypatch.setattr(r.time, 'monotonic', lambda: next(ticks, 10_000))
    result = r.extract_source(pdf(mixed=True))
    assert result['complete'] is False
    assert any('TOTAL_TIMEOUT' in page['issues'] for page in result['pages'])
    assert len(result['pages']) == result['page_count'] == 2


@pytest.mark.parametrize('page', [0, 2, True, 1.5, '1'])
def test_preview_rejects_invalid_page_identity(page):
    r = reader()
    with pytest.raises(r.ReaderError, match='PAGE_OUT_OF_RANGE'):
        r.render_page(pdf(), page)


def test_native_english_ocr_returns_candidates_with_normalized_provenance():
    if not shutil.which('tesseract'): pytest.skip('native Tesseract not installed')
    r = reader()
    result = r.extract_source(png(width=500, text='SYNTHETIC 123'), language='eng')
    page = result['pages'][0]
    assert page['status'] == 'OCR_CANDIDATE'
    assert 'SYNTHETIC' in page['text'] and '123' in page['text']
    assert page['words'] and all(0 <= n <= 1 for word in page['words'] for n in word['bbox'])
    assert all(word['confidence'] is None or 0 <= word['confidence'] <= 1 for word in page['words'])


def test_word_limit_is_explicit_instead_of_complete_truncation(monkeypatch):
    r = reader(); monkeypatch.setattr(r, 'MAX_WORDS_PER_PAGE', 2)
    result = r.extract_source(pdf())
    assert result['complete'] is False
    assert len(result['pages'][0]['words']) == 2
    assert 'TEXT_LIMIT_REACHED' in result['pages'][0]['issues']


def test_cropped_rotated_pdf_boxes_still_identify_visible_page():
    r = reader()
    with fitz.open() as document:
        page = document.new_page(width=500, height=400)
        page.insert_text((120, 140), 'CROPPED', fontsize=12)
        page.set_cropbox(fitz.Rect(100, 100, 400, 300))
        page.set_rotation(180)
        data = document.tobytes()
    result = r.extract_source(data)['pages'][0]
    assert (result['width'], result['height']) == (300, 200)
    word = result['words'][0]
    assert word['text'] == 'CROPPED'
    x0, y0, x1, y1 = word['bbox']
    assert .7 < x0 < .8 and x1 == pytest.approx(280 / 300)
    assert .77 < y0 < .82 and .85 < y1 < .89


def test_text_plus_image_same_page_reports_untrusted_text_layer(monkeypatch):
    r = reader()
    with fitz.open() as document:
        page = document.new_page(width=400, height=200)
        page.insert_image(page.rect, stream=png())
        page.insert_text((20, 25), 'SYNTHETIC OVERLAY')
        result = r.extract_source(document.tobytes())
    assert result['complete'] is False
    assert 'PDF_IMAGES_REVIEW_REQUIRED' in result['pages'][0]['issues']


def test_transparent_png_preview_flattens_on_visible_white_background():
    r = reader(); source = Image.new('RGBA', (20, 20), (0, 0, 0, 0))
    source.putpixel((10, 10), (255, 0, 0, 255))
    out = BytesIO(); source.save(out, 'PNG'); source.close()
    with Image.open(BytesIO(r.render_page(out.getvalue(), 1))) as preview:
        assert preview.getpixel((0, 0)) == (255, 255, 255)
        assert preview.getpixel((10, 10)) == (255, 0, 0)


def test_corrupt_png_crc_is_rejected_before_preview():
    r = reader(); data = bytearray(png())
    # IHDR CRC is bytes29..32; pixel loading alone can ignore its corruption.
    data[29] ^= 255
    with pytest.raises(r.ReaderError, match='SOURCE_INVALID'):
        r.inspect_source(bytes(data))


def test_corrupt_png_pixel_chunk_crc_is_not_silently_accepted():
    r = reader(); data = bytearray(png())
    offset = 8
    while offset < len(data):
        length = int.from_bytes(data[offset:offset+4], 'big')
        if data[offset+4:offset+8] == b'IDAT':
            data[offset+8+length] ^= 255
            break
        offset += length+12
    with pytest.raises(r.ReaderError, match='SOURCE_INVALID'):
        r.inspect_source(bytes(data))


def test_png_original_is_not_modified_and_preview_discards_metadata():
    from PIL.PngImagePlugin import PngInfo
    r = reader(); source = Image.new('RGB', (20, 20), 'white'); metadata = PngInfo()
    metadata.add_text('Comment', 'synthetic-private-sentinel')
    out = BytesIO(); source.save(out, 'PNG', pnginfo=metadata); source.close(); original = out.getvalue()
    rendered = r.render_page(original, 1)
    assert b'synthetic-private-sentinel' in original
    assert b'synthetic-private-sentinel' not in rendered


def test_malformed_ocr_coordinates_cannot_become_valid_evidence(monkeypatch):
    r = reader(); calls = []
    monkeypatch.setattr(r, '_available_languages', lambda: {'jpn', 'eng'})
    raw = {'text': ['synthetic'], 'left': [-15], 'top': [20], 'width': [40], 'height': [30], 'conf': ['92']}
    def recognize(*args, **kwargs):
        calls.append(kwargs)
        return raw
    monkeypatch.setattr(r.pytesseract, 'image_to_data', recognize)
    result = r.extract_source(png())
    assert result['complete'] is False and result['pages'][0]['status'] == 'UNREADABLE'
    assert result['pages'][0]['words'] == []
    assert 'WORD_GEOMETRY_INVALID' in result['pages'][0]['issues']
    assert len(calls) == 1


def test_native_japanese_printed_image_has_real_readable_candidates():
    r = reader()
    if not {'jpn', 'eng'} <= r._available_languages():
        if os.environ.get('FIRE_AI_REQUIRE_JAPANESE_OCR') == '1':
            pytest.fail('Japanese OCR runtime required by this CI environment is unavailable')
        pytest.skip('native Japanese Tesseract data unavailable locally')
    # MuPDF's built-in Japanese font makes the synthetic raster portable;
    # no private template or operating-system font is required.
    with fitz.open() as document:
        page = document.new_page(width=380, height=100)
        page.insert_text((25, 65), '救急報告書', fontsize=36, fontname='japan')
        picture = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes('png')
    result = r.extract_source(picture)
    page_result = result['pages'][0]
    # Fixed status/issue codes and counts only: enough native-CI diagnostics
    # without dumping an original, OCR text, path or native exception message.
    diagnostic = {'status': page_result['status'], 'method': page_result['method'],
                  'issues': page_result['issues'], 'word_count': len(page_result['words'])}
    assert page_result['status'] == 'OCR_CANDIDATE', diagnostic
    assert '救急' in result['pages'][0]['text'].replace(' ', '')
    assert result['pages'][0]['words']
