import re
from rapidfuzz import fuzz
from .label_normalization import compact_text, normalize_text


def get_source_metadata(
    page_data,
):
    return {
        "source_id": page_data.get("source_id"),
        "source_name": page_data.get("source_name"),
        "page": page_data.get("page"),
    }


def find_exact_line(
    expected,
    page_data,
):
    expected_normalized = normalize_text(expected)

    expected_compact = compact_text(expected)

    if not expected_normalized:
        return None

    for item in page_data.get("ocr", []):
        candidate = item.get("text")

        if not candidate:
            continue

        candidate_normalized = normalize_text(candidate)

        candidate_compact = compact_text(candidate)

        if candidate_normalized == expected_normalized:
            return candidate

        if candidate_compact == expected_compact:
            return candidate

    return None


def find_contained_line(
    expected,
    page_data,
):
    expected_normalized = normalize_text(expected)

    expected_compact = compact_text(expected)

    if not expected_normalized:
        return None

    pattern = r"(?:^|\s)" + re.escape(expected_normalized) + r"(?:\s|$)"

    for item in page_data.get("ocr", []):
        candidate = item.get("text")

        if not candidate:
            continue

        candidate_normalized = normalize_text(candidate)

        candidate_compact = compact_text(candidate)

        if re.search(
            pattern,
            candidate_normalized,
        ):
            return candidate

        if len(expected_compact) >= 4 and expected_compact in candidate_compact:
            return candidate

    return None


def find_best_fuzzy_line(
    expected,
    page_data,
):
    expected_normalized = normalize_text(expected)

    if not expected_normalized:
        return {
            "score": 0.0,
            "text": None,
        }

    best_score = 0.0
    best_text = None

    minimum_length = max(
        3,
        int(len(expected_normalized) * 0.4),
    )

    for item in page_data.get("ocr", []):
        candidate = item.get("text")

        if not candidate:
            continue

        candidate_normalized = normalize_text(candidate)

        if not candidate_normalized:
            continue

        if len(candidate_normalized) < minimum_length:
            continue

        score = max(
            fuzz.ratio(
                expected_normalized,
                candidate_normalized,
            ),
            fuzz.token_set_ratio(
                expected_normalized,
                candidate_normalized,
            ),
        )

        if score > best_score:
            best_score = score
            best_text = candidate

    return {
        "score": round(
            best_score,
            2,
        ),
        "text": best_text,
    }
