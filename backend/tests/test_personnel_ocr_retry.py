"""Unit tests for adaptive personnel recipient OCR retry and blind VLM fallback."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import cv2
import numpy as np
from src.extraction.personnel_ocr_retry import (
    _box_bounds,
    _clean_crop_for_ocr,
    _has_ink,
    _tight_text_crop,
    retry_recipient,
)


def _blank_page(h: int = 600, w: int = 800) -> np.ndarray:
    return np.full((h, w, 3), 255, dtype=np.uint8)


class PersonnelOcrRetryTests(unittest.TestCase):
    def test_box_bounds_supports_scalar_and_polygon(self):
        self.assertEqual(_box_bounds([10, 20, 110, 55]), (10, 20, 110, 55))
        self.assertEqual(
            _box_bounds([[12, 22], [115, 22], [115, 58], [12, 58]]),
            (12, 22, 115, 58),
        )
        self.assertIsNone(_box_bounds([]))

    def test_clean_crop_removes_horizontal_rule_and_preserves_text_ink(self):
        crop = np.full((90, 420, 3), 255, dtype=np.uint8)
        cv2.putText(crop, "Juviandy", (90, 54), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 1.4, (20, 20, 20), 2)
        # Draw a full-width horizontal certificate rule touching the text baseline.
        cv2.line(crop, (5, 56), (415, 56), (10, 10, 10), 2)

        cleaned = _clean_crop_for_ocr(crop)
        self.assertIsNotNone(cleaned)
        assert cleaned is not None
        # The rule outside the text area should be gone (left and right edges remain white).
        self.assertGreater(int(np.min(cleaned[:, :16])), 240)
        self.assertGreater(int(np.min(cleaned[:, -16:])), 240)
        # Character strokes remain dark in the middle.
        self.assertLess(int(np.min(cleaned)), 40)

    def test_certificate_gap_skips_when_confident_ocr_exists(self):
        img = _blank_page()
        records = [
            {"text": "This is to certify that", "box": [180, 150, 620, 180], "confidence": 0.98},
            {"text": "Juviandy", "box": [280, 210, 520, 250], "confidence": 0.95},
            {"text": "Telah mengikuti pelatihan", "box": [150, 290, 650, 325], "confidence": 0.97},
        ]
        with (
            patch("pytesseract.image_to_string") as tess_mock,
            patch("app.protection.llm.transcribe_image_text") as vlm_mock,
        ):
            updated, unreadable = retry_recipient(img, records)
        self.assertFalse(unreadable)
        self.assertEqual(updated, records)
        tess_mock.assert_not_called()
        vlm_mock.assert_not_called()

    def test_certificate_gap_uses_layer1_agreement_without_calling_vlm(self):
        img = _blank_page()
        cv2.putText(img, "Budi", (300, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (15, 15, 15), 2)
        records = [
            {"text": "Dengan ini menyatakan bahwa", "box": [180, 140, 620, 170], "confidence": 0.97},
            {"text": "Telah mengikuti pelatihan", "box": [150, 290, 650, 325], "confidence": 0.97},
        ]
        with (
            patch("pytesseract.get_languages", return_value=["eng", "ind"]),
            patch("pytesseract.image_to_string", side_effect=["Budi Santoso", "budi santoso"]),
            patch("app.protection.llm.transcribe_image_text") as vlm_mock,
        ):
            updated, unreadable = retry_recipient(img, records)
        self.assertFalse(unreadable)
        vlm_mock.assert_not_called()
        self.assertEqual(updated[1]["text"], "Budi Santoso")
        self.assertEqual(updated[1]["engine"], "tesseract-recipient-retry")

    def test_certificate_gap_falls_back_to_vlm_and_replaces_garbled_fragment(self):
        img = _blank_page()
        cv2.putText(img, "Juviandy", (250, 240), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 1.4, (20, 20, 20), 2)
        cv2.line(img, (150, 245), (650, 245), (20, 20, 20), 2)
        records = [
            {"text": "This is to certify that", "box": [180, 140, 620, 175], "confidence": 0.97},
            {"text": "uv", "box": [320, 215, 370, 245], "confidence": 0.41},
            {"text": "Has participated in the training", "box": [150, 295, 650, 330], "confidence": 0.96},
        ]
        with (
            patch("pytesseract.get_languages", return_value=["eng", "ind"]),
            patch("pytesseract.image_to_string", side_effect=["uvy", "Juvx"]),
            patch("app.protection.llm.transcribe_image_text", return_value="Juviandy") as vlm_mock,
        ):
            updated, unreadable = retry_recipient(img, records)
        self.assertFalse(unreadable)
        vlm_mock.assert_called_once()
        self.assertEqual([r["text"] for r in updated], [
            "This is to certify that",
            "Juviandy",
            "Has participated in the training",
        ])
        self.assertEqual(updated[1]["engine"], "vlm-recipient-retry")
        self.assertEqual(updated[1]["confidence"], 0.92)

    def test_certificate_gap_rejects_boilerplate_vlm_output_and_flags_unreadable(self):
        img = _blank_page()
        cv2.putText(img, "Juviandy", (250, 240), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 1.4, (20, 20, 20), 2)
        records = [
            {"text": "This is to certify that", "box": [180, 140, 620, 175], "confidence": 0.97},
            {"text": "Telah mengikuti pelatihan", "box": [150, 295, 650, 330], "confidence": 0.96},
        ]
        with (
            patch("pytesseract.get_languages", return_value=["eng"]),
            patch("pytesseract.image_to_string", side_effect=["", ""]),
            patch("app.protection.llm.transcribe_image_text", return_value="This is to certify that"),
        ):
            updated, unreadable = retry_recipient(img, records)
        self.assertTrue(unreadable)
        self.assertEqual(updated, records)

    def test_label_value_gap_recovers_sib_or_assignment_recipient_and_skips_signer_or_blank(self):
        # 1. Non-signer Nama with dark ink on the right -> VLM fallback recovers name.
        img_with_ink = _blank_page()
        cv2.putText(img_with_ink, "Rudi Hartono", (290, 228), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.9, (20, 20, 20), 2)
        records = [
            {"text": "SURAT IZIN BEKERJA", "box": [200, 60, 560, 90], "confidence": 0.98},
            {"text": "Nama / Name", "box": [80, 205, 220, 232], "confidence": 0.96},
        ]
        with (
            patch("pytesseract.get_languages", return_value=["eng"]),
            patch("pytesseract.image_to_string", side_effect=["", ""]),
            patch("app.protection.llm.transcribe_image_text", return_value="Rudi Hartono") as vlm_mock,
        ):
            updated, unreadable = retry_recipient(img_with_ink, records)
        self.assertFalse(unreadable)
        vlm_mock.assert_called_once()
        self.assertEqual([r["text"] for r in updated], [
            "SURAT IZIN BEKERJA",
            "Nama / Name",
            "Rudi Hartono",
        ])

        # 2. Blank whitespace next to Nama -> no OCR/VLM call.
        blank_img = _blank_page()
        with patch("app.protection.llm.transcribe_image_text") as vlm_mock:
            updated_blank, unreadable_blank = retry_recipient(blank_img, records)
        self.assertFalse(unreadable_blank)
        self.assertEqual(updated_blank, records)
        vlm_mock.assert_not_called()

        # 3. Signer block above Nama -> skipped.
        signer_records = [
            {"text": "Yang bertanda tangan di bawah ini", "box": [80, 150, 420, 180], "confidence": 0.96},
            {"text": "Nama", "box": [80, 205, 160, 232], "confidence": 0.96},
        ]
        with patch("app.protection.llm.transcribe_image_text") as vlm_mock:
            updated_signer, unreadable_signer = retry_recipient(img_with_ink, signer_records)
        self.assertFalse(unreadable_signer)
        self.assertEqual(updated_signer, signer_records)
        vlm_mock.assert_not_called()

    def test_dose_report_is_skipped_immediately(self):
        img = _blank_page()
        records = [
            {"text": "EVALUASI DOSIS PEKERJA RADIASI", "box": [120, 60, 620, 90], "confidence": 0.98},
            {"text": "Nama", "box": [80, 150, 150, 180], "confidence": 0.95},
            {"text": "Hp(10)", "box": [320, 150, 400, 180], "confidence": 0.97},
        ]
        with (
            patch("pytesseract.image_to_string") as tess_mock,
            patch("app.protection.llm.transcribe_image_text") as vlm_mock,
        ):
            updated, unreadable = retry_recipient(img, records)
        self.assertFalse(unreadable)
        self.assertEqual(updated, records)
        tess_mock.assert_not_called()
        vlm_mock.assert_not_called()

    def test_tight_text_crop_and_has_ink_ignore_tilted_horizontal_rules(self):
        # 1. Wide 1200px crop with slightly tilted underline and centered cursive text -> isolates text cleanly.
        wide = np.full((120, 1200, 3), 255, dtype=np.uint8)
        cv2.line(wide, (20, 88), (1180, 94), (15, 15, 15), 2)
        cv2.putText(wide, "Juviandy", (490, 80), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 1.4, (20, 20, 20), 2)

        tight = _tight_text_crop(wide)
        self.assertLess(tight.shape[1], 500)
        self.assertGreater(tight.shape[1], 140)
        self.assertTrue(_has_ink(wide))

        # 2. Wide crop with ONLY a slightly tilted horizontal underline -> _has_ink is False.
        rule_only = np.full((120, 1200, 3), 255, dtype=np.uint8)
        cv2.line(rule_only, (20, 88), (1180, 94), (15, 15, 15), 2)
        self.assertFalse(_has_ink(rule_only))

    def test_vision_request_slot_does_not_block_behind_text_llm_slot(self):
        import os
        import tempfile
        from pathlib import Path
        from app.protection import llm

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.object(llm.storage, "ROOT", Path(tmpdir)),
                patch.dict(
                    os.environ,
                    {
                        "BAPETEN_LLM_MAX_CONCURRENT": "1",
                        "BAPETEN_LLM_QUEUE_WAIT": "1",
                        "BAPETEN_VISION_QUEUE_WAIT": "1",
                    },
                ),
            ):
                with llm.request_slot(wait_seconds=0):
                    # Text slot is saturated, yet vision slot acquires its own lock cleanly.
                    with self.assertRaises(RuntimeError):
                        with llm.request_slot(wait_seconds=0):
                            pass
                    acquired = False
                    with llm.vision_request_slot(wait_seconds=0):
                        acquired = True
                    self.assertTrue(acquired)
                    self.assertTrue((Path(tmpdir) / "locks" / "vision-llm.lock").is_file())


if __name__ == "__main__":
    unittest.main()
