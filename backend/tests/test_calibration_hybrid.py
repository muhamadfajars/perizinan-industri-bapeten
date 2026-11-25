import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine"))

from app import calibration_hybrid, classifier  # noqa: E402


def _make_pdf(path: Path, lines: list[str]) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    for ln in lines:
        page.insert_text((50, y), ln, fontsize=11)
        y += 18
    doc.save(str(path))
    doc.close()


def _make_framed_embedded_image_pdf(path: Path) -> bytes:
    """Create a landscape white page embedding a grey calibration card photo."""
    img = Image.new("RGB", (900, 1200), color=(215, 215, 220))
    draw = ImageDraw.Draw(img)
    draw.text((80, 120), "Calibration Certificate", fill=(20, 20, 20))
    draw.text((80, 220), "Manufacturer: LANScientific Co., Ltd.", fill=(20, 20, 20))
    draw.text((80, 280), "Model: TrueX G5", fill=(20, 20, 20))
    draw.text((80, 340), "Instrument Serial number: 1536367", fill=(20, 20, 20))
    img_buf = io.BytesIO()
    img.save(img_buf, format="JPEG", quality=95)

    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.insert_image(pymupdf.Rect(140, 20, 700, 575), stream=img_buf.getvalue())
    raw_bytes = doc.tobytes()
    doc.close()
    path.write_bytes(raw_bytes)
    return raw_bytes


class CalibrationHybridTests(unittest.TestCase):
    def test_full_unit_match_shows_only_matching_equipment_and_omits_dates_and_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "cal_complete.pdf"
            _make_pdf(
                pdf_path,
                [
                    "LANSCIENTIFIC CO.,LTD.",
                    "Calibration Certificate",
                    "Name of Product: Handheld XRF analyzer",
                    "Manufacturer: LANScientific Co., Ltd.",
                    "Model: TrueX G5",
                    "Instrument Serial number: 1536367",
                    "Manufacture Date: 2026-01-16",
                    "Calibration date: 2026-01-22",
                    "Approved: QC02",
                ],
            )
            app = {
                "equipment": [
                    {
                        "merk_unit": "LANScientific",
                        "tipe_unit": "TrueX G5",
                        "nomor_seri_unit": "1536367",
                        "merk_tabung": "LANScientific",
                        "tipe_tabung": "X-Tube G5",
                        "nomor_seri_tabung": "TUBE-999",
                    }
                ]
            }
            doc = {"id": "doc-cal-1", "category": "kalibrasi", "filename": pdf_path.name}
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.calibration_hybrid.llm.request_records") as mock_llm,
            ):
                rows = calibration_hybrid.evaluate(doc, app, {})

        mock_llm.assert_not_called()
        self.assertEqual(len(rows), 3)
        by_field = {r["field"]: r for r in rows}
        self.assertEqual(by_field["Alat 1: Merek Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: Nomor Seri Unit"]["status"], "MATCH")
        # Absent tube fields, dates, and approval must never be emitted for kalibrasi.
        self.assertNotIn("Alat 1: Merek Tabung", by_field)
        self.assertNotIn("Alat 1: Tipe Tabung", by_field)
        self.assertNotIn("Alat 1: No. Seri Insersi Tabung", by_field)
        self.assertNotIn("Tanggal Produksi", by_field)
        self.assertNotIn("Tanggal Kalibrasi / Uji Mutu", by_field)
        self.assertNotIn("Pengesahan", by_field)

    def test_partial_match_hides_review_and_mismatch_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "cal_partial.pdf"
            _make_pdf(
                pdf_path,
                [
                    "Calibration Certificate",
                    "Manufacturer: LANScientific Co., Ltd.",
                    "Model: TrueX",
                    "Instrument Serial number: 9999999",
                ],
            )
            app = {
                "equipment": [
                    {
                        "merk_unit": "LANScientific",
                        "tipe_unit": "TrueX G5",
                        "nomor_seri_unit": "1536367",
                    }
                ]
            }
            doc = {"id": "doc-cal-2", "category": "kalibrasi", "filename": pdf_path.name}
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.calibration_hybrid.llm.request_records") as mock_llm,
            ):
                rows = calibration_hybrid.evaluate(doc, app, {})

        mock_llm.assert_not_called()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["field"], "Alat 1: Merek Unit")
        self.assertEqual(rows[0]["status"], "MATCH")

    def test_zero_match_or_surveymeter_calibration_returns_single_info_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "cal_surveymeter.pdf"
            _make_pdf(
                pdf_path,
                [
                    "Calibration Certificate",
                    "Name of Product: Digital Surveymeter Dose Rate Meter",
                    "Manufacturer: Mirion Technologies",
                    "Model: RDS-31",
                    "Instrument Serial number: SM-12345",
                ],
            )
            app = {
                "equipment": [
                    {
                        "merk_unit": "LANScientific",
                        "tipe_unit": "TrueX G5",
                        "nomor_seri_unit": "1536367",
                    }
                ]
            }
            doc = {"id": "doc-cal-3", "category": "kalibrasi", "filename": pdf_path.name}
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.calibration_hybrid.llm.request_records") as mock_llm,
            ):
                rows = calibration_hybrid.evaluate(doc, app, {})

        mock_llm.assert_not_called()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["field"], "Data Peralatan")
        self.assertEqual(rows[0]["status"], "INFO")
        self.assertEqual(rows[0]["detail"], {"type": "calibration"})

    def test_multi_equipment_selection_by_serial_and_conflict_no_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "cal_multi.pdf"
            _make_pdf(
                pdf_path,
                [
                    "CALIBRATION CERTIFICATE",
                    "Manufacturer: Bruker",
                    "Model: S1 TITAN",
                    "Serial Number: SN-TITAN-2",
                ],
            )
            app = {
                "equipment": [
                    {"merk_unit": "Bruker", "tipe_unit": "S1 TITAN", "nomor_seri_unit": "SN-001"},
                    {"merk_unit": "Bruker", "tipe_unit": "S1 TITAN", "nomor_seri_unit": "SN-TITAN-2"},
                ]
            }
            doc = {"id": "doc-cal-4a", "category": "kalibrasi", "filename": pdf_path.name}
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.calibration_hybrid.llm.request_records") as mock_llm,
            ):
                rows = calibration_hybrid.evaluate(doc, app, {})

            mock_llm.assert_not_called()
            self.assertEqual(len(rows), 3)
            self.assertEqual([r["field"] for r in rows], [
                "Alat 2: Merek Unit",
                "Alat 2: Tipe Unit",
                "Alat 2: Nomor Seri Unit",
            ])

            # Conflicting serial must never guess Alat 1 or Alat 2 even if brand/model match.
            pdf_conflict = Path(tmp) / "cal_multi_other_sn.pdf"
            _make_pdf(
                pdf_conflict,
                [
                    "CALIBRATION CERTIFICATE",
                    "Manufacturer: Bruker",
                    "Model: S1 TITAN",
                    "Serial Number: SN-OTHER-999",
                ],
            )
            doc_conflict = {"id": "doc-cal-4b", "category": "kalibrasi", "filename": pdf_conflict.name}
            with (
                patch("app.storage.file_path", return_value=pdf_conflict),
                patch("app.calibration_hybrid.llm.request_records") as mock_llm2,
            ):
                conflict_rows = calibration_hybrid.evaluate(doc_conflict, app, {})

            mock_llm2.assert_not_called()
            self.assertEqual(len(conflict_rows), 1)
            self.assertEqual(conflict_rows[0]["status"], "INFO")

    def test_llm_fallback_recovers_unstructured_layout_and_keeps_only_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "cal_unstructured.pdf"
            _make_pdf(
                pdf_path,
                [
                    "CERTIFICATE OF CALIBRATION",
                    "Handheld XRF analyzer",
                    "Thermo Scientific   DXL 800   CD0719",
                    "Detector Model: RadEye  Detector S/N: 30456",
                    "Calibration Date: 2025-02-10   QC01",
                ],
            )
            app = {
                "equipment": [
                    {
                        "merk_unit": "Thermo Fisher Scientific",
                        "tipe_unit": "DXL 800 Niton",
                        "nomor_seri_unit": "CD0719",
                    }
                ]
            }
            doc = {"id": "doc-cal-5", "category": "kalibrasi", "filename": pdf_path.name}
            mock_records = [
                {
                    "page": 1,
                    "quote": "Thermo Scientific DXL 800 CD0719",
                    "merk_unit": "Thermo Scientific",
                    "tipe_unit": "DXL 800",
                    "nomor_seri_unit": "CD0719",
                    "merk_tabung": "Invented Brand",
                    "tipe_tabung": "RadEye",
                    "nomor_seri_tabung": "30456",
                }
            ]
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.calibration_hybrid.llm.request_records", return_value=mock_records),
            ):
                rows = calibration_hybrid.evaluate(doc, app, {})

        # Only Nomor Seri Unit is MATCH; REVIEW brand/model and hallucinated/detector tube fields stay hidden.
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["field"], "Alat 1: Nomor Seri Unit")
        self.assertEqual(rows[0]["observed"], "CD0719")
        self.assertEqual(rows[0]["status"], "MATCH")

    def test_framed_embedded_scan_ocr_and_optional_real_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "framed_cal.pdf"
            pdf_bytes = _make_framed_embedded_image_pdf(pdf_path)
            with patch(
                "app.classification_reader.ocr",
                side_effect=["", "Calibration Certificate\nManufacturer: LANScientific Co., Ltd.\nModel: TrueX G5\nInstrument Serial number: 1536367"],
            ):
                cls_res = classifier.classify_document("scan001.pdf", pdf_bytes)
            self.assertEqual(cls_res["category"], "kalibrasi")

        sample_pdf = Path(
            "/home/fajar/.gemini/antigravity/brain/3e8f103a-6e68-49d4-b489-6c9922d93636/.user_uploaded/media_1795576873272_0b5cb64e.pdf"
        )
        if sample_pdf.is_file():
            cls_real = classifier.classify_document("scan_kalibrasi.pdf", sample_pdf.read_bytes())
            self.assertEqual(cls_real["category"], "kalibrasi")
            self.assertEqual(cls_real["layer"], 2)

            doc = {"id": "doc-cal-real", "category": "kalibrasi", "filename": sample_pdf.name}
            app_match = {
                "equipment": [
                    {
                        "merk_unit": "LANScientific",
                        "tipe_unit": "TrueX G5",
                        "nomor_seri_unit": "1536367",
                    }
                ]
            }
            with (
                patch("app.storage.file_path", return_value=sample_pdf),
                patch("app.calibration_hybrid.llm.request_records") as mock_llm,
            ):
                rows_match = calibration_hybrid.evaluate(doc, app_match, {})
                app_none = {
                    "equipment": [
                        {
                            "merk_unit": "Olympus",
                            "tipe_unit": "Vanta C",
                            "nomor_seri_unit": "999888",
                        }
                    ]
                }
                rows_none = calibration_hybrid.evaluate(doc, app_none, {})

            mock_llm.assert_not_called()
            self.assertEqual(
                [(r["field"], r["status"]) for r in rows_match],
                [
                    ("Alat 1: Merek Unit", "MATCH"),
                    ("Alat 1: Tipe Unit", "MATCH"),
                    ("Alat 1: Nomor Seri Unit", "MATCH"),
                ],
            )
            self.assertEqual(len(rows_none), 1)
            self.assertEqual(rows_none[0]["status"], "INFO")

    def test_unreadable_ocr_marks_uncacheable_and_returns_review(self):
        doc = {"id": "doc-cal-empty", "category": "kalibrasi", "filename": "unreadable.pdf"}
        with (
            patch("app.storage.file_path", return_value=Path("/tmp/nonexistent.pdf")),
            patch("app.calibration_hybrid.read_exposure_pages", return_value=[]),
        ):
            rows = calibration_hybrid.evaluate(doc, {"equipment": []}, {})

        self.assertTrue(doc.get("_uncacheable"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["field"], "Sertifikat Kalibrasi")
        self.assertEqual(rows[0]["status"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
