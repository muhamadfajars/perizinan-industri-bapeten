import re
from rapidfuzz import fuzz
from .label_normalization import compact_text, serial_ocr_ambiguity
from .label_candidates import get_source_metadata
from .label_fields import score_field_status
from .label_pages import select_best_source_page, summarize_guided_result
from .label_identity import (
    _document_rejection,
    _empty,
    _extract_scoped_fields,
    _identity_conflict,
    _negative_field,
    _usable_labeled_candidates,
)


def _match_base_document(
    document_ocr,
    expected,
):
    unit_expected = expected.get(
        "unit",
        {},
    )

    tube_expected = expected.get(
        "tabung",
        {},
    )

    unit_match = select_best_source_page(
        document_ocr,
        unit_expected,
    )

    tube_match = select_best_source_page(
        document_ocr,
        tube_expected,
    )

    result = {
        "unit": {
            "selected_source_id": unit_match["source_id"],
            "selected_source_name": unit_match["source_name"],
            "selected_page": unit_match["page"],
            "page_score": unit_match["score"],
            "manufacturer": unit_match["fields"]["manufacturer"],
            "type": unit_match["fields"]["type"],
            "serial_number": unit_match["fields"]["serial_number"],
            "candidate_scores": unit_match["candidate_scores"],
        },
        "tabung": {
            "selected_source_id": tube_match["source_id"],
            "selected_source_name": tube_match["source_name"],
            "selected_page": tube_match["page"],
            "page_score": tube_match["score"],
            "manufacturer": tube_match["fields"]["manufacturer"],
            "type": tube_match["fields"]["type"],
            "serial_number": tube_match["fields"]["serial_number"],
            "candidate_scores": tube_match["candidate_scores"],
        },
    }

    # Optional trace: compare displayed evidence with actual OCR variants.
    import os as _label_os

    if _label_os.environ.get("BAPETEN_LABEL_OCR_DEBUG", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        for _sec in ("unit", "tabung"):
            for _field in ("manufacturer", "type", "serial_number"):
                _entry = result.get(_sec, {}).get(_field, {})
                _evidence = _entry.get("evidence")
                if _evidence is None:
                    _comps = _entry.get("components", [])
                    _evidence = [_c.get("evidence") for _c in _comps]
                print(
                    f"[LABEL-MATCH] {_sec}.{_field}: {_entry.get('status')} | expected={_entry.get('expected')} | evidence={_evidence}",
                    flush=True,
                )

    result["summary"] = summarize_guided_result(result)

    result["matching_score"] = max(
        0,
        unit_match["score"],
    ) + max(
        0,
        tube_match["score"],
    )

    return result


def _match_scoped_document(document_ocr, expected):
    result = _match_base_document(document_ocr, expected)
    for section in ("unit", "tabung"):
        chosen = result[section]
        page_data = next(
            (
                p
                for p in document_ocr
                if p.get("source_id") == chosen.get("selected_source_id")
                and p.get("page") == chosen.get("selected_page")
            ),
            None,
        )
        if page_data is None:
            continue
        extracted = _extract_scoped_fields(page_data)
        meta = get_source_metadata(page_data)
        for field in ("manufacturer", "type", "serial_number"):
            chosen[field] = _negative_field(
                expected.get(section, {}).get(field),
                chosen.get(field, {}),
                extracted[section][field],
                field,
                meta,
            )
    result["summary"] = summarize_guided_result(result)
    result["matching_score"] = sum(
        score_field_status(
            result[section][field],
            {"serial_number": 5, "type": 3, "manufacturer": 2}[field],
            {"serial_number": 3, "type": 1, "manufacturer": 0.5}[field],
        )
        for section in ("unit", "tabung")
        for field in ("manufacturer", "type", "serial_number")
    )
    return result


def _match_missing_fields(document_ocr, expected):
    result = _match_scoped_document(document_ocr, expected)
    available = {}
    decisive = []
    for section in ("unit", "tabung"):
        choice = result[section]
        source = next(
            (
                p
                for p in document_ocr
                if p.get("source_id") == choice.get("selected_source_id")
                and p.get("page") == choice.get("selected_page")
            ),
            None,
        )
        extracted = _extract_scoped_fields(source) if source else None
        meta = get_source_metadata(source) if source else {}
        for kind in ("manufacturer", "type", "serial_number"):
            exp = expected.get(section, {}).get(kind)
            previous = choice.get(kind) or {}
            key = (section, kind)
            candidates = extracted[section][kind] if extracted else []
            groups = _usable_labeled_candidates(candidates, kind)
            available[key] = (exp, previous, groups, meta)
            if not exp or previous.get("status") == "MATCH":
                continue
            if not groups:
                choice[kind] = _empty(exp, meta)
                continue
            # A recognized BRAND label with a different readable value is a real conflict.
            # Do not infer this for type or serial: OCR ambiguities need REVIEW.
            if kind == "manufacturer":
                ranked = sorted(
                    groups.values(),
                    key=lambda g: (
                        len({x["variant"] for x in g}),
                        max(x["confidence"] for x in g),
                    ),
                    reverse=True,
                )
                best_group = ranked[0]
                best = max(best_group, key=lambda x: x["confidence"])
                val = best["value"]
                if compact_text(val) != compact_text(exp) and not serial_ocr_ambiguity(exp, val):
                    choice[kind] = {
                        "status": "MISMATCH",
                        "expected": exp,
                        "evidence": val,
                        "score": round(fuzz.ratio(compact_text(exp), compact_text(val)), 1),
                        "variant": best["variant"],
                        "box": best["box"],
                        **meta,
                    }
                    decisive.append(section)
            # In absence of a reliable alternative: display no made-up document value.
            elif previous.get("status") != "MATCH":
                # A matching alternative discovered by v7 is retained.
                if previous.get("status") == "REVIEW" and previous.get("evidence") is not None:
                    # For negative tests, non-exact type/serial candidates may be real,
                    # but keep REVIEW rather than assert MISMATCH.
                    continue
                choice[kind] = _empty(exp, meta)
    # MISMATCH on blank fields requires independent contradictions in unit AND tube.
    cross_device = {"unit", "tabung"}.issubset(set(decisive))
    if cross_device:
        for (section, kind), (exp, old, groups, meta) in available.items():
            if not exp:
                continue
            field = result[section][kind]
            if field.get("status") == "MATCH" or (
                kind == "manufacturer" and field.get("status") == "MISMATCH"
            ):
                continue
            # User's requested compact negative display: no spurious fuzzy percentages.
            result[section][kind] = _empty(exp, meta, mismatch=True)
    result["summary"] = summarize_guided_result(result)
    result["matching_score"] = sum(
        score_field_status(
            result[s][f],
            {"serial_number": 5, "type": 3, "manufacturer": 2}[f],
            {"serial_number": 3, "type": 1, "manufacturer": 0.5}[f],
        )
        for s in ("unit", "tabung")
        for f in ("manufacturer", "type", "serial_number")
    )
    result["cross_device_conflict"] = cross_device
    return result


def _match_document_identity(document_ocr, expected):
    gate = _identity_conflict(document_ocr, expected)
    result = _match_missing_fields(document_ocr, expected)
    if gate is None:
        result["document_identity_conflict"] = False
        return result
    result["document_identity_conflict"] = True
    result["identity_evidence"] = {
        "detected_unit_brand": gate["value"],
        "sources": gate["evidence"],
    }
    for section in ("unit", "tabung"):
        for field in ("manufacturer", "type", "serial_number"):
            current = result[section].get(field) or {}
            exp = expected.get(section, {}).get(field)
            # An exact match should not be overwritten by a document-level
            # guess: contradictory positive evidence requires REVIEW.
            if current.get("status") == "MATCH":
                result["document_identity_conflict"] = False
                result["identity_evidence"]["reason"] = (
                    "Contradictory exact field match; review required"
                )
                for s in ("unit", "tabung"):
                    for f in ("manufacturer", "type", "serial_number"):
                        if result[s][f].get("status") == "MISMATCH":
                            result[s][f] = _empty(expected.get(s, {}).get(f), {}, mismatch=False)
                result["summary"] = summarize_guided_result(result)
                return result
            result[section][field] = {
                "status": "MISMATCH",
                "expected": exp,
                "evidence": None,
                "score": None,
                "components": [],
                "reason": "Identitas unit pada label berbeda dari Formulir",
            }
    result["summary"] = summarize_guided_result(result)
    result["matching_score"] = 0
    result["cross_device_conflict"] = True
    return result


def _match_document_rejection(document_ocr, expected):
    gate = _document_rejection(document_ocr, expected)
    if gate is None:
        # Retain v9/v6 validated positive matching, do not alter evidence.
        return _match_document_identity(document_ocr, expected)
    result = {}
    for section in ("unit", "tabung"):
        fields = {}
        for field in ("manufacturer", "type", "serial_number"):
            fields[field] = {
                "status": "MISMATCH",
                "expected": expected.get(section, {}).get(field),
                "evidence": None,
                "score": None,
                "components": [],
                "reason": "Dokumen memuat identitas peralatan berbeda",
            }
        result[section] = {
            "selected_source_id": None,
            "selected_source_name": None,
            "selected_page": None,
            "page_score": 0,
            "candidate_scores": [],
            **fields,
        }
    result["summary"] = summarize_guided_result(result)
    result["matching_score"] = 0
    result["document_identity_conflict"] = True
    result["cross_device_conflict"] = True
    result["identity_evidence"] = {
        "detected_unit_brand": gate["value"],
        "sources": gate["evidence"],
    }
    return result


def _match_original_gate(document_ocr, expected):
    if document_ocr and all(p.get("original_zero_match") for p in document_ocr):
        result = {}
        for section in ("unit", "tabung"):
            fields = {
                field: {
                    "status": "MISMATCH",
                    "expected": expected.get(section, {}).get(field),
                    "evidence": None,
                    "score": None,
                    "components": [],
                    "reason": "0 field cocok pada OCR original; dihentikan sesuai kebijakan",
                }
                for field in ("manufacturer", "type", "serial_number")
            }
            result[section] = {
                "selected_source_id": None,
                "selected_source_name": None,
                "selected_page": None,
                "page_score": 0,
                "candidate_scores": [],
                **fields,
            }
        result["summary"] = summarize_guided_result(result)
        result["matching_score"] = 0
        result["original_zero_match"] = True
        return result
    return _match_document_rejection(document_ocr, expected)


def guided_match_label_document(document_ocr, expected):
    result = _match_original_gate(document_ocr, expected)
    changed = False
    for section in ("unit", "tabung"):
        model = str((expected.get(section) or {}).get("type") or "").strip()
        code = compact_text(model)
        # Narrow guard, not a global fuzzy policy change.
        if not re.fullmatch(r"[A-Z]{1,7}[0-9][A-Z0-9]{2,15}", code) or re.search(
            r"\s|[/()]", model
        ):
            continue
        entry = (result.get(section) or {}).get("type") or {}
        if entry.get("status") != "MATCH":
            continue
        values = [
            str(x.get("evidence") or "").strip()
            for x in (entry.get("components") or [])
            if isinstance(x, dict) and x.get("evidence")
        ]
        if not values and entry.get("evidence"):
            values = [str(entry["evidence"])]
        if not values:
            continue
        # Only compare a stand-alone code, never manufacturer/address prose.
        observed = [compact_text(x) for x in values]
        observed = [x for x in observed if re.fullmatch(r"[A-Z0-9]{3,22}", x)]
        if observed and all(x != code for x in observed):
            entry["status"] = "MISMATCH"
            entry["evidence"] = values[0]
            entry["score"] = None
            entry["reason"] = "Kode tipe/model berbeda, termasuk suffix atau prefix tambahan"
            changed = True
    if changed:
        result["summary"] = summarize_guided_result(result)
        result["matching_score"] = sum(
            score_field_status(
                result[s][f],
                {"serial_number": 5, "type": 3, "manufacturer": 2}[f],
                {"serial_number": 3, "type": 1, "manufacturer": 0.5}[f],
            )
            for s in ("unit", "tabung")
            for f in ("manufacturer", "type", "serial_number")
        )
    return result
