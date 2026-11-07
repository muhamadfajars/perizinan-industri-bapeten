from src.extraction.approval_detector import (
    detect_approval,
)
from .personnel_normalization import normalize_name
from .personnel_validity import aggregate_status
from .personnel_licenses import validate_sib, validate_sip
from .personnel_assignment import validate_sprint

PERSONNEL_FIELDS = {
    "COMPETENCE": [
        ("Nama Petugas", "person"),
        ("Masa Berlaku", "expiry"),
        ("Status Kompetensi", "pass"),
        ("Pengesahan", "approval"),
    ],
    "WORK_PERMIT": [
        ("Nama Petugas", "person"),
        ("Nama Fasilitas", "facility"),
        ("Alamat Fasilitas", "address"),
        ("Masa Berlaku", "expiry"),
        ("Pengesahan", "approval"),
    ],
    "WORK_LETTER": [
        ("Nama Petugas", "person"),
        ("Keahlian", "expertise"),
        ("Nama Fasilitas", "facility"),
        ("Pengesahan", "approval"),
    ],
    "ASSIGNMENT": [
        ("Nama Petugas", "person"),
        ("Nama Fasilitas", "facility"),
        ("Keahlian", "expertise"),
        ("Pengesahan", "approval"),
    ],
    "DOSE": [
        ("Nama Fasilitas", "facility"),
        ("Alamat Fasilitas", "address"),
        ("Nama Petugas", "people"),
        ("Pengesahan", "approval"),
    ],
}


def _candidate_evidence(text, expected, kind):
    from src.matching.personnel_evidence import find_evidence

    return find_evidence(text, expected, kind)


def validate_additional_personnel(document, application):
    """One field, one attributable source value; no global-text fuzzy MATCH."""
    from datetime import date
    from dateutil import parser as date_parser
    from src.matching.personnel_comparison import (
        address_evidence,
        workplace_address,
        choose_person_reference,
        personnel_role_quote,
        explicit_assignment_role,
        monitored_dose_person,
        related_facility_score,
        compact_person_quote,
    )
    from src.matching.personnel_evidence import (
        find_evidence,
        find_practice_facility,
        find_pass_status,
        _facility_score,
    )

    dtype = document.get("document_type")
    text = document.get("text") or ""
    general = application.get("general") or {}
    personnel = application.get("personnel") or []
    facility = general.get("nama_fasilitas") or general.get("nama_rs") or general.get("instansi")
    address = general.get("alamat_proyek")
    if isinstance(facility, dict):
        facility = facility.get("value")
    if isinstance(address, dict):
        address = address.get("value")
    role_context = explicit_assignment_role(text) if dtype == "ASSIGNMENT" else None
    best_person = choose_person_reference(text, personnel, role_hint=role_context)
    references = []
    for person in personnel:
        name = person.get("nama") or person.get("name")
        role = (
            person.get("keahlian")
            or person.get("keahlian_klasifikasi")
            or person.get("profesi")
            or person.get("jabatan")
        )
        if name:
            references.append((name, role))
    expected_person = best_person[0] if best_person else (references[0][0] if references else None)
    expected_expertise = (
        best_person[3] if best_person else (references[0][1] if references else None)
    )
    expiry = (document.get("expiry") or {}).get("expiry_date")
    workplace = find_practice_facility(text) if dtype == "WORK_PERMIT" else None
    rows = []
    approval_result = (
        detect_approval(document.get("pages") or [], text)
        if any(kind == "approval" for _label, kind in PERSONNEL_FIELDS[dtype])
        else {}
    )

    def add(label, expected, observed, score, status):
        rows.append(
            {
                "field": label,
                "expected": expected or "—",
                "observed": observed or "—",
                "score": score,
                "status": status,
            }
        )

    for label, kind in PERSONNEL_FIELDS[dtype]:
        if kind == "people":
            seen = set()
            for name, _ in references:
                key = normalize_name(name)
                if key in seen:
                    continue
                seen.add(key)
                observed, score = monitored_dose_person(text, name)
                if observed is not None and score is not None and score >= 85:
                    add(
                        f"Nama Petugas: {name}",
                        name,
                        observed,
                        score,
                        "MATCH" if score >= 90 else "REVIEW",
                    )
        elif kind == "person":
            quote = compact_person_quote(text, expected_person)
            if quote is None and best_person:
                quote = best_person[1]
            # Do not copy a global similarity score if the observed line is absent.
            score = best_person[2] if quote is not None and best_person else None
            add(
                label,
                expected_person,
                quote,
                score,
                "MATCH" if score is not None and score >= 90 else "REVIEW",
            )
        elif kind == "expertise":
            observed, score = personnel_role_quote(
                text, expected_expertise, assignment=dtype == "ASSIGNMENT"
            )
            add(
                label,
                expected_expertise,
                observed,
                score,
                "MATCH" if score is not None and score >= 90 else "REVIEW",
            )
        elif kind == "facility":
            expected = facility
            if dtype == "WORK_PERMIT" and workplace:
                observed = workplace
                score = _facility_score(expected, observed)
                status = (
                    "MATCH"
                    if score is not None and score >= 90
                    else "MISMATCH"
                    if score is None
                    else "REVIEW"
                )
            else:
                observed, score = find_evidence(text, expected, "facility")
                if dtype == "DOSE" and observed:
                    addr_quote, addr_score, _ = address_evidence(text, address)
                    score = related_facility_score(expected, observed, addr_quote, addr_score)
                status = "MATCH" if score is not None and score >= 90 else "REVIEW"
            add(label, expected, observed, score, status)
        elif kind == "address":
            expected = address
            if dtype == "WORK_PERMIT":
                observed, score, status = workplace_address(text, expected)
            else:
                observed, score, status = address_evidence(text, expected)
            add(label, expected, observed, score, status)
        elif kind == "expiry":
            try:
                parsed = date_parser.parse(str(expiry), dayfirst=False).date() if expiry else None
                state = (document.get("expiry") or {}).get("status")
                status = (
                    ("MATCH" if parsed >= date.today() else "MISMATCH")
                    if parsed and state in ("ACTIVE", "EXPIRED")
                    else "REVIEW"
                )
            except (ValueError, TypeError, OverflowError):
                status = "REVIEW"
            add(
                label,
                expiry,
                (document.get("expiry") or {}).get("evidence"),
                None,
                status,
            )
        elif kind == "pass":
            observed, passed = find_pass_status(text)
            add(
                label,
                "Lulus / Kompeten",
                observed,
                100 if passed is True else 0 if passed is False else None,
                "MATCH" if passed is True else "MISMATCH" if passed is False else "REVIEW",
            )
        elif kind == "approval":
            detected = approval_result.get("status") == "DETECTED"
            add(
                label,
                "Bukti pengesahan",
                "Indikasi pengesahan ditemukan" if detected else None,
                100 if detected else None,
                "MATCH" if detected else "REVIEW",
            )
    return {
        "document_type": dtype,
        "fields": rows,
        "approval": approval_result,
        "status": aggregate_status([r["status"] for r in rows]),
    }


def validate_personnel_document(
    document,
    application,
):
    document_type = document.get("document_type")

    if document_type in PERSONNEL_FIELDS:
        return validate_additional_personnel(document, application)

    if document_type == "SIP":
        return validate_sip(
            document,
            application,
        )

    if document_type == "SIB":
        return validate_sib(
            document,
            application,
        )

    if document_type == "SPRINT":
        return validate_sprint(
            document,
            application,
        )

    return {
        "document_type": "UNKNOWN",
        "status": "REVIEW",
        "reason": ("Jenis dokumen belum dapat dikenali."),
    }


def validate_personnel_documents(
    documents,
    application,
):
    results = []

    for document in documents:
        validation = validate_personnel_document(
            document,
            application,
        )

        results.append(
            {
                "source_id": document.get("source_id"),
                "source_name": document.get("source_name"),
                "detected_type": document.get("document_type"),
                "validation": validation,
            }
        )

    return results


from .personnel_normalization import (
    NAME_PREFIXES as NAME_PREFIXES,
    NAME_SUFFIX_PATTERNS as NAME_SUFFIX_PATTERNS,
    GENERAL_REPLACEMENTS as GENERAL_REPLACEMENTS,
    EXPERTISE_REPLACEMENTS as EXPERTISE_REPLACEMENTS,
    normalize_basic as normalize_basic,
    apply_replacements as apply_replacements,
    normalize_expertise as normalize_expertise,
    normalize_hospital as normalize_hospital,
    normalize_address as normalize_address,
    token_set as token_set,
    token_overlap as token_overlap,
    flexible_similarity as flexible_similarity,
    name_similarity as name_similarity,
    expertise_similarity as expertise_similarity,
)

from .personnel_identity import (
    match_personnel_pair as match_personnel_pair,
    location_similarity as location_similarity,
    match_practice_address as match_practice_address,
    match_hospital_name as match_hospital_name,
    match_address as match_address,
)

from .personnel_validity import (
    expiry_result as expiry_result,
)


from .personnel_assignment import (
    extract_sprint_assignment_section as extract_sprint_assignment_section,
    sprint_name_similarity as sprint_name_similarity,
    match_sprint_assigned_person as match_sprint_assigned_person,
)
