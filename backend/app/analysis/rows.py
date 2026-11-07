from __future__ import annotations

import re, time


from ..identity_policy import address_decision, clean_evidence, facility_decision

from ..unit_model import decide as _unit_decision


def _text(value):
    return str(value).strip() if value is not None else ""


def _status(v):
    s = _text(v).upper()
    return {
        "VALID": "MATCH",
        "ACTIVE": "MATCH",
        "DETECTED": "MATCH",
        "INCOMPLETE": "MISSING",
        "EXPIRED": "MISMATCH",
    }.get(s, s if s in {"MATCH", "REVIEW", "MISMATCH", "MISSING"} else "REVIEW")


def _row(
    field,
    expected,
    observed="",
    status="REVIEW",
    score=None,
    page=None,
    note="",
    document_id=None,
    quote="",
    detail=None,
):
    note = _text(note).replace(
        "v43_address_components",
        "Alamat dibandingkan berdasarkan komponen alamat yang terbaca pada dokumen.",
    )
    if re.search(r"(?i)alamat|tempat praktik", _text(field)):
        from ..address_cleanup import clean_address_evidence

        observed = clean_evidence(clean_address_evidence(observed), "address")
        status, score, address_note = address_decision(expected, observed, _status(status), score)
        if address_note:
            note = (" ".join(filter(None, [_text(note), address_note])))[:300]
    elif re.match(r"(?i)^nama\s+(?:fasilitas|rumah\s+sakit|rs|instansi)\b", _text(field)):
        observed = clean_evidence(observed, "facility")
        status, score, facility_note = facility_decision(expected, observed, _status(status), score)
        if facility_note:
            note = (" ".join(filter(None, [_text(note), facility_note])))[:300]
    # v068: only Tipe Unit; NEVER change Merek Unit, Tipe Tabung or serials.
    status, score, model_note = _unit_decision(field, expected, observed, _status(status), score)
    if model_note:
        note = (" ".join(filter(None, [_text(note), model_note])))[:300]
    return {
        "id": f"f{int(time.time_ns())}-{abs(hash((field, expected, observed))) % 99999}",
        "field": _text(field),
        "expected": _text(expected) or "—",
        "observed": _text(observed) or "—",
        "status": _status(status),
        "score": round(float(score), 1) if isinstance(score, (int, float)) else None,
        "page": page if isinstance(page, int) and page > 0 else None,
        "note": _text(note)[:300],
        "document_id": document_id,
        "quote": _text(quote)[:380],
        "detail": detail if isinstance(detail, dict) else None,
    }


def _from_match(field, expected, matcher, doc_id=None):
    m = matcher or {}
    ev = (m.get("evidence") or [{}])[0] if isinstance(m.get("evidence"), list) else {}
    return _row(
        field,
        expected,
        m.get("observed") or m.get("actual") or m.get("value"),
        m.get("status", "REVIEW"),
        m.get("score"),
        ev.get("page") or m.get("page"),
        m.get("reason") or m.get("method", ""),
        doc_id,
        ev.get("quote", ""),
    )
