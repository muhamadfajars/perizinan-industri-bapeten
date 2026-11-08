"""Conservative comparisons: unknown and conflicting evidence must remain reviewable."""

import re
from datetime import datetime
from difflib import SequenceMatcher
from .extraction import norm
from .evidence import compact

MONTHS = {
    m: i
    for i, m in enumerate(
        "januari februari maret april mei juni juli agustus september oktober november desember".split(),
        1,
    )
}


def date_key(value):
    value = compact(value).lower()
    for month, index in MONTHS.items():
        value = re.sub(rf"\b{month}\b", str(index), value)
    parts = re.findall(r"\d+", value)
    if len(parts) != 3:
        return None
    try:
        return datetime(int(parts[2]), int(parts[1]), int(parts[0])).date().isoformat()
    except ValueError:
        return None


def compare(expected, observed, kind="text"):
    if not expected:
        return "INFO", None, "Tidak ada acuan pada formulir; hanya ditampilkan."
    if not observed:
        return "REVIEW", None, "Belum ditemukan dalam hasil pembacaan; periksa sumber dokumen."
    a, b = norm(expected), norm(observed)
    if kind == "date":
        a, b = date_key(expected), date_key(observed)
        if not a or not b:
            return "REVIEW", None, "Tanggal belum dapat dinormalisasi."
    elif kind == "institution":
        a, b = [
            norm(re.sub(r"^(?:PT|CV)\.?\s+", "", value, flags=re.I))
            for value in (expected, observed)
        ]
    elif kind == "role":

        def role(value):
            if re.search(r"\bPPR\b|petugas\s*proteksi\s*radiasi", value, re.I):
                return "ppr"
            if re.search(r"operator", value, re.I):
                return "operator"
            return norm(value)

        a, b = role(expected), role(observed)
        if a == b == "ppr" and norm(expected) != norm(observed):
            scopes = {"analisis", "radiografi", "medik", "industri"}
            left = set(re.findall(r"\w+", expected.lower())) & scopes
            right = set(re.findall(r"\w+", observed.lower())) & scopes
            if left and right and left != right:
                return (
                    "REVIEW",
                    similarity(expected, observed),
                    "Profesi PPR sama, tetapi rincian bidang berbeda.",
                )
            return (
                "MATCH",
                90,
                "Profesi PPR sesuai (skor aturan 90%); rincian keahlian/klasifikasi belum seluruhnya tercantum. Skor ini bukan verifikasi kompetensi.",
            )
    if a == b:
        if kind == "role" and norm(expected) != norm(observed):
            return "MATCH", 95, "Profesi setara (skor aturan 95%); uraian jabatan/lokasi berbeda."
        if kind == "institution" and norm(expected) != norm(observed):
            return (
                "MATCH",
                min(99.9, similarity(expected, observed)),
                "Nama inti instansi sama; penulisan bentuk badan usaha berbeda.",
            )
        return "MATCH", 100, "Nilai sesuai setelah normalisasi format."
    if kind == "address":
        return compare_address(expected, observed)
    score = similarity(a, b)
    if kind == "institution" and score >= 90:
        return (
            "MATCH",
            score,
            "Nama instansi sangat mirip; variasi ejaan tetap ditampilkan untuk ditinjau.",
        )
    return (
        "MISMATCH" if kind in ("serial", "date", "number") else "REVIEW",
        0 if kind in ("serial", "date", "number") else score,
        "Ada perbedaan nilai; periksa bukti sumber.",
    )


def similarity(a, b):
    return round(100 * SequenceMatcher(None, norm(a), norm(b)).ratio(), 1)


def address_tokens(value):
    text = value.lower()
    for short, full in (
        (r"jl[n]?", "jalan"),
        ("kab", "kabupaten"),
        ("kec", "kecamatan"),
        ("kel", "kelurahan"),
        ("prov", "provinsi"),
        ("no", "nomor"),
    ):
        text = re.sub(rf"\b{short}\b\.?", full + " ", text)
    return set(re.findall(r"[a-z]+|\d+[a-z]?", text))


def compare_address(expected, observed):
    left, right = address_tokens(expected), address_tokens(observed)
    score = round(200 * len(left & right) / max(1, len(left) + len(right)), 1)

    # Street and numeric components must agree: high overlap alone can hide another outlet.
    def street(value):
        hit = re.search(r"\b(?:jl[n]?\.?|jalan)\s+(.+?)(?=,|\bno(?:mor)?\.?\s*\d|$)", value, re.I)
        return norm(hit.group(1)) if hit else ""

    a, b = street(expected), street(observed)
    numbers_a = {s for s in left if s[0].isdigit()}
    numbers_b = {s for s in right if s[0].isdigit()}
    conflict = bool(numbers_a and numbers_b and numbers_a != numbers_b)
    if score >= 85 and a and b and a == b and not conflict:
        # Retain a less-than-perfect score for variations beyond punctuation alone.
        return (
            "MATCH",
            min(score, 99),
            "Komponen alamat proyek sesuai; singkatan/pengulangan atau cakupan penulisan berbeda.",
        )
    return (
        "REVIEW",
        score,
        "Komponen alamat belum cukup sesuai atau nomor lokasi berbeda; periksa bukti sumber.",
    )


def choose(records, key, expected):
    choices = [r for r in records if r.get(key)]
    return max(
        choices,
        key=lambda r: SequenceMatcher(None, norm(expected), norm(r[key])).ratio(),
        default=None,
    )
