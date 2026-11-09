"""Management checks must remain grounded in their own document and form category."""

import unittest
from app.management.service import build_rows
from app.management.extraction import culture_evidence
from src.extraction.form_administration import administration_from_table, extract_administration


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
        text = "Dokumen Program Proteksi No. Dokumen : PPR-001 Tanggal Dokumen : 19/07/2026 Dokumen Sistem Manajemen No. Dokumen : SM-002 Tanggal : 19/07/2026"
        self.assertEqual(extract_administration(text)["manajemen"]["number"], "SM-002")

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
        topics = culture_evidence([page(body, 7)])
        self.assertTrue(topics[0]["found"])
        self.assertFalse(topics[1]["found"])
        both = body.replace("Budaya keselamatan", "Budaya keselamatan dan budaya keamanan")
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


if __name__ == "__main__":
    unittest.main()
