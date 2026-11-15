"""Identity vocabulary and conservative name keys shared by extraction and matching."""

import re
from difflib import SequenceMatcher

INSTITUTION = r"(?:PT|CV|RSUD|RSUP|RS|Rumah\s+Sakit|Klinik|Universitas|Institut|Politeknik|Balai|Koperasi|Yayasan|Badan|Dinas|Puskesmas)"
ADDRESS = r"\b(?:jl|jalan|jln|outlet|cabang|kawasan|desa|kelurahan|kel|dusun|kampung|kecamatan|kec|kabupaten|kab|kota|rt|rw|km|komplek[s]?|komp|gedung|ruko|blok)\b"


ADDRESS_LABEL = r"\b(?:alamat(?:\s+(?:proyek|lokasi(?:\s+pemanfaatan)?|perusahaan|fasilitas|tempat))?|lokasi\s+(?:proyek|pemanfaatan)|tempat\s+kegiatan)\s*:"
STRONG_STREET = r"\b(?:jl|jln|jalan|komplek[s]?|komp|kawasan)\b"
INSTITUTION_LABEL = r"\b(?:nama\s+)?(?:instansi|perusahaan|pemohon|fasilitas)\s*:"

OFFICE_LABEL = r"\b(?:alamat\s+kantor(?:\s+pusat)?|kantor\s+pusat|domisili\s+kantor)\b"
PROJECT_LABEL = r"\b(?:alamat\s+(?:proyek|lokasi\s+pemanfaatan|kegiatan)|lokasi\s+(?:proyek|pemanfaatan|kegiatan)|tempat\s+kegiatan)\b"


def office_address(value, text):
    """Reject address spans under an office label, including a separate label line.

    Inspect the source rather than the model's quote: a quote can omit its label.
    A later explicit project label starts a distinct address block.
    """
    normalize = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    target = normalize(value)
    roles = []
    current = []
    role = None
    for line in text.splitlines():
        is_project = bool(re.search(PROJECT_LABEL, line, re.I))
        is_office = bool(re.search(OFFICE_LABEL, line, re.I))
        boundary = (
            is_project
            or is_office
            or bool(
                re.match(
                    r"\s*(?:Alamat\b|Nama\b|Telepon\b|Telp\b|Email\b|Kota\b|Kode\s+Pos\b|BAB\b|\d+\.\d+\s)",
                    line,
                    re.I,
                )
            )
        )
        if boundary:
            if role:
                roles.append((role, " ".join(current)))
            current = []
            role = "project" if is_project else "office" if is_office else None
        current.append(line)
    if role:
        roles.append((role, " ".join(current)))

    # A project label takes precedence when the same address is used for both roles.
    project_matches = any(target in normalize(block) for role, block in roles if role == "project")
    office_matches = any(target in normalize(block) for role, block in roles if role == "office")
    return bool(target) and office_matches and not project_matches


def identity_candidate(text):
    return bool(
        re.search(
            r"alamat|lokasi|identitas|instansi|perusahaan|"
            + ADDRESS
            + r"|\b"
            + INSTITUTION
            + r"\b",
            text,
            re.I,
        )
    )


def address_score(page):
    text = page["text"]
    parts = {re.sub(r"[^a-z]", "", m.lower()) for m in re.findall(ADDRESS, text, re.I)}
    has_label = bool(re.search(ADDRESS_LABEL, text, re.I))
    has_street = bool(re.search(STRONG_STREET, text, re.I))
    has_postal = bool(re.search(r"\b\d{5}\b", text))
    # Ignore body prose mentioning one generic location/building word without address structure.
    if (
        page["page"] > 3
        and not has_label
        and not has_street
        and not (has_postal and parts)
        and len(parts) < 2
    ):
        return 0
    score = 0
    if has_label:
        score += 100
    if has_street:
        score += 60
    if has_postal and parts:
        score += 40
    if len(parts) >= 3:
        score += 50
    elif len(parts) == 2:
        score += 30
    elif page["page"] <= 3 and (parts or re.search(r"\b(?:alamat|lokasi)\b", text, re.I)):
        score += 20
    return score


def institution_score(page):
    text = page["text"]
    has_label = bool(re.search(INSTITUTION_LABEL, text, re.I))
    has_entity = bool(re.search(r"\b" + INSTITUTION + r"\.?\s+[A-Z]", text))
    if page["page"] > 3 and not has_label and not has_entity:
        return 0
    score = 0
    if has_label:
        score += 80
    if has_entity:
        score += 60
    if page["page"] <= 3 and identity_candidate(text):
        score += 20
    return score


def ranked_identity_pages(pages, missing, *, toc_fn):
    scored = []
    for page in pages:
        if toc_fn(page["text"]):
            continue
        score = 0
        if "project_address" in missing:
            score += address_score(page)
        if "institution" in missing:
            score += institution_score(page)
        if score > 0:
            scored.append((score, page["page"], page))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored]


def person_key(value):
    # Remove only known titles at the edges; preserve initials and all name tokens.
    value = str(value or "").strip()
    value = re.sub(r"^(?:(?:prof|dr|drs|dra|ir|h|hj)\.?\s+)+", "", value, flags=re.I)
    value = re.sub(
        r",?\s+(?:(?:S|M|D)\.?\s*(?:T|Si|Kom|Pd|Sc|Kes|H|E)\.?|Ph\.?D\.?)\s*$",
        "",
        value,
        flags=re.I,
    )
    return re.sub(r"[^a-z0-9]", "", value.lower())


def person_similarity(left, right):
    a, b = person_key(left), person_key(right)
    return SequenceMatcher(None, a, b).ratio() if a and b else 0
