"""Filename hints checked against bounded document content at upload time."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Tuple, Optional

from .classification_reader import extract_document_text

CATEGORIES = (
    "formulir",
    "proteksi",
    "manajemen",
    "teknis",
    "personel",
    "tld",
    "spesifikasi",
    "label",
    "impor",
    "kesesuaian",
    "fungsi",
    "paparan",
    "kebocoran",
)

# One source for browser and backend filename rules. Keep this JSON with the
# backend package; the frontend bundles the same file during its build.
_RULES = json.loads(
    Path(__file__).with_name("classification_rules.json").read_text(encoding="utf-8")
)
NAME_PATTERNS: list[tuple[str, str, Optional[str]]] = [
    (f"(?{_RULES['flags']}){rule['pattern']}", rule["category"], rule["subtype"])
    for rule in _RULES["filenamePatterns"]
]

# Layer 2: Regex on extracted text content
CONTENT_PATTERNS: list[tuple[str, str, Optional[str]]] = [
    (r"(?i)FOTO\s+(?:LABEL\s+)?(?:UNIT|TABUNG|GENERATOR)\b", "label", None),
    (r"(?i)(?:[A-Z0-9-]+[ \t]+){0,2}RADIATION\s+SURVEY\s+CERTIFICATE", "paparan", None),
    # Formulir
    (
        r"(?i)FORMULIR\s+PERMOHONAN|BADAN\s+PENGAWAS\s+TENAGA\s+NUKLIR\s+.*PERMOHONAN",
        "formulir",
        None,
    ),
    # Proteksi
    (
        r"(?i)PROGRAM\s+PROTEKSI\s+DAN\s+KESELAMATAN\s+RADIASI|PROGRAM\s+PROTEKSI\s+RADIASI",
        "proteksi",
        None,
    ),
    # Manajemen
    (
        r"(?i)SISTEM\s+MANAJEMEN\s+FASILITAS|SISTEM\s+MANAJEMEN\s+KESELAMATAN|SISTEM\s+MANAJEMEN\b|ASSURANCE\s+QUALIT|QUALITY\s+SYSTEM|SERTIFIKAT\s+MUTU",
        "manajemen",
        None,
    ),
    # Teknis
    (
        r"(?i)DOKUMEN\s+TEKNIS\s+FASILITAS|RENCANA\s+TEKNIS|BANGUNAN\s+GEDUNG\s+PENAHAN|DENAH\s+RUANG\s+RADIOLOGI",
        "teknis",
        None,
    ),
    # Personel
    (r"(?i)SURAT\s+KETERANGAN\s+KERJA", "personel", "Surat Keterangan Kerja"),
    (
        r"(?i)SURAT\s+PENUNJUK{1,2}AN\s+(?:TUGAS|(?:SEBAGAI\s+)?(?:PPR\b|PETUGAS\s+PROTEKSI(?:\s+RADIASI)?))|PENETAPAN\s+PEKERJA\s+RADIASI|PENUNJUKAN\s+(?:PPR\b|PETUGAS\s+PROTEKSI\s+RADIASI)|SURAT\s+KEPUTUSAN\s+PENUNJUKAN|PENGANGKATAN\s+PETUGAS\s+PROTEKSI",
        "personel",
        "Surat Penunjukan Tugas",
    ),
    (r"(?i)SURAT\s+PERINTAH", "personel", "Surat Perintah"),
    (
        r"(?i)SERTIFIKAT\s+PELATIHAN|TRAINING\s+CERTIFICATE|SAFETY\s+RADIATION\s+TRAINING",
        "personel",
        "Sertifikat Pelatihan",
    ),
    (
        r"(?i)SERTIFIKAT\s+KOMPETENSI|SERTIFIKAT\s+LULUS\s+UJI\s+KOMPETENSI|COMPETENCY\s+CERTIFICATE",
        "personel",
        "Sertifikat Kompetensi PPR",
    ),
    (
        r"(?i)(?:SURAT\s+)?IZIN\s+BEKERJA\s+PETUGAS|SURAT\s+IZIN\s+BEKERJA\s+\(SIB\)|SIB\s+PPR",
        "personel",
        "Surat Izin Bekerja (SIB)",
    ),
    (
        r"(?i)ZERO\s+CHECK|ZERO\s+CEK|(?:LAPORAN\s+)?(?:HASIL\s+)?(?:EVALUASI|PEMBACAAN)\s+DOSIS|LAPORAN\s+DOSIS|DOSIS\s+AWAL|DOSIS\s+RADIASI\s+TLD",
        "personel",
        "Evaluasi Dosis / Zero Check",
    ),
    # TLD
    # Technology names and laboratory branding alone do not identify administration.
    (
        r"(?i)DAFTAR\s+(?:PEMAKAI|PENGGUNA|PESERTA)\s+(?:LENCANA\s+)?(?:TLD|OSL|DOSIMETER)\b|PETUGAS\s+(?:TLD|OSL)\b|(?:ADMINISTRASI|KEPESERTAAN)\s+(?:(?:PEMANTAUAN|LAYANAN)\s+)?(?:TLD|OSL|DOSIMETER)\b",
        "tld",
        None,
    ),
    # Spesifikasi
    (
        r"(?i)SPESIFIKASI|SPECIFICATIONS|BROCHURE|TECHNICAL\s+SPECIFICATIONS",
        "spesifikasi",
        None,
    ),
    # Impor
    (
        r"(?i)PERSETUJUAN\s+IMPOR|SURAT\s+PERSETUJUAN\s+IMPOR|IMPORT\s+APPROVAL",
        "impor",
        None,
    ),
    # Kesesuaian
    (
        r"(?i)SERTIFIKAT\s+UJI\s+KESESUAIAN|HASIL\s+UJI\s+KESESUAIAN|LEMBAR\s+HASIL\s+UJI|DATA\s+PERMOHONAN\s+LHU",
        "kesesuaian",
        None,
    ),
    # Fungsi
    (
        r"(?i)ACCEPTANCE\s+TEST|INSTALLATION\s+AND\s+VERIFICATION|SERVICE\s+REPORT|BERITA\s+ACARA\s+UJI\s+FUNGSI|HASIL\s+UJI\s+FUNGSI",
        "fungsi",
        None,
    ),
    # Paparan & Kebocoran
    (
        r"(?i)PENGUKURAN\s+KEBOCORAN\s+TABUNG|UJI\s+KEBOCORAN\s+TABUNG",
        "kebocoran",
        None,
    ),
    (
        r"(?i)PENGUKURAN\s+PAPARAN\s+RADIASI|UJI\s+PAPARAN\s+RADIASI|LAJU\s+DOSIS\s+PAPARAN",
        "paparan",
        None,
    ),
]


# Generic mentions must not outweigh an explicit document title (for example,
# a protection program or a zero-check report mentioning TLD).
WEAK_NAME_HINTS = set(_RULES["weakNameHints"])


def classify_by_filename(
    filename: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Match filename pattern against known document rules.

    Returns:
        (category, subtype, reason) or (None, None, None)
    """
    clean_name = Path(filename).name
    matches = []
    for pattern, cat, subtype in NAME_PATTERNS:
        m = re.search(pattern, clean_name)
        if m:
            hint = re.sub(r"[\s_-]+", " ", m.group(0)).lower().strip()
            matches.append((cat, subtype, m.group(0), hint not in WEAK_NAME_HINTS))
    strong = [match for match in matches if match[3]]
    candidates = strong or matches
    if len({(cat, subtype) for cat, subtype, _, _ in candidates}) > 1:
        return (
            None,
            None,
            "Nama berkas mengarah ke beberapa kategori. Perlu Pilih Kategori.",
        )
    if candidates:
        cat, subtype, evidence, _ = candidates[0]
        return cat, subtype, f"Pola nama berkas cocok: {evidence}"
    return None, None, None


def classify_by_content(
    text: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Match extracted document text against known content patterns.

    Returns:
        (category, subtype, reason) or (None, None, None)
    """
    if not text or len(text.strip()) < 10:
        return None, None, None
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    # A real application form lists every supporting document. Those entries
    # describe requirements, not additional document titles.
    first = text.split("\f")[0]
    if re.search(r"(?im)^\s*FORMULIR\s+PERMOHONAN", first[:1000]) and all(
        re.search(pattern, first, re.I)
        for pattern in (r"nomor\s+registrasi", r"lingkup\s+kegiatan", r"instansi")
    ):
        return "formulir", None, "Judul dan struktur Formulir Permohonan ditemukan"
    # Prioritize the opening page, while retaining conflicts among personnel
    # documents (e.g. SIB and certificate bundled in the same PDF).
    page_results = []
    if "\f" in text:
        for page in text.split("\f"):
            result = classify_by_content(page)
            if result[0] or result[2]:
                page_results.append(result)
        if not page_results:
            return None, None, None
        first_result = page_results[0]
        if first_result[0] == "personel" and any(
            (r[0] == "personel" and r[1] != first_result[1]) or (not r[0] and r[2])
            for r in page_results
        ):
            return (
                None,
                None,
                "Beberapa jenis dokumen personel ditemukan dalam satu file. Perlu Pilih Kategori.",
            )
        return first_result
    # Course syllabi list program/system titles; they are not those documents.
    if re.search(
        r"daftar\s+unit\s+kompetensi|mata\s+ajar|subjects\s+of\s+the\s+training", text[:1200], re.I
    ):
        return None, None, None
    if (
        re.search(
            r"(?im)^\s*(?:SERTIFIKAT\s+PELATIHAN|TRAINING\s+CERTIFICATE|CERTIFICATE)\b", text[:1200]
        )
        and re.search(r"telah\s+mengikuti|has\s+participated|dengan\s+kualifikasi", text, re.I)
        and re.search(r"radiasi|radiation|\bPPR\b|\boperator\b", text, re.I)
    ):
        if re.search(r"(?im)^\s*(?:SURAT\s+)?IZIN\s+BEKERJA\s+PETUGAS", text):
            return (
                None,
                None,
                "Sertifikat dan izin bekerja ditemukan bersama. Perlu Pilih Kategori.",
            )
        return (
            "personel",
            "Sertifikat Pelatihan",
            "Judul sertifikat dan keterangan pelatihan personel ditemukan",
        )
    if (
        re.search(r"(?im)^\s*(?:LAPORAN\s+(?:HASIL\s+)?)?.*UJI\s+PAPARAN\s+RADIASI\b", text[:1200])
        and re.search(r"(?i)\bUJI\s+(?:FUNGSI|KOMISIONING)\b", text[:1200])
    ):
        return "fungsi", None, "Laporan gabungan uji paparan dan uji fungsi/komisioning terdeteksi"
    candidates = {}
    # Require a heading at the start of a line. Mentions within narrative text
    # are not enough evidence to choose a document category.
    for pattern, cat, subtype in CONTENT_PATTERNS:
        for m in re.finditer(pattern, text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            prefix = text[line_start : m.start()]
            line_end = text.find("\n", m.end())
            suffix = text[m.end() : line_end if line_end >= 0 else len(text)]
            if re.search(r"\.{3,}|…|\s\d+\s*$", suffix):
                continue
            if re.fullmatch(r"\s*(?:(?:DOKUMEN|LAPORAN(?:\s+HASIL)?)\s+)?", prefix, re.IGNORECASE):
                candidates[(cat, subtype)] = m.group(0)
    if len(candidates) == 1:
        (cat, subtype), evidence = next(iter(candidates.items()))
        return cat, subtype, f"Judul dokumen cocok: {evidence}"
    if candidates:
        return (
            None,
            None,
            "Judul dokumen mengarah ke beberapa kategori. Perlu Pilih Kategori.",
        )
    if (
        re.search(r"(?i)\btest(?:ing)?\s+report\b", text[:1500])
        and re.search(
            r"(?i)\b(?:radiation\s+protection\s+detection|(?:x[-\s]*[γy]\s+)?radiation\s+dose\s+rate)\b",
            text,
        )
        and not re.search(r"(?i)\b(?:uji\s+fungsi|functional\s+test|acceptance\s+test)\b", text)
    ):
        return "paparan", None, "Laporan pengujian laju dosis / proteksi radiasi terdeteksi"
    if (
        re.search(r"(?i)\b(?:calibration\s+certificate|sertifikat\s+kalibrasi)\b", text[:1200])
        and re.search(
            r"(?i)\b(?:name\s+of\s+product|instrument\s+serial|portable\s+xrf|handheld\s+xrf|x[\s-]*ray\s+(?:analyzer|unit|tube|equipment))\b",
            text,
        )
        and not re.search(
            r"(?i)\b(?:surveymeter|survey\s+meter|dose\s+rate\s+meter|dosimeter|tld|alat\s+ukur)\b",
            text,
        )
    ):
        return "fungsi", None, "Sertifikat kalibrasi/QC pabrikan peralatan sinar-X terdeteksi"
    if re.search(
        r"(?:CAUTION|DANGER|WARNING)\s+(?:X[\s-]*RAY|RADIATION)|"
        r"PRODUCES\s+RADIATION(?:\s+.*?)?\s+WHEN\s+ENERGIZED|"
        r"RADIATION\s+WHEN\s+ENERGIZED",
        text,
        re.I | re.S,
    ):
        return "label", None, "Label peringatan radiasi pada unit/tabung terdeteksi"
    if (
        len(text.strip()) < 800
        and re.search(r"(?i)\bMODEL\s*[:/]\s*\S+", text)
        and re.search(r"(?i)\b(?:SERIAL(?:\s*(?:NO\.?|NUMBER))?|S/?N)\s*[:#]?\s*[A-Z0-9-]{4,}", text)
    ):
        return "label", None, "Label spesifikasi/nomor seri unit atau tabung terdeteksi"
    return None, None, None


def _is_photo_album_pdf(filename: str, file_bytes: bytes, ocr_text: str) -> bool:
    """Detect multi-photo PDFs (unit/label photos) that lack native text and OCR prose."""
    if Path(filename).suffix.lower() != ".pdf":
        return False
    if re.search(
        r"denah|lokasi|peta|layout|gedung|sertifikat|surat|formulir|laporan|uji|program|sistem|tld|osl",
        filename,
        re.I,
    ):
        return False
    if len(re.sub(r"\s+", "", ocr_text or "")) >= 120:
        return False
    import pymupdf

    with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
        native_chars = 0
        photo_pages = 0
        large_images = 0
        for page in doc[:6]:
            native_chars += len(re.sub(r"\s+", "", page.get_text("text") or ""))
            area = max(page.rect.width * page.rect.height, 1)
            page_large = sum(
                1
                for info in page.get_image_info()
                if pymupdf.Rect(info["bbox"]).get_area() / area >= 0.15
            )
            if page_large:
                photo_pages += 1
                large_images += page_large
        return native_chars < 30 and (photo_pages >= 2 or large_images >= 2)


def classify_document(filename: str, file_bytes: Optional[bytes] = None) -> dict[str, Any]:
    """Two-layer classification for a document.

    Layer 1: Filename heuristic analysis.
    Layer 2: Bounded content inspection of six opening pages, up to three OCR pages.
    """
    clean_name = Path(filename).name

    # Filename-only calls remain available, but uploaded bytes are always inspected.
    cat1, sub1, reason1 = classify_by_filename(clean_name)
    if cat1 and file_bytes is None:
        return {
            "filename": clean_name,
            "category": cat1,
            "subtype": sub1,
            "layer": 1,
            "reason": reason1,
            "confidence": 0.95,
        }

    # Layer 2
    reason2 = None
    if file_bytes:
        try:
            text = extract_document_text(clean_name, file_bytes, max_pages=6)
        except Exception:
            return {
                "filename": clean_name,
                "category": "unknown",
                "subtype": None,
                "layer": 0,
                "confidence": 0.0,
                "reason": "Isi dokumen belum dapat diperiksa (file rusak, terkunci, atau OCR gagal). Silakan pilih kategori.",
            }
        cat2, sub2, reason2 = classify_by_content(text)
        conflict = (
            (reason1 and not cat1) or (reason2 and not cat2) or (cat1 and cat2 and cat1 != cat2)
        )
        if conflict:
            return {
                "filename": clean_name,
                "category": "unknown",
                "subtype": None,
                "layer": 0,
                "confidence": 0.0,
                "reason": reason2
                if reason2 and not cat2
                else "Nama berkas dan/atau isi menunjukkan jenis dokumen berbeda. Perlu Pilih Kategori.",
            }
        if cat2:
            return {
                "filename": clean_name,
                "category": cat2,
                "subtype": sub2,
                "layer": 2,
                "reason": reason2,
                "confidence": 0.90,
            }
        if cat1:
            return {
                "filename": clean_name,
                "category": cat1,
                "subtype": sub1,
                "layer": 1,
                "confidence": 0.65,
                "reason": f"{reason1}. Judul pada isi belum terkonfirmasi; periksa kategori.",
            }
        if not reason1 and not reason2 and _is_photo_album_pdf(clean_name, file_bytes, text):
            return {
                "filename": clean_name,
                "category": "label",
                "subtype": None,
                "layer": 2,
                "confidence": 0.80,
                "reason": "PDF berisi rangkaian foto fisik unit/label tanpa teks dokumen.",
            }

    # Unknown
    return {
        "filename": clean_name,
        "category": "unknown",
        "subtype": None,
        "layer": 0,
        "reason": reason1
        or reason2
        or "Dokumen belum teridentifikasi otomatis, silakan tentukan kategori",
        "confidence": 0.0,
    }
