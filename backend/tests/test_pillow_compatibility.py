"""Exercise image consumers with synthetic files; the OCR engine is a boundary."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz
from PIL import Image, UnidentifiedImageError

from app import document_intake, fire_photo_metadata


class PillowCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def assert_image_ocr(self, path: Path, size: tuple[int, int]):
        original = path.read_bytes()
        captured = []

        def recognize(image, *, lang):
            image.load()
            captured.append((image.mode, image.size, len(image.tobytes()), lang))
            return "synthetic OCR result"

        with patch.object(document_intake.pytesseract, "get_languages", return_value=["eng", "jpn"]), \
                patch.object(document_intake.pytesseract, "image_to_string", side_effect=recognize):
            result = document_intake._extract_image(path)

        self.assertEqual(captured, [("RGB", size, size[0] * size[1] * 3, "jpn")])
        self.assertEqual(result, ("synthetic OCR result", "image_ocr", 1, {"ocr_used": True, "ocr_pages": 1}))
        self.assertEqual(path.read_bytes(), original)

    def test_supported_photo_formats_preserve_original_and_metadata_shape(self):
        for image_format, suffix in (("JPEG", "jpg"), ("PNG", "png"), ("TIFF", "tiff"), ("WEBP", "webp")):
            with self.subTest(image_format=image_format):
                path = self.root / f"photo.{suffix}"
                Image.new("RGB", (120, 80), (90, 120, 150)).save(path, format=image_format)
                before = hashlib.sha256(path.read_bytes()).hexdigest()
                result = fire_photo_metadata.analyze_photo_file(path)
                self.assertEqual((result["image_width"], result["image_height"]), (120, 80))
                self.assertEqual(result["perceptual_hash"], "0000000000000000")
                self.assertIn("low_resolution", result["quality_flags"])
                self.assertIn("low_contrast_candidate", result["quality_flags"])
                self.assertEqual(result["analysis_version"], "photo-metadata-v1")
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_supported_image_formats_reach_ocr_as_loaded_rgb(self):
        for image_format, suffix in (("JPEG", "jpg"), ("PNG", "png"), ("TIFF", "tiff"), ("WEBP", "webp")):
            with self.subTest(image_format=image_format):
                path = self.root / f"input.{suffix}"
                Image.new("RGB", (64, 40), (120, 90, 60)).save(path, format=image_format)
                self.assert_image_ocr(path, (64, 40))

    def test_grayscale_palette_and_alpha_images_reach_ocr_as_rgb(self):
        for mode in ("L", "P", "RGBA"):
            with self.subTest(mode=mode):
                path = self.root / f"mode-{mode}.png"
                Image.new(mode, (32, 24)).save(path)
                self.assert_image_ocr(path, (32, 24))

    def test_exif_survives_reading_and_precise_gps_is_not_exposed(self):
        path = self.root / "exif.jpg"
        exif = Image.Exif()
        exif[271] = "Synthetic Camera"
        exif[272] = "Fixture 1"
        exif[274] = 6
        exif[36867] = "2026:10:28 12:34:56"
        exif[36881] = "+09:00"
        exif[34853] = {1: "N", 2: (35, 0, 0), 3: "E", 4: (139, 0, 0)}
        Image.new("RGB", (96, 64), "white").save(path, exif=exif)
        before = path.read_bytes()

        result = fire_photo_metadata.analyze_photo_file(path)

        self.assertEqual(result["camera_make"], "Synthetic Camera")
        self.assertEqual(result["camera_model"], "Fixture 1")
        self.assertEqual(result["orientation"], 6)
        self.assertEqual(result["exif_captured_at"].isoformat(), "2026-10-28T12:34:56+09:00")
        self.assertIs(result["exif_metadata"]["GPSInfoPresent"], True)
        self.assertNotIn("GPSInfo", result["exif_metadata"])
        self.assertEqual(path.read_bytes(), before)

    def test_dhash_gradient_direction_and_distance_remain_deterministic(self):
        ascending = Image.new("L", (9, 8))
        descending = Image.new("L", (9, 8))
        ascending.putdata([x * 25 for _y in range(8) for x in range(9)])
        descending.putdata([(8 - x) * 25 for _y in range(8) for x in range(9)])
        low = fire_photo_metadata.dhash_hex(ascending)
        high = fire_photo_metadata.dhash_hex(descending)
        self.assertEqual(low, "0000000000000000")
        self.assertEqual(high, "ffffffffffffffff")
        self.assertEqual(fire_photo_metadata.dhash_hex(descending.copy()), high)
        self.assertEqual(fire_photo_metadata.hamming_distance_hex(low, high), 64)

    def test_dark_flat_image_quality_flags_keep_their_meaning(self):
        image = Image.new("RGB", (100, 80), "black")
        brightness, contrast, sharpness, flags = fire_photo_metadata.quality_metrics(image)
        self.assertEqual((brightness, contrast, sharpness), (0.0, 0.0, 0.0))
        self.assertEqual(set(flags), {"low_resolution", "too_dark_candidate", "low_contrast_candidate", "low_sharpness_candidate"})

    def test_pdf_raster_pages_reach_ocr_via_pillow(self):
        path = self.root / "scan.pdf"
        with fitz.open() as document:
            document.new_page(width=200, height=100)
            document.new_page(width=100, height=200)
            document.save(path)
        captured = []

        def recognize(image, *, lang):
            image.load()
            captured.append((image.mode, image.size, lang))
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
            return f"page {len(captured)}"

        with patch.object(document_intake.pytesseract, "get_languages", return_value=["eng"]), \
                patch.object(document_intake.pytesseract, "image_to_string", side_effect=recognize):
            result = document_intake._extract_pdf(path, force_ocr=True)

        self.assertEqual(captured, [("RGB", (320, 160), "eng"), ("RGB", (160, 320), "eng")])
        self.assertEqual(result[:3], ("page 1\npage 2", "pdf_ocr", 2))
        self.assertEqual(result[3], {"ocr_used": True, "ocr_pages": 2, "ocr_page_limit": 20})

    def test_text_pdf_keeps_direct_extraction_without_ocr(self):
        path = self.root / "text.pdf"
        text = "Synthetic document with enough direct text for extraction."
        with fitz.open() as document:
            document.new_page().insert_text((40, 40), text)
            document.save(path)
        with patch.object(document_intake, "_ocr_image", side_effect=AssertionError("unexpected OCR")):
            result = document_intake._extract_pdf(path, force_ocr=False)
        self.assertIn(text, result[0])
        self.assertEqual(result[1:], ("pdf_text", 1, {"ocr_used": False}))

    def test_invalid_image_is_rejected_before_ocr(self):
        path = self.root / "invalid.png"
        path.write_bytes(b"synthetic invalid image")
        with patch.object(document_intake.pytesseract, "image_to_string") as recognize:
            with self.assertRaises(UnidentifiedImageError):
                document_intake._extract_image(path)
            recognize.assert_not_called()
        with self.assertRaises(UnidentifiedImageError):
            fire_photo_metadata.analyze_photo_file(path)


if __name__ == "__main__":
    unittest.main()
