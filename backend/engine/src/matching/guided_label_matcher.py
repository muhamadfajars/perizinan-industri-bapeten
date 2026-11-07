from .label_document_matching import guided_match_label_document


def equipment_to_expected(
    equipment,
):
    return {
        "unit": {
            "manufacturer": equipment.get("merk_unit"),
            "type": equipment.get("tipe_unit"),
            "serial_number": equipment.get("nomor_seri_unit"),
        },
        "tabung": {
            "manufacturer": equipment.get("merk_tabung"),
            "type": equipment.get("tipe_tabung"),
            "serial_number": equipment.get("nomor_seri_tabung"),
        },
    }


def count_serial_matches(
    match_result,
):
    count = 0

    for section in [
        "unit",
        "tabung",
    ]:
        status = (
            match_result.get(
                section,
                {},
            )
            .get(
                "serial_number",
                {},
            )
            .get("status")
        )

        if status == "MATCH":
            count += 1

    return count


def auto_match_equipment(
    document_ocr,
    equipment_list,
):
    if not equipment_list:
        return {
            "status": "NO_EQUIPMENT",
            "confidence": "NONE",
            "selected_equipment_index": None,
            "suggested_equipment_index": None,
            "best_score": 0,
            "second_score": 0,
            "score_gap": 0,
            "candidates": [],
            "match": None,
        }

    candidates = []

    for index, equipment in enumerate(equipment_list):
        expected = equipment_to_expected(equipment)

        match_result = guided_match_label_document(
            document_ocr,
            expected,
        )

        score = match_result.get(
            "matching_score",
            0,
        )

        summary = match_result.get(
            "summary",
            {},
        )

        serial_matches = count_serial_matches(match_result)

        candidates.append(
            {
                "equipment_index": index,
                "equipment_number": index + 1,
                "merk_unit": equipment.get("merk_unit"),
                "tipe_unit": equipment.get("tipe_unit"),
                "nomor_seri_unit": equipment.get("nomor_seri_unit"),
                "merk_tabung": equipment.get("merk_tabung"),
                "tipe_tabung": equipment.get("tipe_tabung"),
                "nomor_seri_tabung": equipment.get("nomor_seri_tabung"),
                "score": score,
                "match_count": summary.get(
                    "match",
                    0,
                ),
                "review_count": summary.get(
                    "review",
                    0,
                ),
                "serial_matches": serial_matches,
                "validation_status": summary.get("status"),
                "match_result": match_result,
            }
        )

    candidates.sort(
        key=lambda item: (
            item["score"],
            item["serial_matches"],
            item["match_count"],
        ),
        reverse=True,
    )

    best = candidates[0]

    second = candidates[1] if len(candidates) > 1 else None

    best_score = best["score"]

    second_score = second["score"] if second else 0

    score_gap = best_score - second_score

    if len(equipment_list) == 1:
        status = "AUTO_SELECTED"

        confidence = "HIGH"

        selected_index = best["equipment_index"]

    elif best_score >= 12 and score_gap >= 4:
        status = "AUTO_SELECTED"

        confidence = "HIGH"

        selected_index = best["equipment_index"]

    elif best_score >= 8 and score_gap >= 3:
        status = "AUTO_SELECTED"

        confidence = "MEDIUM"

        selected_index = best["equipment_index"]

    else:
        status = "REVIEW"

        confidence = "LOW"

        selected_index = None

    public_candidates = []

    for item in candidates:
        public_candidates.append(
            {key: value for key, value in item.items() if key != "match_result"}
        )

    return {
        "status": status,
        "confidence": confidence,
        "selected_equipment_index": selected_index,
        "suggested_equipment_index": best["equipment_index"],
        "best_score": best_score,
        "second_score": second_score,
        "score_gap": score_gap,
        "candidates": public_candidates,
        "match": (best["match_result"] if selected_index is not None else None),
        "suggested_match": best["match_result"],
    }


from .label_normalization import (
    OCR_AMBIGUITY_GROUPS as OCR_AMBIGUITY_GROUPS,
    normalize_text as normalize_text,
    compact_text as compact_text,
    normalize_serial_candidate as normalize_serial_candidate,
    is_serial_labeled_line as is_serial_labeled_line,
    split_expected_type as split_expected_type,
    same_ocr_ambiguity_group as same_ocr_ambiguity_group,
    serial_ocr_ambiguity as serial_ocr_ambiguity,
    normalize_type_candidate as normalize_type_candidate,
    is_type_labeled_line as is_type_labeled_line,
)

from .label_candidates import (
    get_source_metadata as get_source_metadata,
    find_exact_line as find_exact_line,
    find_contained_line as find_contained_line,
    find_best_fuzzy_line as find_best_fuzzy_line,
)

from .label_fields import (
    match_simple_field_on_page as match_simple_field_on_page,
    _match_parenthetical_type as _match_parenthetical_type,
    match_type_field_on_page as match_type_field_on_page,
    match_serial_field_on_page as match_serial_field_on_page,
    score_field_status as score_field_status,
)

from .label_pages import (
    select_best_source_page as select_best_source_page,
    summarize_guided_result as summarize_guided_result,
)

from .label_identity import (
    _label_kind as _label_kind,
    _extract_scoped_fields as _extract_scoped_fields,
    _negative_field as _negative_field,
    _empty as _empty,
    _usable_labeled_candidates as _usable_labeled_candidates,
    _document_unit_brands as _document_unit_brands,
    _identity_conflict as _identity_conflict,
    _document_rejection as _document_rejection,
)

from .label_document_matching import (
    _match_base_document as _match_base_document,
    _match_scoped_document as _match_scoped_document,
    _match_missing_fields as _match_missing_fields,
    _match_document_identity as _match_document_identity,
    _match_document_rejection as _match_document_rejection,
    _match_original_gate as _match_original_gate,
)
