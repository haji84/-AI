from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image

from .models import Document
from .settings import settings


PDF_PREVIEW_VERSION = "drawing-pdf-preview-v1"
PDF_BASE_SCALE = 2.0
PDF_MAX_DIMENSION = 2400


@dataclass(frozen=True)
class DrawingPreviewPage:
    page_no: int
    width: int
    height: int


def managed_document_path(document: Document) -> Path:
    root = Path(settings.storage_root).resolve()
    path = (root / document.storage_path).resolve()
    if path != root and root not in path.parents:
        raise ValueError("document path escapes managed storage")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("document file not found")
    return path


def _pdf_scale(rect: fitz.Rect) -> float:
    largest = max(float(rect.width), float(rect.height), 1.0)
    return max(
        0.1,
        min(PDF_BASE_SCALE, PDF_MAX_DIMENSION / largest),
    )


def pdf_preview_info(path: Path) -> list[DrawingPreviewPage]:
    with fitz.open(str(path)) as pdf:
        pages = []
        for index in range(pdf.page_count):
            page = pdf.load_page(index)
            rect = page.rect
            scale = _pdf_scale(rect)
            pages.append(
                DrawingPreviewPage(
                    page_no=index + 1,
                    width=max(1, int(round(rect.width * scale))),
                    height=max(1, int(round(rect.height * scale))),
                )
            )
        return pages


def render_pdf_page_png(
    path: Path,
    *,
    page_no: int,
) -> tuple[bytes, DrawingPreviewPage]:
    with fitz.open(str(path)) as pdf:
        if page_no < 1 or page_no > pdf.page_count:
            raise IndexError("drawing page out of range")
        page = pdf.load_page(page_no - 1)
        scale = _pdf_scale(page.rect)
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            alpha=False,
        )
        payload = pixmap.tobytes("png")
        info = DrawingPreviewPage(
            page_no=page_no,
            width=pixmap.width,
            height=pixmap.height,
        )
        return payload, info


def image_preview_info(path: Path) -> list[DrawingPreviewPage]:
    with Image.open(path) as image:
        return [
            DrawingPreviewPage(
                page_no=1,
                width=int(image.width),
                height=int(image.height),
            )
        ]


def preview_kind(document: Document) -> str:
    mime = (document.mime_type or "").lower()
    suffix = Path(document.original_filename or "").suffix.lower()
    if mime == "application/pdf" or suffix == ".pdf":
        return "pdf"
    if mime.startswith("image/") or suffix in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".tif",
        ".tiff",
        ".bmp",
    }:
        return "image"
    return "unsupported"
