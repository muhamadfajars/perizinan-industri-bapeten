from __future__ import annotations

import re


from .. import storage


from .rows import _row, _text


def _evidence_span(raw, target, kind="name"):
    """Return an observed text span, NEVER a form-derived value.

    Conservative longest contiguous word-window search handles OCR line breaks
    and punctuation without hiding disagreement in serial numbers or names.
    """
    from difflib import SequenceMatcher

    clean = lambda v: re.sub(r"\s+", " ", str(v or "")).strip()
    text = clean(raw)
    expected = clean(target)
    if not expected or not text:
        return ""
    literal = re.search(re.escape(expected), text, re.I)
    if literal:
        return text[literal.start() : literal.end()]
    words = re.findall(r"[a-z0-9]+", expected.casefold())
    stop = {
        "dr",
        "sp",
        "rad",
        "rumah",
        "sakit",
        "jl",
        "jalan",
        "rt",
        "rw",
        "kel",
        "kec",
        "kab",
        "provinsi",
        "dokter",
    }
    keys = [w for w in words if len(w) >= 3 and w not in stop]
    if not keys:
        return ""
    options = []
    for original in str(raw).splitlines():
        line = clean(original)
        if not line or len(line) > 240:
            continue
        tokens = re.findall(r"[a-z0-9]+", line.casefold())
        if not tokens:
            continue
        overlap = sum(
            any(SequenceMatcher(None, k, w).ratio() >= 0.87 for w in tokens) for k in keys
        ) / len(keys)
        if overlap >= (0.74 if kind == "name" else 0.65):
            options.append((overlap, -len(line), line))
    if not options:
        return ""
    return max(options)[2]


def _role_evidence(raw, expected):
    """Professional title evidence must be present in source, not only candidate metadata."""
    text = str(raw or "")
    expected = _text(expected).casefold()
    patterns = []
    if any(x in expected for x in ("sp.rad", "radiologi", "dokter spesialis")):
        patterns = [
            r"(?i)\bdokter\s+spesialis\s+radiologi\b",
            r"(?i)\bsp\s*\.?\s*rad\b",
        ]
    elif "radiograf" in expected:
        patterns = [r"(?i)\bradiografer(?:\s+level\s*\d+)?\b", r"(?i)\bradiografi\b"]
    elif "proteksi radiasi" in expected or "ppr" in expected:
        patterns = [
            r"(?i)\bpetugas\s+proteksi\s+radiasi\b",
            r"(?i)\bppr\s+medik(?:\s+tk\.?\s*\d+)?",
        ]
    else:
        return _evidence_span(text, expected, "role")
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0)
    return ""


def _expiry_expected(person, parsed_expiry):
    if isinstance(person, dict):
        for key in (
            "masa_berlaku_sip",
            "masa_berlaku_sib",
            "masa_berlaku",
            "tanggal_berlaku",
            "expiry_date",
        ):
            if person.get(key):
                return _text(person[key])
    return "Masa berlaku izin"


def _format_personnel_rows(parsed, validation, app, doc):
    """Build personnel result rows from field comparisons."""
    from ..personnel_results import _unified_personnel_table

    dtype = _text(validation.get("document_type") or parsed.get("document_type")).upper()
    if dtype in ("SIP", "SIB", "SPRINT"):
        original = _unified_personnel_table(validation, dtype, parsed.get("text") or "")
        rows = []
        for x in original:
            score = x.get("Skor")
            try:
                score = (
                    float(str(score).strip().rstrip("%")) if score not in ("-", "—", None) else None
                )
            except (ValueError, TypeError):
                score = None
            label = x["Field"]
            row = _row(
                label,
                x.get("Formulir"),
                x.get("Dokumen"),
                x.get("Status"),
                score,
                document_id=doc["id"],
            )
            if label == "Pengesahan":
                row["detail"] = {
                    "type": "approval",
                    "pages": [1],
                    "heading": "Pengesahan " + dtype,
                }
                row["note"] = "Periksa tanda tangan atau stempel pada PDF asli"
            rows.append(row)
        return rows
    if isinstance(validation.get("fields"), list):
        return [
            _row(
                x.get("field"),
                x.get("expected"),
                x.get("observed"),
                x.get("status", "REVIEW"),
                x.get("score"),
                document_id=doc["id"],
            )
            for x in validation["fields"]
        ]
    return [
        _row(
            "Jenis Dokumen",
            dtype,
            "",
            "REVIEW",
            document_id=doc["id"],
            note=validation.get("reason") or "Jenis tidak dikenali",
        )
    ]


def _personnel(doc, app, ref):
    """Extract and validate personnel documents by subtype."""
    from src.extraction.personnel_document import (
        ocr_personnel_documents,
        parse_personnel_documents,
    )
    from src.matching.personnel_document_matcher import validate_personnel_documents

    pages = ocr_personnel_documents(
        [
            {
                "path": str(storage.file_path(doc)),
                "name": doc["filename"],
                "source_id": doc["id"],
            }
        ]
    )
    parsed = parse_personnel_documents(pages)
    kinds = {
        "Surat Izin Praktik (SIP)": "SIP",
        "Surat Izin Bekerja (SIB)": "SIB",
        "Surat Perintah": "SPRINT",
        "Sertifikat Kompetensi": "COMPETENCE",
        "Surat Izin Kerja": "WORK_PERMIT",
        "Surat Keterangan Kerja": "WORK_LETTER",
        "Surat Penunjukan Tugas": "ASSIGNMENT",
        "Evaluasi Dosis": "DOSE",
        "Evaluasi Dosis / Zero Check": "DOSE",
    }
    subtype = _text(doc.get("subtype"))
    for source in parsed:
        if subtype in kinds:
            source["document_type"] = kinds[subtype]
    matches = validate_personnel_documents(parsed, app)
    results = []
    for source, match in zip(parsed, matches):
        results.extend(_format_personnel_rows(source, match.get("validation") or {}, app, doc))
    return results or [
        _row(
            "Dokumen Personel",
            "Bukti identitas/masa berlaku",
            "",
            "REVIEW",
            note="Tidak ada bukti terbaca",
            document_id=doc["id"],
        )
    ]
