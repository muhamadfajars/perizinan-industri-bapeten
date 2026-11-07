from .label_fields import (
    match_serial_field_on_page,
    match_simple_field_on_page,
    match_type_field_on_page,
    score_field_status,
)


def select_best_source_page(
    document_ocr,
    expected,
):
    candidates = []

    for page_data in document_ocr:
        manufacturer = match_simple_field_on_page(
            expected.get("manufacturer"),
            page_data,
        )

        type_result = match_type_field_on_page(
            expected.get("type"),
            page_data,
        )

        serial_result = match_serial_field_on_page(
            expected.get("serial_number"),
            page_data,
        )

        manufacturer_status = manufacturer.get("status")

        type_status = type_result.get("status")

        serial_status = serial_result.get("status")

        score = 0

        score += score_field_status(
            serial_result,
            match_weight=5,
            review_weight=3,
        )

        score += score_field_status(
            type_result,
            match_weight=3,
            review_weight=1,
        )

        score += score_field_status(
            manufacturer,
            match_weight=2,
            review_weight=0.5,
        )

        if manufacturer_status == "MISMATCH":
            score -= 3

        complete_match = (
            manufacturer_status == "MATCH"
            and type_status == "MATCH"
            and serial_status
            in {
                "MATCH",
                "REVIEW",
            }
        )

        if complete_match:
            score += 3

        candidate = {
            "source_id": page_data.get("source_id"),
            "source_name": page_data.get("source_name"),
            "page": page_data.get("page"),
            "score": score,
            "complete_match": complete_match,
            "manufacturer_status": manufacturer_status,
            "type_status": type_status,
            "serial_status": serial_status,
            "fields": {
                "manufacturer": manufacturer,
                "type": type_result,
                "serial_number": serial_result,
            },
        }

        candidates.append(candidate)

    if not candidates:
        return {
            "source_id": None,
            "source_name": None,
            "page": None,
            "score": 0,
            "fields": {
                "manufacturer": {},
                "type": {},
                "serial_number": {},
            },
            "candidate_scores": [],
        }

    candidates.sort(
        key=lambda item: (
            item["complete_match"],
            item["manufacturer_status"] == "MATCH",
            item["serial_status"] == "MATCH",
            item["serial_status"] == "REVIEW",
            item["type_status"] == "MATCH",
            item["score"],
        ),
        reverse=True,
    )

    best = candidates[0]

    candidate_scores = []

    for item in candidates:
        candidate_scores.append(
            {
                "source_id": item["source_id"],
                "source_name": item["source_name"],
                "page": item["page"],
                "score": item["score"],
                "complete_match": item["complete_match"],
                "manufacturer_status": item["manufacturer_status"],
                "type_status": item["type_status"],
                "serial_status": item["serial_status"],
            }
        )

    return {
        "source_id": best["source_id"],
        "source_name": best["source_name"],
        "page": best["page"],
        "score": best["score"],
        "fields": best["fields"],
        "candidate_scores": candidate_scores,
    }


def summarize_guided_result(
    result,
):
    statuses = []

    for section in [
        "unit",
        "tabung",
    ]:
        for field in [
            "manufacturer",
            "type",
            "serial_number",
        ]:
            statuses.append(
                result.get(
                    section,
                    {},
                )
                .get(
                    field,
                    {},
                )
                .get("status")
            )

    if "MISMATCH" in statuses:
        overall = "MISMATCH"

    elif "MISSING" in statuses:
        overall = "INCOMPLETE"

    elif "REVIEW" in statuses:
        overall = "REVIEW"

    else:
        overall = "VALID"

    return {
        "status": overall,
        "match": statuses.count("MATCH"),
        "review": statuses.count("REVIEW"),
        "mismatch": statuses.count("MISMATCH"),
        "missing": statuses.count("MISSING"),
        "total_fields": len(statuses),
    }
