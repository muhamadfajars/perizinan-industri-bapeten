import re
from rapidfuzz import fuzz
from .label_normalization import (
    compact_text,
    is_serial_labeled_line,
    is_type_labeled_line,
    normalize_serial_candidate,
    normalize_text,
    normalize_type_candidate,
    serial_ocr_ambiguity,
    split_expected_type,
)
from .label_candidates import (
    find_best_fuzzy_line,
    find_contained_line,
    find_exact_line,
    get_source_metadata,
)


def match_simple_field_on_page(
    expected,
    page_data,
    fuzzy_threshold=90,
):
    metadata = get_source_metadata(page_data)

    if not expected:
        return {
            "status": "MISSING",
            "expected": expected,
            "evidence": None,
            "score": 0.0,
            **metadata,
        }

    evidence = find_exact_line(
        expected,
        page_data,
    )

    if evidence:
        return {
            "status": "MATCH",
            "expected": expected,
            "evidence": evidence,
            "score": 100.0,
            **metadata,
        }

    evidence = find_contained_line(
        expected,
        page_data,
    )

    if evidence:
        return {
            "status": "MATCH",
            "expected": expected,
            "evidence": evidence,
            "score": 100.0,
            **metadata,
        }

    fuzzy = find_best_fuzzy_line(
        expected,
        page_data,
    )

    if fuzzy["score"] >= fuzzy_threshold:
        status = "REVIEW"

    else:
        status = "MISMATCH"

    return {
        "status": status,
        "expected": expected,
        "evidence": fuzzy["text"],
        "score": fuzzy["score"],
        **metadata,
    }


def _match_parenthetical_type(expected, page_data):
    """Respect model aliases explicitly provided by the form, not suffix guessing."""
    if not expected or "(" not in str(expected) or ")" not in str(expected):
        return None
    raw = str(expected)
    primary = raw[: raw.index("(")].strip()
    alias = raw[raw.index("(") + 1 : raw.rindex(")")].strip()
    variants = [x for x in (primary, alias) if x]
    if not variants:
        return None
    meta = get_source_metadata(page_data)
    items = [str(x.get("text", "")) for x in page_data.get("ocr", [])]
    for variant in variants:
        # Contiguous model codes may be split by spaces/hyphens in OCR.
        tokens = re.findall(r"[A-Za-z0-9]+", variant)
        if not tokens:
            continue
        pattern = r"(?<![A-Za-z0-9])" + r"[\s\-]*".join(map(re.escape, tokens)) + r"(?![A-Za-z0-9])"
        for line in items:
            match = re.search(pattern, line, re.I)
            if match:
                return {
                    "status": "MATCH",
                    "expected": expected,
                    "components": [
                        {
                            "component": variant,
                            "found": True,
                            "score": 100.0,
                            "evidence": match.group(0),
                            "variant": next(
                                (
                                    x.get("variant", "original")
                                    for x in page_data.get("ocr", [])
                                    if str(x.get("text", "")) == line
                                ),
                                "original",
                            ),
                        }
                    ],
                    **meta,
                }
    # Keep true model extensions visible: DR-XD1000PX is not DR-XD1000.
    closest = max(
        (
            fuzz.ratio(compact_text(v), compact_text(line))
            for v in variants
            for line in items
            if line
        ),
        default=0.0,
    )
    near = None
    for line in items:
        for v in variants:
            if compact_text(v) and compact_text(v) in compact_text(line):
                near = line
                break
        if near:
            break
    if near:
        return {
            "status": "REVIEW",
            "expected": expected,
            "components": [
                {
                    "component": primary,
                    "found": False,
                    "score": closest,
                    "evidence": near,
                }
            ],
            "reason": "Kode model memiliki sufiks/varian tambahan, perlu verifikasi",
            **meta,
        }
    return None


def match_type_field_on_page(
    expected,
    page_data,
):
    parenthetical_result = _match_parenthetical_type(expected, page_data)
    if parenthetical_result is not None:
        return parenthetical_result

    metadata = get_source_metadata(page_data)

    if not expected:
        return {
            "status": "MISSING",
            "expected": expected,
            "components": [],
            **metadata,
        }

    components = split_expected_type(expected)

    ocr_items = page_data.get(
        "ocr",
        [],
    )

    # A full compound model may be printed on one row (e.g. KL10-0.6/1.8-125).
    # First compare the WHOLE code, not pieces independently; no suffix deletion.
    normalized_expected = compact_text(expected)
    if normalized_expected and not ("(" in str(expected) and ")" in str(expected)):
        for item in ocr_items:
            raw = str(item.get("text") or "")
            extracted = normalize_type_candidate(raw)
            if compact_text(extracted) == normalized_expected:
                return {
                    "status": "MATCH",
                    "expected": expected,
                    "components": [
                        {
                            "component": expected,
                            "found": True,
                            "score": 100.0,
                            "evidence": extracted,
                        }
                    ],
                    **metadata,
                }

    component_results = []

    for component in components:
        component_normalized = normalize_text(component)

        component_compact = compact_text(component)

        found_result = None

        # 1. Prioritaskan line yang memang punya label MODEL/TYPE
        for item in ocr_items:
            candidate = item.get("text")

            if not candidate:
                continue

            if not is_type_labeled_line(candidate):
                continue

            candidate_value = normalize_type_candidate(candidate)

            candidate_compact = compact_text(candidate_value)

            if candidate_value == component_normalized or candidate_compact == component_compact:
                found_result = {
                    "component": component,
                    "found": True,
                    "score": 100.0,
                    "evidence": candidate,
                }

                break

        if found_result:
            component_results.append(found_result)
            continue

        # 2. Exact OCR line
        for item in ocr_items:
            candidate = item.get("text")

            if not candidate:
                continue

            candidate_normalized = normalize_text(candidate)

            candidate_compact = compact_text(candidate)

            if (
                candidate_normalized == component_normalized
                or candidate_compact == component_compact
            ):
                found_result = {
                    "component": component,
                    "found": True,
                    "score": 100.0,
                    "evidence": candidate,
                }

                break

        if found_result:
            component_results.append(found_result)
            continue

        # 3. Whole-token containment.
        # E7894 boleh cocok dengan "MODEL E7894"
        # tapi tidak dengan E7894X.
        pattern = r"(?:^|\s)" + re.escape(component_normalized) + r"(?:\s|$)"

        for item in ocr_items:
            candidate = item.get("text")

            if not candidate:
                continue

            candidate_normalized = normalize_text(candidate)

            if re.search(
                pattern,
                candidate_normalized,
            ):
                found_result = {
                    "component": component,
                    "found": True,
                    "score": 100.0,
                    "evidence": candidate,
                }

                break

        if found_result:
            component_results.append(found_result)
            continue

        # 4. Fuzzy sebagai fallback terakhir
        best_score = 0.0
        best_candidate = None

        for item in ocr_items:
            candidate = item.get("text")

            if not candidate:
                continue

            candidate_value = normalize_type_candidate(candidate)

            if not candidate_value:
                continue

            minimum_length = max(
                3,
                int(len(component_normalized) * 0.6),
            )

            if len(candidate_value) < minimum_length:
                continue

            score = max(
                fuzz.ratio(
                    component_normalized,
                    candidate_value,
                ),
                fuzz.token_set_ratio(
                    component_normalized,
                    candidate_value,
                ),
            )

            if is_type_labeled_line(candidate):
                score += 5

            if score > best_score:
                best_score = score
                best_candidate = candidate

        component_results.append(
            {
                "component": component,
                "found": best_score >= 90,
                "score": round(
                    min(
                        best_score,
                        100.0,
                    ),
                    2,
                ),
                "evidence": best_candidate,
            }
        )

    found_count = sum(item["found"] for item in component_results)

    if components and found_count == len(components):
        status = "MATCH"

    elif found_count > 0:
        status = "REVIEW"

    else:
        status = "MISMATCH"

    return {
        "status": status,
        "expected": expected,
        "components": component_results,
        **metadata,
    }


def match_serial_field_on_page(
    expected,
    page_data,
):
    metadata = get_source_metadata(page_data)

    if not expected:
        return {
            "status": "MISSING",
            "expected": expected,
            "evidence": None,
            "score": 0.0,
            **metadata,
        }

    expected_compact = compact_text(expected)

    ocr_items = page_data.get(
        "ocr",
        [],
    )

    # 1. Prioritaskan baris yang memang berlabel serial
    serial_candidates = []

    for item in ocr_items:
        candidate = item.get("text")

        if not candidate:
            continue

        if is_serial_labeled_line(candidate):
            serial_candidates.append(candidate)

    # 2. Exact match pada serial-labeled line
    for candidate in serial_candidates:
        candidate_serial = normalize_serial_candidate(candidate)

        if candidate_serial == expected_compact:
            return {
                "status": "MATCH",
                "expected": expected,
                "evidence": candidate,
                "score": 100.0,
                **metadata,
            }

    # Check all exact candidates BEFORE allowing OCR ambiguity to trigger REVIEW.
    # The relevant insert serial can be a separate OCR box on the same label.
    for item in ocr_items:
        raw = str(item.get("text") or "")
        if normalize_serial_candidate(raw) == expected_compact:
            return {
                "status": "MATCH",
                "expected": expected,
                "evidence": raw,
                "score": 100.0,
                **metadata,
            }

    # 3. OCR ambiguity pada serial-labeled line
    for candidate in serial_candidates:
        candidate_serial = normalize_serial_candidate(candidate)

        if serial_ocr_ambiguity(
            expected_compact,
            candidate_serial,
        ):
            return {
                "status": "REVIEW",
                "expected": expected,
                "evidence": candidate,
                "score": None,
                "reason": ("Kemungkinan ambiguity OCR pada nomor seri."),
                **metadata,
            }

    # 4. Exact match di baris lain
    for item in ocr_items:
        candidate = item.get("text")

        if not candidate:
            continue

        candidate_serial = normalize_serial_candidate(candidate)

        if candidate_serial == expected_compact:
            return {
                "status": "MATCH",
                "expected": expected,
                "evidence": candidate,
                "score": 100.0,
                **metadata,
            }

    # 5. OCR ambiguity di baris lain
    for item in ocr_items:
        candidate = item.get("text")

        if not candidate:
            continue

        candidate_serial = normalize_serial_candidate(candidate)

        if serial_ocr_ambiguity(
            expected_compact,
            candidate_serial,
        ):
            return {
                "status": "REVIEW",
                "expected": expected,
                "evidence": candidate,
                "score": None,
                "reason": "Kemungkinan ambiguity OCR pada nomor seri.",
                **metadata,
            }

    # 6. Fuzzy fallback
    best_score = 0.0
    best_candidate = None

    for item in ocr_items:
        candidate = item.get("text")

        if not candidate:
            continue

        candidate_serial = normalize_serial_candidate(candidate)

        if not candidate_serial:
            continue

        minimum_length = max(
            3,
            int(len(expected_compact) * 0.7),
        )

        if len(candidate_serial) < minimum_length:
            continue

        score = fuzz.ratio(
            expected_compact,
            candidate_serial,
        )

        # Bonus jika baris memang berlabel serial
        if is_serial_labeled_line(candidate):
            score += 10

        if score > best_score:
            best_score = score
            best_candidate = candidate

    return {
        "status": "MISMATCH",
        "expected": expected,
        "evidence": best_candidate,
        "score": round(min(best_score, 100.0), 2),
        **metadata,
    }


def score_field_status(
    result,
    match_weight,
    review_weight,
):
    status = result.get("status")

    if status == "MATCH":
        return match_weight

    if status == "REVIEW":
        return review_weight

    return 0
