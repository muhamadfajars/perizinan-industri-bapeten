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
        # Detailed administrative subdistrict/village in document should MATCH when core components agree
        form_addr = "JL. Raya Kebonsari , Kab. Pasuruan, Jawa Timur 67155"
        doc_addr = "Jl. Raya Kebonsari, Desa Legok-Gempol, Pasuruan 67155 Jawa Timur, Indonesia"
        status, score, reason = compare(form_addr, doc_addr, "address")
        self.assertEqual(status, "MATCH")
        self.assertGreaterEqual(score, 85)

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

    def test_document_number_ignores_prose_no_prefixes_and_word_slashes(self):
        pages = [
            page("No : 03/MG/X/2026\nNo. Komitmen/Kebijakan\nDalam kondisi normal. Karena itu\nnormal. 5", 1),
            page("Nomor: TEI – HO – QM – PPR - 001\nNon- Destructive test dan non-condensing\nnomor kontak. 6.2", 2),
        ]
        self.assertEqual([item["value"] for item in metadata([pages[0]])["number"]], ["03/MG/X/2026"])
        self.assertEqual(
            [item["value"] for item in metadata([pages[1]])["number"]],
            ["TEI – HO – QM – PPR - 001"],
        )

    def test_zone_diagram_confirmed_when_zone_described_earlier_on_same_or_previous_page(self):
        pages = [
            page(
                "Pembagian area meliputi Daerah Pengendalian di sekitar unit dan Daerah Supervisi "
                + ("yang dikendalikan selama pengoperasian alat XRF. " * 4)
                + "Gambar 3. Pembagian Daerah Kerja",
                44,
            ),
            page("Gambar 4. Pembagian Daerah Kerja Cabang B", 45),
        ]
        rows = information(pages, lambda *args, **kwargs: make_row("d", *args, **kwargs))
        zones = [r for r in rows if r["field"].startswith("Daerah")]
        self.assertEqual(len(zones), 2)
        for row in zones:
            self.assertFalse(row["detail"].get("review_required", False))
            self.assertEqual(row["detail"]["pages"], [44, 45])

    def test_import_approval_hybrid_llm_fallback_and_full_six_equipment_fields(self):
        from pathlib import Path
        from app.analysis.equipment import _import

        app = {
            "equipment": [
                {
                    "merk_unit": "LANScientific",
                    "tipe_unit": "TrueX G5",
                    "nomor_seri_unit": "1536367",
                    "merk_tabung": "Moxtek",
                    "tipe_tabung": "X-Ray Tube Magnum",
                    "nomor_seri_tabung": "25-82682",
                }
            ]
        }
        doc = {"id": "doc_imp", "filename": "Persetujuan Impor.pdf", "category": "impor"}

        complete_table = {
            "equipment": [
                {
                    "page": 2,
                    "merk_unit": "LANScientific",
                    "tipe_unit": "TrueX G5",
                    "nomor_seri_unit": "1536367",
                    "merk_tabung": "Moxtek",
                    "tipe_tabung": "X-Ray Tube Magnum",
                    "nomor_seri_tabung": "25-82682",
                    "raw_unit": "TrueX G5/1536367",
                    "raw_tabung": "X-Ray Tube Magnum / 25-82682",
                    "quote": "LANScientific | TrueX G5/1536367 | Moxtek | X-Ray Tube Magnum / 25-82682",
                    "needs_review": False,
                }
            ]
        }
        with (
            patch("app.analysis.equipment.storage.file_path", return_value=Path("impor.pdf")),
            patch("src.extraction.import_approval.parse_import_approval", return_value=complete_table),
            patch("app.protection.llm.extract") as llm_mock,
        ):
            rows = _import(dict(doc), app, {})
        llm_mock.assert_not_called()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r["status"] == "MATCH" and r["score"] == 100 for r in rows))
        self.assertTrue(any(r["field"] == "Alat 1: No. Seri Insersi Tabung" for r in rows))
        self.assertEqual(rows[0]["detail"]["type"], "import")
        self.assertEqual(rows[0]["detail"]["pages"], [2])

        source_text = (
            "LAMPIRAN I PERSETUJUAN IMPOR\n"
            "Spesifikasi Teknis Sumber Radiasi Pengion\n"
            "LANScientific TrueX G5 1536367 Moxtek X-Ray Tube Magnum 25-82682"
        )
        llm_record = {
            "page": 2,
            "quote": "LANScientific TrueX G5 1536367 Moxtek X-Ray Tube Magnum 25-82682",
            "merk_unit": "LANScientific",
            "tipe_unit": "TrueX G5",
            "nomor_seri_unit": "1536367",
            "merk_tabung": "Moxtek",
            "tipe_tabung": "X-Ray Tube Magnum",
            "nomor_seri_tabung": "25-82682",
        }
        with (
            patch("app.analysis.equipment.storage.file_path", return_value=Path("impor.pdf")),
            patch("src.extraction.import_approval.parse_import_approval", return_value={"equipment": []}),
            patch("app.protection.reader.read_document", return_value=([page(source_text, 2)], [])),
            patch("app.protection.extraction.table_records", return_value={"equipment": []}),
            patch("app.protection.llm.extract", return_value=[llm_record]) as llm_mock,
        ):
            rows = _import(dict(doc), app, {})
        llm_mock.assert_called_once()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r["status"] == "MATCH" for r in rows))

        failing_doc = dict(doc)
        with (
            patch("app.analysis.equipment.storage.file_path", return_value=Path("impor.pdf")),
            patch("src.extraction.import_approval.parse_import_approval", return_value={"equipment": []}),
            patch("app.protection.reader.read_document", return_value=([page(source_text, 2)], [])),
            patch("app.protection.extraction.table_records", return_value={"equipment": []}),
            patch("app.protection.llm.extract", side_effect=RuntimeError("offline")),
        ):
            rows = _import(failing_doc, app, {})
        self.assertTrue(failing_doc.get("_uncacheable"))
        self.assertTrue(all(r["status"] == "REVIEW" for r in rows))

    def test_grouped_personnel_and_combined_srp_tables(self):
        import tempfile
        from pathlib import Path
        import pymupdf
        from app.protection.extraction import table_records

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grouped_and_combined.pdf"
            with pymupdf.open() as pdf:
                def draw_table(p, y0, col_widths, row_h, rows):
                    xs = [30]
                    for w in col_widths:
                        xs.append(xs[-1] + w)
                    y_end = y0 + row_h * len(rows)
                    for x in xs:
                        p.draw_line((x, y0), (x, y_end))
                    for r_idx in range(len(rows) + 1):
                        y = y0 + r_idx * row_h
                        p.draw_line((xs[0], y), (xs[-1], y))
                    for r_idx, row in enumerate(rows):
                        y = y0 + r_idx * row_h
                        for c_idx, txt in enumerate(row):
                            p.insert_textbox(
                                pymupdf.Rect(xs[c_idx] + 3, y + 3, xs[c_idx + 1] - 3, y + row_h - 3),
                                txt,
                                fontsize=8,
                            )

                p1 = pdf.new_page()
                draw_table(
                    p1,
                    60,
                    [35, 160, 120, 100, 100],
                    32,
                    [
                        ["No", "Nama", "No. SIB", "Exam", "Valid Until"],
                        ["Operator Analisis", "Operator Analisis", "Operator Analisis", "Operator Analisis", "Operator Analisis"],
                        ["1", "Andika Akbar", "456346.425", "05 Jan 2025", "05 Jan 2030"],
                        ["PPR (Petugas Proteksi Radiasi)", "PPR (Petugas Proteksi Radiasi)", "PPR (Petugas Proteksi Radiasi)", "PPR (Petugas Proteksi Radiasi)", "PPR (Petugas Proteksi Radiasi)"],
                        ["1", "Erric Eka K", "414939.113", "07 Nov 2024", "07 Nov 2027"],
                    ],
                )
                p2 = pdf.new_page()
                draw_table(
                    p2,
                    60,
                    [30, 130, 130, 130, 100],
                    85,
                    [
                        ["No", "SRP XRF", "Personel", "Lokasi Pemanfaatan", "Alat Ukur"],
                        [
                            "1",
                            "Thermo Fisher Scientific, XL2 980 PLUS NITON/200286",
                            "1. Andika Akbar (Operator)\n2. Erric Eka K (PPR)",
                            "1. Project Batam Based.\n2. Kawasan Industri Kabil.\n3. XRF digunakan sesuai kebutuhan",
                            "Surveymeter SN 123",
                        ],
                    ],
                )
                pdf.save(path)
            pages = [
                page("LAMPIRAN 5: DAFTAR PERSONIL TEAM ANALISIS", 1),
                page("LAMPIRAN 6: DAFTAR PENGGUNA DAN ALAT KERJA XRF\nSRP XRF\nLokasi Pemanfaatan", 2),
            ]
            records = table_records(path, pages)

        self.assertTrue(
            any(r.get("name") == "Andika Akbar" and r.get("role") == "Operator Analisis" for r in records["personnel"])
        )
        self.assertTrue(
            any(r.get("name") == "Erric Eka K" and "PPR" in (r.get("role") or "") for r in records["personnel"])
        )
        self.assertTrue(
            any(r.get("name") == "Erric Eka K" and r.get("role") == "PPR" and r["page"] == 2 for r in records["personnel"])
        )
        equip = [r for r in records["equipment"] if r.get("nomor_seri_unit") == "200286"]
        self.assertEqual(len(equip), 1)
        self.assertEqual(equip[0].get("merk_unit"), "Thermo Fisher Scientific")
        self.assertEqual(equip[0].get("tipe_unit"), "XL2 980 PLUS NITON")
        self.assertIn("Kawasan Industri Kabil", equip[0].get("location", ""))
        self.assertNotIn("digunakan sesuai kebutuhan", equip[0].get("location", ""))

    def test_native_identity_rejects_prose_abbreviations_and_extracts_prose_location(self):
        from app.protection.extraction import native_identity

        pages = [
            page("RT I : Radiografer Tingkat I\nRT II : Radiografer Tingkat II\ngedung/fasilitas.\n• Evakuasi: Seluruh personel harus keluar.", 1),
            page("Lokasi penyimpanan PT Contoh\nberada di Jl. Hang Kesturi No. 5, Kawasan Industri Kabil Batam.", 20),
        ]
        recs = native_identity(pages)
        addrs = [r["project_address"] for r in recs if r.get("project_address")]
        self.assertEqual(len(addrs), 1)
        self.assertEqual(addrs[0], "Jl. Hang Kesturi No. 5, Kawasan Industri Kabil Batam")

    def test_metadata_extracts_header_control_code_with_rev_and_bare_tanggal(self):
        pages = [
            page(
                "PT CONTOH\nPM-HSE-08-PPKR-Rev 05\nPROGRAM PROTEKSI DAN KESELAMATAN RADIASI\nTanggal: 16-07-2026\nTanggal : 16 Juli 2026",
                1,
            ),
            page("PM-HSE-08-PPKR-R\nPROGRAM PROTEKSI DAN KESELAMATAN RADIASI", 4),
            page("PM-HSE-08-PRP-Rev 05\nPROGRAM PROTEKSI DAN KESELAMATAN RADIASI", 63),
            page("217299-11 / LT / RP / 06 / 2025\nPROGRAM PROTEKSI DAN KESELAMATAN RADIASI", 75),
        ]
        meta = metadata(pages, expected_number="PM-HSE-08-PPKR-Rev 05", expected_date="16/07/2026")
        self.assertEqual([n["value"] for n in meta["number"]], ["PM-HSE-08-PPKR-Rev 05"])
        self.assertEqual(len(meta["date"]), 1)
        self.assertEqual(compare("16/07/2026", meta["date"][0]["value"], "date")[0], "MATCH")

    def test_has_real_tube_cue_filters_generic_prose(self):
        from app.protection.extraction import _has_real_tube_cue

        self.assertFalse(_has_real_tube_cue("Pencatatan jam kerja tabung (X-ray tube log)."))
        self.assertFalse(_has_real_tube_cue("Bagian dalam ruangan radiography tempat tabung X-ray berada."))
        self.assertTrue(_has_real_tube_cue("No. Seri Insersi Tabung: S21693"))
        self.assertTrue(_has_real_tube_cue("Tabel X-Ray Tube dan Unit"))
        self.assertTrue(_has_real_tube_cue("XTube DXL 800 Niton"))

    def test_approval_prefers_bilingual_signature_sheet_over_prose_mentions(self):
        from app.protection.evidence import approval_evidence

        pages = [
            page(
                "DOKUMEN PROGRAM\n"
                "Disusun Oleh,\nErric Eka\nRadiation Protection Officer\n"
                "Diperiksa Oleh,\nUsman\nOperational Manager\n"
                "Disetujui Oleh,\nRaden Erwin\nDirector",
                1,
            ),
            page("Revisi perubahan nama PPR yang bertanggung jawab dalam lembar pengesahan", 4),
            page("Pimpinan mengesahkan perencanaan tersebut; manajer terkait menindaklanjuti.", 12),
        ]
        found = approval_evidence(pages)
        self.assertEqual([item["page"] for item in found], [1])

    def test_legal_section_keeps_lowercase_items_across_pages(self):
        pages = [
            page(
                "1.6 Referensi\n"
                "a) Undang-Undang Nomor 10 Tahun 1997 tentang Ketenaganukliran\n"
                "b) Peraturan Pemerintah Nomor 45 Tahun 2023",
                11,
            ),
            page(
                "c) Peraturan Pemerintah Nomor 28 Tahun 2025\n"
                "d) Peraturan BAPETEN Nomor 4 Tahun 2024\n"
                "f) Peraturan BAPETEN Nomor 5 Tahun 2025\n"
                "BAB II MANAJEMEN KESELAMATAN\nPP 2 Tahun 2020",
                12,
            ),
        ]
        rows = information(pages, lambda *args, **kwargs: make_row("d", *args, **kwargs))
        laws = [r for r in rows if r["detail"]["group"] == "Dasar hukum"]
        self.assertEqual(len(laws), 5)
        self.assertTrue(all(r["detail"]["pages"] for r in laws))

    def test_metadata_clusters_ocr_number_variants_and_keeps_genuine_conflicts(self):
        pages = [
            {
                "page": 1,
                "text": "DOKUMEN PROGRAM PROTEKSI\nNomor Dokumen: OO2/SIMPRG/PPR-QA/V/2026",
                "native_text": "",
                "method": "ocr",
                "has_visual": True,
            },
            {
                "page": 2,
                "text": "DOKUMEN PROGRAM PROTEKSI\nNomor Dokumen: 002/SIM/PRG/PPR-QA/V/2026",
                "native_text": "DOKUMEN PROGRAM PROTEKSI\nNomor Dokumen: 002/SIM/PRG/PPR-QA/V/2026",
                "method": "ocr",
                "has_visual": True,
            },
        ]
        meta = metadata(pages)
        self.assertEqual([n["value"] for n in meta["number"]], ["002/SIM/PRG/PPR-QA/V/2026"])

        conflict_pages = [
            page("DOKUMEN PROGRAM PROTEKSI\nNomor Dokumen: 001/SIM/PRG/2026", 1),
            page("DOKUMEN PROGRAM PROTEKSI\nNomor Dokumen: 002/SIM/PRG/2026", 2),
        ]
        conflict_meta = metadata(conflict_pages)
        self.assertEqual(
            sorted(n["value"] for n in conflict_meta["number"]),
            ["001/SIM/PRG/2026", "002/SIM/PRG/2026"],
        )

    def test_equipment_kv_tables_text_blocks_measuring_exclusion_and_serial_core_link(self):
        import os
        import tempfile
        import pymupdf
        from app.protection.extraction import extract_records, table_records

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_path = tmp.name
        try:
            doc = pymupdf.open()
            pg = doc.new_page(width=595, height=842)
            # Generic 3-col horizontal table (Merk + Tipe/No. Seri) without "Unit" in header
            y0, x_cols = 50, [40, 90, 220, 480]
            h_rows = [
                ["No", "Merk", "Tipe / No. Seri"],
                ["1", "Rigaku", "NEX CG / SN: RG-44556"],
            ]
            for r_i, vals in enumerate(h_rows):
                y_top, y_bot = y0 + r_i * 22, y0 + (r_i + 1) * 22
                for c_i, val in enumerate(vals):
                    rect = pymupdf.Rect(x_cols[c_i], y_top, x_cols[c_i + 1], y_bot)
                    pg.draw_rect(rect)
                    pg.insert_text((x_cols[c_i] + 4, y_top + 15), val, fontsize=9)
            # Vertical 2-col key-value specification table (without measuring tools)
            kv_y0, kv_x = 130, [40, 220, 480]
            kv_rows = [
                ["Parameter", "Nilai"],
                ["Merk", "Bruker"],
                ["Tipe", "S1 Titan"],
                ["No. Seri Unit", "BT-9001"],
                ["Tabung Sinar-X", ""],
                ["Merk", "Moxtek"],
                ["No. Seri", "MX-778"],
            ]
            for r_i, vals in enumerate(kv_rows):
                y_top, y_bot = kv_y0 + r_i * 20, kv_y0 + (r_i + 1) * 20
                for c_i, val in enumerate(vals):
                    rect = pymupdf.Rect(kv_x[c_i], y_top, kv_x[c_i + 1], y_bot)
                    pg.draw_rect(rect)
                    if val:
                        pg.insert_text((kv_x[c_i] + 4, y_top + 14), val, fontsize=9)
            # Measuring tool table that must be excluded
            m_y0, m_x = 300, [40, 140, 250, 360, 480]
            m_rows = [
                ["Alat", "Merk", "Tipe", "No. Seri"],
                ["Surveymeter", "Thermo", "RadEye", "11223"],
            ]
            for r_i, vals in enumerate(m_rows):
                y_top, y_bot = m_y0 + r_i * 20, m_y0 + (r_i + 1) * 20
                for c_i, val in enumerate(vals):
                    rect = pymupdf.Rect(m_x[c_i], y_top, m_x[c_i + 1], y_bot)
                    pg.draw_rect(rect)
                    pg.insert_text((m_x[c_i] + 4, y_top + 14), val, fontsize=9)
            doc.new_page(width=595, height=842)
            doc.save(pdf_path)
            doc.close()

            pages = [
                page("Data Pesawat Sinar-X\nMerk\nNo. Seri\nTipe\nSurveymeter", 1),
                page(
                    "Spesifikasi Pesawat Portable\n"
                    "Merk : Evident   Tipe : Vanta M   No. Seri : S/N 00EV33445\n"
                    "No. Seri Tabung : TB-8899\n"
                    "Lokasi Pemanfaatan : Site Morowali, Sulawesi Tengah\n\n\n\n"
                    "Merk Unit   Rigaku\n"
                    "Tipe Unit   NEX\n"
                    "No. Seri Unit   RG-9988\n\n\n\n"
                    "Daftar Alat Ukur\nMerk : Automess   Tipe : 6150AD   No. Seri : AM-999",
                    2,
                ),
            ]
            tbl = table_records(pdf_path, pages)
            serials_tbl = {r.get("nomor_seri_unit") for r in tbl["equipment"]}
            self.assertEqual(serials_tbl, {"RG-44556", "BT-9001"})
            bruker = next(r for r in tbl["equipment"] if r.get("nomor_seri_unit") == "BT-9001")
            self.assertEqual(bruker.get("merk_tabung"), "Moxtek")
            self.assertEqual(bruker.get("nomor_seri_tabung"), "MX-778")
            self.assertNotIn("11223", serials_tbl)

            with patch("app.protection.llm.extract", return_value=[]):
                recs, _ = extract_records(
                    pdf_path,
                    pages,
                    {
                        "identity": {"institution": "PT Uji", "project_address": "Morowali"},
                        "equipment": [
                            {
                                "merk_unit": "Evident",
                                "tipe_unit": "Vanta M",
                                "nomor_seri_unit": "EV33445",
                                "nomor_seri_tabung": "TB-8899",
                            }
                        ],
                    },
                )
            all_serials = {r.get("nomor_seri_unit") for r in recs["equipment"]}
            self.assertIn("S/N 00EV33445", all_serials)
            self.assertIn("RG-9988", all_serials)
            self.assertNotIn("AM-999", all_serials)

            rows = build_rows(
                "d",
                {
                    "equipment": [
                        {
                            "merk_unit": "Evident",
                            "tipe_unit": "Vanta M",
                            "nomor_seri_unit": "EV33445",
                            "nomor_seri_tabung": "TB-8899",
                        }
                    ]
                },
                pages,
                recs,
                semantic={"legal_sections": [], "dose": []},
            )
            merk_row = next(r for r in rows if r["field"] == "Alat 1: Merek Unit")
            self.assertEqual(merk_row["status"], "MATCH")
            self.assertEqual(merk_row["observed"], "Evident")
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    def test_legal_section_variants_and_semantic_alnum_grounding(self):
        from app.protection.semantic import recover

        pages = [
            page("1.2 Dasar Hukum\nMengacu pada regulasi keselamatan radiasi yang berlaku.\n1.3 Tujuan", 1),
            page(
                "II. Dasar Hukum dan Peraturan Perundang-undangan:\n"
                "1. Undang-Undang Nomor 10 Tahun 1997 tentang Ketenaganukliran\n"
                "2. Peraturan Pemerintah Nomor 45 Tahun 2023\n"
                "3. Peraturan Pemerintah Nomor 28 Tahun 2025\n"
                "4. Peraturan BAPETEN Nomor 4 Tahun 2024\n"
                "5. Peraturan BAPETEN Nomor 5 Tahun 2025\n"
                "BAB III ORGANISASI",
                4,
            ),
        ]
        rows = information(pages, lambda *args, **kwargs: make_row("d", *args, **kwargs))
        laws = [r for r in rows if r["detail"]["group"] == "Dasar hukum"]
        self.assertEqual(len(laws), 5)
        self.assertTrue(all(r["detail"]["pages"] == [4] for r in laws))

        raw_source = (
            "1.4 Acuan Peraturan:\n"
            "• Undang - Undang Nomor 10 Tahun 1997 tentang Ketenaganukliran dan Keselamatan.\n"
            "• Peraturan Pemerintah Nomor 45 Tahun 2023 tentang Keselamatan Radiasi."
        )
        normalized_quote = (
            "Undang-Undang Nomor 10 Tahun 1997 tentang Ketenaganukliran dan Keselamatan. "
            "Peraturan Pemerintah Nomor 45 Tahun 2023 tentang Keselamatan Radiasi."
        )
        with patch(
            "app.protection.llm.request_records",
            return_value=[{"page": 3, "category": "legal_section", "quote": normalized_quote}],
        ):
            ev, warnings = recover("laws", [page(raw_source, 3)])
        self.assertEqual(len(ev), 1)
        self.assertFalse(any("diabaikan" in w for w in warnings))

    def test_zone_text_fallback_prefers_zone_division_over_glossary_and_keeps_unconfirmed_diagrams(self):
        text_only_pages = [
            {
                "page": 2,
                "text": "Daftar Istilah\nDaerah Pengendalian adalah suatu daerah kerja tertentu.",
                "method": "text",
                "has_visual": False,
            },
            {
                "page": 3,
                "text": "Peta Lokasi Pabrik dan Fasilitas Umum",
                "method": "text",
                "has_visual": True,
            },
            {
                "page": 9,
                "text": (
                    "4.1 Pembagian Daerah Kerja\n"
                    "a. Daerah Pengendalian (Controlled Area): batas laju dosis > 3 mSv/tahun, dipasang tanda radiasi.\n"
                    "b. Daerah Pengawasan / Supervisi (Supervised Area): batas laju dosis > 1 mSv/tahun dan <= 3 mSv/tahun."
                ),
                "method": "text",
                "has_visual": False,
            },
        ]
        rows = information(
            text_only_pages,
            lambda *args, **kwargs: make_row("d", *args, **kwargs),
            semantic={"legal_sections": [], "dose": []},
        )
        ctrl = next(r for r in rows if r["field"] == "Daerah Pengendalian")
        supv = next(r for r in rows if r["field"] == "Daerah Pengawasan / Supervisi")
        self.assertEqual(ctrl["detail"]["pages"][0], 9)
        self.assertIn("3 mSv/tahun", ctrl["observed"])
        self.assertNotIn("Denah kandidat ditemukan", ctrl["observed"])
        self.assertFalse(ctrl["detail"].get("review_required"))
        self.assertEqual(supv["detail"]["pages"], [9])

        # Unconfirmed diagram candidate behavior must remain intact
        diag_pages = [
            {
                "page": 5,
                "text": "Denah Ruangan Fasilitas Utama",
                "method": "text",
                "has_visual": True,
            }
        ]
        diag_rows = information(
            diag_pages,
            lambda *args, **kwargs: make_row("d", *args, **kwargs),
            semantic={"legal_sections": [], "dose": []},
        )
        diag_ctrl = next(r for r in diag_rows if r["field"] == "Daerah Pengendalian")
        self.assertEqual(diag_ctrl["observed"], "Denah kandidat ditemukan; jenis daerah belum terkonfirmasi")
        self.assertTrue(diag_ctrl["detail"].get("review_required"))

    def test_dose_statements_handles_intro_bullets_kendala_and_rejects_nbd_only(self):
        from app.protection.dose import dose_statements

        pages = [
            page(
                "4.3 Penetapan Pembatas Dosis\n"
                "Pembatasan dosis saat beroperasi di fasilitas saat ini ditetapkan sebagai berikut.\n"
                "1. Pekerja radiasi: 5 mSv/tahun.\n"
                "2. Masyarakat umum: 0,5 mSv/tahun.\n"
                "Nilai batas dosis pekerja radiasi adalah 20 mSv/tahun.",
                7,
            )
        ]
        found = dose_statements(pages)
        self.assertTrue(found)
        self.assertIn("5 mSv/tahun", found[0]["quote"])
        self.assertNotIn("20 mSv/tahun", found[0]["quote"])

        kendala_pages = [
            page("Kendala dosis (dose constraint) untuk operasi saat ini sebesar 3 mSv/tahun.", 8)
        ]
        self.assertEqual(len(dose_statements(kendala_pages)), 1)

        nbd_only = [
            page(
                "Pembatas dosis harus tidak melampaui Nilai Batas Dosis pekerja radiasi sebesar 20 mSv/tahun.",
                9,
            )
        ]
        self.assertEqual(dose_statements(nbd_only), [])

        frac_nbd = [
            page("Penetapan pembatas dosis:\nPekerja radiasi 1/4 NBD (5 mSv/tahun).", 10)
        ]
        frac_found = dose_statements(frac_nbd)
        self.assertEqual(len(frac_found), 1)
        self.assertIn("5 mSv/tahun", frac_found[0]["quote"])

    def test_law_regex_variants_and_robust_legal_section_extraction(self):
        from app.protection.evidence import LAW, law_key, legal_section

        samples = [
            ("Perka BAPETEN Nomor 4 Tahun 2013", ("Perba", "4", "2013")),
            ("Perba BAPETEN No. 5 Tahun 2025", ("Perba", "5", "2025")),
            ("Peraturan Badan Pengawas Tenaga Nuklir (BAPETEN) Nomor 4 Tahun 2024", ("Perba", "4", "2024")),
            ("UU RI No. 10 Thn. 1997", ("UU", "10", "1997")),
            ("Undang – Undang Nomor 10 Tahun 1997 tentang Ketenaganukliran", ("UU", "10", "1997")),
            ("UU. No. 10 Tahun 1997", ("UU", "10", "1997")),
        ]
        for text, expected in samples:
            match = LAW.search(text)
            self.assertIsNotNone(match, text)
            self.assertEqual(law_key(*match.groups()), expected, text)

        for heading in ("I.2. Dasar Hukum", "BAB II DASAR HUKUM", "1.3 Dasar Hukum"):
            doc_pages = [
                page(
                    f"{heading}\n"
                    "1.3.1 Peraturan Nasional\n"
                    "A. Undang-Undang\n"
                    "UU RI No. 10 Thn. 1997\n"
                    "B. Peraturan Pemerintah\n"
                    "A. Peraturan Badan Pengawas Tenaga Nuklir\nNomor 4 Tahun 2024\n"
                    "C. Perba BAPETEN No. 5 Tahun 2025\n"
                    "I.3. Tujuan dan Ruang Lingkup\nPP No. 2 Tahun 2020",
                    3,
                )
            ]
            sec = legal_section(doc_pages)
            keys = {law_key(*m.groups()) for item in sec for m in LAW.finditer(item["text"])}
            self.assertIn(("UU", "10", "1997"), keys, heading)
            self.assertIn(("Perba", "4", "2024"), keys, heading)
            self.assertIn(("Perba", "5", "2025"), keys, heading)
            self.assertNotIn(("PP", "2", "2020"), keys, heading)

        inline_pages = [
            page(
                "Dasar Hukum : Undang-Undang Nomor 10 Tahun 1997 dan PP No. 45 Tahun 2023\n"
                "II. Tujuan\nPP No. 2 Tahun 2020",
                2,
            )
        ]
        inline_keys = {
            law_key(*m.groups()) for item in legal_section(inline_pages) for m in LAW.finditer(item["text"])
        }
        self.assertEqual(inline_keys, {("UU", "10", "1997"), ("PP", "45", "2023")})

        prose_pages = [
            page(
                "I.1. Pendahuluan\n"
                "Dokumen ini disusun untuk pemanfaatan sumber radiasi di PT Contoh.\n"
                "Penyusunan dokumen ini mengacu pada berbagai dasar hukum dan referensi yang berlaku, "
                "antara lain Undang-Undang Nomor 10 Tahun 1997 tentang Ketenaganukliran, "
                "Peraturan Pemerintah Nomor 45 Tahun 2023, dan Perka BAPETEN Nomor 4 Tahun 2013.\n"
                "I.2. Kebijakan Perusahaan\nPeraturan Pemerintah Nomor 28 Tahun 2025 dalam narasi lain.",
                5,
            )
        ]
        prose_sec = legal_section(prose_pages)
        prose_keys = {law_key(*m.groups()) for item in prose_sec for m in LAW.finditer(item["text"])}
        self.assertEqual(prose_keys, {("UU", "10", "1997"), ("PP", "45", "2023"), ("Perba", "4", "2013")})
        self.assertEqual(legal_section([page("UU 10 Tahun 1997 dan PP 45 Tahun 2023.", 1)]), [])

    def test_kv_personnel_extractor_and_zone_visual_attachment_and_header_logo_ocr_skip(self):
        import io
        import os
        import tempfile
        import pymupdf
        from PIL import Image
        from app.protection.extraction import _kv_personnel_records
        from app.protection.reader import read_document

        # 1. Non-table personnel KV blocks and bulleted lists
        pers_pages = [
            page(
                "Daftar Pekerja Radiasi:\n"
                "1. Budi Santoso (Petugas Proteksi Radiasi)\n"
                "- Ani Wijaya - Operator XRF\n\n\n\n"
                "Nama : Citra Dewi\n"
                "Jabatan : Pekerja Radiasi\n"
                "Lokasi : Site Morowali\n"
                "Nama Instansi : PT Uji Contoh",
                4,
            )
        ]
        recs = _kv_personnel_records(pers_pages)
        by_name = {r["name"]: r for r in recs}
        self.assertEqual(by_name["Budi Santoso"]["role"], "Petugas Proteksi Radiasi")
        self.assertEqual(by_name["Ani Wijaya"]["role"], "Operator XRF")
        self.assertEqual(by_name["Citra Dewi"]["role"], "Pekerja Radiasi")
        self.assertNotIn("PT Uji Contoh", by_name)

        # 2. Adjacent uncaptioned visual page linked when zone falls back to text
        zone_pages = [
            {
                "page": 9,
                "text": (
                    "4.1 Pembagian Daerah Kerja\n"
                    "Daerah Pengendalian ditetapkan pada area ruang penyinaran dengan laju dosis > 3 mSv/tahun.\n"
                    "Daerah Pengawasan ditetapkan di sekitar area kerja."
                ),
                "method": "text",
                "has_visual": False,
            },
            {
                "page": 10,
                "text": "Lampiran 3 — Tata Letak Fasilitas",
                "method": "text",
                "has_visual": True,
            },
        ]
        rows = information(
            zone_pages,
            lambda *args, **kwargs: make_row("d", *args, **kwargs),
            semantic={"legal_sections": [], "dose": []},
        )
        ctrl = next(r for r in rows if r["field"] == "Daerah Pengendalian")
        self.assertEqual(ctrl["detail"]["pages"], [9, 10])
        self.assertNotIn("Denah kandidat ditemukan", ctrl["observed"])
        self.assertFalse(ctrl["detail"].get("review_required"))

        # 3. Header-only logo (>8% page area) on readable native page skips OCR; body image still triggers OCR
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_path = tmp.name
        try:
            buf = io.BytesIO()
            Image.new("RGB", (400, 120), color=(20, 60, 120)).save(buf, format="PNG")
            img_bytes = buf.getvalue()
            doc = pymupdf.open()
            p1 = doc.new_page(width=595, height=842)
            # Header banner in top 15% of page (~14% area) + >=120 chars native text
            p1.insert_image(pymupdf.Rect(40, 20, 555, 135), stream=img_bytes)
            p1.insert_text(
                (40, 200),
                "Dokumen Program Proteksi dan Keselamatan Radiasi resmi PT Contoh\n"
                "untuk kegiatan analisis industri di lapangan dengan teks native yang lengkap dan jelas.",
                fontsize=11,
            )
            p2 = doc.new_page(width=595, height=842)
            # Body figure in middle of page (~15% area) + 150 chars native text (< 600)
            p2.insert_image(pymupdf.Rect(100, 260, 480, 460), stream=img_bytes)
            p2.insert_text((40, 120), "Teks pengantar singkat sebelum gambar tabel hasil pindai.", fontsize=11)
            doc.save(pdf_path)
            doc.close()

            with patch("app.protection.reader.subprocess.run") as mock_run:
                mock_run.return_value = type("Res", (), {"returncode": 0, "stdout": b"OCR text"})()
                read_pages, _ = read_document(pdf_path)
            self.assertEqual(read_pages[0]["method"], "text")
            self.assertEqual(read_pages[1]["method"], "ocr")
            self.assertEqual(mock_run.call_count, 1)
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    def test_table51_equipment_approval_date_prose_identity_and_absent_personnel_fastpath(self):
        from app.protection.extraction import _kv_equipment_records, extract_records, native_identity

        # 1. Approval table date on Lembar Pengesahan
        p1 = page(
            "LEMBAR PENGESAHAN\n"
            "Nomor dokumen : ALP-MNL-XRAY-001\n"
            "Tindakan   Nama   Jabatan   Tanda Tangan   Tanggal\n"
            "Disetujui\n"
            "Fery Faizal   FGM   18/09/2026\n"
            "oleh\n",
            1,
        )
        meta = metadata([p1], expected_number="ALP-MNL-XRAY-001", expected_date="18/09/2026")
        self.assertEqual(meta["date"][0]["value"], "18/09/2026")

        # 2. Prose org + location extraction without LLM
        p7 = page(
            "BAB I PENDAHULUAN\n"
            "PT ALP Petro Industry merupakan perusahaan yang berlokasi di Jl. Raya\n"
            "Kebonsari, Desa Legok, Kecamatan Gempol, Kabupaten Pasuruan, Provinsi Jawa\n"
            "Timur dengan bidang usaha yang meliputi Industri Minyak.",
            7,
        )
        ident = native_identity([p7])
        self.assertEqual(ident[0]["institution"], "PT ALP Petro Industry")
        self.assertIn("Jl. Raya Kebonsari", ident[0]["project_address"])

        # 3. Combined Tipe / nomor. seri unit & M54 / 24-76646 tube serial in KV layout
        p36 = page(
            "Tabel 5.1. Spesifikasi teknis peralatan\n"
            "Merek                      Rigaku\n"
            "Tipe / nomor. seri unit      NEX QC2450+\n"
            "Nomor seri tabung sinar-X    M54 / 24-76646\n",
            36,
        )
        eq = _kv_equipment_records([p36])
        self.assertEqual(len(eq), 1)
        self.assertEqual(eq[0]["merk_unit"], "Rigaku")
        self.assertEqual(eq[0]["tipe_unit"], "NEX QC2450+")
        self.assertEqual(eq[0]["nomor_seri_unit"], "QC2450+")
        self.assertEqual(eq[0]["tipe_tabung"], "M54")
        self.assertEqual(eq[0]["nomor_seri_tabung"], "24-76646")

        # 4. Absent personnel in document skips LLM completely
        app = {
            "general": {"instansi_asli": "PT ALP Petro Industry", "alamat_proyek": "Jl. Raya Kebonsari, Pasuruan"},
            "personnel": [{"nama": "Fani Priyo Kurniawan", "role": "Operator"}],
            "equipment": [{"merk_unit": "Rigaku", "tipe_unit": "NEX QC2450+", "nomor_seri_unit": "QC2450+", "tipe_tabung": "M54", "nomor_seri_tabung": "24-76646"}],
        }
        pages = [p1, p7, page("Operator harus mematuhi SOP proteksi radiasi.", 15), p36]
        with patch("app.protection.extraction.table_records", return_value={"personnel": [], "equipment": []}), patch(
            "app.protection.extraction.llm.extract", return_value=[]
        ) as llm_mock:
            _, warns = extract_records("unused", pages, app)
        self.assertNotIn("personnel", [c.args[0] for c in llm_mock.call_args_list])
        self.assertNotIn("identity", [c.args[0] for c in llm_mock.call_args_list])
        self.assertEqual(warns, [])


if __name__ == "__main__":
    unittest.main()
