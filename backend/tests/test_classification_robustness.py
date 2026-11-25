"""Upload classification must distinguish title evidence from misleading hints."""

import io
import unittest
from unittest.mock import patch

import pymupdf
from PIL import Image
from docx import Document
from app.classifier import classify_document, classify_by_content
from app.classification_reader import extract_document_text


class ClassificationRobustnessTests(unittest.TestCase):
    def test_personnel_subtype_follows_explicit_title_not_filename(self):
        with patch("app.classifier.extract_document_text", return_value="SURAT KETERANGAN KERJA"):
            result = classify_document("Sertifikat Pelatihan PPR.pdf", b"pdf")
        self.assertEqual(result["category"], "personel")
        self.assertEqual(result["subtype"], "Surat Penugasan / Keterangan Kerja")
        with patch("app.classifier.extract_document_text", return_value="SURAT KETERANGAN KERJA"):
            result2 = classify_document("Pengangkatan karyawan PPR.pdf", b"pdf")
        self.assertEqual(result2["category"], "personel")
        self.assertEqual(result2["subtype"], "Surat Penugasan / Keterangan Kerja")

    def test_training_certificate_is_not_its_management_course(self):
        text = "SERTIFIKAT PELATIHAN\nTelah mengikuti pelatihan PPR\fDAFTAR UNIT KOMPETENSI\nSISTEM MANAJEMEN"
        self.assertEqual(classify_by_content(text)[:2], ("personel", "Sertifikat Pelatihan"))
        self.assertIsNone(classify_by_content(text.split("\f")[1])[0])

    def test_same_page_training_and_work_permit_is_ambiguous(self):
        self.assertIsNone(
            classify_by_content(
                "SERTIFIKAT PELATIHAN\nTelah mengikuti pelatihan PPR\nIzin Bekerja Petugas Fasilitas Radiasi"
            )[0]
        )

    def test_ocr_uses_installed_configured_languages_and_retries_sparse_text(self):
        from app.classification_reader import ocr

        with (
            patch.dict("os.environ", {"BAPETEN_TESS_LANG": "ind+eng"}),
            patch(
                "app.classification_reader.pytesseract.get_languages", return_value=["eng", "ind"]
            ),
            patch(
                "app.classification_reader.pytesseract.image_to_string",
                side_effect=["", "SURAT IZIN BEKERJA PETUGAS"],
            ) as recognize,
        ):
            self.assertIn("IZIN BEKERJA", ocr(Image.new("RGB", (20, 20))))
        self.assertEqual(recognize.call_count, 2)
        self.assertEqual(recognize.call_args_list[0].kwargs["lang"], "ind+eng")
        self.assertEqual(recognize.call_args.kwargs["config"], "--psm 11")

    def test_english_radiation_survey_title(self):
        self.assertEqual(
            classify_by_content(
                "Thermo Scientific Portable XRF Analyzers\nDXL Radiation Survey Certificate"
            )[0],
            "paparan",
        )

    def test_misleading_filename_cannot_override_content(self):
        with patch(
            "app.classifier.extract_document_text", return_value="SISTEM MANAJEMEN KESELAMATAN"
        ) as read:
            result = classify_document("Program Proteksi.pdf", b"pdf")
        read.assert_called_once()
        self.assertEqual(result["category"], "unknown")

    def test_filename_hint_is_explicitly_unverified_when_content_has_no_title(self):
        with patch(
            "app.classifier.extract_document_text", return_value="Tidak ada judul yang dikenali"
        ):
            result = classify_document("Program Proteksi.pdf", b"pdf")
        self.assertEqual(result["layer"], 1)
        self.assertLess(result["confidence"], 0.9)
        self.assertIn("belum terkonfirmasi", result["reason"])

    def test_read_failure_does_not_trust_filename(self):
        result = classify_document("Program Proteksi.pdf", b"broken pdf")
        self.assertEqual(result["category"], "unknown")

    def test_form_references_do_not_compete_with_its_title(self):
        text = "FORMULIR PERMOHONAN\nNomor Registrasi: 123\nLingkup Kegiatan: Analisis\nInstansi: Klinik ABC\nPROGRAM PROTEKSI RADIASI\nSISTEM MANAJEMEN"
        self.assertEqual(classify_by_content(text)[0], "formulir")

    def test_cover_precedes_later_reference_headings(self):
        self.assertEqual(
            classify_by_content("PROGRAM PROTEKSI RADIASI\fSISTEM MANAJEMEN")[0], "proteksi"
        )
        self.assertIsNone(classify_by_content("PROGRAM PROTEKSI RADIASI\nSISTEM MANAJEMEN")[0])

    def test_bundle_of_personnel_types_requires_manual_choice(self):
        result = classify_by_content(
            "Izin Bekerja Petugas Fasilitas Radiasi\fSertifikat Kompetensi Petugas Proteksi Radiasi"
        )
        self.assertIsNone(result[0])
        self.assertIn("Beberapa jenis", result[2])

    def test_toc_and_body_mentions_are_not_titles(self):
        for text in (
            "DAFTAR ISI\nSistem Manajemen ..... 12",
            "2.1 SISTEM MANAJEMEN",
            "Mengacu pada PROGRAM PROTEKSI RADIASI yang berlaku",
        ):
            self.assertIsNone(classify_by_content(text)[0], text)

    def test_docx_table_cover_and_split_runs_are_read(self):
        doc = Document()
        cell = doc.add_table(rows=1, cols=1).cell(0, 0)
        paragraph = cell.paragraphs[0]
        paragraph.add_run("SISTEM MANA")
        paragraph.add_run("JEMEN KESELAMATAN")
        output = io.BytesIO()
        doc.save(output)
        text = extract_document_text("document.docx", output.getvalue())
        self.assertEqual(classify_by_content(text)[0], "manajemen")

    def test_native_header_does_not_hide_scan_on_later_page(self):
        doc = pymupdf.open()
        for _ in range(4):
            page = doc.new_page()
            page.insert_text((30, 30), "Header Instansi " * 12)
        png = io.BytesIO()
        Image.new("RGB", (400, 500), "white").save(png, format="PNG")
        page.insert_image(pymupdf.Rect(30, 80, 500, 750), stream=png.getvalue())
        with patch(
            "app.classification_reader.ocr", return_value="PROGRAM PROTEKSI RADIASI"
        ) as read:
            text = extract_document_text("scan.pdf", doc.tobytes())
        self.assertEqual(read.call_count, 1)
        self.assertEqual(classify_by_content(text)[0], "proteksi")
        doc.close()

    def test_ocr_is_bounded_and_tiff_supported(self):
        doc = pymupdf.open()
        for _ in range(12):
            doc.new_page()
        with patch("app.classification_reader.ocr", return_value="SCAN") as read:
            text = extract_document_text("scan.pdf", doc.tobytes())
        self.assertEqual(read.call_count, 3)
        self.assertEqual(len(text.split("\f")), 6)
        doc.close()

    def test_english_dose_rate_combined_report_and_equipment_calibration(self):
        self.assertEqual(
            classify_by_content(
                "Test Report\nTesting Type: Commission Test\nItem Name: Radiation protection detection"
            )[0],
            "paparan",
        )
        self.assertEqual(
            classify_by_content(
                "LAPORAN HASIL UJI PAPARAN RADIASI, DAN UJI FUNGSI/ UJI KOMISIONING PESAWAT SINAR-X"
            )[0],
            "fungsi",
        )
        self.assertEqual(
            classify_by_content(
                "LANScientific Co., Ltd.\nCalibration Certificate\nName of Product: Handheld XRF analyzer\nInstrument Serial number: 1536367"
            )[0],
            "kalibrasi",
        )
        self.assertEqual(
            classify_by_content("SERTIFIKAT UJI MUTU PERALATAN\nNomor Seri: SN-001")[0],
            "mutu",
        )
        self.assertEqual(
            classify_by_content("CERTIFICATE OF QUALITY\nModel: TrueX G5")[0],
            "mutu",
        )
        self.assertEqual(
            classify_by_content(
                "Calibration Certificate\nName of Product: Digital Surveymeter Dose Rate Meter\nSerial: SM-123"
            )[0],
            "kalibrasi",
        )
        self.assertIsNone(
            classify_by_content(
                "Untuk melampirkan sertifikat kalibrasi alat ukur, lihat bab 5."
            )[0]
        )
        image = io.BytesIO()
        Image.new("RGB", (10, 10)).save(image, format="TIFF")
        with patch("app.classification_reader.ocr", return_value="SURAT IZIN BEKERJA PETUGAS"):
            self.assertEqual(
                classify_by_content(extract_document_text("scan.tiff", image.getvalue()))[0],
                "personel",
            )

    def test_dosimetry_lhu_overrides_weak_lhu_hint_and_structural_fallback(self):
        lhu_text = (
            "LABORATORIUM TEKNOLOGI RADIASI\n"
            "Perihal : Laporan Hasil Uji\n"
            "LAPORAN HASIL UJI\n"
            "PEMANTAUAN DOSIS PERORANGAN DENGAN LENCANA TLD\n"
            "Periode Pemakaian : Februari - April 2026\n"
        )
        with patch("app.classifier.extract_document_text", return_value=lhu_text):
            res = classify_document("LHU 292932.pdf", b"pdf")
        self.assertEqual(
            (res["category"], res["subtype"], res["layer"]),
            ("personel", "Evaluasi Dosis / Zero Check", 2),
        )
        self.assertEqual(
            classify_by_content(
                "No. Urut | No. Lencana | Nama | Hp(10) | Hp(0,07)\n"
                "Periode Pemakaian : Mei - Juli 2026\nElemen TLD dibaca dengan TLD reader"
            )[:2],
            ("personel", "Evaluasi Dosis / Zero Check"),
        )
        # Statutory dose-limit citations mentioning Hp(10) and TLD without badge report fields stay None.
        self.assertIsNone(
            classify_by_content(
                "Berdasarkan PERKA BAPETEN No. 4/2013, NBD untuk Hp(10): 20 mSv/tahun untuk pemakai TLD."
            )[0]
        )
