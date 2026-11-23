"""Generalisation and failure-path checks; model answers are controlled, sources synthetic."""

import unittest
from unittest.mock import patch
from app.protection.extraction import extract_records, grounded
from app.protection.semantic import recover, culture_fallback, protection_fallback
from app.protection.service import build_rows, mark_unread_information
from app.management.service import build_rows as management_rows
from app.management.extraction import culture_evidence


def page(text, number=1):
    return {"page": number, "text": text, "native_text": text, "has_visual": False}


class SemanticFallbackTests(unittest.TestCase):
    @patch("app.protection.llm.request_records", return_value=[])
    def test_law_type_is_part_of_completeness_trigger(self, request):
        text = "Regulasi fasilitas meliputi UU No. 10 Tahun 1997. PP No. 45 Tahun 2023. PP No. 28 Tahun 2025. Perba No. 4 Tahun 2024. PP No. 5 Tahun 2025."
        protection_fallback([page(text)])
        self.assertEqual(request.call_args.args[1], "Analisis bagian laws")

    @patch("app.protection.llm.request_records")
    def test_dedicated_legal_section_skips_llm_and_excludes_other_subchapters(self, request):
        pages = [
            page(
                "I.6. Referensi\n"
                "1. Undang-Undang Nomor 10 Tahun 1997\n"
                "2. Peraturan Pemerintah Nomor 45 Tahun 2023\n"
                "3. Peraturan Pemerintah Nomor 28 Tahun 2025\n"
                "4. Peraturan Pemerintah Nomor 29 Tahun 2008\n"
                "II.1. Organisasi",
                10,
            ),
            page(
                "III.2. Ketentuan Tambahan\n"
                "Mengacu pula pada Peraturan BAPETEN Nomor 5 Tahun 2025 dan Perba No. 4 Tahun 2024.",
                18,
            ),
        ]
        semantic, _ = protection_fallback(pages)
        self.assertNotIn("legal_sections", semantic)
        request.assert_not_called()
        rows = build_rows("d", {}, pages, {}, semantic=semantic)
        laws = [r for r in rows if r["detail"]["group"] == "Dasar hukum"]
        perba5 = next(r for r in laws if "Nomor 5 Tahun 2025" in r["field"])
        self.assertEqual(perba5["detail"]["pages"], [])

    @patch("app.protection.llm.request_records")
    def test_model_cannot_erase_explicit_current_dose_conflict(self, request):
        first = "Saat ini pembatas dosis operasional yang digunakan adalah 4 mSv/tahun."
        second = "Saat ini pembatas dosis operasional yang digunakan adalah 6 mSv/tahun."
        request.return_value = [{"page": 8, "category": "dose", "quote": first}]
        semantic, _ = protection_fallback([page(first + " " + second, 8)])
        self.assertTrue(semantic["dose_review"])
        self.assertEqual(len(semantic["dose"]), 2)

    @patch("app.protection.extraction.table_records")
    @patch("app.protection.llm.extract")
    def test_existing_person_without_role_does_not_skip_fallback(self, extract, tables):
        tables.return_value = {
            "personnel": [{"name": "Ani", "page": 4, "quote": "Ani", "method": "table"}],
            "equipment": [],
        }
        extract.side_effect = lambda kind, pages: (
            [{"name": "Ani", "role": "Operator", "page": 4, "quote": "Petugas Ani Operator"}]
            if kind == "personnel"
            else []
        )
        records, _ = extract_records("unused", [page("Petugas Ani Operator", 4)])
        self.assertTrue(any(r.get("role") == "Operator" for r in records["personnel"]))

    @patch("app.protection.extraction.table_records")
    @patch("app.protection.llm.extract", return_value=[])
    def test_form_entity_not_covered_triggers_search_without_passing_form_values(
        self, extract, tables
    ):
        tables.return_value = {
            "personnel": [
                {"name": "Ani", "role": "Operator", "page": 4, "quote": "Petugas Ani Operator"}
            ],
            "equipment": [],
        }
        extract_records(
            "unused", [page("Petugas Ani Operator", 4)], {"personnel": [{"nama": "Budi"}]}
        )
        calls = [c for c in extract.call_args_list if c.args[0] == "personnel"]
        self.assertTrue(calls)
        self.assertNotIn("Budi", str(calls))

    def test_unreadable_source_marks_missing_information_for_review(self):
        rows = build_rows("d", {}, [], {})
        mark_unread_information(rows)
        self.assertTrue(
            all(r["detail"].get("review_required") for r in rows if r["status"] == "INFO")
        )

    @patch("app.protection.llm.request_records")
    def test_dose_statement_excludes_separate_general_limit_sentence(self, request):
        quote = "Untuk operasi rutin fasilitas, pembatas dosis yang berlaku ditetapkan sebesar 4 mSv/tahun. Nilai batas dosis pekerja radiasi adalah 20 mSv/tahun."
        request.return_value = [{"page": 11, "category": "dose", "quote": quote}]
        semantic, _ = protection_fallback([page(quote, 11)])
        self.assertIn("4 mSv/tahun", semantic["dose"][0]["quote"])
        self.assertNotIn("20 mSv/tahun", semantic["dose"][0]["quote"])
        self.assertEqual(semantic["dose"][0]["context_quote"], quote)

    @patch(
        "app.protection.extraction.table_records", return_value={"personnel": [], "equipment": []}
    )
    @patch("app.protection.llm.extract")
    def test_partial_identity_still_reads_address(self, extract, tables):
        text = "PT Contoh\nOperasi berlokasi di Kawasan Industri Blok D Kabupaten Baru"
        extract.side_effect = lambda kind, pages: (
            [
                {
                    "page": 1,
                    "quote": text,
                    "institution": "PT Contoh",
                    "project_address": "Kawasan Industri Blok D Kabupaten Baru",
                }
            ]
            if kind == "identity"
            else []
        )
        records, _ = extract_records("unused", [page(text)])
        self.assertTrue(any(r.get("project_address") for r in records["identity"]))
        self.assertTrue(any(call.args[0] == "identity" for call in extract.call_args_list))

    def test_role_filled_from_same_person_with_its_own_source(self):
        records = {
            "personnel": [
                {"name": "Ani", "page": 1, "quote": "Ani"},
                {"name": "Budi", "role": "PPR", "page": 2, "quote": "Budi PPR"},
                {"name": "Ani", "role": "Operator", "page": 3, "quote": "Ani Operator"},
            ]
        }
        rows = build_rows(
            "d", {"personnel": [{"nama": "Ani", "keahlian_klasifikasi": "Operator"}]}, [], records
        )
        role = next(r for r in rows if "Profesi" in r["field"])
        self.assertEqual((role["observed"], role["page"], role["status"]), ("Operator", 3, "MATCH"))
        self.assertEqual(role["detail"]["pages"], [3])

    def test_equipment_fill_does_not_borrow_other_serial(self):
        rows = build_rows(
            "d",
            {"equipment": [{"nomor_seri_unit": "U1", "merk_tabung": "Acme"}]},
            [],
            {
                "equipment": [
                    {"nomor_seri_unit": "U1", "page": 1, "quote": "U1"},
                    {
                        "nomor_seri_unit": "U2",
                        "merk_tabung": "Other",
                        "page": 2,
                        "quote": "U2 Other",
                    },
                    {"nomor_seri_unit": "U1", "merk_tabung": "Acme", "page": 3, "quote": "U1 Acme"},
                ]
            },
        )
        row = next(r for r in rows if "Merek Tabung" in r["field"])
        self.assertEqual((row["observed"], row["page"]), ("Acme", 3))

    def test_ungrounded_or_unanchored_records_rejected(self):
        source = page("Operator Ani bekerja di Jalan Melati.")
        self.assertEqual(
            grounded(
                [{"page": 1, "quote": source["text"], "role": "Operator"}], [source], "personnel"
            ),
            [],
        )
        self.assertEqual(
            grounded(
                [{"page": 1, "quote": "Operator Budi", "name": "Budi"}], [source], "personnel"
            ),
            [],
        )

    @patch("app.protection.llm.request_records")
    def test_alternative_regulation_heading_and_exact_law_numbers(self, request):
        text = "Acuan Regulasi Fasilitas\nUU No. 10 Tahun 1997 tentang Ketenaganukliran. PP No. 45 Tahun 2023."
        request.return_value = [{"page": 6, "category": "legal_section", "quote": text}]
        semantic, _ = protection_fallback([page(text, 6)])
        rows = build_rows("d", {}, [page(text, 6)], {}, semantic=semantic)
        laws = [r for r in rows if r["detail"]["group"] == "Dasar hukum"]
        self.assertEqual(sum(bool(r["detail"]["pages"]) for r in laws), 2)
        self.assertTrue(all(r["status"] == "INFO" for r in laws))

    @patch("app.protection.llm.request_records")
    def test_hallucinated_law_quote_or_page_rejected(self, request):
        text = "Acuan regulasi: PP No. 45 Tahun 2023 tentang keselamatan radiasi."
        request.return_value = [
            {"page": 9, "category": "legal_section", "quote": text},
            {"page": 1, "category": "legal_section", "quote": text.replace("45", "28")},
        ]
        evidence, warnings = recover("laws", [page(text)])
        self.assertEqual(evidence, [])
        self.assertEqual(len(warnings), 2)

    @patch("app.protection.llm.request_records")
    def test_semantic_culture_requires_dedicated_heading_and_does_not_extract_unrelated_pages(self, request):
        # Text inside chapter that uses unconventional phrasing not matched by extraction regex
        safety = "Seluruh staf operasional mengutamakan prosedur kerja proteksi radiasi dan saling mengingatkan potensi bahaya kerja secara berkesinambungan tanpa henti pada instalasi."
        security = "Penjagaan fasilitas radiasi mewajibkan seluruh staf mengawasi setiap orang yang memasuki area penyimpanan sumber dan segera menginformasikan ke penanggung jawab proteksi."
        request.return_value = [
            {"page": 7, "category": "safety", "quote": safety},
            {"page": 7, "category": "security", "quote": security},
        ]
        # Without culture heading (e.g. passing mentions in random pages/chapters), fallback is NOT called and nothing is extracted
        unrelated_pages = [page("BAB IV PELATIHAN\n" + safety + "\n" + security, 7)]
        topics, warnings = culture_fallback(unrelated_pages, culture_evidence(unrelated_pages))
        self.assertFalse(any(t["found"] for t in topics))
        self.assertTrue(all(t.get("review_required") for t in topics))
        self.assertEqual(request.call_count, 0)

        # With dedicated culture chapter heading, semantic recovery within that chapter succeeds
        pages = [page("BAB I BUDAYA KESELAMATAN DAN KEAMANAN\n" + safety + "\n" + security, 7)]
        topics, _ = culture_fallback(pages, culture_evidence(pages))
        self.assertTrue(all(t["found"] for t in topics))
        self.assertEqual(request.call_count, 1)
        row = management_rows("d", {}, pages, [], topics=topics)[-1]
        self.assertEqual(row["observed"], "Ditemukan")
        self.assertEqual(row["detail"]["pages"], [7])

    @patch("app.protection.llm.request_records", side_effect=TimeoutError)
    def test_timeout_is_review_not_absence(self, request):
        pages = [page("BAB I BUDAYA KESELAMATAN DAN BUDAYA KEAMANAN\nKomitmen keselamatan dan keamanan perusahaan.")]
        topics, warnings = culture_fallback(pages, culture_evidence(pages))
        row = management_rows("d", {}, pages, [], topics=topics)[-1]
        self.assertTrue(row["detail"]["review_required"])
        self.assertEqual(row["status"], "INFO")
        self.assertTrue(warnings)

    @patch("app.protection.llm.request_records", return_value=[])
    def test_generic_dose_limit_not_presented_as_confirmed_constraint(self, request):
        pages = [
            page(
                "Nilai batas dosis pekerja radiasi 20 mSv per tahun. Pembatas dosis akan dibahas pada revisi mendatang."
            )
        ]
        semantic, _ = protection_fallback(pages)
        row = next(
            r
            for r in build_rows("d", {}, pages, {}, semantic=semantic)
            if r["field"] == "Pembatas Dosis"
        )
        self.assertTrue(row["detail"]["review_required"])
        self.assertEqual(row["detail"]["pages"], [])

    @patch("app.protection.llm.request_records")
    def test_conflicting_active_doses_require_review(self, request):
        first = "Pembatas dosis yang diterapkan pada operasi fasilitas adalah 4 mSv/tahun."
        second = "Pembatas dosis yang diterapkan pada operasi fasilitas adalah 6 mSv/tahun."
        request.return_value = [
            {"page": 8, "category": "dose", "quote": q} for q in (first, second)
        ]
        semantic, _ = protection_fallback([page(first + " " + second, 8)])
        self.assertTrue(semantic["dose_review"])

    @patch("app.protection.llm.request_records")
    def test_current_explicit_dose_uses_fast_path(self, request):
        pages = [page("Saat ini pembatas dosis operasional yang digunakan adalah 4 mSv/tahun.")]
        semantic, _ = protection_fallback(pages)
        self.assertNotIn("dose", semantic)
        request.assert_not_called()

    @patch("app.protection.llm.request_records", return_value=[])
    def test_candidate_limit_and_no_silent_truncation(self, request):
        pages = [page("Budaya keselamatan " * 1000, 1)] + [
            page("Budaya keselamatan", n) for n in range(2, 7)
        ]
        _, warnings = recover("culture", pages)
        self.assertLessEqual(request.call_count, 3)
        self.assertTrue(any("dibatasi" in w for w in warnings))
        self.assertTrue(
            all(
                sum(len(p["text"]) for p in call.args[2]) <= 12000
                for call in request.call_args_list
            )
        )
        _, warnings = recover("culture", pages[:1])
        self.assertTrue(any("terlalu panjang" in w for w in warnings))

    @patch("app.protection.llm.request_records")
    def test_toc_not_sent_to_model(self, request):
        recover("culture", [page("DAFTAR ISI\nBudaya keselamatan .... 7")])
        request.assert_not_called()

    @patch("app.protection.llm.request_records", return_value=[])
    def test_single_stage_operational_dose_without_saat_ini_confirmed_even_over_candidate_limit(
        self, request
    ):
        stmt = "Penetapan pembatas dosis operasional untuk pekerja radiasi berlaku sebesar 5 mSv/tahun."
        pages = [
            page(stmt, 4),
            page("Pembatas dosis pekerja radiasi ditetapkan sebesar 5 mSv/tahun.", 7),
            page("Target pembatas dosis disebutkan secara umum dalam prosedur.", 9),
            page("Evaluasi pembatas dosis berkala dilakukan setiap tahun.", 11),
            page("Pembatas dosis merupakan bagian dari program proteksi.", 13),
        ]
        semantic, warnings = protection_fallback(pages)
        self.assertFalse(semantic["dose_review"])
        self.assertFalse(any("dosis" in w.lower() or "dose" in w.lower() for w in warnings))
        row = next(
            r
            for r in build_rows("d", {}, pages, {}, semantic=semantic)
            if r["field"] == "Pembatas Dosis"
        )
        self.assertFalse(row["detail"].get("review_required"))
        self.assertEqual(row["detail"]["pages"], [4])

    @patch("app.protection.llm.request_records", return_value=[])
    def test_multistage_or_shielding_rate_dose_remains_review(self, request):
        multistage = [
            page("Konstruksi menggunakan pembatas dosis sebesar 6 mSv/tahun.", 5),
            page("Operasi Tahap 1 menetapkan pembatas dosis sebesar 4 mSv/tahun.", 6),
        ]
        sem_multi, _ = protection_fallback(multistage)
        self.assertTrue(sem_multi["dose_review"])

        shielding_rate = [
            page("Pembatas dosis pada dinding perisai didesain < 2.5 µSv/jam.", 8),
        ]
        sem_rate, _ = protection_fallback(shielding_rate)
        self.assertTrue(sem_rate["dose_review"])

    def test_ranked_pages_laws_prefers_actual_citations_over_generic_prose(self):
        from app.protection.context import ranked_pages

        pages = [
            page("Peraturan dan ketentuan internal perusahaan selalu dipatuhi oleh staf.", 2),
            page(
                "Penyusunan mengacu pada dasar hukum Undang-Undang Nomor 10 Tahun 1997 "
                "dan Peraturan Pemerintah Nomor 45 Tahun 2023.",
                5,
            ),
        ]
        ordered = ranked_pages("laws", pages, r"regulasi|peraturan|dasar\s+hukum")
        self.assertEqual(ordered[0]["page"], 5)

    @patch("app.protection.llm.request_records")
    def test_skips_laws_llm_when_no_law_exists_and_caps_dose_calls_to_one(self, request):
        request.return_value = [
            {
                "page": 4,
                "category": "dose",
                "quote": "Penetapan pembatas dosis operasional untuk pekerja radiasi berlaku sebesar 5 mSv/tahun.",
            }
        ]
        pages = [
            page("Penetapan pembatas dosis operasional untuk pekerja radiasi berlaku sebesar 5 mSv/tahun.", 4),
            page("Target pembatas dosis 5 mSv/tahun disebut kembali pada ringkasan.", 9),
        ]
        semantic, _ = protection_fallback(pages)
        self.assertFalse(semantic["dose_review"])
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[1], "Analisis bagian dose")


if __name__ == "__main__":
    unittest.main()
