import unittest
from datetime import date
from unittest.mock import patch

from app.personnel_policy import conditional_rows
from app.personnel_semantic import enrich, permit_role_evidence, recover, assigned_holder


class PersonnelSemanticTests(unittest.TestCase):
    def test_assignment_fallback_uses_recipient_not_signer(self):
        text = "Yang bertanda tangan dibawah ini:\nNama: Sari Dewi\nJabatan: Direktur\nDengan ini menugaskan kepada :\nNama\n: Rudi Hartono\nJabatan: Operator"
        evidence = assigned_holder([{'page': 4, 'text': text}])
        self.assertEqual([r['person'] for r in evidence], ['Rudi Hartono'])
        self.assertEqual(evidence[0]['page'], 4)
        self.assertEqual(assigned_holder([{'page': 1, 'text': "Nama: Sari Dewi\nJabatan: Direktur"}]), [])

    def test_assignment_groups_under_recipient_during_llm_outage(self):
        text = "Yang bertanda tangan di bawah ini:\nNama: Sari Dewi\nDengan ini menugaskan kepada:\nNama: Rudi Hartono\nJabatan: Operator"
        rows = [{'field': 'Nama', 'expected': 'Sari Dewi', 'observed': 'Sari Dewi', 'status': 'MATCH', 'detail': {}}]
        with patch('app.personnel_semantic.recover', return_value=([], ['LLM tidak tersedia'])):
            result = enrich({'pages': [{'page': 1, 'native_text': text, 'ocr': []}]}, rows,
                            {'personnel': [{'nama': 'Rudi Hartono'}, {'nama': 'Sari Dewi'}]}, {'id': 'd', 'filename': 'surat.pdf'})
        self.assertEqual(result[0]['detail']['person_name'], 'Rudi Hartono')
        self.assertEqual(result[0]['observed'], 'Rudi Hartono')
        self.assertEqual(result[0]['status'], 'REVIEW')

    def test_dose_never_emits_role_even_if_llm_finds_one(self):
        parsed, rows, app, doc = self.setup_case()
        parsed['document_type'] = 'DOSE'
        record = dict(page=2, person='Budi Santoso', role='Operator', expiry='', start_line=1, end_line=3)
        for response in ([record], []):
            with patch('app.personnel_semantic.llm.request_records', return_value=response):
                result = enrich(parsed, rows, app, doc)
            self.assertNotIn('Profesi / Keahlian', [r['field'] for r in result])

    def test_unlabelled_permit_role_is_read_from_layout_without_known_role_words(self):
        text = (
            "No. SIB / Working Permit Number\n470683.120.20.180826\n"
            "Klasifikasi Bebas yang Belum Dikenal\nNama / Name\nJuviandy"
        )
        evidence = permit_role_evidence([{"page": 1, "text": text}], "Juviandy")
        self.assertEqual(evidence["value"], "Klasifikasi Bebas yang Belum Dikenal")
        self.assertEqual(evidence["method"], "layout")
        self.assertIn("Juviandy", evidence["quote"])

    def test_line_evidence_is_copied_by_code_and_bounds_are_checked(self):
        record = dict(
            kind="holder",
            person="Budi Santoso",
            value="Budi Santoso",
            page=2,
            start_line=1,
            end_line=3,
            role="Operator",
            expiry="19 Juli 2027",
        )
        rows, _ = self.run_case([record])
        self.assertEqual(rows["Nama"]["status"], "MATCH")
        self.assertEqual(rows["Nama"]["quote"], " ".join(self.setup_case()[0]["text"].split()))
        self.assertEqual(rows["Masa Berlaku"]["observed"], "19/07/2027")
        for start, end in ((0, 3), (1, 99), (3, 1), (True, 3)):
            bad, doc = self.run_case([{**record, "start_line": start, "end_line": end}])
            self.assertEqual(bad["Nama"]["status"], "REVIEW")
            self.assertTrue(doc["_uncacheable"])

    def test_compact_holder_record_carries_role_and_expiry_once(self):
        text = self.setup_case()[0]["text"]
        record = {
            **self.record("holder", "Budi Santoso", text),
            "role": "Operator",
            "expiry": "19 Juli 2027",
        }
        rows, _ = self.run_case([record])
        self.assertEqual(rows["Profesi / Keahlian"]["status"], "MATCH")
        self.assertEqual(rows["Masa Berlaku"]["observed"], "19/07/2027")

    def test_duration_start_is_not_declared_as_expiry(self):
        text = "Nama / Name: Budi Santoso\nBerlaku 5 tahun sejak 19 Juli 2026"
        rows, _ = self.run_case(
            [
                self.record("holder", "Budi Santoso", text),
                self.record("expiry", "19 Juli 2026", text),
            ],
            text,
        )
        self.assertEqual(rows["Masa Berlaku"]["status"], "REVIEW")
        self.assertIn("durasi", rows["Masa Berlaku"]["note"])

    def test_analysis_handler_reaches_semantic_path(self):
        from app.analysis.personnel import _personnel

        parsed, _, app, doc = self.setup_case()
        with (
            patch("app.analysis.personnel.storage.file_path", return_value="unused.pdf"),
            patch("src.extraction.personnel_document.ocr_personnel_documents", return_value=[]),
            patch(
                "src.extraction.personnel_document.parse_personnel_documents", return_value=[parsed]
            ),
            patch(
                "src.matching.personnel_document_matcher.validate_personnel_documents",
                return_value=[
                    {
                        "validation": {
                            "fields": [
                                {
                                    "field": "Nama Petugas",
                                    "expected": "Budi Santoso",
                                    "observed": "Budi Santoso",
                                    "status": "MATCH",
                                }
                            ]
                        }
                    }
                ],
            ),
            patch(
                "app.personnel_semantic.llm.request_records",
                return_value=[self.record("holder", "Budi Santoso", parsed["text"])],
            ) as request,
        ):
            rows = _personnel(doc, app, {})
        request.assert_called_once()
        self.assertEqual(rows[0]["field"], "Nama")
        self.assertEqual(rows[0]["detail"]["method"], "llm")

    def setup_case(
        self, text="Nama / Name: Budi Santoso\nProfesi: Operator\nBerlaku sampai 19 Juli 2027"
    ):
        parsed = {
            "document_type": "COMPETENCE",
            "text": text,
            "pages": [{"page": 2, "native_text": text, "ocr": []}],
        }
        doc = {
            "id": "doc1",
            "filename": "sertifikat.pdf",
            "category": "personel",
            "subtype": "Sertifikat Kompetensi PPR",
        }
        app = {"personnel": [{"nama": "Budi Santoso", "keahlian": "Operator"}]}
        original = [
            {
                "field": "Nama Petugas",
                "expected": "Budi Santoso",
                "observed": "Budi Santoso",
                "status": "MATCH",
            }
        ]
        rows = conditional_rows(parsed, original, app, doc)
        return parsed, rows, app, doc

    def record(self, kind, value, quote, person="Budi Santoso", page=2):
        return dict(kind=kind, value=value, quote=quote, person=person, page=page)

    def run_case(self, records, text=None):
        args = self.setup_case(text) if text else self.setup_case()
        with patch("app.personnel_semantic.llm.request_records", return_value=records) as request:
            rows = enrich(*args, today=date(2026, 11, 12))
        request.assert_called_once()
        return {r["field"]: r for r in rows}, args[-1]

    def test_real_fallback_called_even_for_unverified_rule_match(self):
        text = self.setup_case()[0]["text"]
        rows, doc = self.run_case(
            [
                self.record("holder", "Budi Santoso", text),
                self.record("role", "Operator", text),
                self.record("expiry", "19 Juli 2027", text),
            ]
        )
        self.assertEqual(rows["Nama"]["status"], "MATCH")
        self.assertEqual(rows["Profesi / Keahlian"]["status"], "MATCH")
        self.assertEqual(rows["Masa Berlaku"]["observed"], "19/07/2027")
        self.assertEqual(rows["Masa Berlaku"]["status"], "INFO")
        self.assertEqual(rows["Nama"]["detail"]["pages"], [2])
        self.assertEqual(rows["Nama"]["detail"]["evidence"][0]["method"], "llm")
        self.assertNotIn("_uncacheable", doc)
        self.assertNotIn("Nomor Dokumen", rows)

    def test_no_holder_or_model_failure_cannot_leave_rule_match(self):
        rows, doc = self.run_case([])
        self.assertEqual(rows["Nama"]["status"], "REVIEW")
        self.assertTrue(doc["_uncacheable"])
        args = self.setup_case()
        with patch("app.personnel_semantic.llm.request_records", side_effect=TimeoutError):
            rows = enrich(*args)
        self.assertEqual(rows[0]["status"], "REVIEW")
        self.assertNotIn("person_id", rows[0]["detail"])
        self.assertTrue(args[-1]["_uncacheable"])

    def test_hallucinated_quote_page_or_value_rejected(self):
        for record in (
            self.record("holder", "Budi Santoso", "Nama / Name: Budi Santoso", page=99),
            self.record("holder", "Budi Santoso", "Penerima sertifikat: Budi Santoso"),
            self.record("holder", "Orang Lain", "Nama / Name: Budi Santoso"),
        ):
            with self.subTest(record=record):
                rows, doc = self.run_case([record])
                self.assertEqual(rows["Nama"]["status"], "REVIEW")
                self.assertTrue(doc["_uncacheable"])

    def test_signer_role_is_not_assigned_to_holder(self):
        text = "Nama / Name: Budi Santoso\nDitandatangani: Andi\nProfesi: PPR"
        rows, _ = self.run_case(
            [
                self.record("holder", "Budi Santoso", "Nama / Name: Budi Santoso"),
                self.record("role", "PPR", "Ditandatangani: Andi Profesi: PPR", person="Andi"),
            ],
            text,
        )
        self.assertNotIn("Profesi / Keahlian", rows)

    def test_expiry_requires_validity_context_and_ambiguous_dates_review(self):
        for statement, value in (
            ("Tanggal lahir: 19 Juli 2027", "19 Juli 2027"),
            ("Berlaku 19 Juli 2025 sampai 19 Juli 2027", "19 Juli 2025 sampai 19 Juli 2027"),
        ):
            text = "Nama / Name: Budi Santoso\n" + statement
            rows, _ = self.run_case(
                [self.record("holder", "Budi Santoso", text), self.record("expiry", value, text)],
                text,
            )
            if "Masa Berlaku" in rows:
                self.assertNotEqual(rows["Masa Berlaku"]["observed"], "19/07/2027")

    def test_multiple_owners_and_duplicate_reference_names_do_not_group(self):
        text = "Nama / Name: Budi Santoso\nNama / Name: Andi"
        rows, _ = self.run_case(
            [
                self.record("holder", "Budi Santoso", text),
                self.record("holder", "Andi", text, person="Andi"),
            ],
            text,
        )
        self.assertEqual(rows["Nama"]["status"], "REVIEW")
        self.assertNotIn("person_id", rows["Nama"]["detail"])
        args = self.setup_case()
        args[2]["personnel"].append(dict(args[2]["personnel"][0]))
        with patch(
            "app.personnel_semantic.llm.request_records",
            return_value=[self.record("holder", "Budi Santoso", args[0]["text"])],
        ):
            result = enrich(*args)
        self.assertEqual(result[0]["status"], "REVIEW")

    def test_context_budget_is_explicit_and_no_text_never_calls_model(self):
        with patch("app.personnel_semantic.llm.request_records", return_value=[]) as request:
            _, warnings = recover([{"page": i, "text": "a " * 5000} for i in range(1, 5)])
            self.assertEqual(request.call_count, 2)
            self.assertTrue(warnings)
            request.reset_mock()
            _, warnings = recover([])
            request.assert_not_called()
            self.assertTrue(warnings)

    def test_verified_holder_survives_unanchored_signer_candidate(self):
        text = "Dengan ini menyatakan bahwa:\nRama Chandra\ntelah mengikuti pelatihan\nAnthony Ivan\nDirector"
        rows, doc = self.run_case(
            [
                {"page": 2, "person": "Rama Chandra", "role": "", "expiry": "", "start_line": 1, "end_line": 2},
                {"page": 2, "person": "Anthony Ivan", "role": "Director", "expiry": "", "start_line": 4, "end_line": 5},
            ],
            text,
        )
        # Setup has Budi Santoso in form, so Rama Chandra is REVIEW for name mismatch vs form,
        # NOT rejected for missing holder anchor or _uncacheable.
        self.assertEqual(rows["Nama"]["observed"], "Rama Chandra")
        self.assertNotIn("_uncacheable", doc)

    def test_semantic_page_text_suppresses_noisy_ocr_duplicates_on_native_pages(self):
        from app.personnel_semantic import _semantic_page_text

        page = {
            "page": 1,
            "native_text": "BADAN PENGAWAS TENAGA NUKLIR\nIzin Bekerja Petugas Fasilitas Radiasi\nNama / Name\nJuviandy\nBerlaku s.d / Valid Until\n13 Agustus 2031\nDirektur Perizinan Fasilitas Radiasi dan Zat Radioaktif",
            "ocr": [
                {"text": "BADAN PENGAWAS TENAGA NUKLIR"},
                {"text": "Izin Bekerja Petugas Fasilitas Radiasi"},
                {"text": "Direigug Perizinan Fasilitas Baggs"},
                {"text": "Jovian"},
            ],
        }
        cleaned = _semantic_page_text(page)
        self.assertIn("Juviandy", cleaned)
        self.assertNotIn("Jovian", cleaned)
        self.assertNotIn("Direigug", cleaned)

    def test_long_page_uses_absolute_line_numbers_across_chunks(self):
        filler = [f"Baris pengantar {i} " + ("x" * 90) for i in range(90)]
        lines = filler + ["Nama / Name: Budi Santoso", "Profesi: Operator"]
        start = len(filler) + 1
        record = {
            "page": 2,
            "person": "Budi Santoso",
            "role": "Operator",
            "expiry": "",
            "start_line": start,
            "end_line": start + 1,
        }
        with patch("app.personnel_semantic.llm.request_records", return_value=[record]):
            evidence, warnings = recover([{"page": 2, "text": "\n".join(lines)}])
        self.assertFalse(warnings)
        self.assertEqual(next(x for x in evidence if x["kind"] == "holder")["value"], "Budi Santoso")

    def test_unique_minor_ocr_name_variation_can_map_to_form(self):
        text = "Nama / Name: Budi Santos0\nProfesi: Operator"
        parsed, rows, app, doc = self.setup_case(text)
        record = {
            "page": 2,
            "person": "Budi Santos0",
            "role": "Operator",
            "expiry": "",
            "start_line": 1,
            "end_line": 2,
        }
        with patch("app.personnel_semantic.llm.request_records", return_value=[record]):
            result = {r["field"]: r for r in enrich(parsed, rows, app, doc)}
        self.assertEqual(result["Nama"]["status"], "MATCH")
        self.assertEqual(result["Nama"]["observed"], "Budi Santos0")

    def test_certificate_holder_accepted_without_explicit_nama_label_and_signer_rejected(self):
        text = "\n".join(
            [
                "SERTIFIKAT PELATIHAN",
                "No. 001/2026",
                "Dengan ini menyatakan bahwa,",
                "This is to certify that,",
                "SHAFIRA RAFA MAULIDA",
                "Telah mengikuti training",
                "has participated in the training :",
                "Bogor, 21 April 2026",
                "Atas nama (on behalf of) PT Contoh",
                "Andi Wijaya",
                "Direktur PT Contoh",
            ]
        )
        parsed = {
            "document_type": "TRAINING",
            "text": text,
            "pages": [{"page": 1, "native_text": text, "ocr": []}],
        }
        doc = {
            "id": "doc_cert",
            "filename": "sertifikat.pdf",
            "category": "personel",
            "subtype": "Sertifikat Pelatihan",
        }
        app = {"personnel": [{"nama": "Shafira Rafa Maulida", "keahlian": "PPR"}]}
        records = [
            {
                "page": 1,
                "person": "SHAFIRA RAFA MAULIDA",
                "role": "",
                "expiry": "",
                "start_line": 5,
                "end_line": 7,
            },
            {
                "page": 1,
                "person": "Andi Wijaya",
                "role": "",
                "expiry": "",
                "start_line": 9,
                "end_line": 11,
            },
        ]
        with patch("app.personnel_semantic.llm.request_records", return_value=records):
            result = {r["field"]: r for r in enrich(parsed, [], app, doc)}
        self.assertEqual(result["Nama"]["status"], "MATCH")
        self.assertEqual(result["Nama"]["observed"], "SHAFIRA RAFA MAULIDA")
        self.assertIn("Dengan ini menyatakan bahwa", result["Nama"]["quote"])
        self.assertNotIn("_uncacheable", doc)

    def test_unlabelled_certificate_single_line_uses_adjacent_predicate_not_atas_nama(self):
        text = "\n".join(
            [
                "SERTIFIKAT",
                "Rudi Hartono",
                "Telah mengikuti pelatihan Proteksi Radiasi",
                "Atas nama PT Contoh",
                "Budi Santoso",
                "Direktur",
            ]
        )
        records = [
            {
                "page": 1,
                "person": "Rudi Hartono",
                "role": "",
                "expiry": "",
                "start_line": 2,
                "end_line": 2,
            },
            {
                "page": 1,
                "person": "Budi Santoso",
                "role": "",
                "expiry": "",
                "start_line": 4,
                "end_line": 6,
            },
        ]
        with patch("app.personnel_semantic.llm.request_records", return_value=records):
            evidence, warnings = recover([{"page": 1, "text": text}])
        holders = [e for e in evidence if e["kind"] == "holder"]
        self.assertEqual([h["person"] for h in holders], ["Rudi Hartono"])
        self.assertIn("Telah mengikuti", holders[0]["quote"])
        self.assertFalse(warnings)

    def test_dose_table_holder_row_expands_to_table_header_and_keeps_period_clean(self):
        def page_text(period_line, worker_line):
            return "\n".join(
                [
                    "LAPORAN HASIL UJI",
                    "ZERO CHECK",
                    "Nama Pekerja Radiasi",
                    "Kurva Kalibrasi",
                    "Dosis Efektif ( mSv )",
                    "Hp(10)",
                    "Hp(0,07)",
                    "Periode pemakaian :",
                    period_line,
                    "Divisi : -",
                    "1",
                    "001",
                    worker_line,
                    "Metode Uji",
                    "Catatan",
                    "Kepala, NuklindoLab",
                    "Dr. Eko Pudjadi",
                ]
            )

        p1 = page_text("September - November 2026", "Rama Chandra")
        p2 = "\n".join(
            [
                "LAPORAN HASIL UJI",
                "ZERO CHECK",
                "Nama Pekerja Radiasi",
                "Kurva Kalibrasi",
                "Dosis Efektif ( mSv )",
                "Hp(10)",
                "Hp(0,07)",
                "Desember 2026 - Februari 2027",
                "Periode pemakaian :",
                "Divisi : -",
                "1",
                "001",
                "[Rama Chandra",
                "Metode Uji",
                "Catatan",
                "Kepala, NuklindoLab",
                "Dr. Eko Pudjadi",
            ]
        )
        parsed = {
            "document_type": "DOSE",
            "text": p1 + "\n" + p2,
            "pages": [
                {"page": 1, "native_text": p1, "ocr": []},
                {"page": 2, "native_text": p2, "ocr": []},
            ],
        }
        doc = {
            "id": "doc_zc",
            "filename": "zero_check.pdf",
            "category": "personel",
            "subtype": "Evaluasi Dosis / Zero Check",
        }
        app = {"personnel": [{"nama": "Rama Chandra", "keahlian": "Operator"}]}
        original = [
            {
                "field": "Nama Petugas",
                "expected": "Rama Chandra",
                "observed": "Rama Chandra",
                "status": "MATCH",
                "score": 100,
            }
        ]
        rows = conditional_rows(parsed, original, app, doc, today=date(2026, 11, 16))
        records = [
            {
                "page": 1,
                "person": "Rama Chandra",
                "role": "Pekerja Radiasi",
                "expiry": "September - November 2026",
                "start_line": 13,
                "end_line": 13,
            },
            {
                "page": 2,
                "person": "Rama Chandra",
                "role": "Pekerja Radiasi",
                "expiry": "Desember 2026 - Februari 2027",
                "start_line": 13,
                "end_line": 13,
            },
            {
                "page": 1,
                "person": "Dr. Eko Pudjadi",
                "role": "Kepala, NuklindoLab",
                "expiry": "",
                "start_line": 17,
                "end_line": 17,
            },
        ]
        with patch("app.personnel_semantic.llm.request_records", return_value=records):
            result = {r["field"]: r for r in enrich(parsed, rows, app, doc, today=date(2026, 11, 16))}
        self.assertEqual(result["Nama"]["status"], "MATCH")
        self.assertEqual(result["Nama"]["observed"], "Rama Chandra")
        self.assertEqual(result["Nama"]["detail"]["pages"], [1, 2])
        self.assertEqual(
            result["Periode Pemakaian"]["observed"],
            "September - November 2026; Desember 2026 - Februari 2027",
        )
        self.assertEqual(result["Periode Pemakaian"]["status"], "INFO")
        self.assertFalse(result["Periode Pemakaian"]["detail"].get("review_required"))
        self.assertEqual(result["Periode Pemakaian"]["detail"]["pages"], [1, 2])
        self.assertNotIn("_uncacheable", doc)

    def test_assigned_holder_handles_columnar_orders_and_work_letters(self):
        col_work_letter = (
            "SURAT KETERANGAN KERJA\n"
            "Dengan ini menugaskan kepada :\n"
            "Nama    \n"
            "Tempat/ Tanggal Lahir  \n"
            "NIK / No. Identitas    \n"
            "Jabatan       \n"
            ": Juviandy    \n"
            ": Palembang, 19-02-1995  \n"
            ": 1671071902950008 \n"
            ": Petugas Proteksi Radiasi\n"
        )
        col_assignment = (
            "Surat penunjukkan tugas\n"
            "Dengan ini menugaskan kepada:\n"
            "Nama\n"
            "NIK\n"
            "No. SIB\n"
            "Alamat\n"
            ": Shafira Rafa Maulida\n"
            ": 3277036605020003\n"
        )
        order_text = "SURAT PERINTAH\nDengan ini memerintahkan kepada:\nNama: Neza Putri\nJabatan: PPR"
        statement_text = "SURAT KETERANGAN KERJA\nYang bertanda tangan di bawah ini menerangkan bahwa:\nNama: Isra Pratama\nJabatan: Radiografer"

        self.assertEqual([r["person"] for r in assigned_holder([{"page": 1, "text": col_work_letter}])], ["Juviandy"])
        self.assertEqual([r["person"] for r in assigned_holder([{"page": 1, "text": col_assignment}])], ["Shafira Rafa Maulida"])
        self.assertEqual([r["person"] for r in assigned_holder([{"page": 2, "text": order_text}])], ["Neza Putri"])
        self.assertEqual([r["person"] for r in assigned_holder([{"page": 3, "text": statement_text}])], ["Isra Pratama"])
        self.assertEqual(
            assigned_holder([{"page": 1, "text": "Dengan ini menugaskan kepada:\nNama:\nNIK: 123456\nJabatan: Direktur"}]),
            [],
        )

    def test_merged_assignment_formats_extract_name_and_radiation_role(self):
        from src.matching.personnel_document_matcher import validate_personnel_document

        cases = [
            (
                "Juviandy",
                "Petugas Proteksi Radiasi",
                (
                    "SURAT KETERANGAN KERJA\n"
                    "Dengan ini menugaskan kepada :\n"
                    "Nama\nTempat/ Tanggal Lahir\nNIK / No. Identitas\nJabatan\n"
                    ": Juviandy\n: Palembang, 19-02-1995\n: 1671071902950008\n: Petugas Proteksi Radiasi\n"
                    "Adalah benar merupakan karyawan dari CV Mulia Perbaikan Garansi dan bekerja sebagai Manager sejak 2019 "
                    "hingga saat ini masih aktif bekerja dan akan bertugas juga sebagai Petugas Proteksi Radiasi.\n"
                    "Direktur, Sari Dewi"
                ),
            ),
            (
                "Shafira Rafa Maulida",
                "Petugas Proteksi Radiasi",
                (
                    "Surat penunjukkan tugas\n"
                    "Dengan ini menugaskan kepada:\n"
                    "Nama\nNIK\nNo. SIB\nAlamat\n"
                    ": Shafira Rafa Maulida\n: 3277036605020003\n: 468442\n: Jl. Cidurian Utara No. 43\n"
                    "Untuk melaksanakan tugas di PT Tuku Emas Indonesia sebagai Petugas Proteksi Radiasi.\n"
                    "Demikian surat tugas ini dibuat"
                ),
            ),
            (
                "Isra Pratama",
                "Radiografer",
                (
                    "SURAT KETERANGAN KERJA\n"
                    "Yang bertanda tangan di bawah ini menerangkan bahwa:\n"
                    "Nama: Isra Pratama\n"
                    "Saat ini aktif bekerja sebagai Radiografer di fasilitas radiologi."
                ),
            ),
        ]
        for expected_name, expected_role, text in cases:
            with self.subTest(person=expected_name):
                app = {"general": {"instansi": "PT Tuku Emas Indonesia"}, "personnel": [{"nama": expected_name, "keahlian": expected_role}]}
                parsed = {"document_type": "ASSIGNMENT", "text": text, "pages": [{"page": 1, "text": text, "native_text": text, "ocr": []}]}
                validation = validate_personnel_document(parsed, app)
                rows = conditional_rows(parsed, validation["fields"], app, {"id": "doc1", "filename": "tugas.pdf", "subtype": "Surat Penugasan / Keterangan Kerja"})
                by_field = {r["field"]: r for r in rows}
                self.assertEqual(by_field["Nama"]["observed"], expected_name)
                self.assertEqual(by_field["Nama"]["status"], "MATCH")
                self.assertEqual(by_field["Profesi / Keahlian"]["observed"], expected_role)
                self.assertEqual(by_field["Profesi / Keahlian"]["status"], "MATCH")
                self.assertNotEqual(by_field["Profesi / Keahlian"]["observed"], "Manager")
