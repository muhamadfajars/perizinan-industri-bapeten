from rapidfuzz import fuzz
from .personnel_normalization import (
    expertise_similarity,
    name_similarity,
    normalize_address,
    normalize_hospital,
    token_overlap,
)


def match_personnel_pair(
    document_text,
    personnel_list,
):
    candidates = []

    for index, person in enumerate(personnel_list):
        name = person.get("nama")

        expertise = person.get("keahlian_klasifikasi")

        name_score = name_similarity(
            name,
            document_text,
        )

        expertise_score = expertise_similarity(
            expertise,
            document_text,
        )

        pair_score = name_score * 0.55 + expertise_score * 0.45

        if name_score >= 88 and expertise_score >= 78:
            status = "MATCH"

        elif name_score >= 75 and expertise_score >= 60:
            status = "REVIEW"

        else:
            status = "MISMATCH"

        candidates.append(
            {
                "personnel_index": index,
                "name": name,
                "expertise": expertise,
                "name_score": round(
                    name_score,
                    2,
                ),
                "expertise_score": round(
                    expertise_score,
                    2,
                ),
                "pair_score": round(
                    pair_score,
                    2,
                ),
                "status": status,
            }
        )

    candidates.sort(
        key=lambda item: item["pair_score"],
        reverse=True,
    )

    if not candidates:
        return {
            "status": "MISSING",
            "selected_personnel_index": None,
            "candidates": [],
        }

    best = candidates[0]

    second = candidates[1] if len(candidates) > 1 else None

    gap = best["pair_score"] - (second["pair_score"] if second else 0)

    if best["status"] == "MATCH" and (gap >= 3 or len(candidates) == 1):
        final_status = "MATCH"

    elif best["status"] in {
        "MATCH",
        "REVIEW",
    }:
        final_status = "REVIEW"

    else:
        final_status = "MISMATCH"

    return {
        "status": final_status,
        "selected_personnel_index": best["personnel_index"],
        "best": best,
        "score_gap": round(
            gap,
            2,
        ),
        "candidates": candidates,
    }


def location_similarity(
    expected,
    document_text,
):
    expected = normalize_address(expected)

    document = normalize_address(document_text)

    if not expected or not document:
        return 0.0

    if expected in document:
        return 100.0

    token_score = fuzz.token_set_ratio(
        expected,
        document,
    )

    partial_score = fuzz.partial_ratio(
        expected,
        document,
    )

    overlap = token_overlap(
        expected,
        document,
    )

    return round(
        max(
            token_score,
            partial_score,
            overlap,
        ),
        2,
    )


def match_practice_address(
    expected,
    document_text,
):
    score = location_similarity(
        expected,
        document_text,
    )

    if score >= 78:
        status = "MATCH"

    elif score >= 58:
        status = "REVIEW"

    else:
        status = "MISMATCH"

    return {
        "status": status,
        "expected": expected,
        "score": score,
    }


def match_hospital_name(
    expected,
    document_text,
):
    expected = normalize_hospital(expected)

    actual = normalize_hospital(document_text)

    if not expected or not actual:
        return {
            "status": "MISSING",
            "expected": expected,
            "score": 0,
        }

    score = max(
        fuzz.token_set_ratio(
            expected,
            actual,
        ),
        fuzz.partial_ratio(
            expected,
            actual,
        ),
        token_overlap(
            expected,
            actual,
        ),
    )

    if score >= 82:
        status = "MATCH"

    elif score >= 65:
        status = "REVIEW"

    else:
        status = "MISMATCH"

    return {
        "status": status,
        "expected": expected,
        "score": round(
            score,
            2,
        ),
    }


def match_address(
    expected,
    document_text,
):
    score = location_similarity(
        expected,
        document_text,
    )

    if score >= 75:
        status = "MATCH"

    elif score >= 55:
        status = "REVIEW"

    else:
        status = "MISMATCH"

    return {
        "status": status,
        "expected": expected,
        "score": score,
    }
