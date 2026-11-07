import re
from rapidfuzz import fuzz
from .label_normalization import compact_text, serial_ocr_ambiguity


def _label_kind(text):
    text = str(text or "").strip()
    if re.search(
        r"^(?:INSERTION\s+TUB[EI]|INSERT\s+MODEL|TUBE\s+MODEL|X[- ]?RAY\s+TUBE)\s*:",
        text,
        re.I,
    ):
        return "tabung"
    if re.search(r"^(?:GENERATOR|UNIT\s+MODEL|MODEL\s+X[- ]?RAY\s+UNIT)\s*:", text, re.I):
        return "unit"
    return None


def _extract_scoped_fields(page_data):
    """Extract explicit field-labeled evidence, preserving OCR provenance.

    Do not guess serials from arbitrary bare alphanumeric strings; an unmatched
    field without contextual evidence must remain REVIEW.
    """
    grouped = {}
    for row in page_data.get("ocr", []):
        grouped.setdefault(str(row.get("variant") or "original"), []).append(row)
    found = {
        "unit": {"manufacturer": [], "type": [], "serial_number": []},
        "tabung": {"manufacturer": [], "type": [], "serial_number": []},
    }
    for variant, rows in grouped.items():
        section = "unit"
        for ix, row in enumerate(rows):
            raw = str(row.get("text") or "").strip()
            if not raw:
                continue
            heading = _label_kind(raw)
            if heading:
                section = heading
            kind = None
            val = None
            m = re.match(r"^\s*(?:BRAND|MANUFACTURER|MAKE|MERK)\s*[:#-]\s*(.+)$", raw, re.I)
            if m:
                kind, val = "manufacturer", m.group(1).strip()
            m = re.match(
                r"^\s*(?:INSERT\s+MODEL|UNIT\s+MODEL|MODEL|TYPE|TIPE)\s*[:#-]\s*(.+)$",
                raw,
                re.I,
            )
            if m:
                kind, val = "type", m.group(1).strip()
            m = re.match(
                r"^\s*(?:SER(?:IAL)?\.?\s*NO\.?|SERIAL(?:\s+NUMBER)?|S\s*/\s*N|SN)\s*[:#.\-]?\s*(.+)$",
                raw,
                re.I,
            )
            if m:
                kind, val = "serial_number", m.group(1).strip()
            if not kind:
                # Two OCR boxes: 'SER NO' followed by actual serial.
                if re.match(r"^\s*(?:SER(?:IAL)?\.?\s*NO\.?|SN)\s*[:#.\-]?\s*$", raw, re.I):
                    if ix + 1 < len(rows):
                        nxt = str(rows[ix + 1].get("text") or "").strip()
                        if re.fullmatch(r"[A-Za-z0-9-]{4,30}", nxt):
                            kind, val = "serial_number", nxt
            if not kind or not val:
                continue
            value = val.strip()
            if kind == "manufacturer":
                if len(value) > 65 or not re.search(r"[A-Za-z]{2}", value):
                    continue
            elif kind == "serial_number":
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-/ ]{2,35}", value):
                    continue
            elif kind == "type":
                if len(value) > 65:
                    continue
            record = {
                "value": value,
                "raw": raw,
                "variant": variant,
                "confidence": float(row.get("confidence") or 0),
                "box": row.get("box"),
            }
            found[section][kind].append(record)
    return found


def _negative_field(expected, old, candidates, kind, meta):
    if old.get("status") == "MATCH" or not expected:
        return old
    if not candidates:
        return {
            "status": "REVIEW",
            "expected": expected,
            "evidence": None,
            "score": None,
            "reason": "Nilai field tidak teridentifikasi dengan yakin",
            **meta,
        }
    # A field-specific alternative is useful evidence, but cannot be selected
    # by fuzzy similarity to the submitted form. Prefer OCR agreement and trust.
    by_value = {}
    for x in candidates:
        norm = compact_text(x["value"])
        if norm:
            by_value.setdefault(norm, []).append(x)
    if not by_value:
        return {
            "status": "REVIEW",
            "expected": expected,
            "evidence": None,
            "score": None,
            **meta,
        }
    expected_compact = compact_text(expected)
    for key, group in by_value.items():
        if key == expected_compact:
            best = max(group, key=lambda x: x["confidence"])
            return {
                "status": "MATCH",
                "expected": expected,
                "evidence": best["value"],
                "score": 100.0,
                "variant": best["variant"],
                "box": best["box"],
                **meta,
            }
    ranked = sorted(
        by_value.values(),
        key=lambda g: (len({r["variant"] for r in g}), max(r["confidence"] for r in g)),
        reverse=True,
    )
    group = ranked[0]
    best = max(group, key=lambda x: x["confidence"])
    val = best["value"]
    if kind == "serial_number":
        ambiguous = serial_ocr_ambiguity(expected, val)
    else:
        ambiguous = serial_ocr_ambiguity(expected, val) if kind == "type" else False
    # If candidate text could be a misread form value, conservative REVIEW.
    uncertain = ambiguous or (len(ranked) > 1 and len({r["variant"] for r in group}) < 2)
    status = "REVIEW" if uncertain else "MISMATCH"
    return {
        "status": status,
        "expected": expected,
        "evidence": val,
        "score": round(fuzz.ratio(expected_compact, compact_text(val)), 1),
        "variant": best["variant"],
        "box": best["box"],
        "reason": "Nilai alternatif diperoleh dari label field dokumen",
        **meta,
    }


def _empty(expected, meta, mismatch=False):
    return {
        "status": "MISMATCH" if mismatch else "REVIEW",
        "expected": expected,
        "evidence": None,
        "score": None,
        "components": [],
        "reason": (
            "Identitas dokumen bertentangan; field tidak ditemukan"
            if mismatch
            else "Field tidak ditemukan pada label"
        ),
        **meta,
    }


def _usable_labeled_candidates(candidates, kind):
    # Only records extracted from an explicit label, never arbitrary fuzzy snippets.
    vals = {}
    for rec in candidates:
        key = compact_text(rec.get("value"))
        if key:
            vals.setdefault(key, []).append(rec)
    return vals


def _document_unit_brands(document_ocr):
    """Find independently labeled manufacturer evidence, never fuzzy evidence.

    Accept explicit unit BRAND/MANUFACTURER labels or a named company on the
    equipment label. Reject importers, addresses, and tube manufacturers.
    """
    groups = {}
    for page in document_ocr or []:
        rows_by_variant = {}
        for row in page.get("ocr", []):
            rows_by_variant.setdefault(str(row.get("variant") or "original"), []).append(row)
        for variant, rows in rows_by_variant.items():
            scope = "unit"
            for row in rows:
                raw = str(row.get("text") or "").strip()
                if not raw:
                    continue
                heading = _label_kind(raw)
                if heading:
                    scope = heading
                if scope != "unit":
                    continue
                brand = None
                m = re.match(r"^\s*(?:BRAND|MANUFACTURER|MAKE|MERK)\s*[:#-]\s*(.+)", raw, re.I)
                if m:
                    brand = m.group(1).strip()
                elif not re.search(
                    r"\b(?:IMPORTED|DISTRIBUTED|AUSTRALIA\s+BY|ADDRESS)\b", raw, re.I
                ):
                    # Company designation is evidence of a manufacturer's name
                    # even on labels without a BRAND: row (e.g., Fujifilm).
                    m = re.match(
                        r"^\s*([A-Za-z][\w.&\- ]{2,55}?)\s+(?:CORPORATION|CORP\.?|INC\.?|LTD\.?|CO\.?\s*,?\s*LTD\.?)\b",
                        raw,
                        re.I,
                    )
                    if m:
                        brand = m.group(1).strip()
                if not brand:
                    continue
                # Keep only a credible name, not a whole address or instruction.
                brand = re.sub(r"\s+", " ", brand).strip()
                norm = compact_text(brand)
                if len(norm) < 4 or len(norm) > 35:
                    continue
                groups.setdefault(norm, {"value": brand, "variants": set(), "evidence": []})
                groups[norm]["variants"].add(variant)
                groups[norm]["evidence"].append(
                    {
                        "text": raw,
                        "variant": variant,
                        "page": page.get("page"),
                        "source_id": page.get("source_id"),
                    }
                )
    return groups


def _identity_conflict(document_ocr, expected):
    expected_brand = compact_text(expected.get("unit", {}).get("manufacturer"))
    groups = _document_unit_brands(document_ocr)
    if not expected_brand or not groups:
        return None
    # One preprocessing output does not prove an unfamiliar brand; demand OCR
    # agreement across at least two variants to reject a whole document.
    reliable = [g for g in groups.values() if len(g["variants"]) >= 2]
    if not reliable:
        return None
    # A confirmed occurrence of the form brand vetoes the global rejection.
    if any(compact_text(g["value"]) == expected_brand for g in reliable):
        return None
    # Multiple independently recognized brands may belong to different units
    # on a mixed scan, so do not declare the complete document incorrect.
    if len({compact_text(g["value"]) for g in reliable}) != 1:
        return None
    return reliable[0]


def _document_rejection(document_ocr, expected):
    gate = _identity_conflict(document_ocr, expected)
    if gate is None:
        return None
    # Require absence of an exact expected UNIT brand on the label. Keep mixed
    # brand equipment sets out of blanket rejections.
    unit_brand = compact_text(expected.get("unit", {}).get("manufacturer"))
    for page in document_ocr:
        for row in page.get("ocr", []):
            line = str(row.get("text", ""))
            if unit_brand and re.search(
                r"(?<![A-Z0-9])" + re.escape(unit_brand) + r"(?![A-Z0-9])",
                compact_text(line),
            ):
                return None
    return gate
