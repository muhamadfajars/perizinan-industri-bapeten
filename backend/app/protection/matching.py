"""Conservative comparisons: unknown and conflicting evidence must remain reviewable."""

import re
from datetime import datetime
from difflib import SequenceMatcher
from .extraction import norm
from .evidence import compact
from .identity import person_similarity

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
            norm(
                re.sub(
                    r"\brs\.?\b",
                    "rumahsakit",
                    re.sub(r"^(?:PT|CV)\.?\s+", "", value, flags=re.I),
                    flags=re.I,
                )
            )
            for value in (expected, observed)
        ]
    elif kind == "role":
        if any(
            re.search(
                r"\b(?:bukan|tidak|belum|non|nonaktif|mantan|eks|calon|pensiun|not|former)\b",
                value,
                re.I,
            )
            for value in (expected, observed)
        ):
            return (
                "REVIEW",
                similarity(expected, observed),
                "Ada negasi atau keterangan status profesi; periksa konteks pada sumber.",
            )

        def role(value):
            if re.search(r"\bPPR\b|petugas\s*proteksi\s*radiasi", value, re.I):
                return "ppr"
            if re.search(r"\boperator\b", value, re.I):
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
    if kind in ("brand", "model"):
        from ..exposure_hybrid import evaluate_exposure_field

        field_key = "merk_unit" if kind == "brand" else "tipe_unit"
        status, eq_score, note = evaluate_exposure_field(field_key, expected, observed)
        return status, eq_score, note or "Ada perbedaan nilai; periksa bukti sumber."
    score = similarity(a, b)
    if kind == "institution" and score >= 90:
        return (
            "MATCH",
            score,
            "Nama instansi sangat mirip; variasi ejaan tetap ditampilkan untuk ditinjau.",
        )
    if kind == "institution":
        return compare_institution(expected, observed, score)
    if kind == "number" and min(len(a), len(b)) >= 4:
        clean_exp = re.sub(r"[\s_/.-]+", " ", str(expected).strip().casefold()).strip()
        clean_obs = re.sub(r"[\s_/.-]+", " ", str(observed).strip().casefold()).strip()
        if clean_obs.startswith(clean_exp + " ") or clean_exp.startswith(clean_obs + " "):
            return (
                "REVIEW",
                score,
                "Kode dasar nomor dokumen sesuai, tetapi terdapat perbedaan rincian/akhiran; periksa bukti sumber.",
            )
    return (
        "MISMATCH" if kind in ("serial", "date", "number") else "REVIEW",
        0 if kind in ("serial", "date", "number") else score,
        "Ada perbedaan nilai; periksa bukti sumber.",
    )


_INSTITUTION_GENERIC_TOKENS = {
    "pt",
    "cv",
    "ud",
    "fa",
    "tbk",
    "persero",
    "perseroda",
    "perum",
    "pd",
    "yayasan",
    "koperasi",
    "ltd",
    "co",
    "inc",
    "corp",
    "llc",
    "gmbh",
    "sdn",
    "bhd",
    "indonesia",
    "nusantara",
    "rumah",
    "sakit",
    "rs",
    "rsud",
    "rsj",
    "rsu",
    "rsia",
    "rumkit",
    "klinik",
    "puskesmas",
    "laboratorium",
    "lab",
    "balai",
    "dinas",
    "badan",
    "kementerian",
    "universitas",
    "institut",
    "politeknik",
    "umum",
    "daerah",
    "utama",
    "pratama",
    "cabang",
    "site",
    "plant",
    "factory",
    "office",
    "head",
    "kantor",
    "pusat",
    "unit",
    "divisi",
    "departemen",
    "bagian",
    "tk",
    "tingkat",
}
_CORPORATE_PREFIXES = {"pt", "cv", "ud", "fa", "tbk", "persero", "ltd", "co", "inc"}


def compare_institution(expected, observed, score):
    """Distinguish minor institution/acronym/typo variants (REVIEW) from different entities (MISMATCH)."""

    def _inst_words(value):
        t = re.sub(r"\brs\.?\b|\brumkit\b", "rumah sakit", str(value or "").lower())
        return [w for w in re.findall(r"[a-z0-9]+", t) if w]

    raw_a = _inst_words(expected)
    raw_b = _inst_words(observed)
    core_list_a = [w for w in raw_a if w not in _INSTITUTION_GENERIC_TOKENS]
    core_list_b = [w for w in raw_b if w not in _INSTITUTION_GENERIC_TOKENS]
    words_a = set(core_list_a)
    words_b = set(core_list_b)

    fuzzy_shared = any(
        SequenceMatcher(None, wa, wb).ratio() >= 0.80
        for wa in words_a
        for wb in words_b
    )
    non_corp_a = [w for w in raw_a if w not in _CORPORATE_PREFIXES]
    non_corp_b = [w for w in raw_b if w not in _CORPORATE_PREFIXES]
    initials_a = "".join(w[0] for w in non_corp_a)
    initials_b = "".join(w[0] for w in non_corp_b)
    acronym_match = (
        len(initials_a) >= 2 and (initials_a in words_b or initials_a == norm(observed))
    ) or (len(initials_b) >= 2 and (initials_b in words_a or initials_b == norm(expected)))
    core_sim = (
        round(100 * SequenceMatcher(None, "".join(core_list_a), "".join(core_list_b)).ratio(), 1)
        if (core_list_a and core_list_b)
        else 0.0
    )
    if words_a and words_b and not fuzzy_shared and not acronym_match and core_sim < 55.0:
        return ("MISMATCH", score, "Nama instansi pada dokumen berbeda dari formulir.")
    return ("REVIEW", score, "Ada perbedaan penulisan nama instansi; periksa bukti sumber.")


def similarity(a, b):
    return round(100 * SequenceMatcher(None, norm(a), norm(b)).ratio(), 1)


_ADMIN_STOPWORDS = {
    "kabupaten",
    "kota",
    "provinsi",
    "propinsi",
    "daerah",
    "wilayah",
    "desa",
    "kelurahan",
    "kecamatan",
    "negara",
    "indonesia",
    "republic",
    "republik",
    "dki",
    "istimewa",
    "khusus",
}

_ADDRESS_GENERIC_TOKENS = _ADMIN_STOPWORDS | {
    "jalan",
    "nomor",
    "blok",
    "rt",
    "rw",
    "gang",
    "kavling",
    "lantai",
    "gedung",
    "komplek",
    "ruko",
    "kawasan",
    "utara",
    "selatan",
    "barat",
    "timur",
    "tengah",
    "pusat",
    "raya",
}


def address_tokens(value):
    text = value.lower()
    for short, full in (
        (r"jl[n]?", "jalan"),
        ("kab", "kabupaten"),
        ("kec", "kecamatan"),
        ("kel", "kelurahan"),
        ("prov", "provinsi"),
        ("no", "nomor"),
        (r"komp(?:leks)?", "komplek"),
        ("gg", "gang"),
        ("kav", "kavling"),
        ("lt", "lantai"),
        (r"gdg|gd", "gedung"),
        (r"ds", "desa"),
    ):
        text = re.sub(rf"\b{short}\b\.?", full + " ", text)
    return set(re.findall(r"[a-z]+|\d+[a-z]?", text))


def compare_address(expected, observed):
    left, right = address_tokens(expected), address_tokens(observed)
    score = round(200 * len(left & right) / max(1, len(left) + len(right)), 1)

    # Street/landmark and numeric components must agree: high overlap alone can hide another outlet.
    def street(value):
        normalized = re.sub(r"\bkomp(?:lek[s]?)?\b\.?", "komplek", value, flags=re.I)
        normalized = re.sub(r"\b(?:gdg|gd)\b\.?", "gedung", normalized, flags=re.I)
        hit = re.search(
            r"\b(?:jl[n]?\.?|jalan)\s+(.+?)(?=,|\bno(?:mor)?\.?\s*\d|$)", normalized, re.I
        )
        if hit:
            return ("street", norm(hit.group(1)), hit.group(1))
        landmark = re.search(
            r"\b(?:komplek|kawasan|gedung|ruko|blok)\s+(.+?)(?=,|\bno(?:mor)?\.?\s*\d|$)",
            normalized,
            re.I,
        )
        return ("landmark", norm(landmark.group(1)), landmark.group(1)) if landmark else ("", "", "")

    a_kind, a, a_raw = street(expected)
    b_kind, b, b_raw = street(observed)
    numbers_a = {s for s in left if s[0].isdigit()}
    numbers_b = {s for s in right if s[0].isdigit()}
    conflict = bool(numbers_a and numbers_b and numbers_a != numbers_b)

    content_a = left - _ADMIN_STOPWORDS
    content_b = right - _ADMIN_STOPWORDS
    min_content = min(len(content_a), len(content_b))
    content_overlap = len(content_a & content_b) / max(1, min_content) if min_content else 0

    if a and b and a_kind == b_kind and a == b and not conflict:
        if score >= 85:
            # Retain a less-than-perfect score for variations beyond punctuation alone.
            return (
                "MATCH",
                min(score, 99),
                "Komponen alamat proyek sesuai; singkatan/pengulangan atau cakupan penulisan berbeda.",
            )
        if content_overlap >= 0.85 and min_content >= 3:
            effective_score = max(
                score, min(95.0, round(0.5 * score + 0.5 * (content_overlap * 100), 1))
            )
            return (
                "MATCH",
                effective_score,
                "Komponen utama alamat sesuai; dokumen mencantumkan rincian wilayah (desa/kecamatan) yang lebih lengkap.",
            )

    loc_a = left - _ADDRESS_GENERIC_TOKENS
    loc_b = right - _ADDRESS_GENERIC_TOKENS
    min_loc = min(len(loc_a), len(loc_b))
    loc_overlap = len(loc_a & loc_b) / max(1, min_loc) if min_loc else 0.0
    street_tokens_a = address_tokens(a_raw) - _ADDRESS_GENERIC_TOKENS if a_raw else set()
    street_tokens_b = address_tokens(b_raw) - _ADDRESS_GENERIC_TOKENS if b_raw else set()
    street_shared = bool(street_tokens_a & street_tokens_b)
    street_sim = SequenceMatcher(None, a, b).ratio() if (a and b) else 0.0

    clearly_different_street = (
        bool(a and b)
        and min_loc >= 3
        and not street_shared
        and street_sim < 0.55
        and loc_overlap < 0.35
    )
    zero_location_overlap = min_loc >= 3 and loc_overlap == 0.0 and score < 35.0
    if clearly_different_street or zero_location_overlap:
        return (
            "MISMATCH",
            score,
            "Alamat pada dokumen menunjukkan lokasi yang berbeda dari Alamat Proyek pada formulir.",
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
        key=lambda r: (
            person_similarity(expected, r[key])
            if key == "name"
            else SequenceMatcher(None, norm(expected), norm(r[key])).ratio()
        ),
        default=None,
    )
