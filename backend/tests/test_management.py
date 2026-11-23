"""Management checks must remain grounded in their own document and form category."""

import unittest
from app.management.service import build_rows
from app.management.extraction import culture_evidence
from app.analysis.reference import _to_form
from src.extraction.form_administration import (
    administration_documents_from_table,
    administration_from_table,
    extract_administration,
)


def page(text, number=1):
    return {"page": number, "text": text, "native_text": text, "has_visual": True}


class ManagementTests(unittest.TestCase):
    def test_management_number_uses_its_own_form_row(self):
        table = [
            ["1", "Dokumen Program Proteksi", "No. Dokumen : PPR-001 - Tanggal : 19/07/2026"],
            ["2", "Dokumen Sistem\\nManajemen", "No. Dokumen : SM-002 - Tanggal : 19/07/2026"],
        ]
        self.assertEqual(administration_from_table(table)["number"], "PPR-001")
        self.assertEqual(administration_from_table(table, "manajemen")["number"], "SM-002")
        table_with_header = [
            ["No", "Persyaratan", "Keterangan"],
            *table,
        ]
        docs = administration_documents_from_table(table_with_header)
        self.assertEqual(
            docs,
            [
                {
                    "document": "Dokumen Program Proteksi",
                    "number": "PPR-001",
                    "date": "19/07/2026",
                },
                {
                    "document": "Dokumen Sistem Manajemen",
                    "number": "SM-002",
                    "date": "19/07/2026",
                },
            ],
        )
        text = "Dokumen Program Proteksi No. Dokumen : PPR-001 Tanggal Dokumen : 19/07/2026 Dokumen Sistem Manajemen No. Dokumen : SM-002 Tanggal : 19/07/2026"
        extracted = extract_administration(text)
        self.assertEqual(extracted["manajemen"]["number"], "SM-002")
        self.assertEqual(extracted["manajemen"]["date"], "19/07/2026")
        form = _to_form({"general": {"instansi": "PT Contoh"}, "administration": extracted})
        self.assertEqual(form["managementDocument"], {"number": "SM-002", "date": "19/07/2026"})
        self.assertEqual(len(form["administrationDocuments"]), 2)

    def test_only_three_comparison_fields_and_missing_address_is_not_invented(self):
        rows = build_rows(
            "d",
            {
                "general": {"instansi": "PT Contoh", "alamat_proyek": "Jalan Contoh 1"},
                "administration": {
                    "manajemen": {"number": "SM-002"},
                    "proteksi": {"number": "PPR-001"},
                },
            },
            [page("Nomor: SM-002"), page("LEMBAR PENGESAHAN", 2)],
            [{"institution": "PT Contoh", "page": 1, "quote": "PT Contoh"}],
        )
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            [r["field"] for r in rows[:3]], ["Nama Instansi", "Alamat", "Nomor Dokumen"]
        )
        self.assertEqual(rows[0]["status"], "MATCH")
        self.assertEqual(rows[1]["status"], "REVIEW")
        self.assertIsNone(rows[1]["score"])
        self.assertEqual(rows[2]["status"], "MATCH")
        self.assertTrue(all(r["status"] == "INFO" and r["score"] is None for r in rows[3:]))
        self.assertEqual(rows[3]["detail"]["pages"], [2])
        self.assertTrue(all(r["detail"]["type"] == "management" for r in rows))

    def test_conflicting_numbers_are_review_and_absent_reference_is_info(self):
        rows = build_rows(
            "d",
            {"administration": {"manajemen": {"number": "SM-002"}}},
            [page("Nomor: SM-002"), page("Nomor: SM-003", 2)],
            [],
        )
        self.assertEqual(rows[2]["status"], "REVIEW")
        self.assertEqual(rows[0]["status"], "INFO")

    def test_culture_requires_explanation_not_toc_or_heading(self):
        topics = culture_evidence(
            [
                page("DAFTAR ISI\nBudaya Keselamatan dan Budaya Keamanan .... 7"),
                page("BAB 1\nBUDAYA KESELAMATAN DAN BUDAYA KEAMANAN", 2),
            ]
        )
        self.assertFalse(any(t["found"] for t in topics))
        body = (
            "Budaya keselamatan merupakan prioritas perusahaan. "
            + "Pelatihan pekerja dan pelaporan kejadian dilakukan secara berkala untuk memperbaiki proses keselamatan. "
            * 4
        )
        # Without dedicated chapter/subchapter heading, passing mentions are ignored
        self.assertFalse(any(t["found"] for t in culture_evidence([page(body, 7)])))
        self.assertFalse(any(t["found"] for t in culture_evidence([page("BAB IV PELATIHAN\n" + body, 7)])))

        # With dedicated chapter/subchapter heading, explanation is extracted
        safety_chapter = "BAB I BUDAYA KESELAMATAN\n" + body
        topics = culture_evidence([page(safety_chapter, 7)])
        self.assertTrue(topics[0]["found"])
        self.assertFalse(topics[1]["found"])

        both = (
            "BAB I BUDAYA KESELAMATAN DAN BUDAYA KEAMANAN\n"
            + body.replace("Budaya keselamatan", "Budaya keselamatan dan budaya keamanan")
        )
        self.assertTrue(all(t["found"] for t in culture_evidence([page(both, 8)])))

    def test_culture_sections_exclude_unrelated_chapters(self):
        explanation = (
            " merupakan prioritas perusahaan. "
            + "Prosedur diterapkan untuk menjaga keselamatan pekerja, pelaporan kejadian, dan pelatihan personel secara berkala. "
            * 4
        )
        text = (
            "2.4 Budaya Keselamatan\nBudaya keselamatan"
            + explanation
            + "\n2.5 Budaya Keamanan\nBudaya keamanan"
            + explanation
            + "\nBAB 3 KETENTUAN LAIN\nBudaya keselamatan"
            + explanation
        )
        topics = culture_evidence([page(text, 5), page("Budaya keamanan" + explanation, 6)])
        self.assertTrue(all(t["found"] for t in topics))
        self.assertTrue(all(e["page"] == 5 for t in topics for e in t["evidence"]))

    def test_number_mismatch_is_not_hidden(self):
        rows = build_rows(
            "d",
            {"administration": {"manajemen": {"number": "SM-002"}}},
            [page("Nomor: SM-003")],
            [],
        )
        self.assertEqual(rows[2]["status"], "MISMATCH")

    def test_chapter_culture_heading_across_subsections(self):
        body = (
            "BAB I\n"
            "BUDAYA KESELAMATAN DAN BUDAYA KEAMANAN\n"
            "1.1 Umum\n"
            "Berkaitan dengan budaya keselamatan dan budaya keamanan radiasi, PT Contoh memiliki Organisasi Proteksi Radiasi yang bertanggung jawab pada penyelenggaraan dan pengawasan keselamatan kerja radiasi, pencegahan paparan berlebih, serta pelatihan dan pelaporan kejadian secara berkelanjutan di seluruh fasilitas.\n"
            "1.2 Kebijakan\n"
            "Seluruh personel berkomitmen penuh menjaga kepatuhan operasional dan prosedur keamanan sumber radiasi.\n"
            "BAB II PENDEKATAN BERTINGKAT\n"
            "Uraian bab lain yang tidak termasuk budaya."
        )
        topics = culture_evidence([page(body, 5)])
        self.assertTrue(all(t["found"] for t in topics))
        self.assertTrue(all(t["evidence"][0]["page"] == 5 for t in topics))

    def test_roman_dot_subsection_culture_and_prose_address_extraction(self):
        from unittest.mock import patch
        from app.management.extraction import identities
        from app.protection.identity import ranked_identity_pages
        from app.protection.evidence import toc

        doc_pages = [
            page(
                "I.1. Pendahuluan\n"
                "Fasilitas PT Contoh berlokasi di Kawasan Industri Blok D, Kec. Timur, Kab. Baru.\n"
                "I.2. Budaya Keselamatan dan Keamanan\n"
                "Manajemen berkomitmen menerapkan budaya keselamatan dan/atau keamanan secara menyeluruh melalui "
                "pelatihan pekerja radiasi, komunikasi terbuka antar unit kerja, pelaporan insiden tanpa rasa takut "
                "akan sanksi, evaluasi berkala terhadap prosedur operasional, serta pengendalian akses yang ketat "
                "terhadap seluruh fasilitas dan sumber radiasi pengion agar keselamatan pekerja dan masyarakat "
                "tetap terjaga secara konsisten.\n"
                "I.3. Ruang Lingkup\n"
                "Pembahasan ruang lingkup operasional fasilitas secara umum.",
                5,
            ),
            page(
                "II.1. Kebijakan Lain\n"
                "Budaya keselamatan dan keamanan merupakan prioritas lain yang hanya disebut ulang pada bab kedua "
                "bersama berbagai rincian administrasi dan pengelolaan arsip perusahaan secara rutin setiap tahun.",
                12,
            ),
        ]
        topics = culture_evidence(doc_pages)
        self.assertTrue(all(t["found"] for t in topics))
        self.assertTrue(all(e["page"] == 5 for t in topics for e in t["evidence"]))

        with patch("app.protection.llm.extract", return_value=[]):
            recs, _ = identities(doc_pages)
        addrs = [r["project_address"] for r in recs if r.get("project_address")]
        self.assertIn("Kawasan Industri Blok D, Kec. Timur, Kab. Baru", addrs)

        ranked = ranked_identity_pages(
            [page("Ringkasan umum dokumen.", 1), doc_pages[0]],
            ["project_address"],
            toc_fn=toc,
        )
        self.assertEqual(ranked[0]["page"], 5)

        with patch("app.protection.llm.extract", return_value=[]) as mock_extract:
            recs_no_addr, _ = identities([page("PT CONTOH MANDIRI\nSISTEM MANAJEMEN FASILITAS", 1)])
        self.assertTrue(any(r.get("institution") for r in recs_no_addr))
        self.assertEqual(mock_extract.call_count, 1)

    def test_underscore_document_number_and_prose_institution(self):
        from unittest.mock import patch
        from app.management.extraction import identities

        doc_pages = [
            page(
                "DOKUMEN SISTEM MANAJEMEN\n"
                "No. Dokumen: HSE_GDL_009_Dokumen Sistem\n"
                "Manajemen_1.0_ID_IDN\n"
                "Versi dan Tanggal: 0.1 (12 Mei 2026)\n"
                "Direktur/Pimpinan PT DHI Excellence Logging\n"
                "Tanggal: 12 Mei 2026",
                1,
            ),
            page(
                "Dokumen ini merupakan dokumen resmi PT DHI EXCELLENCE LOGGING sebagai pihak yang bertanggung jawab dan pemohon izin.\n"
                "Pemeriksaan dilakukan oleh rumah sakit atau klinik yang ditunjuk.\n"
                "Doc Number: HSE_GDL_009_Dokumen Sistem Manajemen_1.0_ID_IDN Status: Initial draft",
                6,
            ),
        ]
        with patch("app.protection.llm.extract", return_value=[]):
            recs, _ = identities(doc_pages)
        insts = [r["institution"] for r in recs if r.get("institution")]
        self.assertIn("PT DHI Excellence Logging", insts)
        self.assertFalse(any("rumah sakit" in i.lower() for i in insts))

        rows = build_rows(
            "d",
            {
                "general": {"instansi": "PT DHI Excellence Logging"},
                "administration": {
                    "manajemen": {"number": "HSE_GDL_009_Dokumen Sistem Manajemen_1.0_ID_IDN"}
                },
            },
            doc_pages,
            recs,
        )
        num_row = next(r for r in rows if r["field"] == "Nomor Dokumen")
        self.assertEqual(num_row["status"], "MATCH")
        self.assertEqual(num_row["observed"], "HSE_GDL_009_Dokumen Sistem Manajemen_1.0_ID_IDN")
        inst_row = next(r for r in rows if r["field"] == "Nama Instansi")
        self.assertEqual(inst_row["status"], "MATCH")

        # Short base code on form vs full code with title/version suffix -> REVIEW (not MISMATCH 0%)
        from app.protection.matching import compare

        status, score, _ = compare(
            "HSE_GDL_009", "HSE_GDL_009_Dokumen Sistem Manajemen_1.0_ID_IDN", "number"
        )
        self.assertEqual(status, "REVIEW")
        self.assertGreater(score, 0)
        # Different trailing digit without separator must remain MISMATCH 0%
        self.assertEqual(compare("HSE_GDL_009", "HSE_GDL_0091", "number")[:2], ("MISMATCH", 0))


if __name__ == "__main__":
    unittest.main()
