"""Unit tests for hybrid deterministic + bounded Qwen evaluator (`spesifikasi`)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine"))

from app import specification_hybrid  # noqa: E402


def _make_pdf(path: Path, lines: list[str]) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    for ln in lines:
        page.insert_text((50, y), ln, fontsize=11)
        y += 18
    doc.save(str(path))
    doc.close()


class SpecificationHybridTests(unittest.TestCase):
    def test_deterministic_brochure_fast_path_and_conditional_omits_absent_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "brochure_udr.pdf"
            _make_pdf(
                pdf_path,
                [
                    "United Imaging Healthcare",
                    "Product Brochure",
                    "Model: uDR 566i",
                    "High-frequency digital radiography system.",
                ],
            )
            app = {
                "equipment": [
                    {
                        "merk_unit": "United Imaging Healthcare",
                        "tipe_unit": "uDR 566i",
                        "nomor_seri_unit": "SN-UNIT-99",
                        "merk_tabung": "Canon",
                        "tipe_tabung": "E7252X",
                        "nomor_seri_tabung": "SN-TUBE-88",
                    }
                ]
            }
            doc = {"id": "doc-spec-1", "category": "spesifikasi", "filename": pdf_path.name}
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.specification_hybrid.llm.request_records") as mock_llm,
            ):
                rows = specification_hybrid.evaluate(doc, app, {})

        mock_llm.assert_not_called()
        by_field = {r["field"]: r for r in rows}
        self.assertEqual(
            set(by_field.keys()),
            {"Alat 1: Merek Unit", "Alat 1: Tipe Unit"},
        )
        self.assertEqual(by_field["Alat 1: Merek Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["status"], "MATCH")
        self.assertNotIn("Alat 1: Nomor Seri Unit", by_field)
        self.assertNotIn("Alat 1: Merek Tabung", by_field)
        self.assertNotIn("_uncacheable", doc)

    def test_conditional_tube_fields_appear_when_evidenced_and_match_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "datasheet_tube.pdf"
            _make_pdf(
                pdf_path,
                [
                    "Technical Datasheet",
                    "Manufacturer: LANScientific",
                    "Instrument Model: TrueX G5",
                    "Tube Manufacturer: Moxtek",
                    "Tube Model: MAGNUM",
                ],
            )
            app = {
                "equipment": [
                    {
                        "merk_unit": "LANScientific",
                        "tipe_unit": "TrueX G5",
                        "nomor_seri_unit": "1536367",
                        "merk_tabung": "Moxtek",
                        "tipe_tabung": "MAGNUM",
                        "nomor_seri_tabung": "TUBE-001",
                    }
                ]
            }
            doc = {"id": "doc-spec-2", "category": "spesifikasi", "filename": pdf_path.name}
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.specification_hybrid.llm.request_records") as mock_llm,
            ):
                rows = specification_hybrid.evaluate(doc, app, {})

        mock_llm.assert_not_called()
        by_field = {r["field"]: r for r in rows}
        self.assertEqual(
            set(by_field.keys()),
            {
                "Alat 1: Merek Unit",
                "Alat 1: Tipe Unit",
                "Alat 1: Merek Tabung",
                "Alat 1: Tipe Tabung",
            },
        )
        self.assertEqual(by_field["Alat 1: Merek Tabung"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: Tipe Tabung"]["status"], "MATCH")

    def test_llm_fallback_recovers_unstructured_brochure_rejects_generic_nouns_and_handles_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "unstructured_brochure.pdf"
            _make_pdf(
                pdf_path,
                [
                    "CARE STREAM HEALTH PORTFOLIO",
                    "Handheld XRF Analyzer",
                    "Portable digital imaging module DRX-Plus with integrated X-Ray Tube XT-200.",
                ],
            )
            app = {
                "equipment": [
                    {
                        "merk_unit": "LANScientific",
                        "tipe_unit": "TrueX G5",
                        "merk_tabung": "Moxtek",
                        "tipe_tabung": "MAGNUM",
                    }
                ]
            }
            doc = {"id": "doc-spec-3", "category": "spesifikasi", "filename": pdf_path.name}
            llm_response = [
                {
                    "page": 1,
                    "quote": "Portable digital imaging module DRX-Plus with integrated X-Ray Tube XT-200.",
                    "merk_unit": "HallucinatedBrand",
                    "tipe_unit": "Handheld XRF Analyzer",  # generic noun -> rejected
                    "nomor_seri_unit": "",
                    "merk_tabung": "",
                    "tipe_tabung": "XT-200",
                    "nomor_seri_tabung": "",
                },
                {
                    "page": 1,
                    "quote": "Portable digital imaging module DRX-Plus",
                    "merk_unit": "",
                    "tipe_unit": "DRX-Plus",
                    "nomor_seri_unit": "",
                    "merk_tabung": "",
                    "tipe_tabung": "",
                    "nomor_seri_tabung": "",
                },
            ]
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.specification_hybrid.llm.request_records", return_value=llm_response) as mock_llm,
            ):
                rows = specification_hybrid.evaluate(doc, app, {})

        self.assertEqual(mock_llm.call_count, 1)
        by_field = {r["field"]: r for r in rows}
        self.assertNotIn("Alat 1: Merek Unit", by_field)  # HallucinatedBrand rejected by grounding
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["observed"], "DRX-Plus")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["status"], "MISMATCH")
        self.assertIn("terbaca Qwen", by_field["Alat 1: Tipe Unit"]["note"])
        self.assertEqual(by_field["Alat 1: Tipe Tabung"]["observed"], "XT-200")
        self.assertEqual(by_field["Alat 1: Tipe Tabung"]["status"], "MISMATCH")

        # Now verify graceful error handling marks _uncacheable=True and returns REVIEW row.
        doc_err = {"id": "doc-spec-err", "category": "spesifikasi", "filename": pdf_path.name}
        with tempfile.TemporaryDirectory() as tmp:
            pdf_err = Path(tmp) / "err.pdf"
            _make_pdf(pdf_err, ["Technical Specifications", "Some unmatched model"])
            with (
                patch("app.storage.file_path", return_value=pdf_err),
                patch("app.specification_hybrid.llm.request_records", side_effect=TimeoutError("timeout")),
            ):
                err_rows = specification_hybrid.evaluate(doc_err, app, {})
        self.assertTrue(doc_err.get("_uncacheable"))
        self.assertEqual(len(err_rows), 1)
        self.assertEqual(err_rows[0]["status"], "REVIEW")

    def test_multi_equipment_selection_picks_unique_match_and_returns_review_when_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "spec_multi.pdf"
            _make_pdf(
                pdf_path,
                [
                    "Siemens Healthineers",
                    "Ysio Max Digital Radiography",
                ],
            )
            equipments = [
                {"merk_unit": "GE", "tipe_unit": "Optima XR220"},
                {"merk_unit": "Siemens", "tipe_unit": "Ysio Max"},
            ]
            doc = {"id": "doc-spec-multi", "category": "spesifikasi", "filename": pdf_path.name}
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.specification_hybrid.llm.request_records") as mock_llm,
            ):
                rows = specification_hybrid.evaluate(doc, {"equipment": equipments}, {})
            mock_llm.assert_not_called()
            by_field = {r["field"]: r for r in rows}
            self.assertEqual(by_field["Alat 2: Merek Unit"]["status"], "MATCH")
            self.assertEqual(by_field["Alat 2: Tipe Unit"]["status"], "MATCH")

            # Duplicate matching equipment on form -> ambiguous -> single REVIEW row without guessing.
            ambiguous = [
                {"merk_unit": "Siemens", "tipe_unit": "Ysio Max"},
                {"merk_unit": "Siemens", "tipe_unit": "Ysio Max"},
            ]
            doc_amb = {"id": "doc-spec-amb", "category": "spesifikasi", "filename": pdf_path.name}
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.specification_hybrid.llm.request_records", return_value=[]),
            ):
                amb_rows = specification_hybrid.evaluate(doc_amb, {"equipment": ambiguous}, {})
            self.assertEqual(len(amb_rows), 1)
            self.assertEqual(amb_rows[0]["field"], "Pemilihan peralatan")
            self.assertEqual(amb_rows[0]["status"], "REVIEW")

    def test_unreadable_ocr_scan_marks_uncacheable_and_returns_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            blank_img = Path(tmp) / "blank_spec.png"
            Image.new("RGB", (200, 120), color=(255, 255, 255)).save(blank_img)
            doc = {"id": "doc-spec-blank", "category": "spesifikasi", "filename": blank_img.name}
            app = {"equipment": [{"merk_unit": "Siemens", "tipe_unit": "Ysio Max"}]}
            with (
                patch("app.storage.file_path", return_value=blank_img),
                patch("app.specification_hybrid.read_exposure_pages", return_value=[{"page": 1, "method": "OCR", "text": ""}]),
                patch("app.specification_hybrid.llm.request_records") as mock_llm,
            ):
                rows = specification_hybrid.evaluate(doc, app, {})
        mock_llm.assert_not_called()
        self.assertTrue(doc.get("_uncacheable"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["field"], "Spesifikasi Alat")
        self.assertEqual(rows[0]["status"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
