"""Administrative references read only from the application form."""

import re


def extract_administration(text):
    flat = re.sub(r"\s+", " ", text)
    match = re.search(
        r"Dokumen Program Proteksi(?: dan Keselamatan)?(?: Radiasi)?(.*?)"
        r"(?=\d*\s*Dokumen Sistem Manajemen|B\.\s*Kelengkapan|$)",
        flat,
        re.I,
    )
    body = match.group(1) if match else ""
    number = re.search(r"No\.?\s*Dokumen\s*:\s*(.*?)\s*-?\s*Tanggal", body, re.I)
    date = re.search(
        r"Tanggal\s+(?:Pengesahan\s+)?Dokumen\s*:\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})", body, re.I
    )
    return {
        "proteksi": {
            "number": number.group(1).strip() if number else "",
            "date": date.group(1) if date else "",
        }
    }


def administration_from_table(table):
    for row in table:
        if len(row) < 3:
            continue
        label = re.sub(r"\s+", " ", str(row[1] or ""))
        if not re.search(r"Program\s+Proteksi", label, re.I):
            continue
        body = re.sub(r"\s+", " ", str(row[2] or ""))
        number = re.search(r"No\.?\s*Dokumen\s*:\s*(.*?)\s*-\s*Tanggal", body, re.I)
        date = re.search(r"Tanggal[^:]*:\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})", body, re.I)
        return {
            "number": number.group(1).strip() if number else "",
            "date": date.group(1) if date else "",
        }
    return None
