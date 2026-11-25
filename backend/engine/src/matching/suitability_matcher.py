"""Conservative shared institution, address, and equipment comparison helpers."""

import re
from difflib import SequenceMatcher


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").casefold())


def _words(s):
    t = str(s or "").casefold()
    t = re.sub(r"\brsud\b", "rumah sakit umum daerah", t)
    t = re.sub(r"\brsj\b", "rumah sakit jiwa", t)
    t = re.sub(r"\brs\b|\brumkit\b", "rumah sakit", t)
    t = re.sub(r"\btk\b", "tingkat", t)
    t = re.sub(r"\bjl\b|\bjln\b", "jalan", t)
    t = re.sub(r"\bno\b", "nomor", t)
    return re.findall(r"[a-z0-9]+", t)


def _score(a, b):
    wa, wb = set(_words(a)), set(_words(b))
    if not wa or not wb:
        return 0.0
    containment = len(wa & wb) / min(len(wa), len(wb)) * 100
    similarity = SequenceMatcher(None, " ".join(_words(a)), " ".join(_words(b))).ratio() * 100
    return round(max(similarity, containment * 0.92), 1)


def _result(status, score=0.0, reason=None):
    d = {"status": status, "score": round(score, 2)}
    if reason:
        d["reason"] = reason
    return d


def _street_number(s):
    t = " ".join(_words(s))
    nums = re.findall(r"\b(?:nomor|no)\s*(\d+[a-z]?)\b", t)
    return nums[0] if nums else None


def compare_institution(form_value, suitability_value):
    if not form_value or not suitability_value:
        return _result("MISSING")
    a, b = _words(form_value), _words(suitability_value)
    aa, bb = set(a), set(b)
    score = _score(form_value, suitability_value)
    # Extra suffix/registry code is fine, but core name must be supported.
    if aa == bb or (min(len(aa), len(bb)) >= 2 and len(aa & bb) / min(len(aa), len(bb)) >= 0.85):
        return _result("MATCH", max(score, 90))
    return _result("REVIEW" if score >= 65 else "MISMATCH", score)


def _address_features(value):
    s = str(value or "").lower()
    s = re.split(r"(?i)\b(?:telp|telepon|fax|phone)\s*[.:]", s)[0]
    s = re.sub(
        r"(?i)\b(?:rumah\s+sakit|rs\.?|rumkit|klinik)[^,]{0,85},\s*(?=(?:jl|jln|jalan)\b)",
        "",
        s,
    )
    s = re.sub(r"(?i)\b(?:jl|jln)\.?", "jalan", s)
    s = re.sub(r"(?i)\bno\b\.?\s*", "nomor ", s)
    s = re.sub(r"(?i)\b(?:rt|rw)\s*\.?\s*\d+(?:\s*/\s*\d+)?", " ", s)
    s = re.sub(r"(?i)\b(?:kp|kampung|kec|kecamatan|kel|kelurahan)\s*[. ]", " ", s)
    s = re.sub(r"(?i)\b(?:kode\s*pos)\s*[:.]?", " ", s)
    return s


def _number_from_street(s):
    s = _address_features(s)
    m = re.search(r"(?i)\bjalan\s+.{1,85}?\bnomor\s*(\d+[a-z]?)\b", s)
    return m.group(1) if m else None


def _street_tokens(s):
    s = _address_features(s)
    m = re.search(r"(?i)\bjalan\s+(.+?)(?:\bnomor\b|,|$)", s)
    if not m:
        return set()
    return set(re.findall(r"[a-z0-9]+", m.group(1))) - {"dr", "tni", "ad", "mayor"}


def compare_address(form_value, suitability_value):
    if not form_value or not suitability_value:
        return _result("MISSING")
    a, b = _address_features(form_value), _address_features(suitability_value)
    n1, n2 = _number_from_street(a), _number_from_street(b)
    street1, street2 = _street_tokens(a), _street_tokens(b)
    score = _score(a, b)
    if n1 and n2 and n1 != n2:
        return _result("REVIEW", score, "Nomor bangunan berbeda")
    if street1 and street2:
        overlap = len(street1 & street2) / max(1, min(len(street1), len(street2)))
        if overlap >= 0.75 and n1 and n2 and n1 == n2:
            # Score measures verified components, rather than unclean whole text.
            return _result("MATCH", max(90, round(90 + 10 * overlap, 1)))
        if overlap >= 0.75:
            return _result("REVIEW", max(score, 75), "Nomor bangunan belum sama-sama tersedia")
        if overlap < 0.40:
            return _result("REVIEW", score, "Nama jalan tampak berbeda")
    if score >= 90:
        return _result(
            "REVIEW",
            score,
            "Alamat mirip tetapi komponen inti belum cukup terverifikasi",
        )
    return _result("REVIEW", score, "Verifikasi alamat pada dokumen asli")


def compare_equipment_value(left, right, kind="type"):
    if not left or not right:
        return _result("MISSING")
    aa, bb = _norm(left), _norm(right)
    if aa == bb:
        return _result("MATCH", 100)
    if kind == "serial":
        return _result("MISMATCH", SequenceMatcher(None, aa, bb).ratio() * 100)
    score = _score(left, right)
    if kind == "brand":
        words_left = set(_words(left))
        words_right = set(_words(right))
        if len(words_left) == 1 and words_left <= words_right:
            return _result("MATCH", 100)
    if kind == "type" and len(aa) >= 5 and len(bb) >= 5 and (aa in bb or bb in aa):
        return _result("MATCH", 100)
    return _result("MATCH" if score >= 95 else "REVIEW" if score >= 65 else "MISMATCH", score)
