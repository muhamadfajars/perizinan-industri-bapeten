from __future__ import annotations

import re


from .. import storage

from ..identity_policy import (
    address_decision,
    facility_decision,
    candidate_lines,
    select_candidate,
)


from .rows import _text
from .constants import NAMES


def _document_text_pages(doc):
    """Read existing searchable source only, never launch another OCR job.

    Missing text layer = do not guess / retain original extracted evidence.
    """
    try:
        path = storage.file_path(doc)
        ext = path.suffix.lower()
        if ext == ".pdf":
            import fitz

            with fitz.open(str(path)) as pdf:
                return [(i + 1, pdf[i].get_text(sort=True)) for i in range(min(len(pdf), 8))]
        if ext == ".docx":
            from docx import Document

            d = Document(str(path))
            fragments = [p.text for p in d.paragraphs]
            for table in d.tables:
                for row in table.rows[:80]:
                    fragments.append(" | ".join(c.text for c in row.cells))
            return [(None, "\n".join(fragments))]
    except (OSError, ValueError, ImportError):
        return []
    return []


def _identity_postprocess(rows, doc):
    """Replace ONLY with stronger on-document, labeled evidence.

    Every changed value has document page/quote provenance. A new score is
    recalculated for the new observation, never reused from an old candidate.
    """
    targets = [
        r
        for r in rows
        if isinstance(r, dict)
        and (
            re.search(r"(?i)alamat|tempat\s+praktik", _text(r.get("field")))
            or re.match(
                r"(?i)^nama\s+(?:fasilitas|rumah\s+sakit|rs|instansi)\b",
                _text(r.get("field")),
            )
        )
    ]
    if not targets:
        return rows
    pages = _document_text_pages(doc)
    if not pages:
        return rows
    discovered = {
        "address": candidate_lines(pages, "address"),
        "facility": candidate_lines(pages, "facility"),
    }
    for r in targets:
        kind = (
            "address"
            if re.search(r"(?i)alamat|tempat\s+praktik", _text(r.get("field")))
            else "facility"
        )
        expected = r.get("expected")
        original = r.get("observed")
        candidate = select_candidate(discovered[kind], expected, kind, original)
        if not candidate:
            continue
        value = candidate["value"]
        if kind == "address":
            status, score, note = address_decision(
                expected, value, r.get("status"), candidate["score"]
            )
        else:
            status, score, note = facility_decision(
                expected, value, r.get("status"), candidate["score"]
            )
        # Do not promote a missing or weak identity based only on superficial similarity.
        if kind == "address" and status != "MATCH" and r.get("status") == "MATCH":
            continue
        if kind == "facility" and not value:
            continue
        r["observed"] = value
        r["score"] = round(score, 1) if isinstance(score, (int, float)) else None
        r["status"] = status
        if isinstance(candidate.get("page"), int):
            r["page"] = candidate["page"]
        r["quote"] = candidate.get("quote", "")[:380]
        r["note"] = (
            " ".join(x for x in (note, "Bukti identitas: baris sumber yang ditandai") if x)
        )[:300]
    return rows


def _personnel_title(doc):
    """Only use trusted uploader subtype, never the uploaded filename."""
    if doc.get("category") != "personel":
        return NAMES.get(doc.get("category"), "Dokumen")
    subtype = _text(doc.get("subtype"))
    titles = {
        "Surat Izin Praktik (SIP)": "SIP",
        "Surat Izin Bekerja (SIB)": "SIB",
        "Surat Perintah": "Surat Perintah",
        "Sertifikat Kompetensi": "Sertifikat Kompetensi",
        "Surat Izin Kerja": "Surat Izin Kerja",
        "Surat Keterangan Kerja": "Surat Keterangan Kerja",
        "Surat Penunjukan Tugas": "Surat Penunjukan Tugas",
        "Evaluasi Dosis": "Evaluasi Dosis",
        "Evaluasi Dosis / Zero Check": "Evaluasi Dosis / Zero Check",
    }
    title = titles.get(subtype)
    return f"Dokumen Personel - {title}" if title else NAMES["personel"]


def _pdf_approval_page(doc):
    """Locate a display page, not signature validity, without additional OCR.

    Prefer an actual heading or signature context over blindly displaying the
    whole PDF. One-page PDF can safely display its only physical page.
    Multi-page scanned PDF without provenance remains unlocated (never guess).
    """
    try:
        from .. import storage
        import fitz

        path = storage.file_path(doc)
        if path.suffix.lower() != ".pdf":
            return None
        with fitz.open(str(path)) as pdf:
            if len(pdf) == 1:
                return 1
            chosen = None
            for i in range(min(len(pdf), 35)):
                txt = pdf[i].get_text(sort=True)
                if re.search(r"(?i)\bdaftar\s+isi\b", txt[:1000]):
                    continue
                if re.search(r"(?i)\b(?:lembar|halaman)\s+pengesahan\b", txt):
                    return i + 1
                if re.search(
                    r"(?i)\b(?:ditandatangani\s+(?:secara|oleh)|disahkan\s+oleh|menyetujui\s*:)\b",
                    txt,
                ):
                    chosen = i + 1
            return chosen
    except Exception:
        return None


def _postprocess_evidence(rows, doc):
    """Ensure every approval row can show existing evidence via one-page preview.

    MATCH indicates a textual/detector decision, NOT a verified signature.
    No OCR is repeated, even on scanned docs.
    """
    approval_rows = [
        r
        for r in rows
        if isinstance(r, dict)
        and re.search(r"(?i)\b(?:pengesahan|tanda\s+tangan)\b", _text(r.get("field")))
    ]
    if not approval_rows:
        return rows
    needs_page = any(
        not (r.get("detail") or {}).get("pages") and not r.get("page") for r in approval_rows
    )
    fallback_page = _pdf_approval_page(doc) if needs_page else None
    for r in approval_rows:
        detail = r.get("detail") if isinstance(r.get("detail"), dict) else {}
        pages = [p for p in (detail.get("pages") or []) if isinstance(p, int) and p > 0]
        if not pages:
            p = r.get("page")
            if isinstance(p, int) and p > 0:
                pages = [p]
            elif fallback_page:
                pages = [fallback_page]
        r["detail"] = {
            **detail,
            "type": "approval",
            "pages": pages,
            "heading": detail.get("heading") or "Bukti Pengesahan",
        }
        if pages and not r.get("page"):
            r["page"] = pages[0]
        if not pages and _text(doc.get("filename")).lower().endswith(".docx"):
            r["note"] = "Bukti pengesahan dokumen Word perlu diverifikasi secara visual."
    return rows
