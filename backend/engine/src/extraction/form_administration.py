"""Administrative references read only from the application form."""

import re


def _compact(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_number_and_date(body):
    body = _compact(body)
    number = re.search(
        r"No\.?\s*Dokumen\s*:\s*(.*?)(?:\s*-\s*Tanggal|\s+Tanggal\b|$)",
        body,
        re.I,
    )
    date = re.search(r"Tanggal[^:]*:\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})", body, re.I)
    return {
        "number": number.group(1).strip(" -") if number else "",
        "date": date.group(1) if date else "",
    }


def extract_administration(text):
    flat = _compact(text)
    match = re.search(
        r"Dokumen Program Proteksi(?: dan Keselamatan)?(?: Radiasi)?(.*?)"
        r"(?=\d*\s*Dokumen Sistem Manajemen|B\.\s*Kelengkapan|$)",
        flat,
        re.I,
    )
    body = match.group(1) if match else ""
    proteksi = _parse_number_and_date(body)
    management = re.search(
        r"Dokumen\s+Sistem\s+Manajemen(.*?)(?=B\.\s*Kelengkapan|Dokumen\s+Program|$)", flat, re.I
    )
    manajemen = _parse_number_and_date(management.group(1) if management else "")
    documents = []
    if match:
        documents.append(
            {"document": "Dokumen Program Proteksi dan Keselamatan Radiasi", **proteksi}
        )
    if management:
        documents.append({"document": "Dokumen Sistem Manajemen", **manajemen})
    return {
        "manajemen": manajemen,
        "proteksi": proteksi,
        "documents": documents,
    }


def administration_from_table(table, category="proteksi"):
    for row in table:
        if len(row) < 3:
            continue
        label = _compact(str(row[1] or "").replace("\\n", " "))
        pattern = r"Sistem\s+Manajemen" if category == "manajemen" else r"Program\s+Proteksi"
        if not re.search(pattern, label, re.I):
            continue
        return _parse_number_and_date(row[2] or "")
    return None


def administration_documents_from_table(table):
    if not table or len(table) < 2 or len(table[0]) < 3:
        return []
    header = " ".join(_compact(cell).lower() for cell in table[0])
    if "persyaratan" not in header or "keterangan" not in header:
        return []
    documents = []
    for row in table[1:]:
        if len(row) < 3:
            continue
        title = _compact(str(row[1] or "").replace("\\n", " "))
        if not title:
            continue
        documents.append({"document": title, **_parse_number_and_date(row[2] or "")})
    return documents
