"""Bounded, local reading of private originals; no text is confirmed here.

PDF/image parsing and rendering stay in memory. Pytesseract creates temporary
image/TSV files and removes them on success/error/timeout; production must use
an access-restricted temporary directory. The caller must isolate this module
in a killable worker: cooperative deadlines cannot interrupt native PDF/PIL
parsing. No originals, text, filenames or native exception messages are logged.
"""
from contextlib import contextmanager
from io import BytesIO
import math
import re
import subprocess
import time
import warnings

import pymupdf as fitz
from PIL import Image, ImageOps
import pytesseract


MAX_SOURCE_BYTES = 25 * 1024 * 1024
MAX_PAGES = 50
MAX_RENDER_PIXELS = 12_000_000
MAX_EDGE_PIXELS = 16_384
MAX_PDF_OBJECTS = 50_000
MAX_WORDS_PER_PAGE = 5_000
MAX_WORDS_TOTAL = 25_000
MAX_TEXT_CHARS_PER_PAGE = 50_000
MAX_TEXT_CHARS_TOTAL = 250_000
OCR_TIMEOUT_SECONDS = 15
TOTAL_TIMEOUT_SECONDS = 90
RENDER_SCALE = 2.0

ERROR_CODES = frozenset({
    'SOURCE_EMPTY', 'SOURCE_TOO_LARGE', 'SOURCE_UNSUPPORTED', 'SOURCE_INVALID',
    'SOURCE_ENCRYPTED', 'SOURCE_MULTIFRAME_UNSUPPORTED', 'PDF_UNSAFE_CONTENT',
    'PDF_OBJECT_LIMIT_EXCEEDED', 'PAGE_LIMIT_EXCEEDED', 'PAGE_TOO_LARGE',
    'PAGE_OUT_OF_RANGE', 'OCR_LANGUAGE_INVALID', 'OCR_ENGINE_UNAVAILABLE',
    'OCR_LANGUAGE_UNAVAILABLE', 'OCR_TIMEOUT', 'OCR_FAILED', 'TOTAL_TIMEOUT',
    'READ_FAILED', 'TEXT_LIMIT_REACHED', 'NO_TEXT_FOUND', 'WORD_GEOMETRY_INVALID',
    'PDF_ANNOTATIONS_REVIEW_REQUIRED', 'PDF_HIDDEN_TEXT_REVIEW_REQUIRED',
    'PDF_IMAGES_REVIEW_REQUIRED', 'PDF_FORM_REVIEW_REQUIRED', 'PDF_LAYERS_REVIEW_REQUIRED',
})


class ReaderError(ValueError):
    def __init__(self, code: str):
        self.code = code if code in ERROR_CODES else 'SOURCE_INVALID'
        super().__init__(self.code)


def _dimensions(width, height, scale=1.0):
    if not all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0
               for value in (width, height, scale)):
        raise ReaderError('PAGE_TOO_LARGE')
    pixels = (math.ceil(width * scale), math.ceil(height * scale))
    if max(pixels) > MAX_EDGE_PIXELS or pixels[0] * pixels[1] > MAX_RENDER_PIXELS:
        raise ReaderError('PAGE_TOO_LARGE')
    return pixels


def _validate_pdf(document):
    if not document.is_pdf or document.is_repaired:
        raise ReaderError('SOURCE_INVALID')
    if document.needs_pass or document.is_encrypted or document.xref_get_key(-1, 'Encrypt')[0] != 'null':
        raise ReaderError('SOURCE_ENCRYPTED')
    if not 1 <= document.page_count <= MAX_PAGES:
        raise ReaderError('PAGE_LIMIT_EXCEEDED')
    if document.xref_length() > MAX_PDF_OBJECTS:
        raise ReaderError('PDF_OBJECT_LIMIT_EXCEEDED')
    if document.embfile_count():
        raise ReaderError('PDF_UNSAFE_CONTENT')
    # Structural actions are never executed, and active/embedded content is
    # rejected before either inspection or rendering. Only raster previews are
    # exposed by the integration, never an inline original PDF.
    for xref in range(1, document.xref_length()):
        obj = document.xref_object(xref, compressed=False)
        if re.search(r'/(?:JavaScript|JS|EmbeddedFiles|EmbeddedFile|RichMedia|Launch|SubmitForm|ImportData)\b', obj):
            raise ReaderError('PDF_UNSAFE_CONTENT')
    for page in document:
        _dimensions(page.rect.width, page.rect.height, RENDER_SCALE)
        # A small visible page can contain a huge compressed raster image.
        for image in page.get_images(full=True):
            _dimensions(image[2], image[3])
        for image in page.get_image_info():
            _dimensions(image['width'], image['height'])


@contextmanager
def _source(data):
    source = None
    try:
        if type(data) is not bytes:
            raise ReaderError('SOURCE_INVALID')
        if not data:
            raise ReaderError('SOURCE_EMPTY')
        if len(data) > MAX_SOURCE_BYTES:
            raise ReaderError('SOURCE_TOO_LARGE')
        if data.startswith(b'%PDF-'):
            source = fitz.open(stream=data, filetype='pdf')
            _validate_pdf(source)
            yield 'application/pdf', source
        elif data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff'):
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as original:
                    if original.format not in {'PNG', 'JPEG'}:
                        raise ReaderError('SOURCE_UNSUPPORTED')
                    media = 'image/png' if original.format == 'PNG' else 'image/jpeg'
                    _dimensions(*original.size)
                    if getattr(original, 'n_frames', 1) != 1:
                        raise ReaderError('SOURCE_MULTIFRAME_UNSUPPORTED')
                    # Pixel decoding alone can ignore a damaged PNG IDAT CRC.
                    # Verify the container first, then reopen for the decode.
                    original.verify()
                with Image.open(BytesIO(data)) as original:
                    original.load()
                    with ImageOps.exif_transpose(original) as oriented:
                        # Transparent scans must look the same on the white
                        # document canvas used for OCR and the preview.
                        if oriented.mode in {'RGBA', 'LA'} or 'transparency' in oriented.info:
                            with oriented.convert('RGBA') as rgba:
                                source = Image.new('RGB', rgba.size, 'white')
                                source.paste(rgba, mask=rgba.getchannel('A'))
                        else:
                            source = oriented.convert('RGB')
                    source.info.clear()
                yield media, source
        else:
            raise ReaderError('SOURCE_UNSUPPORTED')
    except ReaderError:
        raise
    except Exception:
        raise ReaderError('SOURCE_INVALID') from None
    finally:
        if source is not None:
            source.close()


def inspect_source(data: bytes) -> dict:
    """Validate format, resource bounds and active PDF content without OCR."""
    with _source(data) as (media, source):
        return {'media_type': media, 'page_count': source.page_count if media == 'application/pdf' else 1}


def _page(number, width, height):
    return {'page': number, 'width': width, 'height': height, 'status': 'UNREADABLE',
            'method': 'none', 'text': '', 'words': [], 'issues': []}


def _issue(page, code):
    if code not in page['issues']:
        page['issues'].append(code)


def _deadline(deadline):
    if time.monotonic() >= deadline:
        raise ReaderError('TOTAL_TIMEOUT')


def _available_languages():
    try:
        result = subprocess.run([pytesseract.pytesseract.tesseract_cmd, '--list-langs'],
                                capture_output=True, timeout=3, check=False)
        if result.returncode != 0:
            return set()
        return {line.strip() for line in result.stdout.decode('utf-8', errors='replace').splitlines()[1:]
                if re.fullmatch(r'[A-Za-z0-9_]+', line.strip())}
    except (OSError, subprocess.SubprocessError):
        return set()


def _normalized(rect, width, height):
    coords = [float(rect[0]) / width, float(rect[1]) / height, float(rect[2]) / width, float(rect[3]) / height]
    if not all(math.isfinite(value) for value in coords):
        raise ReaderError('WORD_GEOMETRY_INVALID')
    # Words partly outside the crop cannot safely identify a printed value.
    if min(coords) < -0.0001 or max(coords) > 1.0001 or coords[0] >= coords[2] or coords[1] >= coords[3]:
        raise ReaderError('WORD_GEOMETRY_INVALID')
    return [max(0.0, min(1.0, value)) for value in coords]


def _append_words(page, words, budget):
    chars = 0
    for word in words:
        text = word['text'].strip()
        if not text:
            continue
        cost = len(text) + (1 if page['words'] else 0)
        if (len(page['words']) >= MAX_WORDS_PER_PAGE or budget['words'] <= 0
                or chars + cost > MAX_TEXT_CHARS_PER_PAGE or cost > budget['chars']):
            _issue(page, 'TEXT_LIMIT_REACHED')
            break
        page['words'].append({**word, 'text': text})
        chars += cost; budget['chars'] -= cost; budget['words'] -= 1
    page['text'] = ' '.join(word['text'] for word in page['words'])


def _pdf_issues(document, page, result):
    if any(True for _ in page.annots() or ()):
        _issue(result, 'PDF_ANNOTATIONS_REVIEW_REQUIRED')
    if any(True for _ in page.widgets() or ()):
        _issue(result, 'PDF_FORM_REVIEW_REQUIRED')
    if document.xref_get_key(document.pdf_catalog(), 'OCProperties')[0] != 'null':
        _issue(result, 'PDF_LAYERS_REVIEW_REQUIRED')
    if any(item[0] == 'ignore-text' for item in page.get_bboxlog()):
        _issue(result, 'PDF_HIDDEN_TEXT_REVIEW_REQUIRED')


def _render_pdf(page):
    _dimensions(page.rect.width, page.rect.height, RENDER_SCALE)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE), alpha=False, annots=True)
    _dimensions(pixmap.width, pixmap.height)
    return Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)


def _ocr(image, result, language, deadline, budget):
    _deadline(deadline)
    available = _available_languages()
    if not available:
        raise ReaderError('OCR_ENGINE_UNAVAILABLE')
    if not set(language.split('+')) <= available:
        raise ReaderError('OCR_LANGUAGE_UNAVAILABLE')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ReaderError('TOTAL_TIMEOUT')
    try:
        raw = pytesseract.image_to_data(image, lang=language, output_type=pytesseract.Output.DICT,
                                       timeout=min(OCR_TIMEOUT_SECONDS, remaining))
    except pytesseract.TesseractNotFoundError:
        raise ReaderError('OCR_ENGINE_UNAVAILABLE') from None
    except pytesseract.TesseractError:
        raise ReaderError('OCR_FAILED') from None
    except RuntimeError:
        raise ReaderError('OCR_TIMEOUT') from None
    except Exception:
        raise ReaderError('OCR_FAILED') from None
    _deadline(deadline)
    def words():
        for index, text in enumerate(raw['text']):
            if not isinstance(text, str) or not text.strip():
                continue
            left, top, width, height = (float(raw[key][index]) for key in ('left', 'top', 'width', 'height'))
            confidence = float(raw['conf'][index])
            if not math.isfinite(confidence):
                raise ReaderError('OCR_FAILED')
            yield {'text': text, 'bbox': _normalized((left, top, left+width, top+height), image.width, image.height),
                   'confidence': max(0.0, min(1.0, confidence/100)) if confidence >= 0 else None}
    try:
        _append_words(result, words(), budget)
    except ReaderError:
        raise
    except Exception:
        raise ReaderError('OCR_FAILED') from None
    result['method'] = 'tesseract'
    result['status'] = 'OCR_CANDIDATE' if result['words'] else 'UNREADABLE'
    if not result['words']:
        _issue(result, 'NO_TEXT_FOUND')


def extract_source(data: bytes, *, language='jpn+eng') -> dict:
    """Return page/word evidence. ``complete`` is coverage, never correctness.

    Every OCR result and native text word still needs human confirmation before
    it is used as a fact. Unavailable pages remain in the result and do not pass.
    """
    if not isinstance(language, str) or len(language) > 64 or not re.fullmatch(r'[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*', language):
        raise ReaderError('OCR_LANGUAGE_INVALID')
    deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS
    budget = {'words': MAX_WORDS_TOTAL, 'chars': MAX_TEXT_CHARS_TOTAL}
    pages = []
    with _source(data) as (media, source):
        count = source.page_count if media == 'application/pdf' else 1
        for number in range(1, count+1):
            native = source.load_page(number-1) if media == 'application/pdf' else None
            result = _page(number, native.rect.width if native is not None else source.width,
                           native.rect.height if native is not None else source.height)
            pages.append(result)
            try:
                _deadline(deadline)
                if native is None:
                    _ocr(source, result, language, deadline, budget)
                    continue
                _pdf_issues(source, native, result)
                raw = native.get_text('words', sort=True)
                _deadline(deadline)
                if raw:
                    if native.get_image_info():
                        _issue(result, 'PDF_IMAGES_REVIEW_REQUIRED')
                    words = ({'text': item[4], 'bbox': _normalized(fitz.Rect(item[:4]) * native.rotation_matrix,
                                                                 native.rect.width, native.rect.height),
                              'confidence': None} for item in raw)
                    _append_words(result, words, budget)
                    result['status'], result['method'] = 'TEXT_EXTRACTED', 'pdf_text'
                    if not result['words']:
                        result['status'] = 'UNREADABLE'
                        _issue(result, 'NO_TEXT_FOUND')
                else:
                    with _render_pdf(native) as image:
                        _ocr(image, result, language, deadline, budget)
            except ReaderError as error:
                result['status'] = 'OCR_UNAVAILABLE' if error.code in {'OCR_ENGINE_UNAVAILABLE', 'OCR_LANGUAGE_UNAVAILABLE'} else 'UNREADABLE'
                _issue(result, error.code)
            except Exception:
                result['status'] = 'UNREADABLE'
                _issue(result, 'READ_FAILED')
    return {'schema_version': 1, 'page_count': len(pages),
            'complete': all(page['status'] in {'TEXT_EXTRACTED', 'OCR_CANDIDATE'} and not page['issues'] for page in pages),
            'pages': pages, 'issues': sorted({issue for page in pages for issue in page['issues']})}


def render_page(data: bytes, page: int) -> bytes:
    """Render one sanitized PNG in displayed orientation; never return active PDF."""
    with _source(data) as (media, source):
        count = source.page_count if media == 'application/pdf' else 1
        if type(page) is not int or not 1 <= page <= count:
            raise ReaderError('PAGE_OUT_OF_RANGE')
        output = BytesIO()
        if media == 'application/pdf':
            with _render_pdf(source.load_page(page-1)) as image:
                image.save(output, format='PNG')
        else:
            source.save(output, format='PNG')
        return output.getvalue()
