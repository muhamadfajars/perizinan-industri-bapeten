import re
from rapidfuzz import fuzz
from src.extraction.approval_detector import (
    detect_approval,
)
from .personnel_normalization import normalize_basic, normalize_name
from .personnel_identity import match_address, match_hospital_name
from .personnel_validity import aggregate_status


def extract_sprint_assignment_section(
    text,
):
    if not text:
        return {
            "found": False,
            "text": "",
            "start_marker": None,
            "end_marker": None,
        }

    original = str(text)

    normalized = normalize_basic(original)

    start_patterns = [
        r"\bmemerintahkan\s+kepada\b",
        r"\bmemerintahkan\b",
        r"\bkepada\s*:",
        r"\bkepada\b",
    ]

    end_patterns = [
        r"\buntuk\s*:",
        r"\buntuk\b",
        r"\bdengan\s+tugas\b",
        r"\buntuk\s+melaksanakan\b",
    ]

    start_match = None

    for pattern in start_patterns:
        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )

        if match:
            start_match = match
            break

    if not start_match:
        return {
            "found": False,
            "text": "",
            "start_marker": None,
            "end_marker": None,
        }

    section_start = start_match.end()

    remaining = normalized[section_start:]

    end_position = None
    end_marker = None

    for pattern in end_patterns:
        match = re.search(
            pattern,
            remaining,
            flags=re.IGNORECASE,
        )

        if match:
            position = match.start()

            if end_position is None or position < end_position:
                end_position = position
                end_marker = match.group(0)

    if end_position is not None:
        section = remaining[:end_position]

    else:
        section = remaining[:1000]

    return {
        "found": True,
        "text": section.strip(),
        "start_marker": start_match.group(0),
        "end_marker": end_marker,
    }


def sprint_name_similarity(
    expected_name,
    assignment_text,
):
    expected = normalize_name(expected_name)

    actual = normalize_name(assignment_text)

    if not expected or not actual:
        return 0.0

    if expected in actual:
        return 100.0

    expected_tokens = set(expected.split())

    actual_tokens = set(actual.split())

    if expected_tokens and expected_tokens.issubset(actual_tokens):
        return 100.0

    ratio = fuzz.ratio(expected, actual)

    token_score = fuzz.token_set_ratio(
        expected,
        actual,
    )

    partial_score = fuzz.partial_ratio(
        expected,
        actual,
    )

    return round(
        max(
            ratio,
            token_score,
            partial_score,
        ),
        2,
    )


def match_sprint_assigned_person(
    document_text,
    personnel_list,
):
    assignment = extract_sprint_assignment_section(document_text)

    if not assignment["found"]:
        return {
            "status": "REVIEW",
            "selected_personnel_index": None,
            "name": None,
            "name_score": 0.0,
            "assignment_section": None,
            "reason": (
                "Bagian petugas yang ditugaskan pada Surat Perintah belum dapat diidentifikasi."
            ),
            "candidates": [],
        }

    assignment_text = assignment["text"]

    candidates = []

    for index, person in enumerate(personnel_list):
        name = person.get("nama")

        score = sprint_name_similarity(
            name,
            assignment_text,
        )

        candidates.append(
            {
                "personnel_index": index,
                "name": name,
                "name_score": score,
            }
        )

    candidates.sort(
        key=lambda item: item["name_score"],
        reverse=True,
    )

    if not candidates:
        return {
            "status": "MISSING",
            "selected_personnel_index": None,
            "name": None,
            "name_score": 0.0,
            "assignment_section": assignment_text,
            "reason": ("Data personel pada Formulir Permohonan kosong."),
            "candidates": [],
        }

    best = candidates[0]

    second = candidates[1] if len(candidates) > 1 else None

    second_score = second["name_score"] if second else 0

    gap = best["name_score"] - second_score

    if best["name_score"] >= 90 and (gap >= 5 or len(candidates) == 1):
        status = "MATCH"
        reason = None

    elif best["name_score"] >= 75:
        status = "REVIEW"

        reason = "Nama petugas mirip dengan data Formulir, tetapi perlu konfirmasi evaluator."

    else:
        status = "MISMATCH"

        reason = "Nama petugas yang ditugaskan tidak sesuai dengan data personel pada Formulir."

    return {
        "status": status,
        "selected_personnel_index": best["personnel_index"],
        "name": best["name"],
        "name_score": best["name_score"],
        "assignment_section": assignment_text,
        "score_gap": round(
            gap,
            2,
        ),
        "reason": reason,
        "candidates": candidates,
    }


def validate_sprint(
    document,
    application,
):
    text = document["text"]

    general = application.get(
        "general",
        {},
    )

    personnel = application.get(
        "personnel",
        [],
    )

    assigned_person = match_sprint_assigned_person(
        text,
        personnel,
    )

    hospital = match_hospital_name(
        general.get("instansi"),
        text,
    )

    address = match_address(
        general.get("alamat_proyek"),
        text,
    )

    approval = detect_approval(
        document.get(
            "pages",
            [],
        ),
        text,
    )

    approval_status = "MATCH" if approval.get("status") == "DETECTED" else "REVIEW"

    overall = aggregate_status(
        [
            assigned_person["status"],
            hospital["status"],
            address["status"],
            approval_status,
        ]
    )

    return {
        "document_type": "SPRINT",
        "assigned_person": assigned_person,
        "hospital": hospital,
        "address": address,
        "approval": {
            **approval,
            "validation_status": approval_status,
        },
        "status": overall,
    }
