import io
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from PIL import Image, ImageDraw


class LabelHybridTests(unittest.TestCase):
    def _sample_app(self):
        return {
            "equipment": [
                {
                    "merk_unit": "AcmeRay",
                    "tipe_unit": "Model X-100",
                    "nomor_seri_unit": "SN998877",
                    "merk_tabung": "TubeCorp",
                    "tipe_tabung": "Insert T-50",
                    "nomor_seri_tabung": "TB-112233",
                }
            ]
        }

    def _docs(self):
        return [
            {
                "id": "a" * 32,
                "app_id": "b" * 32,
                "sha256": "c" * 64,
                "disk_filename": "unit.pdf",
                "filename": "foto_unit.pdf",
                "category": "label",
            },
            {
                "id": "d" * 32,
                "app_id": "b" * 32,
                "sha256": "e" * 64,
                "disk_filename": "tabung.jpg",
                "filename": "foto_tabung.jpg",
                "category": "label",
            },
        ]

    def test_exact_deterministic_match_skips_llm_and_rescue(self):
        import app.label_hybrid  # noqa: F401
        from app.analysis.labels import _label_group

        app = self._sample_app()
        docs = self._docs()
        perfect_pages = [
            {
                "source_id": docs[0]["id"],
                "source_name": docs[0]["filename"],
                "source_type": "pdf",
                "page": 1,
                "ocr": [
                    {"text": "AcmeRay"},
                    {"text": "Model X-100"},
                    {"text": "SN: SN998877"},
                ],
            },
            {
                "source_id": docs[1]["id"],
                "source_name": docs[1]["filename"],
                "source_type": "image",
                "page": 1,
                "ocr": [
                    {"text": "TubeCorp"},
                    {"text": "Insert T-50"},
                    {"text": "S/N: TB-112233"},
                ],
            },
        ]
        with (
            patch("app.label_hybrid.rescue_label_pages") as rescue_mock,
            patch("app.protection.llm.request_records") as llm_mock,
        ):
            rows = _label_group(docs, app, {}, prefetched_pages=perfect_pages)

        rescue_mock.assert_not_called()
        llm_mock.assert_not_called()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r["status"] == "MATCH" for r in rows))

    def test_hybrid_llm_recovers_grounded_partial_and_rejects_hallucinations(self):
        from app.analysis.labels import _label_group

        app = self._sample_app()
        docs = self._docs()
        noisy_pages = [
            {
                "source_id": docs[0]["id"],
                "source_name": docs[0]["filename"],
                "source_type": "pdf",
                "page": 2,
                "ocr": [
                    {"text": "AcmeRay"},
                    {"text": "M0del X-I00"},
                    {"text": "SN998877"},
                ],
            },
            {
                "source_id": docs[1]["id"],
                "source_name": docs[1]["filename"],
                "source_type": "image",
                "page": 1,
                "ocr": [
                    {"text": "S/N: TB-112233"},
                ],
            },
        ]
        llm_response = [
            # Hallucinated quote not present in OCR must be discarded.
            {
                "block_id": 0,
                "page": 2,
                "quote": "FABRICATED BRAND XYZ",
                "merk_unit": "",
                "tipe_unit": "Model X-100",
                "nomor_seri_unit": "",
                "merk_tabung": "FakeCorp",
                "tipe_tabung": "",
                "nomor_seri_tabung": "",
            },
            # Misassigned model string into merk_unit must be ignored by swap guard.
            {
                "block_id": 0,
                "page": 2,
                "quote": "M0del X-I00",
                "merk_unit": "M0del X-I00",
                "tipe_unit": "M0del X-I00",
                "nomor_seri_unit": "",
                "merk_tabung": "",
                "tipe_tabung": "",
                "nomor_seri_tabung": "",
            },
            # Grounded exact serial from tube photo upgrades to MATCH.
            {
                "block_id": 1,
                "page": 1,
                "quote": "S/N: TB-112233",
                "merk_unit": "",
                "tipe_unit": "",
                "nomor_seri_unit": "",
                "merk_tabung": "",
                "tipe_tabung": "",
                "nomor_seri_tabung": "TB-112233",
            },
        ]
        with (
            patch("app.analysis.labels.storage.file_path", return_value=Path("missing_file")),
            patch("app.protection.llm.request_records", return_value=llm_response) as llm_mock,
        ):
            rows = _label_group(docs, app, {}, prefetched_pages=noisy_pages)

        llm_mock.assert_called_once()
        by_field = {r["field"]: r for r in rows}
        self.assertEqual(by_field["Alat 1: Merek Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["status"], "REVIEW")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["observed"], "M0del X-I00")
        self.assertEqual(by_field["Alat 1: Merek Tabung"]["status"], "REVIEW")
        self.assertEqual(by_field["Alat 1: Merek Tabung"]["observed"], "-")
        self.assertEqual(by_field["Alat 1: No. Seri Insersi Tabung"]["status"], "MATCH")
        self.assertIn("TB-112233", by_field["Alat 1: No. Seri Insersi Tabung"]["observed"])
        self.assertEqual(by_field["Alat 1: No. Seri Insersi Tabung"]["document_id"], docs[1]["id"])

    def test_llm_failure_marks_documents_uncacheable(self):
        from app.analysis.labels import _label_group

        app = self._sample_app()
        docs = self._docs()
        partial_pages = [
            {
                "source_id": docs[0]["id"],
                "source_name": docs[0]["filename"],
                "source_type": "pdf",
                "page": 1,
                "ocr": [{"text": "AcmeRay"}],
            }
        ]
        with (
            patch("app.analysis.labels.storage.file_path", return_value=Path("missing_file")),
            patch("app.protection.llm.request_records", side_effect=RuntimeError("offline")),
        ):
            rows = _label_group(docs, app, {}, prefetched_pages=partial_pages)

        self.assertTrue(all(d.get("_uncacheable") for d in docs))
        self.assertEqual(len(rows), 6)

    def test_swapped_model_string_rejected_for_merk(self):
        from app.analysis.labels import _label_group

        app = self._sample_app()
        docs = self._docs()[:1]
        pages = [
            {
                "source_id": docs[0]["id"],
                "source_name": docs[0]["filename"],
                "source_type": "pdf",
                "page": 1,
                "ocr": [{"text": "SN998877"}, {"text": "Model X100"}],
            }
        ]
        llm_resp = [
            {
                "block_id": 0,
                "page": 1,
                "quote": "Model X100",
                "merk_unit": "Model X100",
                "tipe_unit": "Model X100",
                "nomor_seri_unit": "",
                "merk_tabung": "",
                "tipe_tabung": "",
                "nomor_seri_tabung": "",
            }
        ]
        with (
            patch("app.analysis.labels.storage.file_path", return_value=Path("missing_file")),
            patch("app.protection.llm.request_records", return_value=llm_resp),
        ):
            rows = _label_group(docs, app, {}, prefetched_pages=pages)
        by_field = {r["field"]: r for r in rows}
        self.assertEqual(by_field["Alat 1: Merek Unit"]["observed"], "-")
        self.assertIn("Model X100", by_field["Alat 1: Tipe Unit"]["observed"])

    def test_rescue_extracts_embedded_pdf_white_sticker_text(self):
        from app.label_hybrid import rescue_label_pages

        img = Image.new("RGB", (600, 400), (20, 20, 20))
        draw = ImageDraw.Draw(img)
        draw.rectangle([120, 120, 480, 280], fill=(250, 250, 250))
        draw.text((150, 175), "SN: 987654", fill=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        pdf = pymupdf.open()
        page = pdf.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(50, 50, 545, 450), stream=buf.getvalue())
        pdf_bytes = pdf.tobytes()

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            Path(tmp.name).write_bytes(pdf_bytes)
            doc = {
                "id": "a" * 32,
                "app_id": "b" * 32,
                "sha256": "c" * 64,
                "filename": "embed.pdf",
                "category": "label",
            }
            pages = [
                {
                    "source_id": doc["id"],
                    "source_name": doc["filename"],
                    "source_type": "pdf",
                    "page": 1,
                    "ocr": [],
                }
            ]
            with patch("app.label_hybrid.storage.file_path", return_value=Path(tmp.name)):
                rescued = rescue_label_pages([doc], pages)
            texts = " ".join(r.get("text", "") for r in rescued[0]["ocr"])
            self.assertIn("987654", texts)

    def test_rescue_reads_upside_down_metallic_plate_and_tilted_text(self):
        from PIL import ImageFont
        from app.label_hybrid import rescue_label_pages

        # Build a synthetic upside-down metallic gray nameplate inside a PDF.
        img = Image.new("RGB", (720, 480), (145, 148, 150))
        draw = ImageDraw.Draw(img)
        draw.rectangle([180, 150, 540, 310], outline=(35, 35, 35), width=3)
        font = ImageFont.load_default(size=32)
        draw.text((210, 175), "Model # XZ900", fill=(20, 20, 20), font=font)
        draw.text((210, 235), "Serial # AB1234", fill=(20, 20, 20), font=font)
        rotated = img.rotate(180)
        buf = io.BytesIO()
        rotated.save(buf, format="PNG")

        pdf = pymupdf.open()
        page = pdf.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(50, 50, 545, 420), stream=buf.getvalue())
        pdf_bytes = pdf.tobytes()

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            Path(tmp.name).write_bytes(pdf_bytes)
            doc = {
                "id": "a" * 32,
                "app_id": "b" * 32,
                "sha256": "c" * 64,
                "filename": "metallic.pdf",
                "category": "label",
            }
            pages = [
                {
                    "source_id": doc["id"],
                    "source_name": doc["filename"],
                    "source_type": "pdf",
                    "page": 1,
                    "ocr": [],
                }
            ]
            with patch("app.label_hybrid.storage.file_path", return_value=Path(tmp.name)):
                rescued = rescue_label_pages([doc], pages)
            texts = " ".join(r.get("text", "") for r in rescued[0]["ocr"])
            self.assertIn("AB1234", texts)

    def test_cross_page_aggregation_and_type_ocr_ambiguity_and_stopword_filter(self):
        from app.analysis.labels import _label_group
        from app.label_hybrid import _is_sane_llm_value

        self.assertFalse(_is_sane_llm_value("tipe_unit", "EQUIPMENT"))
        self.assertFalse(_is_sane_llm_value("nomor_seri_unit", "2026/01/16"))
        self.assertFalse(_is_sane_llm_value("nomor_seri_tabung", "SN"))
        self.assertTrue(_is_sane_llm_value("nomor_seri_unit", "CD0719"))

        app = {
            "equipment": [
                {
                    "merk_unit": "OptiBrand",
                    "tipe_unit": "Alpha G5",
                    "nomor_seri_unit": "8877665",
                    "merk_tabung": "TubeMaker",
                    "tipe_tabung": "Insert X-9",
                    "nomor_seri_tabung": "99-11223",
                }
            ]
        }
        docs = self._docs()
        pages = [
            {
                "source_id": docs[0]["id"],
                "source_name": docs[0]["filename"],
                "source_type": "pdf",
                "page": 1,
                "ocr": [{"text": "OptiBrand", "confidence": 0.9}],
            },
            {
                "source_id": docs[0]["id"],
                "source_name": docs[0]["filename"],
                "source_type": "pdf",
                "page": 2,
                "ocr": [
                    {"text": "THIS EQUIPMENT", "confidence": 0.9},
                    {"text": "Alpha GS", "confidence": 0.8},
                    {"text": "SERIAL# 8877665", "confidence": 0.9},
                ],
            },
            {
                "source_id": docs[1]["id"],
                "source_name": docs[1]["filename"],
                "source_type": "image",
                "page": 1,
                "ocr": [{"text": "99-11223", "confidence": 0.95}],
            },
        ]
        llm_resp = [
            {
                "block_id": 1,
                "page": 2,
                "quote": "THIS EQUIPMENT\nAlpha GS",
                "merk_unit": "",
                "tipe_unit": "EQUIPMENT",
                "nomor_seri_unit": "",
                "merk_tabung": "",
                "tipe_tabung": "",
                "nomor_seri_tabung": "",
            }
        ]
        with (
            patch("app.analysis.labels.storage.file_path", return_value=Path("missing_file")),
            patch("app.protection.llm.request_records", return_value=llm_resp),
        ):
            rows = _label_group(docs, app, {}, prefetched_pages=pages)

        by_field = {r["field"]: r for r in rows}
        self.assertEqual(by_field["Alat 1: Merek Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["status"], "REVIEW")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["observed"], "Alpha GS")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["score"], 85.7)
        self.assertEqual(by_field["Alat 1: Merek Tabung"]["status"], "REVIEW")
        self.assertEqual(by_field["Alat 1: Merek Tabung"]["observed"], "-")
        self.assertIsNone(by_field["Alat 1: Merek Tabung"]["score"])
        self.assertEqual(by_field["Alat 1: Nomor Seri Unit"]["status"], "MATCH")
        self.assertEqual(by_field["Alat 1: No. Seri Insersi Tabung"]["status"], "MATCH")

    def test_labeled_partial_model_priority_and_symmetric_missing_doc_routing(self):
        from app.analysis.labels import _label_group

        docs = self._docs()
        app = {
            "equipment": [
                {
                    "merk_unit": "BrandZ Corp",
                    "tipe_unit": "Zeta 900 Alpha",
                    "nomor_seri_unit": "UNIT777",
                    "merk_tabung": "BrandZ Corp",
                    "tipe_tabung": "Tube Zeta 900",
                    "nomor_seri_tabung": "TUBE888",
                }
            ]
        }
        # Body text has "Alpha Zeta" (partial, unlabeled) while nameplate has "Model # Zeta900" (partial, labeled).
        # Missing tube fields must inherit docs[1] (proven via tube brand) rather than docs[0].
        pages = [
            {
                "source_id": docs[0]["id"],
                "source_name": docs[0]["filename"],
                "source_type": "pdf",
                "page": 1,
                "ocr": [
                    {"text": "Alpha Zeta", "confidence": 0.9},
                    {"text": "Model # Zeta900", "confidence": 0.85},
                    {"text": "Serial # UNIT777", "confidence": 0.95},
                ],
            },
            {
                "source_id": docs[1]["id"],
                "source_name": docs[1]["filename"],
                "source_type": "image",
                "page": 1,
                "ocr": [
                    {"text": "BrandZ", "confidence": 0.85},
                ],
            },
        ]
        with (
            patch("app.analysis.labels.storage.file_path", return_value=Path("missing_file")),
            patch("app.protection.llm.request_records", return_value=[]),
        ):
            rows = _label_group(docs, app, {}, prefetched_pages=pages)

        by_field = {r["field"]: r for r in rows}
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["status"], "REVIEW")
        self.assertEqual(by_field["Alat 1: Tipe Unit"]["observed"], "Zeta900")
        self.assertLess(by_field["Alat 1: Tipe Unit"]["score"], 100.0)
        # Missing tube fields must point to tube document docs[1]
        self.assertEqual(by_field["Alat 1: Tipe Tabung"]["observed"], "-")
        self.assertEqual(by_field["Alat 1: Tipe Tabung"]["document_id"], docs[1]["id"])
        self.assertEqual(by_field["Alat 1: No. Seri Insersi Tabung"]["observed"], "-")
        self.assertEqual(by_field["Alat 1: No. Seri Insersi Tabung"]["document_id"], docs[1]["id"])

        # Reversed case: unit serial is missing while tube serial is present -> missing unit field inherits docs[0].
        reversed_pages = [
            {
                "source_id": docs[0]["id"],
                "source_name": docs[0]["filename"],
                "source_type": "pdf",
                "page": 1,
                "ocr": [{"text": "Model # Zeta900", "confidence": 0.9}],
            },
            {
                "source_id": docs[1]["id"],
                "source_name": docs[1]["filename"],
                "source_type": "image",
                "page": 1,
                "ocr": [{"text": "S/N: TUBE888", "confidence": 0.95}],
            },
        ]
        with (
            patch("app.analysis.labels.storage.file_path", return_value=Path("missing_file")),
            patch("app.protection.llm.request_records", return_value=[]),
        ):
            rev_rows = _label_group(docs, app, {}, prefetched_pages=reversed_pages)
        rev_by_field = {r["field"]: r for r in rev_rows}
        self.assertEqual(rev_by_field["Alat 1: Nomor Seri Unit"]["observed"], "-")
        self.assertEqual(rev_by_field["Alat 1: Nomor Seri Unit"]["document_id"], docs[0]["id"])


if __name__ == "__main__":
    unittest.main()
