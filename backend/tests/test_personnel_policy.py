"""Conditional personnel fields and grouping must preserve source ownership."""

import unittest
from datetime import date

from app.personnel_policy import conditional_rows, group_sections


class PersonnelPolicyTests(unittest.TestCase):
    def test_duplicate_form_names_do_not_link_automatically(self):
        rows = self.evaluate(
            "Budi Santoso", people=[{"nama": "Budi Santoso"}, {"nama": "Budi Santoso"}]
        )
        self.assertEqual(rows[0]["status"], "REVIEW")
        self.assertNotIn("person_id", rows[0]["detail"])

    def evaluate(self, text, *, original=None, kind="COMPETENCE", people=None):
        people = (
            people if people is not None else [{"nama": "Budi Santoso", "keahlian": "Operator"}]
        )
        original = (
            original
            if original is not None
            else [
                {
                    "field": "Nama Petugas",
                    "expected": "Budi Santoso",
                    "observed": "Budi Santoso",
                    "status": "MATCH",
                    "score": 100,
                }
            ]
        )
        parsed = {
            "text": text,
            "document_type": kind,
            "pages": [{"page": 3, "native_text": text, "ocr": []}],
        }
        doc = {"id": "doc1", "filename": "sertifikat.pdf", "subtype": "Sertifikat Kompetensi PPR"}
        return conditional_rows(
            parsed, original, {"personnel": people}, doc, today=date(2026, 11, 12)
        )

    def test_only_name_mandatory_no_document_number_or_invented_expiry(self):
        rows = self.evaluate(
            "Sertifikat Budi Santoso\nNomor: ABC-123\nTanggal pelatihan 20 November 2027"
        )
        fields = {r["field"]: r for r in rows}
        self.assertEqual(set(fields), {"Nama"})
        self.assertEqual(fields["Nama"]["status"], "MATCH")
        self.assertEqual(fields["Nama"]["detail"]["pages"], [3])

    def test_permit_requires_role_and_expiry_even_when_not_read(self):
        rows = self.evaluate("Nama / Name: Budi Santoso", kind="SIB")
        fields = {r["field"]: r for r in rows}
        self.assertEqual(set(fields), {"Nama", "Profesi / Keahlian", "Masa Berlaku"})
        self.assertEqual(fields["Profesi / Keahlian"]["status"], "REVIEW")
        self.assertEqual(fields["Masa Berlaku"]["status"], "REVIEW")

    def test_dose_does_not_compare_profession(self):
        rows = self.evaluate(
            "Budi Santoso\nProfesi: Operator\nPeriode pemakaian Januari - Maret 2027", kind="DOSE"
        )
        self.assertNotIn("Profesi / Keahlian", [r["field"] for r in rows])

    def test_dose_uses_usage_period_instead_of_expiry(self):
        rows = self.evaluate(
            "Budi Santoso\nPeriode pemakaian September 2026 - Februari 2027",
            kind="DOSE",
        )
        fields = {r["field"]: r for r in rows}
        self.assertIn("Periode Pemakaian", fields)
        self.assertNotIn("Masa Berlaku", fields)
        self.assertEqual(fields["Periode Pemakaian"]["status"], "INFO")
        self.assertEqual(fields["Periode Pemakaian"]["detail"]["pages"], [3])

    def test_period_label_never_returns_dose_column_or_empty_label(self):
        for text, expected in (
            (
                "Hp(0,07)\nPeriode pemakaian :\nSeptember - November 2026\nDivisi : -",
                "September - November 2026",
            ),
            ("Periode penggunaan:\n01/02/2026\n-\n28/02/2026", "01/02/2026 - 28/02/2026"),
            (
                "Periode pemakaian :\nDivisi: -\nTanggal pelayanan 01/02/2026",
                "Belum ditemukan dalam teks terbaca",
            ),
            ("Periode pemakaian: 31/02/2026 - 01/03/2026", "Belum ditemukan dalam teks terbaca"),
        ):
            rows = self.evaluate(text, kind="DOSE")
            row = next(r for r in rows if r["field"] == "Periode Pemakaian")
            self.assertEqual(row["observed"], expected)
            self.assertEqual(row["status"], "REVIEW" if expected.startswith("Belum") else "INFO")

    def test_name_without_actual_source_cannot_match_or_group(self):
        rows = self.evaluate("Sertifikat milik orang lain")
        self.assertEqual(rows[0]["status"], "REVIEW")
        self.assertNotIn("person_id", rows[0]["detail"])

    def test_no_form_name_is_review_even_if_no_original_name_row(self):
        rows = self.evaluate("Sertifikat milik orang lain", original=[], people=[])
        self.assertEqual(rows[0]["field"], "Nama")
        self.assertEqual(rows[0]["status"], "REVIEW")

    def test_expiry_active_is_info_expired_or_ambiguous_is_review(self):
        for statement, status in (
            ("Berlaku sampai 19 Juli 2027", "INFO"),
            ("Berlaku sampai 19 Juli 2025", "REVIEW"),
            ("Masa berlaku: tanggal tidak terbaca", "REVIEW"),
            ("Berlaku sampai 19 Juli 2027\nBerlaku sampai 19 Juli 2028", "REVIEW"),
        ):
            with self.subTest(statement=statement):
                rows = self.evaluate("Budi Santoso\n" + statement)
                validity = next(r for r in rows if r["field"] == "Masa Berlaku")
                self.assertEqual(validity["status"], status)
                self.assertIsNone(validity["score"])
                self.assertEqual(validity["expected"], "—")
                self.assertEqual(validity["detail"]["pages"], [3])

    def test_role_with_evidence_is_compared_and_negation_is_review(self):
        for role, status in (("Operator", "MATCH"), ("Bukan Operator", "REVIEW")):
            original = [
                {
                    "field": "Nama Petugas",
                    "expected": "Budi Santoso",
                    "observed": "Budi Santoso",
                    "status": "MATCH",
                },
                {"field": "Keahlian", "observed": role},
            ]
            rows = self.evaluate("Budi Santoso\n" + role, original=original)
            self.assertEqual(rows[1]["status"], status)

    def test_approval_is_information_and_keeps_actual_page(self):
        rows = self.evaluate("Budi Santoso\nDisahkan oleh direktur", kind="ASSIGNMENT")
        approval = next(r for r in rows if r["field"] == "Pengesahan")
        self.assertEqual(approval["status"], "INFO")
        self.assertEqual(approval["detail"]["pages"], [3])

    def test_grouping_keeps_file_ids_and_does_not_link_ambiguous_owner(self):
        rows = self.evaluate("Budi Santoso")
        sections = [
            {
                "id": "prot",
                "category": "proteksi",
                "name": "Program Proteksi Radiasi",
                "rows": [],
            },
            {
                "id": "a",
                "category": "personel",
                "name": "SIB",
                "rows": rows,
                "source_documents": [{"id": "doc1", "filename": "sib_budi.pdf"}],
            },
        ]
        rows2 = [{**r, "document_id": "doc2"} for r in rows]
        sections.append(
            {
                "id": "b",
                "category": "personel",
                "name": "Sertifikat",
                "rows": rows2,
                "source_documents": [{"id": "doc2", "filename": "serkom_budi.pdf"}],
            }
        )
        unknown_rows = [{**r, "document_id": "doc3"} for r in self.evaluate("Nama tidak terbaca")]
        unknown = {
            "id": "c",
            "category": "personel",
            "rows": unknown_rows,
            "source_documents": [{"id": "doc3", "filename": "scan_buram.pdf"}],
        }
        sections.append(unknown)
        sections.append({"id": "lbl", "category": "label", "name": "Label", "rows": []})

        groups = group_sections(sections)
        self.assertEqual([g["category"] for g in groups], ["proteksi", "personel", "label"])
        personel = groups[1]
        self.assertEqual(personel["name"], "Dokumen Personel · 3 file")
        self.assertEqual({r["document_id"] for r in personel["rows"]}, {"doc1", "doc2", "doc3"})
        self.assertEqual(
            [d["id"] for d in personel["source_documents"]],
            ["doc1", "doc2", "doc3"],
        )
        unknown_row = next(r for r in personel["rows"] if r["document_id"] == "doc3")
        self.assertEqual(unknown_row["status"], "REVIEW")
        self.assertNotIn("person_id", unknown_row["detail"])

    def test_shared_document_kept_unified_and_tagged_as_collective(self):
        rows_budi = self.evaluate(
            "Budi Santoso", people=[{"nama": "Budi Santoso", "keahlian": "PPR"}]
        )
        orig_rama = [
            {
                "field": "Nama Petugas",
                "expected": "Rama Chandra",
                "observed": "Rama Chandra",
                "status": "MATCH",
                "score": 100,
            }
        ]
        rows_rama = self.evaluate(
            "Rama Chandra",
            original=orig_rama,
            people=[{"nama": "Rama Chandra", "keahlian": "Operator"}],
        )
        shared_rows = [{**r, "document_id": "doc_shared"} for r in rows_budi] + [
            {**r, "document_id": "doc_shared"} for r in rows_rama
        ]
        sections = [
            {
                "id": "s1",
                "category": "personel",
                "name": "SIB",
                "rows": [{**r, "document_id": "doc_budi"} for r in rows_budi],
                "source_documents": [{"id": "doc_budi", "filename": "sib_budi.pdf"}],
            },
            {
                "id": "s2",
                "category": "personel",
                "name": "SK Kolektif",
                "rows": shared_rows,
                "source_documents": [{"id": "doc_shared", "filename": "sk_kolektif.pdf"}],
            },
            {
                "id": "s3",
                "category": "personel",
                "name": "Sertifikat",
                "rows": [{**r, "document_id": "doc_rama"} for r in rows_rama],
                "source_documents": [{"id": "doc_rama", "filename": "sertif_rama.pdf"}],
            },
        ]
        groups = group_sections(sections)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["name"], "Dokumen Personel · 3 file")
        self.assertEqual(
            {r["document_id"] for r in groups[0]["rows"]},
            {"doc_budi", "doc_shared", "doc_rama"},
        )
        shared_doc_rows = [r for r in groups[0]["rows"] if r["document_id"] == "doc_shared"]
        self.assertEqual(len(shared_doc_rows), len(shared_rows))
        shared_budi = next(
            r for r in shared_doc_rows if r["detail"].get("person_name") == "Budi Santoso"
        )
        self.assertTrue(shared_budi["detail"]["shared_document"])
        self.assertEqual(shared_budi["detail"]["co_owners"], ["Rama Chandra"])
