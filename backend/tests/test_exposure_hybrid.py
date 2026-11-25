import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine"))

from app.analysis import equipment, programs  # noqa: E402
from app.exposure_hybrid import (  # noqa: E402
    _in_detector_only_context,
    enrich_exposure_rows,
    enrich_functional_rows,
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

    def test_model_only_label_promoted_and_generic_noun_rejected(self):
        pages = [
            {
                "page": 1,
                "text": (
                    "Equipment Name: X-ray fluorescence spectrometer\n"
                    "Equipment Model: TrueX\n"
                    "Approved by: QC Stamp"
                ),
            }
        ]
        # Adversarial LLM returns generic noun in tipe_unit and real model in nomor_seri_unit.
        mock_records = [
            {
                "page": 1,
                "quote": "Equipment Model: TrueX",
                "facility_name": "",
                "facility_address": "",
                "merk_unit": "",
                "tipe_unit": "X-ray fluorescence spectrometer",
                "nomor_seri_unit": "TrueX",
                "merk_tabung": "",
                "tipe_tabung": "",
                "nomor_seri_tabung": "",
                "approval_quote": "Approved by: QC Stamp",
            }
        ]
        with patch("app.exposure_hybrid.llm.request_records", return_value=mock_records):
            records, warn = extract_exposure_llm(pages, {"tipe_unit", "nomor_seri_unit"})
        self.assertFalse(warn)
        self.assertEqual(records[0].get("tipe_unit"), "TrueX")
        self.assertNotIn("nomor_seri_unit", records[0])

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

    def test_functional_hybrid_recovers_commissioning_and_calibration_and_blocks_importer(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "commissioning.pdf"
            _make_pdf(
                pdf_path,
                [
                    "LAPORAN HASIL UJI PAPARAN RADIASI DAN UJI FUNGSI",
                    "Identitas Penguji",
                    "Nama Perusahaan/Importir: PT Mitra Teknik",
                    "Alat Ukur: Survey Meter Rex Smart / RSM-100S",
                    "Nomor Seri: SM-9911",
                    "Identitas Peralatan",
                    "Merek: LANScientific",
                    "Tipe/Model: TrueX G5",
                    "Nomor Seri: 1536367",
                ],
            )
            app = {
                "general": {"instansi": "PT Tuku Emas Indonesia", "alamat_proyek": "Jl. Sudirman 10"},
                "equipment": [
                    {
                        "merk_unit": "LANScientific",
                        "tipe_unit": "TrueX G5",
                        "nomor_seri_unit": "1536367",
                    }
                ],
            }
            doc = {"id": "doc-fn-1", "category": "fungsi", "filename": pdf_path.name}
            ref = {"general": app["general"], "equipment": app["equipment"]}
            mock_records = [
                {
                    "page": 1,
                    "quote": "Merek: LANScientific Tipe/Model: TrueX G5 Nomor Seri: 1536367",
                    "facility_name": "PT Mitra Teknik",
                    "facility_address": "",
                    "merk_unit": "LANScientific",
                    "tipe_unit": "TrueX G5",
                    "nomor_seri_unit": "1536367",
                    "merk_tabung": "",
                    "tipe_tabung": "",
                    "nomor_seri_tabung": "",
                    "approval_quote": "",
                }
            ]
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("app.exposure_hybrid.llm.request_records", return_value=mock_records),
            ):
                rows = equipment._functional(doc, app, ref)

        by_field = {r["field"]: r for r in rows}
        self.assertEqual(by_field["Alat 1: Merek Unit"]["observed"], "LANScientific")
        self.assertEqual(by_field["Alat 1: Merek Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["observed"], "TrueX G5")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: Nomor Seri Unit"]["observed"], "1536367")
        self.assertEqual(by_field["Alat 1: Nomor Seri Unit"]["status"], "MATCH")
        # Importer/contractor must NOT leak into Nama Fasilitas
        if "Nama Fasilitas" in by_field:
            self.assertNotEqual(by_field["Nama Fasilitas"]["observed"], "PT Mitra Teknik")

    def test_functional_llm_failure_marks_uncacheable(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "cal_cert.pdf"
            _make_pdf(pdf_path, ["Calibration Certificate", "Model: TrueX G5"])
            app = {
                "general": {"instansi": "PT Tuku Emas Indonesia"},
                "equipment": [{"merk_unit": "LANScientific", "tipe_unit": "TrueX G5", "nomor_seri_unit": "1536367"}],
            }
            doc = {"id": "doc-fn-err", "category": "fungsi", "filename": pdf_path.name}
            with patch("app.exposure_hybrid.llm.request_records", side_effect=TimeoutError("timeout")):
                _, warn = enrich_functional_rows(doc, app, str(pdf_path), [])
        self.assertTrue(warn)

    def test_facility_address_mismatch_vs_review_in_hybrid_and_supp(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "exposure_addr.pdf"
            _make_pdf(
                pdf_path,
                [
                    "LAPORAN UJI PAPARAN RADIASI",
                    "Alamat Lokasi: Jl. Mesjid Darul Falah No. 17, Petukangan Utara, Jakarta Selatan 12260",
                    "Alamat Sama: Jl. Tekno Raya Blok H1 No. 8, Kel. Setu, Kota Tangerang Selatan, Banten",
                    "Alamat Parsial: Jl. Tekno Raya No. 18, Setu, Kota Tangerang Selatan",
                    "Equipment Model: TrueX G5",
                ],
            )
            eq = [{"merk_unit": "LANScientific", "tipe_unit": "TrueX G5", "nomor_seri_unit": "1536367"}]
            app = {
                "general": {
                    "instansi": "PT Tuku Emas Indonesia",
                    "alamat_proyek": "Jl. Tekno Raya Blok H1 No. 8, Setu, Kota Tangerang Selatan, Banten 15314",
                },
                "equipment": eq,
            }

            # Case 1: enrich_exposure_rows marks distinct address as MISMATCH.
            raw_mismatch = {
                "rows": [
                    {
                        "field": "Alamat Fasilitas",
                        "expected": app["general"]["alamat_proyek"],
                        "observed": "",
                        "status": "REVIEW",
                    }
                ]
            }
            mock_diff = [
                {
                    "page": 1,
                    "quote": "Equipment Model: TrueX G5",
                    "facility_name": "",
                    "facility_address": "Jl. Mesjid Darul Falah No. 17, Petukangan Utara, Jakarta Selatan 12260",
                    "merk_unit": "",
                    "tipe_unit": "",
                    "nomor_seri_unit": "",
                    "merk_tabung": "",
                    "tipe_tabung": "",
                    "nomor_seri_tabung": "",
                    "approval_quote": "",
                }
            ]
            with patch("app.exposure_hybrid.llm.request_records", return_value=mock_diff):
                out_diff, _ = enrich_exposure_rows(
                    {"id": "doc-addr-1", "category": "paparan"}, app, str(pdf_path), raw_mismatch
                )
            self.assertEqual(out_diff["rows"][0]["status"], "MISMATCH")

            # Case 2: enrich_functional_rows marks matching address as MATCH and same-street different number as REVIEW.
            base_rows = [
                {
                    "field": "Alamat Fasilitas",
                    "expected": app["general"]["alamat_proyek"],
                    "observed": "",
                    "status": "REVIEW",
                }
            ]
            mock_match = [
                {
                    **mock_diff[0],
                    "facility_address": "Jl. Tekno Raya Blok H1 No. 8, Kel. Setu, Kota Tangerang Selatan, Banten",
                }
            ]
            mock_review = [
                {
                    **mock_diff[0],
                    "facility_address": "Jl. Tekno Raya No. 18, Setu, Kota Tangerang Selatan",
                }
            ]
            with patch("app.exposure_hybrid.llm.request_records", return_value=mock_match):
                out_match, _ = enrich_functional_rows(
                    {"id": "doc-addr-2", "category": "fungsi"}, app, str(pdf_path), base_rows
                )
            self.assertEqual(out_match[0]["status"], "MATCH")

            with patch("app.exposure_hybrid.llm.request_records", return_value=mock_review):
                out_review, _ = enrich_functional_rows(
                    {"id": "doc-addr-3", "category": "fungsi"}, app, str(pdf_path), base_rows
                )
            self.assertEqual(out_review[0]["status"], "REVIEW")

            # Case 3: programs._supp upgrades clearly distinct REVIEW Alamat Fasilitas to MISMATCH.
            supp_raw = {
                "rows": [
                    {
                        "field": "Alamat Fasilitas",
                        "expected": app["general"]["alamat_proyek"],
                        "observed": "Jl. Mesjid Darul Falah No. 8, Petukangan Utara, Jakarta Selatan 12260",
                        "status": "REVIEW",
                        "score": 25.0,
                        "evidence": [{"page": 1, "quote": "Jl. Mesjid Darul Falah"}],
                    }
                ]
            }
            with (
                patch("app.storage.file_path", return_value=pdf_path),
                patch("src.extraction.supplementary_matching.analyze", return_value=supp_raw),
                patch("app.exposure_hybrid.enrich_exposure_rows", return_value=(supp_raw, False)),
            ):
                supp_rows = programs._supp(
                    {"id": "doc-addr-4", "category": "paparan", "filename": pdf_path.name},
                    app,
                    {},
                )
            self.assertEqual(supp_rows[0]["status"], "MISMATCH")


if __name__ == "__main__":
    unittest.main()
