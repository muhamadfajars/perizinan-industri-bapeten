import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine"))

from app.analysis import programs  # noqa: E402
from app.exposure_hybrid import (  # noqa: E402
    _in_detector_only_context,
    enrich_exposure_rows,
    evaluate_exposure_field,
    extract_exposure_llm,
    is_token_subset_model,
)


def _make_pdf(path: Path, lines: list[str]) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    for ln in lines:
        page.insert_text((50, y), ln, fontsize=11)
        y += 18
    doc.save(str(path))
    doc.close()


class ExposureHybridTests(unittest.TestCase):
    def test_token_subset_vs_suffix_mismatch(self):
        self.assertTrue(is_token_subset_model("DXL 800 Niton", "DXL 800"))
        self.assertTrue(is_token_subset_model("TrueX G5", "TrueX"))
        self.assertFalse(is_token_subset_model("E7894X", "E7894"))
        self.assertFalse(is_token_subset_model("DXL 800", "DXL 900 Niton"))

        st_brand, sc_brand, _ = evaluate_exposure_field(
            "merk_unit", "Thermo Fisher Scientific", "Thermo Scientific"
        )
        self.assertEqual(st_brand, "REVIEW")
        self.assertIsNotNone(sc_brand)
        self.assertTrue(70 <= sc_brand < 100)

        st_type, sc_type, _ = evaluate_exposure_field("tipe_unit", "DXL 800 Niton", "DXL 800")
        self.assertEqual(st_type, "REVIEW")
        self.assertIsNotNone(sc_type)
        self.assertTrue(60 <= sc_type < 100)

        st_suffix, _, _ = evaluate_exposure_field("tipe_unit", "E7894X", "E7894")
        self.assertEqual(st_suffix, "MISMATCH")

    def test_detector_context_guard_blocks_surveymeter(self):
        text = (
            "Thermo Scientific Portable XRF Analyzers\n"
            "Instrument Model: DXL 800    Detector Model: RadEye\n"
            "Instrument S/N: CD0719      Detector S/N: 30456\n"
            "Calibration Date: 5/5/2022\n"
        )
        self.assertTrue(_in_detector_only_context("RadEye", text))
        self.assertTrue(_in_detector_only_context("30456", text))
        self.assertFalse(_in_detector_only_context("DXL 800", text))
        self.assertFalse(_in_detector_only_context("CD0719", text))

    def test_oem_survey_certificate_hybrid_and_anti_contamination(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "rad_cert_unit.pdf"
            _make_pdf(
                pdf_path,
                [
                    "Thermo Scientific Portable XRF Analyzers",
                    "DXL Radiation Survey Certificate",
                    "Instrument Model: DXL 800      Detector Model: RadEye",
                    "Instrument S/N: CD0719        Detector S/N: 30456",
                    "Calibration Date: 5/5/2022",
                    "Conducted by: Yao Yanhong      Survey Date: 4/12/2023",
                    "Thermo Scientific  2 Radcliff Road Tewksbury MA 01876 USA",
                ],
            )
            app = {
                "general": {
                    "instansi": "Mulia Perbaikan Bergaransi",
                    "alamat_proyek": "Jl. Letnan Munandar Sekayu Musi Banyuasin",
                },
                "equipment": [
                    {
                        "merk_unit": "Thermo Fisher Scientific",
                        "tipe_unit": "DXL 800 Niton",
                        "nomor_seri_unit": "CD0719",
                        "merk_tabung": "Thermo Fisher Scientific",
                        "tipe_tabung": "XTube DXL 800 Niton",
                        "nomor_seri_tabung": "174943-04204",
                    }
                ],
            }
            doc = {"id": "doc-rad-1", "category": "paparan", "filename": pdf_path.name}
            ref = {"general": app["general"], "equipment": app["equipment"]}

            mock_llm_records = [
                {
                    "page": 1,
                    "quote": "Thermo Scientific Portable XRF Analyzers",
                    "facility_name": "Thermo Scientific",
                    "facility_address": "2 Radcliff Road Tewksbury MA 01876 USA",
                    "merk_unit": "Thermo Scientific",
                    "tipe_unit": "DXL 800",
                    "nomor_seri_unit": "CD0719",
                    "merk_tabung": "",
                    "tipe_tabung": "RadEye",
                    "nomor_seri_tabung": "30456",
                    "approval_quote": "Conducted by: Yao Yanhong",
                }
            ]

            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.exposure_hybrid.llm.request_records", return_value=mock_llm_records),
            ):
                rows = programs._supp(doc, app, ref)

        by_field = {r["field"]: r for r in rows}
        self.assertEqual(by_field["Alat 1: Merek unit"]["observed"], "Thermo Scientific")
        self.assertEqual(by_field["Alat 1: Merek unit"]["status"], "REVIEW")
        self.assertIsNotNone(by_field["Alat 1: Merek unit"]["score"])

        self.assertEqual(by_field["Alat 1: Tipe unit"]["observed"], "DXL 800")
        self.assertEqual(by_field["Alat 1: Tipe unit"]["status"], "REVIEW")
        self.assertIsNotNone(by_field["Alat 1: Tipe unit"]["score"])

        self.assertEqual(by_field["Alat 1: No. seri unit"]["observed"], "CD0719")
        self.assertEqual(by_field["Alat 1: No. seri unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: No. seri unit"]["score"], 100.0)

        self.assertNotIn("Alat 1: Tipe tabung", by_field)
        self.assertNotIn("Alat 1: No. seri insersi tabung", by_field)
        self.assertEqual(by_field["Alamat Fasilitas"]["observed"], "—")
        self.assertEqual(by_field["Nama Fasilitas"]["observed"], "—")

        self.assertEqual(by_field["Pengesahan"]["status"], "MATCH")
        self.assertEqual(by_field["Pengesahan"]["page"], 1)
        self.assertFalse(doc.get("_uncacheable"))

    def test_hallucinated_llm_values_are_rejected(self):
        pages = [{"page": 1, "text": "Commission Test\nEquipment Model: TrueX\nApproved by: QC"}]
        mock_records = [
            {
                "page": 1,
                "quote": "Equipment Model: TrueX",
                "facility_name": "PT Fiktif Sejahtera",
                "facility_address": "Jl. Palsu No 99",
                "merk_unit": "LANScientific",
                "tipe_unit": "TrueX",
                "nomor_seri_unit": "INVENTED-9999",
                "merk_tabung": "",
                "tipe_tabung": "",
                "nomor_seri_tabung": "",
                "approval_quote": "Approved by: QC",
            }
        ]
        with patch("app.exposure_hybrid.llm.request_records", return_value=mock_records):
            records, warn = extract_exposure_llm(
                pages, {"merk_unit", "tipe_unit", "nomor_seri_unit", "approval_quote"}
            )
        self.assertFalse(warn)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["tipe_unit"], "TrueX")
        self.assertNotIn("nomor_seri_unit", rec)
        self.assertNotIn("merk_unit", rec)
        self.assertNotIn("facility_name", rec)
        self.assertEqual(rec["approval_quote"], "Approved by: QC")

    def test_llm_skipped_when_deterministic_already_matched(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "complete_local.pdf"
            _make_pdf(pdf_path, ["Laporan Uji Paparan"])
            app = {
                "general": {"instansi": "RS Harapan", "alamat_proyek": "Jl. Merdeka 1"},
                "equipment": [{"merk_unit": "Philips", "tipe_unit": "Optima", "nomor_seri_unit": "SN1"}],
            }
            doc = {"id": "doc-ok", "category": "paparan", "filename": pdf_path.name}
            raw = {
                "rows": [
                    {"field": "Nama Fasilitas", "expected": "RS Harapan", "observed": "RS Harapan", "status": "MATCH"},
                    {"field": "Alamat Fasilitas", "expected": "Jl. Merdeka 1", "observed": "Jl. Merdeka 1", "status": "MATCH"},
                    {"field": "Alat 1: Merek unit", "expected": "Philips", "observed": "Philips", "status": "MATCH"},
                    {"field": "Alat 1: Tipe unit", "expected": "Optima", "observed": "Optima", "status": "MATCH"},
                    {"field": "Alat 1: No. seri unit", "expected": "SN1", "observed": "SN1", "status": "MATCH"},
                    {"field": "Pengesahan", "expected": "ttd", "observed": "Halaman 1", "status": "MATCH"},
                ]
            }
            with patch("app.exposure_hybrid.llm.request_records") as mock_llm:
                _, warn = enrich_exposure_rows(doc, app, str(pdf_path), raw)
            self.assertFalse(warn)
            mock_llm.assert_not_called()

    def test_llm_failure_marks_document_uncacheable(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "offline_test.pdf"
            _make_pdf(pdf_path, ["Laporan Uji Paparan", "Model: AlphaX"])
            app = {
                "general": {"instansi": "PT Contoh"},
                "equipment": [{"merk_unit": "Beta", "tipe_unit": "AlphaX", "nomor_seri_unit": "SN01"}],
            }
            doc = {"id": "doc-off", "category": "paparan", "filename": pdf_path.name}
            raw = {"rows": [{"field": "Nama Fasilitas", "expected": "PT Contoh", "observed": "", "status": "REVIEW"}]}
            with patch("app.exposure_hybrid.llm.request_records", side_effect=TimeoutError("timeout")):
                _, warn = enrich_exposure_rows(doc, app, str(pdf_path), raw)
        self.assertTrue(warn)

    def test_multi_equipment_selection_via_llm_serial(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "multi_eq.pdf"
            _make_pdf(
                pdf_path,
                [
                    "Radiation Protection Detection Report",
                    "Testing equipment: AT1123 Device ID: NJRS-562",
                    "Tested device model: TrueX Pro  Serial: SN-22222",
                    "Checked by: Supervisor",
                ],
            )
            app = {
                "general": {"instansi": "PT Industri Maju"},
                "equipment": [
                    {"merk_unit": "BrandA", "tipe_unit": "TrueX G5", "nomor_seri_unit": "SN-11111"},
                    {"merk_unit": "BrandB", "tipe_unit": "TrueX Pro", "nomor_seri_unit": "SN-22222"},
                ],
            }
            doc = {"id": "doc-multi", "category": "paparan", "filename": pdf_path.name}
            ref = {"general": app["general"], "equipment": app["equipment"]}
            mock_records = [
                {
                    "page": 1,
                    "quote": "Tested device model: TrueX Pro Serial: SN-22222",
                    "facility_name": "",
                    "facility_address": "",
                    "merk_unit": "",
                    "tipe_unit": "TrueX Pro",
                    "nomor_seri_unit": "SN-22222",
                    "merk_tabung": "",
                    "tipe_tabung": "",
                    "nomor_seri_tabung": "",
                    "approval_quote": "Checked by: Supervisor",
                }
            ]
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.exposure_hybrid.llm.request_records", return_value=mock_records),
            ):
                rows = programs._supp(doc, app, ref)
        fields = {r["field"]: r for r in rows}
        self.assertIn("Alat 2: Tipe unit", fields)
        self.assertEqual(fields["Alat 2: Tipe unit"]["status"], "MATCH")
        self.assertEqual(fields["Alat 2: No. seri unit"]["status"], "MATCH")
        self.assertNotIn("Alat 1: Tipe unit", fields)


if __name__ == "__main__":
    unittest.main()
