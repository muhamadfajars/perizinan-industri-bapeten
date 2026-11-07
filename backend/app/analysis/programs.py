from __future__ import annotations

import re


from .. import storage


from .rows import _from_match, _row, _text
from .equipment import _absent_value
from .constants import FIELDS, PROG, SUPP


def _program(doc, app, ref):
    from src.extraction.program_documents import analyze

    kind = PROG[doc["category"]]
    raw = analyze(str(storage.file_path(doc)), kind, ref)
    rows = [
        _from_match("Nama Fasilitas", ref["nama_fasilitas"], raw.get("hospital"), doc["id"]),
        _from_match("Alamat Fasilitas", ref["alamat_proyek"], raw.get("address"), doc["id"]),
    ]
    ap = raw.get("approval") or {}
    proof = (ap.get("evidence") or [{}])[0]
    rows.append(
        _row(
            "Lembar Pengesahan",
            "Keberadaan halaman berjudul Lembar Pengesahan",
            f"PDF halaman {proof.get('page')}" if proof.get("page") else "",
            ap.get("status", "REVIEW"),
            100 if ap.get("status") == "MATCH" else None,
            proof.get("page"),
            "Halaman pengesahan ditemukan; tanda tangan/stempel tetap diperiksa secara visual",
            doc["id"],
            proof.get("quote"),
            {
                "type": "approval",
                "pages": [
                    x.get("page") for x in ap.get("evidence", []) if isinstance(x.get("page"), int)
                ],
                "heading": "Lembar Pengesahan",
            },
        )
    )
    if doc["category"] == "perawatan":
        maintenance = raw.get("maintenance") or {}
        secs = maintenance.get("section") or []
        sec = secs[0] if secs else {}
        rows.append(
            _row(
                "Klausul Uji Kesesuaian",
                "Subbab Uji Kesesuaian",
                "Ditemukan" if sec else "",
                "MATCH" if sec and sec.get("frequencies") and sec.get("parameters") else "REVIEW",
                100 if sec and sec.get("frequencies") and sec.get("parameters") else None,
                sec.get("page"),
                "Subbab terbaca lintas halaman; periksa rincian di bawah tabel",
                doc["id"],
                detail={
                    "type": "maintenance",
                    "pages": sec.get("source_pages") or ([sec["page"]] if sec.get("page") else []),
                    "heading": sec.get("heading") or "Uji Kesesuaian",
                    "frequencies": sec.get("frequencies") or [],
                    "parameters": sec.get("parameters") or [],
                },
            )
        )
    if doc["category"] == "proteksi":
        for p in raw.get("personnel") or []:
            rows.append(
                _row(
                    "Petugas: " + _text(p.get("name")),
                    p.get("name"),
                    p.get("observed"),
                    p.get("status"),
                    p.get("score"),
                    ((p.get("evidence") or [{}])[0]).get("page"),
                    document_id=doc["id"],
                )
            )
    for i, group in enumerate(raw.get("equipment") or [], 1):
        for field in group:
            if field.get("field") not in FIELDS:
                continue
            ev = (field.get("evidence") or [{}])[0]
            rows.append(
                _row(
                    f"Alat {i}: {field.get('label_override') or FIELDS[field['field']]}",
                    field.get("expected"),
                    field.get("observed"),
                    field.get("status"),
                    field.get("score"),
                    ev.get("page"),
                    field.get("reason") or "",
                    doc["id"],
                    ev.get("quote"),
                )
            )
    return rows


def _supp(doc, app, ref):
    from src.extraction.supplementary_matching import analyze

    raw = analyze(str(storage.file_path(doc)), SUPP[doc["category"]], ref)
    rows = []
    for x in raw.get("rows") or []:
        evidence = (x.get("evidence") or [{}])[0]
        page = x.get("page") or evidence.get("page")
        is_approval = "pengesahan" in _text(x.get("field")).casefold()
        field_name = _text(x.get("field"))
        status = x.get("status")
        score = x.get("score")
        # A model suffix is material, never silently accept E7894X as E7894.
        if "tipe" in field_name.lower() and (x.get("expected") and x.get("observed")):
            from src.matching.import_approval_matcher import compare_field

            kind = "tipe_tabung" if "tabung" in field_name.lower() else "tipe_unit"
            check = compare_field(kind, x["expected"], x["observed"])
            if check["status"] == "MISMATCH":
                status = "MISMATCH"
                score = check["score"]
        # Paparan / kebocoran: compare only equipment fields evidenced in this document.
        # Keep facility and approval checks even when absent: their completeness matters.
        # A literal dash, null or empty OCR reading is not evidence of a mismatch.
        if (
            doc["category"] in ("paparan", "kebocoran")
            and re.match(r"(?i)^\s*alat\s*\d+\s*:", field_name)
            and _absent_value(x.get("observed"))
        ):
            continue
        rows.append(
            _row(
                x.get("field"),
                x.get("expected"),
                x.get("observed"),
                status,
                score,
                page,
                x.get("reason") or "",
                doc["id"],
                x.get("quote") or evidence.get("quote"),
                {
                    "type": "approval",
                    "pages": [page] if isinstance(page, int) and page > 0 else [],
                    "heading": "Pengesahan Dokumen",
                }
                if is_approval
                else None,
            )
        )
    return rows
