"""Regression checks for scan coverage, source windows and conservative matching."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pymupdf
from app.protection.reader import read_document
from app.protection.extraction import (
    native_identity,
    grounded,
    extract_records,
    metadata,
    table_records,
)
from app.protection.context import ranked_pages, adjacent_window
from app.protection.matching import compare, choose
from app.protection.identity import person_key, ranked_identity_pages
from app.protection.semantic import recover
from app.protection.evidence import information, toc
from app.protection import llm
from app.protection.service import evaluate as evaluate_protection, make_row
from app.management.extraction import culture_sections, identities
from app.management.service import evaluate as evaluate_management
from app import performance


def page(text, n=1, **extra):
    return {"page": n, "text": text, **extra}


class ReadingRobustnessTests(unittest.TestCase):
    @patch("app.protection.llm.extract", return_value=[])
    def test_missing_address_does_not_query_every_company_mention(self, extract):
        pages = [page("PT Contoh", 1)] + [
            page("PT Contoh telah mengalokasikan sumber daya.", n) for n in range(2, 8)
        ]
        records, _ = identities(pages)
        self.assertTrue(any(r.get("institution") == "PT Contoh" for r in records))
        self.assertEqual(extract.call_count, 1)
        self.assertEqual(extract.call_args.kwargs["only_fields"], ["project_address"])
        self.assertEqual([p["page"] for p in extract.call_args.args[1]], [1, 2])

    @patch.dict(os.environ, {"BAPETEN_TESS_LANG": "ind+eng", "BAPETEN_TESSERACT_CMD": "tesseract"})
    @patch("app.protection.reader.subprocess.run")
    def test_late_scan_with_long_native_header_gets_ocr(self, run):
        run.return_value = SimpleNamespace(
            returncode=0, stdout=b"RSUD Contoh\nGedung Melati Blok A", stderr=b""
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mixed.pdf"
            with pymupdf.open() as pdf:
                for _ in range(4):
                    p = pdf.new_page()
                    p.insert_textbox(
                        pymupdf.Rect(30, 20, 550, 180),
                        "Kop surat instansi untuk pengujian pembacaan dokumen. " * 5,
                    )
                pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200), False)
                pixmap.clear_with(255)
                p.insert_image(pymupdf.Rect(40, 200, 550, 750), stream=pixmap.tobytes("png"))
                pdf.save(path)
            pages, warnings = read_document(path)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(pages[3]["method"], "ocr")
        self.assertIn("Gedung Melati", pages[3]["text"])
        self.assertEqual(warnings, [])
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-l") + 1], "ind+eng")
        self.assertEqual(command[command.index("--psm") + 1], "3")

    def test_native_empty_does_not_hide_ocr_identity(self):
        records = native_identity(
            [page("RSUD Sentosa\nGedung Melati Blok A 12345", native_text="", method="ocr")]
        )
        self.assertEqual(records[0]["institution"], "RSUD Sentosa")
        self.assertEqual(records[0]["method"], "ocr")
        self.assertEqual(records[1]["project_address"], "Gedung Melati Blok A 12345")

    def test_identity_after_first_three_pages_and_not_in_prose(self):
        records = native_identity(
            [
                page(
                    "Profil Instansi\nNama Instansi: Yayasan Sentosa\nAlamat: Komp. Melati Blok A 12345",
                    20,
                )
            ]
        )
        self.assertEqual(records[0]["institution"], "Yayasan Sentosa")
        self.assertIn("Komp.", records[1]["project_address"])
        self.assertEqual(native_identity([page("PT Sentosa saat ini menggunakan alat.")]), [])

    def test_address_abbreviations_are_grounded(self):
        for value in ("Kec. Baru Kab. Sentosa", "Komp. Melati Blok A", "Gedung Satu", "Ruko Mawar"):
            source = page("Lokasi: " + value)
            records = grounded(
                [{"page": 1, "quote": source["text"], "project_address": value}],
                [source],
                "identity",
            )
            self.assertEqual(records[0]["project_address"], value)

    def test_negated_and_former_roles_never_match(self):
        for value in (
            "Bukan operator",
            "Operator nonaktif",
            "Belum menjadi Operator",
            "Mantan Operator",
            "Non-PPR",
            "Tidak ditunjuk sebagai PPR",
        ):
            self.assertEqual(
                compare("PPR" if "PPR" in value else "Operator", value, "role")[0], "REVIEW"
            )
        self.assertEqual(compare("Operator", "Operator Alat XRF", "role")[0], "MATCH")
        self.assertEqual(compare("PPR", "Petugas Proteksi Radiasi", "role")[0], "MATCH")

    def test_person_titles_help_pairing_without_altering_source(self):
        full = "Prof. Dr. Ir. H. Budi Santoso, M.T."
        self.assertEqual(person_key(full), person_key("Budi Santoso"))
        self.assertEqual(person_key("Drazen"), "drazen")
        selected = choose([{"name": "Budi Santosa"}, {"name": full}], "name", "Budi Santoso")
        self.assertEqual(selected["name"], full)
        self.assertEqual(compare("Budi Santoso", full)[0], "REVIEW")

    def test_headings_and_both_culture_aspects_beat_keyword_noise(self):
        pages = [page("keselamatan keamanan pelaporan " * 200, i) for i in range(1, 8)]
        pages += [
            page("BAB IV BUDAYA KESELAMATAN\nPenjelasan komitmen", 30),
            page("A. Budaya Keamanan\nPenjelasan tanggung jawab", 40),
        ]
        selected = ranked_pages("culture", pages, r"budaya|keselamatan|keamanan|pelaporan")
        self.assertEqual({p["page"] for p in selected[:2]}, {30, 40})

    @patch("app.protection.llm.request_records")
    def test_next_page_evidence_keeps_its_actual_page(self, request):
        quote = "Pembatas dosis operasional yang diterapkan pada fasilitas adalah 4 mSv/tahun."
        pages = [page("Penetapan Pembatas Dosis", 30), page(quote, 31)]
        request.return_value = [{"page": 31, "category": "dose", "quote": quote}]
        evidence, _ = recover("dose", pages)
        self.assertEqual(evidence[0]["page"], 31)
        self.assertEqual([p["page"] for p in request.call_args_list[0].args[2]], [30, 31])
        self.assertEqual(len(adjacent_window(page("x" * 11000), [page("y" * 2000, 2)])), 1)

    def test_culture_heading_variants_do_not_capture_next_chapter(self):
        for title in (
            "BAB IV BUDAYA KESELAMATAN",
            "2.4 Budaya Keselamatan Radiasi",
            "BAB IV BUDAYA KESELAMATAN DAN KEAMANAN SUMBER RADIASI",
            "A. Budaya Keselamatan",
            "Budaya Keselamatan",
        ):
            sections = culture_sections(
                [page(title + "\nUraian komitmen organisasi.\nBAB V LAINNYA\nTidak terkait.")]
            )
            self.assertIn("Uraian", sections[0]["text"])
            self.assertNotIn("Tidak terkait", sections[0]["text"])

    @patch("app.protection.reader.subprocess.run")
    def test_dense_native_page_with_small_logo_skips_redundant_ocr(self, run):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dense.pdf"
            with pymupdf.open() as pdf:
                p = pdf.new_page()
                p.insert_textbox(
                    pymupdf.Rect(30, 120, 550, 750),
                    "Paragraf isi dokumen program proteksi radiasi digital lengkap. " * 25,
                )
                pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
                pixmap.clear_with(255)
                p.insert_image(pymupdf.Rect(30, 20, 300, 110), stream=pixmap.tobytes("png"))
                pdf.save(path)
            pages, _ = read_document(path)
        run.assert_not_called()
        self.assertEqual(pages[0]["method"], "text")

    def test_landmark_address_and_rs_institution_matching(self):
        self.assertEqual(
            compare(
                "Komp. Melati Blok A, Kec. Baru, Kab. Sentosa",
                "Komplek Melati Blok A, Kecamatan Baru, Kabupaten Sentosa",
                "address",
            )[0],
            "MATCH",
        )
        self.assertEqual(
            compare("Komp. Melati Blok A No. 1", "Komplek Melati Blok A No. 2", "address")[0],
            "REVIEW",
        )
        self.assertEqual(compare("RS Sentosa", "Rumah Sakit Sentosa", "institution")[0], "MATCH")
        self.assertEqual(compare("Klinik Sentosa", "RS Sentosa", "institution")[0], "REVIEW")

    @patch(
        "app.protection.extraction.table_records", return_value={"personnel": [], "equipment": []}
    )
    @patch("app.protection.llm.extract")
    def test_protection_extract_records_dedups_adjacent_windows_and_early_stops(
        self, extract, tables
    ):
        pages = [
            page("Lokasi pemanfaatan berada di Gedung Melati Blok A 12345.", 1),
            page("Pengelola fasilitas adalah RSUD Sentosa.", 2),
            page("Lokasi cadangan di Gedung Mawar 99999.", 3),
            page("Alamat tambahan di Gedung Anggrek 88888.", 4),
        ]
        extract.return_value = [
            {
                "page": 1,
                "quote": pages[0]["text"],
                "institution": "",
                "project_address": "Gedung Melati Blok A 12345",
            },
            {
                "page": 2,
                "quote": pages[1]["text"],
                "institution": "RSUD Sentosa",
                "project_address": "",
            },
        ]
        records, warnings = extract_records("unused", pages)
        self.assertEqual(extract.call_count, 1)
        self.assertEqual([p["page"] for p in extract.call_args.args[1]], [1, 2])
        self.assertTrue(any(r.get("institution") == "RSUD Sentosa" for r in records["identity"]))
        self.assertFalse(any("dibatasi" in w for w in warnings))

    @patch("app.protection.llm.request_records")
    def test_semantic_culture_early_stops_once_both_aspects_found(self, request):
        safety = (
            "Manajemen membangun komitmen keselamatan radiasi melalui pelatihan pekerja, "
            "pelaporan insiden tanpa hukuman, pembelajaran dari kejadian, dan evaluasi rutin bersama seluruh staf."
        )
        security = (
            "Setiap petugas menjaga keamanan sumber radiasi, kerahasiaan akses ruangan, "
            "pelaporan ancaman mencurigakan, serta mengikuti latihan penanganan keamanan secara berkala setiap tahun."
        )
        pages = [
            page("BAB IV BUDAYA KESELAMATAN\n" + safety, 1),
            page("4.2 Budaya Keamanan\n" + security, 2),
            page("Penjelasan umum pelaksanaan kegiatan keselamatan radiasi.", 3),
            page("Catatan pelaporan keamanan fasilitas.", 4),
        ]
        request.return_value = [
            {"page": 1, "category": "safety", "quote": safety},
            {"page": 2, "category": "security", "quote": security},
        ]
        evidence, warnings = recover("culture", pages)
        self.assertEqual(request.call_count, 1)
        self.assertEqual({e["category"] for e in evidence}, {"safety", "security"})
        self.assertEqual(warnings, [])

    def test_metadata_scans_late_pages_and_zone_supports_denah_titles(self):
        pages = [
            page("Halaman Sampul\nTanggal Dibuat: 19/07/2026\nNo: 19/07/2026", 1, has_visual=False),
            *[page("Isi teks biasa.", n, has_visual=False) for n in range(2, 6)],
            page("Lembar Akhir\nKode Dokumen: SOP.01.2026", 6, has_visual=False),
            page("Denah Ruangan Radiologi dan Daerah Pengendalian", 7, has_visual=True),
        ]
        meta = metadata(pages)
        self.assertEqual([n["value"] for n in meta["number"]], ["SOP.01.2026"])
        rows = information(pages, lambda *args, **kwargs: make_row("d", *args, **kwargs))
        zones = [r for r in rows if r["field"].startswith("Daerah")]
        self.assertTrue(all(r["detail"]["pages"] == [7] for r in zones))
        self.assertFalse(zones[0]["detail"].get("review_required", False))
        self.assertTrue(zones[1]["detail"]["review_required"])

    def test_office_address_label_on_previous_line_is_not_project(self):
        source = page(
            "PT Contoh\nAlamat Kantor:\nJl. Mawar No. 12, Bandung 40111\n"
            "Lokasi Pemanfaatan:\nJl. Melati No. 15, Bandung 40112"
        )
        records = native_identity([source])
        addresses = [r["project_address"] for r in records if r.get("project_address")]
        self.assertEqual(addresses, ["Jl. Melati No. 15, Bandung 40112"])
        proposed = [
            {
                "page": 1,
                "project_address": "Jl. Mawar No. 12, Bandung 40111",
                "quote": "Jl. Mawar No. 12, Bandung 40111",
            }
        ]
        self.assertEqual(grounded(proposed, [source], "identity"), [])

    @patch("app.protection.llm.extract", return_value=[])
    def test_management_office_only_address_still_requires_retrieval(self, extract):
        records, _ = identities(
            [page("PT Contoh\nAlamat Kantor:\nJl. Mawar No. 12, Bandung 40111")]
        )
        self.assertFalse(any(r.get("project_address") for r in records))
        self.assertTrue(extract.called)

    def test_generic_floor_plan_does_not_confirm_either_zone(self):
        rows = information(
            [page("Denah Ruangan", 8, has_visual=True)],
            lambda *args, **kwargs: make_row("d", *args, **kwargs),
        )
        zones = [r for r in rows if r["field"].startswith("Daerah")]
        self.assertEqual(len(zones), 2)
        for row in zones:
            self.assertTrue(row["detail"]["review_required"])
            self.assertEqual(row["detail"]["pages"], [8])

    def test_metadata_in_middle_of_long_document_keeps_source_page(self):
        pages = [page("Uraian program.", n) for n in range(1, 21)]
        pages[9] = page("Nomor Dokumen: SOP.01.2026\nTanggal Dokumen: 12/11/2026", 10)
        result = metadata(pages)
        self.assertEqual([r["value"] for r in result["number"]], ["SOP.01.2026"])
        self.assertEqual([r["page"] for r in result["number"]], [10])
        self.assertEqual([r["value"] for r in result["date"]], ["12/11/2026"])
        self.assertEqual([r["page"] for r in result["date"]], [10])

    def test_metadata_prefers_document_labels_and_form_value_over_references(self):
        pages = [
            page("No Dokumen SM-01/2026\nTanggal Efektif 19/07/2026", 1),
            page("No: SK-001/2025\nTanggal Dibuat 01/05/2023", 12),
        ]
        result = metadata(pages, expected_number="SM-01/2026", expected_date="19 Juli 2026")
        self.assertEqual([r["value"] for r in result["number"]], ["SM-01/2026"])
        self.assertEqual([r["value"] for r in result["date"]], ["19/07/2026"])

    def test_same_office_and_project_address_keeps_explicit_project(self):
        source = page(
            "Alamat Kantor:\nJl. Industri No. 12, Bekasi\n"
            "Alamat Proyek:\nJl. Industri No. 12, Bekasi"
        )
        records = native_identity([source])
        addresses = [r["project_address"] for r in records if r.get("project_address")]
        self.assertEqual(addresses, ["Jl. Industri No. 12, Bekasi"])
        proposed = [
            {
                "page": 1,
                "project_address": "Jl. Industri No. 12, Bekasi",
                "quote": "Alamat Proyek: Jl. Industri No. 12, Bekasi",
            }
        ]
        self.assertTrue(grounded(proposed, [source], "identity"))

    def test_llm_office_quote_is_rejected_even_if_project_uses_same_address(self):
        source = page(
            "Alamat Kantor: Jl. Industri No. 12, Bekasi\nAlamat Proyek: Jl. Industri No. 12, Bekasi"
        )
        proposed = [
            {
                "page": 1,
                "project_address": "Jl. Industri No. 12, Bekasi",
                "quote": "Alamat Kantor: Jl. Industri No. 12, Bekasi",
            }
        ]
        self.assertEqual(grounded(proposed, [source], "identity"), [])

    @patch("app.protection.extraction.llm.extract")
    @patch("app.protection.extraction.table_records")
    def test_unrelated_incomplete_equipment_does_not_trigger_llm(self, tables, extract):
        tables.return_value = {
            "personnel": [],
            "equipment": [
                {
                    "merk_unit": "Merek A",
                    "tipe_unit": "Tipe A",
                    "nomor_seri_unit": "UNIT-01",
                    "merk_tabung": "Merek T",
                    "tipe_tabung": "Tipe T",
                    "nomor_seri_tabung": "TUBE-01",
                    "page": 1,
                    "quote": "UNIT-01 TUBE-01",
                    "method": "table",
                },
                {
                    "nomor_seri_unit": "CABANG-99",
                    "page": 1,
                    "quote": "CABANG-99",
                    "method": "table",
                },
            ],
        }
        extract_records(
            "unused.pdf",
            [page("Daftar Pesawat Sinar-X", 1)],
            {"equipment": [{"nomor_seri_unit": "UNIT-01", "nomor_seri_tabung": "TUBE-01"}]},
        )
        self.assertNotIn("equipment", [call.args[0] for call in extract.call_args_list])

    def test_table_records_handles_header_aliases_and_continuation_page(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tables.pdf"
            with pymupdf.open() as pdf:
                cols = [30, 140, 270, 400, 565]

                def draw_grid(p, y0, row_h, rows):
                    y_end = y0 + row_h * len(rows)
                    for x in cols:
                        p.draw_line((x, y0), (x, y_end))
                    for row_idx in range(len(rows) + 1):
                        y = y0 + row_idx * row_h
                        p.draw_line((cols[0], y), (cols[-1], y))
                    for row_idx, row in enumerate(rows):
                        y = y0 + row_idx * row_h
                        for col_idx, txt in enumerate(row):
                            p.insert_textbox(
                                pymupdf.Rect(
                                    cols[col_idx] + 4, y + 4, cols[col_idx + 1] - 4, y + row_h - 4
                                ),
                                txt,
                                fontsize=9,
                            )

                p1 = pdf.new_page()
                draw_grid(
                    p1,
                    80,
                    40,
                    [
                        ["Merk Unit", "Nomor Seri Unit", "Merk Tabung", "No. Seri Insersi Tabung"],
                        ["MerekA", "UNIT-101", "TabungA", "TUBE-101"],
                    ],
                )
                p2 = pdf.new_page()
                draw_grid(
                    p2,
                    80,
                    40,
                    [
                        ["MerekB", "UNIT-202", "TabungB", "TUBE-202"],
                        ["MerekC", "UNIT-303", "TabungC", "TUBE-303"],
                    ],
                )
                pdf.save(path)
            pages = [
                page("Daftar Alat\nNomor Seri Unit", 1),
                page("Lanjutan daftar alat", 2),
            ]
            records = table_records(path, pages)
        self.assertEqual(
            [r["nomor_seri_unit"] for r in records["equipment"]],
            ["UNIT-101", "UNIT-202", "UNIT-303"],
        )
        self.assertEqual(
            [r["nomor_seri_tabung"] for r in records["equipment"]],
            ["TUBE-101", "TUBE-202", "TUBE-303"],
        )
        self.assertEqual([r["page"] for r in records["equipment"]], [1, 2, 2])

    @patch.dict(os.environ, {}, clear=True)
    @patch("app.performance.os.sched_getaffinity", return_value=set(range(80)))
    def test_shared_node_default_cpu_budget(self, affinity):
        self.assertEqual(performance.settings(), (4, 2, 80))

    @patch.dict(os.environ, {"BAPETEN_OCR_PROCESSES": "20", "BAPETEN_OCR_CPU_THREADS": "4"})
    @patch("app.performance.os.sched_getaffinity", return_value=set(range(6)))
    def test_worker_budget_respects_affinity(self, affinity):
        workers, threads, available = performance.settings()
        self.assertLessEqual(workers * threads, available)

    def test_ranked_identity_pages_ignores_late_generic_prose_and_prioritizes_labels(self):
        pages = [
            page("PANDUAN PELATIHAN", 1),
            page(
                "Lokasi Proyek: Jl. Industri Raya No. 12 Kec. Cikarang Kab. Bekasi Jawa Barat 17530",
                2,
            ),
            page(
                "Bab 3 Budaya Keselamatan\nSetiap pekerja wajib memahami lokasi kerja dan gedung fasilitas.",
                9,
            ),
            page(
                "PT Contoh Mandiri\nKomp. Pergudangan Sentra Blok B No. 4 Tangerang Banten 15111",
                10,
            ),
        ]
        ranked = ranked_identity_pages(pages, ("project_address",), toc_fn=toc)
        self.assertEqual([item["page"] for item in ranked], [2, 10])

    @patch(
        "app.protection.extraction.table_records", return_value={"personnel": [], "equipment": []}
    )
    @patch("app.protection.llm.configuration", return_value=(True, "qwen3:8b", "mock"))
    @patch("app.protection.llm.extract", return_value=[])
    def test_identity_windows_stay_single_page_when_dense_and_cap_two_calls(
        self, extract_mock, config_mock, tables_mock
    ):
        pad = "x" * 2600
        pages = [
            page("PT Uji Padat\n" + pad, 1),
            page(
                "Kegiatan ini berada di kawasan Jl. Melati No. 5 Kec. Coblong Bandung Jawa Barat 40123\n"
                + pad,
                2,
            ),
            page(
                "Pelaksanaan dilakukan di area Jl. Mawar No. 9 Kec. Gubeng Surabaya Jawa Timur 60111\n"
                + pad,
                3,
            ),
            page(
                "Operasional berlangsung pada Jl. Kenanga No. 10 Kec. Pedurungan Semarang Jawa Tengah 50123\n"
                + pad,
                4,
            ),
        ]
        self.assertEqual([p["page"] for p in adjacent_window(pages[1], pages, max_chars=4500)], [2])
        self.assertEqual([p["page"] for p in adjacent_window(pages[1], pages)], [2, 3])

        _, mgmt_warnings = identities(pages)
        mgmt_calls = [call for call in extract_mock.call_args_list]
        self.assertEqual(len(mgmt_calls), 2)
        self.assertTrue(all(len(call.args[1]) == 1 for call in mgmt_calls))
        self.assertTrue(any("2 kandidat terbaik" in item for item in mgmt_warnings))

        extract_mock.reset_mock()
        _, prot_warnings = extract_records("unused.pdf", pages)
        prot_identity_calls = [
            call for call in extract_mock.call_args_list if call.args[0] == "identity"
        ]
        self.assertEqual(len(prot_identity_calls), 2)
        self.assertTrue(all(len(call.args[1]) == 1 for call in prot_identity_calls))
        self.assertTrue(any("dibatasi 2 halaman kandidat" in item for item in prot_warnings))

    @patch.dict(
        os.environ,
        {
            "BAPETEN_PROTECTION_LLM": "1",
            "BAPETEN_LLM_MODEL": "qwen3:8b",
            "BAPETEN_LLM_THREADS": "16",
        },
        clear=True,
    )
    def test_llm_uses_compact_identity_budget_and_thread_setting(self):
        with patch("app.protection.llm.request_records", return_value=[]) as request_mock:
            llm.extract("identity", [page("Lokasi Proyek: Jl. Industri No. 1", 1)])
            self.assertEqual(request_mock.call_args.kwargs["output_limit"], 450)

        payloads = []

        class _FakeResponse:
            def __init__(self, body):
                self._body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self._body

        def fake_urlopen(req, timeout=None):
            url = getattr(req, "full_url", str(req))
            if req.data:
                payload = json.loads(req.data.decode("utf-8"))
                payloads.append(payload)
            if url.endswith("/api/tags"):
                return _FakeResponse(json.dumps({"models": [{"name": "qwen3:8b"}]}).encode())
            return _FakeResponse(
                json.dumps(
                    {
                        "response": '{"records": []}',
                        "message": {"content": '{"records": []}'},
                    }
                ).encode()
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            llm.request_records(
                {"type": "object"},
                "Identitas ringkas",
                [page("Alamat: Jl. Industri No. 1 Bekasi 17530", 1)],
                "Ekstrak alamat.",
                output_limit=450,
            )
            llm.request_records(
                {"type": "object"},
                "Analisis penuh",
                [page("Teks panjang " + ("x" * 5200), 1)],
                "Ekstrak penuh.",
                output_limit=2300,
            )

        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[0]["options"]["num_ctx"], 4096)
        self.assertEqual(payloads[0]["options"]["num_predict"], 450)
        self.assertEqual(payloads[0]["options"]["num_thread"], 16)
        self.assertEqual(payloads[1]["options"]["num_ctx"], 8192)
        self.assertEqual(payloads[1]["options"]["num_predict"], 2300)
        self.assertEqual(payloads[1]["options"]["num_thread"], 16)

    @patch("app.storage.file_path", return_value=Path("unused.pdf"))
    @patch("app.protection.semantic.protection_fallback", return_value=({}, ["fallback warning"]))
    @patch("app.protection.semantic.culture_fallback", return_value=([], ["culture warning"]))
    @patch(
        "app.protection.service.extract_records",
        return_value=({"identity": [], "personnel": [], "equipment": []}, ["extract warning"]),
    )
    @patch("app.management.service.identities", return_value=([], ["mgmt extract warning"]))
    @patch("app.protection.service.read_document")
    @patch("app.management.service.read_document")
    def test_evaluate_omits_reading_notes_row_even_with_warnings(
        self,
        mgmt_read_mock,
        prot_read_mock,
        _identities_mock,
        _extract_mock,
        _culture_fb_mock,
        _prot_fb_mock,
        _file_path_mock,
    ):
        sample_pages = [page("PT Uji Catatan\nAlamat: Jl. Industri No. 1 Bekasi 17530", 1)]
        prot_read_mock.return_value = (sample_pages, ["Halaman 2: OCR gagal"])
        mgmt_read_mock.return_value = (sample_pages, ["Halaman 2: OCR gagal"])

        prot_doc = {"id": "doc-prot"}
        prot_rows = evaluate_protection(prot_doc, {}, {})
        self.assertFalse(
            any(
                r.get("field") == "Catatan pembacaan"
                or (r.get("detail") or {}).get("group") == "Catatan pembacaan"
                for r in prot_rows
            )
        )
        self.assertTrue(prot_doc.get("_uncacheable"))

        mgmt_doc = {"id": "doc-mgmt"}
        mgmt_rows = evaluate_management(mgmt_doc, {}, {})
        self.assertFalse(
            any(
                r.get("field") == "Catatan pembacaan"
                or (r.get("detail") or {}).get("group") == "Catatan pembacaan"
                for r in mgmt_rows
            )
        )
        self.assertTrue(mgmt_doc.get("_uncacheable"))


if __name__ == "__main__":
    unittest.main()
