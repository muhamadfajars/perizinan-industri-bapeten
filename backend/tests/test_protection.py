"""Protection rules use synthetic evidence, never private sample content."""

import unittest
from unittest.mock import patch
from app.protection.service import build_rows, make_row
from app.protection.evidence import information
from app.protection.extraction import grounded, metadata
from app.protection.matching import compare
from src.extraction.form_administration import administration_from_table
from src.extraction.technical_tables import parse_equipment_table


def page(text, number=1):
    return {"page": number, "text": text, "method": "text", "has_visual": True}


class ProtectionTests(unittest.TestCase):
    def test_administration_table_does_not_mix_management_and_protection(self):
        table = [
            ["No", "Persyaratan", "Keterangan"],
            [
                "1",
                "Dokumen Program\nProteksi dan Keselamatan\nRadiasi",
                "- No. Dokumen : PPR/01\n- Tanggal : 23/10/2026\nPengesahan\nDokumen",
            ],
            ["2", "Dokumen Sistem Manajemen", "- No. Dokumen : SM/02"],
        ]
        self.assertEqual(
            administration_from_table(table), {"number": "PPR/01", "date": "23/10/2026"}
        )

    def test_maximum_conditions_are_not_extracted_or_compared(self):
        table = [
            [
                "No",
                "Merk Unit",
                "Tipe / No Seri Unit",
                "Merk Tabung",
                "Tipe / No Seri Tabung",
                "Kondisi Maksimal",
            ],
            [
                "1",
                "Contoh",
                "Tipe: X\nNo Seri: U1",
                "Contoh",
                "Tipe: T\nNo Seri: T1",
                "50 kV / 200 µA",
            ],
        ]
        equipment = parse_equipment_table(table)
        self.assertTrue(equipment)
        self.assertNotIn("tegangan_maksimum_kv", equipment[0])
        self.assertNotIn("arus_maksimum_ma", equipment[0])
        rows = build_rows(
            "d",
            {"equipment": [{**equipment[0], "tegangan_maksimum_kv": 50, "arus_maksimum_ma": 0.2}]},
            [],
            {},
        )
        self.assertFalse(any("maksimum" in r["field"].lower() for r in rows))

    def test_mandatory_laws_always_displayed_without_matching(self):
        rows = information(
            [
                page(
                    "1.6 Dasar Hukum / Referensi\nUndang-Undang Nomor 10 Tahun 1997. PP No. 2 Tahun 2020."
                )
            ],
            lambda *args, **kwargs: make_row("d", *args, **kwargs),
        )
        laws = [r for r in rows if r["field"].startswith("Dasar hukum")]
        self.assertEqual(len(laws), 6)
        self.assertEqual(sum(r["detail"]["required"] for r in laws), 5)
        self.assertTrue(
            all(r["status"] == "INFO" and r["score"] is None and r["expected"] == "—" for r in laws)
        )
        self.assertIn("Belum ditemukan", laws[1]["observed"])

    def test_legal_references_are_scoped_and_only_include_regulations(self):
        rows = information(
            [
                page("DAFTAR ISI\n1.6 Dasar Hukum / Referensi ..... 8\nPP 28 Tahun 2025", 2),
                page("PP 28 Tahun 2025\n1.6 Dasar Hukum / Referensi\n1. UU 10 Tahun 1997", 8),
                page(
                    "2. PP 45 Tahun 2023\n3. Manual Book Portable XRF\nAcuan pengoperasian alat.\n4. PP 2 Tahun 2020",
                    9,
                ),
                page("1.7 Ketentuan lain\nPP 28 Tahun 2025", 10),
            ],
            lambda *args, **kwargs: make_row("d", *args, **kwargs),
        )
        laws = [r for r in rows if r["detail"]["group"] == "Dasar hukum"]
        self.assertEqual(laws[0]["detail"]["pages"], [8])
        self.assertEqual(laws[1]["detail"]["pages"], [9])
        self.assertFalse(laws[2]["detail"]["pages"])
        self.assertFalse(laws[-1]["detail"]["required"])
        self.assertIn("Nomor 2 Tahun 2020", laws[-1]["field"])
        self.assertFalse(any("Manual Book" in r["field"] for r in laws))

    def test_legal_section_numbers_can_vary(self):
        for heading in [
            "2.4 Dasar Hukum / Referensi",
            "3.2 Landasan Hukum",
            "Dasar Hukum",
            "B. Referensi",
        ]:
            rows = information(
                [page(heading + "\nUU 10 Tahun 1997\n3.3 Ketentuan lain\nPP 28 Tahun 2025")],
                lambda *args, **kwargs: make_row("d", *args, **kwargs),
            )
            self.assertEqual(rows[0]["detail"]["pages"], [1], heading)
            self.assertFalse(rows[2]["detail"]["pages"], heading)
            self.assertIn("tentang Ketenaganukliran", rows[0]["field"])

    def test_zone_sources_only_use_diagrams_and_approval_prefers_sheet(self):
        rows = information(
            [
                page("Penjelasan Daerah Pengendalian dan Daerah Supervisi", 12),
                page("Gambar 6. Pembagian Daerah Kerja", 44),
                page("Gambar 7. Pembagian Daerah Kerja", 45),
                page("LEMBAR PENGESAHAN\nDisetujui Oleh Direktur", 2),
                page("Petugas wajib memberikan tanda tangan pada formulir", 18),
            ],
            lambda *args, **kwargs: make_row("d", *args, **kwargs),
        )
        zones = [r for r in rows if r["field"].startswith("Daerah")]
        self.assertTrue(all(r["detail"]["pages"] == [44, 45] for r in zones))
        self.assertEqual(rows[-1]["detail"]["pages"], [2])

    def test_missing_legal_section_does_not_use_mentions_elsewhere(self):
        rows = information(
            [page("UU 10 Tahun 1997\nPP 45 Tahun 2023")],
            lambda *args, **kwargs: make_row("d", *args, **kwargs),
        )
        laws = [r for r in rows if r["detail"]["group"] == "Dasar hukum"]
        self.assertEqual(len(laws), 5)
        self.assertTrue(all(not r["detail"]["pages"] for r in laws))

    def test_approval_heading_does_not_certify_signature(self):
        rows = information(
            [page("LEMBAR PENGESAHAN\nDisetujui Oleh Direktur")],
            lambda *args, **kwargs: make_row("d", *args, **kwargs),
        )
        approval = rows[-1]
        self.assertEqual(approval["status"], "INFO")
        self.assertIn("stempel tidak diwajibkan", approval["note"])
        self.assertTrue(approval["detail"]["images"])
        self.assertEqual(approval["detail"]["pages"], [1])

    def test_toc_does_not_supply_content_evidence(self):
        rows = information(
            [page("DAFTAR ISI\nDaerah Pengendalian ..... 40\nNilai batas dosis 20 mSv ..... 45")],
            lambda *args, **kwargs: make_row("d", *args, **kwargs),
        )
        self.assertTrue(all(not r["detail"]["pages"] for r in rows))

    def test_ungrounded_llm_results_are_rejected(self):
        pages = [page("Nama: Budi\nJabatan: Operator")]
        records = [
            {"page": 1, "quote": "Nama: Budi", "name": "Budi", "role": "Dokter"},
            {"page": 8, "quote": "Nama: Budi", "name": "Budi"},
            {"page": 1, "quote": "Nama: Andi", "name": "Andi"},
        ]
        accepted = grounded(records, pages, "personnel")
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["name"], "Budi")
        self.assertNotIn("role", accepted[0])

    def test_equipment_pairs_and_conflicts_not_cherry_picked(self):
        app = {"equipment": [{"nomor_seri_unit": "UNIT-A", "nomor_seri_tabung": "TUBE-A"}]}
        records = {
            "equipment": [
                {
                    "nomor_seri_unit": "UNIT-A",
                    "nomor_seri_tabung": "TUBE-B",
                    "page": 1,
                    "quote": "UNIT-A TUBE-B",
                },
                {
                    "nomor_seri_unit": "UNIT-B",
                    "nomor_seri_tabung": "TUBE-A",
                    "page": 2,
                    "quote": "UNIT-B TUBE-A",
                },
            ]
        }
        rows = build_rows("d", app, [], records)
        tube = next(r for r in rows if r["field"] == "Alat 1: No. Seri Insersi Tabung")
        self.assertEqual(tube["status"], "MISMATCH")
        self.assertEqual(tube["observed"], "TUBE-B")
        records["equipment"].append(
            {
                "nomor_seri_unit": "UNIT-A",
                "nomor_seri_tabung": "TUBE-C",
                "page": 3,
                "quote": "UNIT-A TUBE-C",
            }
        )
        rows = build_rows("d", app, [], records)
        self.assertEqual(next(r for r in rows if r["field"] == tube["field"])["status"], "REVIEW")

    def test_only_institution_and_project_address_are_identity_references(self):
        app = {
            "general": {
                "instansi_asli": "PT Contoh",
                "alamat_instansi": "Jalan Kantor",
                "alamat_proyek": "Jalan Proyek",
            }
        }
        records = {
            "identity": [
                {
                    "institution": "PT Contoh",
                    "project_address": "Jalan Proyek",
                    "page": 1,
                    "quote": "PT Contoh Jalan Proyek",
                }
            ]
        }
        rows = build_rows("d", app, [], records)
        self.assertFalse(any(r["field"] == "Alamat Instansi / Kantor" for r in rows))
        self.assertEqual(next(r for r in rows if r["field"] == "Nama Instansi")["status"], "MATCH")
        self.assertEqual(
            next(r for r in rows if r["field"] == "Alamat")["status"],
            "MATCH",
        )
        self.assertEqual(
            [r["field"] for r in rows[:4]],
            ["Nama Instansi", "Alamat", "Nomor Dokumen", "Tanggal Dokumen"],
        )

    def test_dose_prefers_current_operating_statement_not_general_limits(self):
        from app.protection.dose import dose_statements

        statement = "PT Contoh saat ini berada pada Masa Operasi Tahap 1, sehingga pembatas dosis operasional yang digunakan adalah 6 mSv/tahun sebagai target pengendalian."
        pages = [
            page("Nilai Batas Dosis pekerja 20 mSv/tahun.", 6),
            page("Konstruksi menggunakan pembatas dosis sebesar 6 mSv/tahun.", 7),
            page(
                "Tahap berikutnya berdasarkan Q3. "
                + statement
                + " Evaluasi dilakukan setiap tahun.",
                32,
            ),
        ]
        found = dose_statements(pages)
        self.assertEqual(found[0], {"page": 32, "quote": statement})
        self.assertNotIn(6, [x["page"] for x in found])
        self.assertEqual(dose_statements([pages[0]]), [])

    def test_date_formats_and_name_variations(self):
        self.assertEqual(compare("23/10/2026", "23 Oktober 2026", "date")[0], "MATCH")
        self.assertEqual(compare("Siti Hermawati", "Siti Hermawan")[0], "REVIEW")
        self.assertEqual(compare("ABC123", "ABC128", "serial")[0], "MISMATCH")

    def test_missing_reference_is_display_only(self):
        self.assertEqual(make_row("d", "Nomor Dokumen", "", "PPR-1", [])["status"], "INFO")

    def test_scanned_date_is_not_hidden_by_native_header(self):
        evidence = {
            **page("PT Contoh\nTanggal Dibuat\n19/07/2026"),
            "native_text": "PT Contoh",
            "method": "ocr",
        }
        self.assertEqual(metadata([evidence])["date"][0]["value"], "19/07/2026")
        rows = build_rows(
            "d", {"administration": {"proteksi": {"date": "19/07/2026"}}}, [evidence], {}
        )
        self.assertEqual(
            next(r for r in rows if r["field"] == "Tanggal Dokumen")["status"], "MATCH"
        )
        self.assertEqual(next(r for r in rows if r["field"] == "Tanggal Dokumen")["score"], 100)

    def test_profession_match_is_separate_from_person_identity(self):
        rows = build_rows(
            "d",
            {"personnel": [{"nama": "Siti Hermawati", "keahlian_klasifikasi": "Operator"}]},
            [],
            {
                "personnel": [
                    {
                        "name": "Siti Hermawan",
                        "role": "Operator",
                        "page": 1,
                        "quote": "Siti Hermawan Operator",
                    }
                ]
            },
        )
        name = next(r for r in rows if r["field"].endswith(": Nama"))
        role = next(r for r in rows if r["field"].endswith(": Profesi / Keahlian"))
        self.assertEqual(name["status"], "REVIEW")
        self.assertGreater(name["score"], 80)
        self.assertEqual(role["status"], "MATCH")
        self.assertIn("tidak mengonfirmasi identitas", role["note"])
        self.assertEqual(name["detail"]["person_id"], role["detail"]["person_id"])

    def test_equivalent_roles_have_explicit_scores(self):
        self.assertEqual(
            compare("Operator", "Operator Alat XRF (Cabang A)", "role")[:2], ("MATCH", 95)
        )
        self.assertEqual(compare("Operator", "Operator", "role")[:2], ("MATCH", 100))
        status, score, _ = compare("Contoh Indonesia", "PT Contoh Indonesia", "institution")
        self.assertEqual(status, "MATCH")
        self.assertLess(score, 100)
        self.assertEqual(
            compare("PT Contoh Indonesia", "PT Contoh Indonesia", "institution")[:2], ("MATCH", 100)
        )
        self.assertEqual(
            compare(
                "PPR Analisis Menggunakan Sumber Radiasi Pengion",
                "Petugas Proteksi Radiasi (PPR)",
                "role",
            )[:2],
            ("MATCH", 90),
        )
        self.assertEqual(compare("PPR Analisis", "PPR Radiografi", "role")[0], "REVIEW")
        self.assertEqual(compare("Siti Aminah", "Siti Aminah")[:2], ("MATCH", 100))

    def test_similar_institution_and_address_but_not_other_outlet(self):
        status, score, _ = compare(
            "Mulia Perbaikan Bergaransi", "CV. MULIA PERBAIKAN GARANSI", "institution"
        )
        self.assertEqual(status, "MATCH")
        self.assertTrue(90 <= score < 100)
        address = "Jl. Mawar No. 12, Sekayu, Kabupaten Musi Banyuasin, Sumatera Selatan 30711"
        same = "Jalan Mawar No. 12, Sekayu, Kab. Musi Banyuasin, Sumatera Selatan 30711, Kab. Musi Banyuasin"
        self.assertEqual(compare(address, same, "address")[0], "MATCH")
        self.assertEqual(compare(address, address.replace("12", "15"), "address")[0], "REVIEW")
        self.assertEqual(
            compare(address, address.replace("Mawar", "Melati"), "address")[0], "REVIEW"
        )

    def test_other_location_records_are_not_supporting_information(self):
        records = {
            "personnel": [
                {"name": "Orang Lain", "role": "Operator", "page": 1, "quote": "Orang Lain"}
            ],
            "equipment": [{"nomor_seri_unit": "OTHER", "page": 2, "quote": "OTHER"}],
        }
        rows = build_rows("d", {}, [], records)
        self.assertFalse(any("tambahan / lokasi lain" in r["field"] for r in rows))
        supporting = [
            r for r in rows if r["detail"]["group"] in ("Dasar hukum", "Isi program", "Pengesahan")
        ]
        self.assertEqual(len(supporting), 9)
        self.assertTrue(all(r["status"] == "INFO" for r in supporting))

    def test_equivalent_date_spellings_do_not_create_conflict(self):
        rows = build_rows(
            "d",
            {"administration": {"proteksi": {"date": "19/07/2026"}}},
            [page("Date: 19/07/2026\nTanggal Dokumen: 19 Juli 2026")],
            {},
        )
        self.assertEqual(
            next(r for r in rows if r["field"] == "Tanggal Dokumen")["status"], "MATCH"
        )

    @patch("app.protection.extraction.llm.extract", side_effect=RuntimeError("offline"))
    @patch(
        "app.protection.extraction.table_records", return_value={"personnel": [], "equipment": []}
    )
    def test_offline_llm_keeps_warning_and_no_fabricated_value(self, tables, extract):
        from app.protection.extraction import extract_records

        records, warnings = extract_records("unused", [page("Nama perusahaan: Contoh")])
        self.assertFalse(records["identity"])
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
