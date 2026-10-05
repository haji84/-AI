from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from PIL import ExifTags, Image, ImageFilter, ImageStat

from .settings import settings


ANALYSIS_VERSION = "photo-metadata-v1"
LOW_RESOLUTION_MIN_EDGE = 800
DARK_THRESHOLD = 35.0
BRIGHT_THRESHOLD = 220.0
LOW_CONTRAST_THRESHOLD = 18.0
LOW_SHARPNESS_THRESHOLD = 12.0
NEAR_DUPLICATE_MAX_DISTANCE = 6


def managed_document_path(storage_path: str) -> Path:
    root = Path(settings.storage_root).resolve()
    path = (root / storage_path).resolve()
    if path != root and root not in path.parents:
        raise ValueError("document path escapes managed storage")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    return path


def _clean_exif_value(value):
    if isinstance(value, bytes):
        return value[:256].hex()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, tuple):
        return [_clean_exif_value(x) for x in value]
    try:
        return str(value)
    except Exception:
        return None


def extract_exif(image: Image.Image) -> dict:
    raw = image.getexif()
    out: dict[str, object] = {}
    for tag_id, value in raw.items():
        name = ExifTags.TAGS.get(tag_id, str(tag_id))
        if name == "GPSInfo":
            # Keep no precise GPS coordinates in the generic profile.
            # A future controlled evidence workflow can explicitly opt in.
            out["GPSInfoPresent"] = True
            continue
        out[name] = _clean_exif_value(value)
    return out


def parse_exif_datetime(exif: dict) -> datetime | None:
    value = exif.get("DateTimeOriginal") or exif.get("DateTimeDigitized") or exif.get("DateTime")
    if not isinstance(value, str):
        return None
    try:
        naive = datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None

    offset = exif.get("OffsetTimeOriginal") or exif.get("OffsetTimeDigitized") or exif.get("OffsetTime")
    if isinstance(offset, str) and re.fullmatch(r"[+-]\d{2}:\d{2}", offset.strip()):
        try:
            return datetime.fromisoformat(naive.strftime("%Y-%m-%dT%H:%M:%S") + offset.strip())
        except ValueError:
            return None

    # Do not invent a timezone. Preserve the raw EXIF value in exif_metadata instead.
    return None


def dhash_hex(image: Image.Image) -> str:
    gray = image.convert("L").resize((9, 8))
    px = list(gray.getdata())
    bits = 0
    bit_no = 0
    for y in range(8):
        row = y * 9
        for x in range(8):
            if px[row + x] > px[row + x + 1]:
                bits |= 1 << bit_no
            bit_no += 1
    return f"{bits:016x}"


def hamming_distance_hex(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError:
        return None


def quality_metrics(image: Image.Image) -> tuple[float, float, float, list[str]]:
    gray = image.convert("L")
    stat = ImageStat.Stat(gray)
    brightness = float(stat.mean[0])
    contrast = float(stat.stddev[0])

    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_stat = ImageStat.Stat(edges)
    sharpness = float(edge_stat.stddev[0])

    flags: list[str] = []
    if min(image.size) < LOW_RESOLUTION_MIN_EDGE:
        flags.append("low_resolution")
    if brightness < DARK_THRESHOLD:
        flags.append("too_dark_candidate")
    if brightness > BRIGHT_THRESHOLD:
        flags.append("too_bright_candidate")
    if contrast < LOW_CONTRAST_THRESHOLD:
        flags.append("low_contrast_candidate")
    if sharpness < LOW_SHARPNESS_THRESHOLD:
        flags.append("low_sharpness_candidate")
    return brightness, contrast, sharpness, flags


def analyze_photo_file(path: Path) -> dict:
    with Image.open(path) as image:
        image.load()
        exif = extract_exif(image)
        brightness, contrast, sharpness, flags = quality_metrics(image)
        return {
            "image_width": int(image.width),
            "image_height": int(image.height),
            "orientation": int(exif["Orientation"]) if isinstance(exif.get("Orientation"), int) else None,
            "exif_captured_at": parse_exif_datetime(exif),
            "camera_make": str(exif.get("Make")).strip() if exif.get("Make") else None,
            "camera_model": str(exif.get("Model")).strip() if exif.get("Model") else None,
            "exif_metadata": exif,
            "perceptual_hash": dhash_hex(image),
            "brightness_score": round(brightness, 4),
            "contrast_score": round(contrast, 4),
            "sharpness_score": round(sharpness, 4),
            "quality_flags": flags,
            "analysis_version": ANALYSIS_VERSION,
        }
