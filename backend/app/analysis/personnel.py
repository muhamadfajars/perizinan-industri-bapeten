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
    if dtype in ("SIB", "SPRINT"):
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
                approval_pages = [
                    p.get("page")
                    for p in (parsed.get("pages") or [])
                    if isinstance(p, dict) and isinstance(p.get("page"), int) and p.get("page") > 0
                ]
                row["detail"] = {
                    "type": "approval",
                    "pages": approval_pages[:1] or [1],
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


_SUBTYPE_CANONICAL = {
    "Sertifikat Kompetensi": "Sertifikat Kompetensi PPR",
    "Evaluasi Dosis": "Evaluasi Dosis / Zero Check",
    "Surat Perintah": "Surat Penugasan / Keterangan Kerja",
    "Surat Keterangan Kerja": "Surat Penugasan / Keterangan Kerja",
    "Surat Penunjukan Tugas": "Surat Penugasan / Keterangan Kerja",
}


def _page_text_for_classification(page_data: dict) -> str:
    parts = []
    native = _text(page_data.get("native_text"))
    if native:
        parts.append(native)
    ocr_lines = [
        _text(line.get("text")) if isinstance(line, dict) else _text(line)
        for line in (page_data.get("ocr") or [])
    ]
    ocr_joined = "\n".join(line for line in ocr_lines if line)
    if ocr_joined:
        parts.append(ocr_joined)
    return "\n".join(parts)


def _scope_personnel_pages(pages: list[dict], target_subtype: str) -> list[dict]:
    """Filter bundled multi-subtype personnel pages to pages matching `target_subtype`."""
    from ..classifier import classify_by_content

    target = _SUBTYPE_CANONICAL.get(target_subtype, target_subtype)
    current_sub: str | None = None
    tagged: list[tuple[str | None, dict]] = []
    observed_subtypes: set[str] = set()
    for page_data in pages:
        cat, sub, _ = classify_by_content(_page_text_for_classification(page_data))
        if cat == "personel" and sub:
            current_sub = _SUBTYPE_CANONICAL.get(sub, sub)
            observed_subtypes.add(current_sub)
        tagged.append((current_sub, page_data))
    if len(observed_subtypes) < 2:
        return pages
    scoped = [page_data for sub, page_data in tagged if sub == target]
    return scoped or pages


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
    if not doc.get("_virtual_extra") and "_observed_pages" not in doc:
        doc["_observed_pages"] = [
            (
                p.get("page") if isinstance(p.get("page"), int) and p.get("page") > 0 else idx + 1,
                _page_text_for_classification(p),
            )
            for idx, p in enumerate(pages)
            if isinstance(p, dict)
        ]
    subtype = _text(doc.get("subtype"))
    is_multi_personnel = bool(doc.get("_virtual_extra")) or any(
        isinstance(e, dict) and e.get("category") == "personel"
        for e in (doc.get("extra_categories") or [])
    )
    if is_multi_personnel and subtype and len(pages) > 1:
        pages = _scope_personnel_pages(pages, subtype)
    parsed = parse_personnel_documents(pages)
    kinds = {
        "Surat Izin Bekerja (SIB)": "SIB",
        "Surat Penugasan / Keterangan Kerja": "ASSIGNMENT",
        "Surat Perintah": "ASSIGNMENT",
        "Sertifikat Kompetensi": "COMPETENCE",
        "Sertifikat Kompetensi PPR": "COMPETENCE",
        "Sertifikat Pelatihan": "TRAINING",
        "Surat Keterangan Kerja": "ASSIGNMENT",
        "Surat Penunjukan Tugas": "ASSIGNMENT",
        "Evaluasi Dosis": "DOSE",
        "Evaluasi Dosis / Zero Check": "DOSE",
    }
    for source in parsed:
        if subtype in kinds:
            source["document_type"] = kinds[subtype]
    matches = validate_personnel_documents(parsed, app)
    results = []
    from ..personnel_policy import conditional_rows
    from ..personnel_semantic import enrich

    for source, match in zip(parsed, matches):
        original = _format_personnel_rows(source, match.get("validation") or {}, app, doc)
        rows = conditional_rows(source, original, app, doc)
        results.extend(enrich(source, rows, app, doc))
    return results or [
        _row(
            "Nama",
            "Nama petugas pada formulir",
            "",
            "REVIEW",
            note="Tidak ada bukti terbaca",
            document_id=doc["id"],
        )
    ]
