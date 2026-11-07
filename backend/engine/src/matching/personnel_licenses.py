from src.extraction.approval_detector import (
    detect_approval,
)
from .personnel_identity import match_personnel_pair
from .personnel_validity import aggregate_status, expiry_result


def validate_sip(
    document,
    application,
):
    text = document["text"]

    personnel = application.get(
        "personnel",
        [],
    )

    general = application.get(
        "general",
        {},
    )

    employee = match_personnel_pair(
        text,
        personnel,
    )

    # SIP terbaru: cocokan TEMPAT PRAKTIK
    # dengan alamat proyek, bukan nama instansi.
    from src.matching.personnel_evidence import find_address

    expected_address = general.get("alamat_proyek")
    if isinstance(expected_address, dict):
        expected_address = expected_address.get("value")
    found_address, found_score = find_address(text, expected_address)
    practice_place = {
        "expected": expected_address,
        "observed": found_address,
        "score": found_score,
        "status": ("MATCH" if found_score is not None and found_score >= 85 else "REVIEW"),
    }

    validity = expiry_result(document)
    approval = detect_approval(document.get("pages") or [], text)

    overall = aggregate_status(
        [
            employee["status"],
            practice_place["status"],
            validity["status"],
        ]
    )

    return {
        "document_type": "SIP",
        "employee": employee,
        "practice_place": practice_place,
        "validity": validity,
        "approval": approval,
        "status": overall,
    }


def validate_sib(
    document,
    application,
):
    text = document["text"]

    employee = match_personnel_pair(
        text,
        application.get(
            "personnel",
            [],
        ),
    )

    validity = expiry_result(document)

    overall = aggregate_status(
        [
            employee["status"],
            validity["status"],
        ]
    )

    return {
        "document_type": "SIB",
        "employee": employee,
        "validity": validity,
        "status": overall,
    }
