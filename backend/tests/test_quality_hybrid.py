import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine"))

from app import quality_hybrid  # noqa: E402


def _make_pdf(path: Path, lines: list[str]) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    for ln in lines:
        page.insert_text((50, y), ln, fontsize=11)
        y += 18
    doc.save(str(path))
    doc.close()


class QualityHybridTests(unittest.TestCase):
    def test_deterministic_quality_certificate_skips_llm_when_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "cal_cert_complete.pdf"
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
            doc = {"id": "doc-q-1", "category": "mutu", "filename": pdf_path.name}
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.quality_hybrid.llm.request_records") as mock_llm,
            ):
                rows = quality_hybrid.evaluate(doc, app, {})

        mock_llm.assert_not_called()
        by_field = {r["field"]: r for r in rows}
        self.assertEqual(by_field["Alat 1: Merek Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: Nomor Seri Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Tanggal Produksi"]["observed"], "2026-01-16")
        self.assertEqual(by_field["Tanggal Produksi"]["status"], "INFO")
        self.assertEqual(by_field["Tanggal Kalibrasi / Uji Mutu"]["observed"], "2026-01-22")
        self.assertEqual(by_field["Pengesahan"]["status"], "MATCH")
        # Tube fields absent on unit-only factory cert must not fabricate false mismatches.
        self.assertNotIn("Alat 1: Merek Tabung", by_field)
        self.assertNotIn("Alat 1: No. Seri Insersi Tabung", by_field)

    def test_llm_fallback_recovers_unstructured_layout_and_blocks_hallucination(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "unstructured_qc.pdf"
            _make_pdf(
                pdf_path,
                [
                    "FACTORY QUALITY CONTROL CERTIFICATE",
                    "Handheld XRF analyzer",
                    "Thermo Scientific   DXL 800   CD0719",
                    "Detector Model: RadEye  Detector S/N: 30456",
                    "Tested: 2023-04-12   QC01",
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
            doc = {"id": "doc-q-2", "category": "mutu", "filename": pdf_path.name}
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
                    "manufacture_date": "",
                    "calibration_date": "2023-04-12",
                    "approval_quote": "QC01",
                }
            ]
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.quality_hybrid.llm.request_records", return_value=mock_records),
            ):
                rows = quality_hybrid.evaluate(doc, app, {})

        by_field = {r["field"]: r for r in rows}
        self.assertEqual(by_field["Alat 1: Merek Unit"]["observed"], "Thermo Scientific")
        self.assertEqual(by_field["Alat 1: Merek Unit"]["status"], "REVIEW")
        self.assertIsNotNone(by_field["Alat 1: Merek Unit"]["score"])
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["observed"], "DXL 800")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["status"], "REVIEW")
        self.assertEqual(by_field["Alat 1: Nomor Seri Unit"]["observed"], "CD0719")
        self.assertEqual(by_field["Alat 1: Nomor Seri Unit"]["status"], "MATCH")
        # Hallucinated brand & detector traps rejected cleanly.
        self.assertNotIn("Alat 1: Merek Tabung", by_field)
        self.assertNotIn("Alat 1: Tipe Tabung", by_field)
        self.assertNotIn("Alat 1: No. Seri Insersi Tabung", by_field)

    def test_multi_equipment_selection_by_serial_and_llm_failure_uncacheable(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "multi_unit_qc.pdf"
            _make_pdf(
                pdf_path,
                [
                    "CERTIFICATE OF QUALITY",
                    "Manufacturer: Bruker",
                    "Model: S1 TITAN",
                    "Serial Number: SN-TITAN-2",
                ],
            )
            app = {
                "equipment": [
                    {"merk_unit": "Olympus", "tipe_unit": "Vanta C", "nomor_seri_unit": "SN-001"},
                    {"merk_unit": "Bruker", "tipe_unit": "S1 TITAN", "nomor_seri_unit": "SN-TITAN-2"},
                ]
            }
            doc = {"id": "doc-q-multi", "category": "mutu", "filename": pdf_path.name}
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.quality_hybrid.llm.request_records", side_effect=TimeoutError("timeout")),
            ):
                rows = quality_hybrid.evaluate(doc, app, {})

        self.assertTrue(doc.get("_uncacheable"))
        by_field = {r["field"]: r for r in rows}
        self.assertIn("Alat 2: Merek Unit", by_field)
        self.assertEqual(by_field["Alat 2: Merek Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 2: Nomor Seri Unit"]["status"], "MATCH")
        self.assertNotIn("Alat 1: Merek Unit", by_field)


if __name__ == "__main__":
    unittest.main()
