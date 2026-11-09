"""Display-only content: regulations, dose limits, controlled areas and approval."""

import re

REQUIRED_LAWS = [
    ("UU", "10", "1997"),
    ("PP", "45", "2023"),
    ("PP", "28", "2025"),
    ("Perba", "4", "2024"),
    ("Perba", "5", "2025"),
]
REQUIRED_LAW_TITLES = {
    ("UU", "10", "1997"): "Undang-Undang Nomor 10 Tahun 1997 tentang Ketenaganukliran",
    (
        "PP",
        "45",
        "2023",
    ): "Peraturan Pemerintah Nomor 45 Tahun 2023 tentang Keselamatan Radiasi Pengion dan Keamanan Zat Radioaktif",
    (
        "PP",
        "28",
        "2025",
    ): "Peraturan Pemerintah Nomor 28 Tahun 2025 tentang Penyelenggaraan Perizinan Berusaha Berbasis Risiko",
    (
        "Perba",
        "4",
        "2024",
    ): "Peraturan Badan Pengawas Tenaga Nuklir Nomor 4 Tahun 2024 tentang Izin Bekerja Petugas pada Fasilitas Radiasi dan/atau Kegiatan Pemanfaatan Sumber Radiasi Pengion",
    (
        "Perba",
        "5",
        "2025",
    ): "Peraturan Badan Pengawas Tenaga Nuklir Nomor 5 Tahun 2025 tentang Standar Kegiatan Usaha dan/atau Standar Produk/Jasa pada Penyelenggaraan Perizinan Berusaha Berbasis Risiko Sektor Ketenaganukliran",
}
LAW = re.compile(
    r"\b(Peraturan\s+Presiden|Perpres|Peraturan\s+Menteri(?:\s+[A-Za-z]+){0,6}?|Permen|Peraturan\s+Daerah|Perda|Undang[\s-]*Undang|UU|Peraturan\s+Pemerintah|PP|"
    r"Peraturan\s+(?:Kepala\s+)?(?:BAPETEN|Badan\s+Pengawas\s+Tenaga\s+Nuklir)|PERBA|PERKA)"
    r"\s*(?:Republik\s+Indonesia\s*)?(?:(?:Nomor|No\.?)\s*)*(\d{1,3})\s*(?:Tahun\s*|/\s*)(\d{4})\b",
    re.I,
)


def compact(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def toc(text):
    return bool(
        re.search(r"daftar\s+isi", text[:1000], re.I) or len(re.findall(r"\.{4,}", text)) > 6
    )


def snippets(pages, pattern, *, numeric=False):
    found = []
    for page in pages:
        if toc(page["text"]):
            continue
        text = compact(page["text"])
        for hit in re.finditer(pattern, text, re.I):
            quote = text[max(0, hit.start() - 60) : hit.end() + 750]
            if numeric and not re.search(r"\d[\d.,]*\s*(?:mSv|µSv|μSv|uSv|Sv)\b", quote, re.I):
                continue
            found.append({"page": page["page"], "quote": quote, "has_visual": page["has_visual"]})
            break
    return found


def legal_section(pages):
    """Find a legal-reference heading regardless of its section number."""
    result = []
    active = False
    heading = re.compile(
        r"(?m)^[ \t]*(?:(?:\d+(?:\s*\.\s*\d+)*[.)]?|[A-Z][.)])\s+)?(?:Dasar\s+Hukum(?:\s*/\s*Referensi)?|Landasan\s+Hukum|Referensi\s+Hukum|Referensi)[ \t]*$",
        re.I,
    )
    end = re.compile(
        r"(?m)^\s*(?:BAB\s+(?:[IVXLCDM]+|\d+)\b|\d+\s*\.\s*\d+(?:\s*\.\s*\d+)*\s+|[A-Z][.)]\s+)",
        re.I,
    )
    for page in pages:
        text = page["text"]
        if toc(text):
            continue
        if not active:
            start = heading.search(text)
            if not start:
                continue
            active = True
            text = text[start.end() :]
        stop = end.search(text)
        if stop:
            text = text[: stop.start()]
        if text.strip():
            result.append({**page, "text": text})
        if stop:
            break
    return result


def information(pages, make_row):
    from .dose import dose_statements

    laws = {}
    reference_pages = legal_section(pages)
    for page in reference_pages:
        if toc(page["text"]):
            continue
        text = compact(page["text"])
        for match in LAW.finditer(text):
            kind, number, year = match.groups()
            kind = (
                "UU"
                if re.match(r"UU|Undang", kind, re.I)
                else "PP"
                if re.fullmatch(r"PP|Peraturan\s+Pemerintah", kind, re.I)
                else "Perba"
                if re.search(r"BAPETEN|Pengawas|PERBA|PERKA", kind, re.I)
                else compact(kind)
            )
            laws.setdefault((kind, str(int(number)), year), []).append(
                {"page": page["page"], "quote": text[match.start() : match.end() + 220]}
            )
    rows = []
    for key in [*REQUIRED_LAWS, *(k for k in laws if k not in REQUIRED_LAWS)]:
        found = laws.get(key, [])
        title = REQUIRED_LAW_TITLES.get(key, f"{key[0]} Nomor {key[1]} Tahun {key[2]}")
        note = (
            "Tercantum pada bagian Dasar Hukum / Referensi."
            if found
            else "Belum ditemukan pada bagian Dasar Hukum / Referensi; periksa dokumen sumber."
        )
        rows.append(
            make_row(
                "Dasar hukum: " + title,
                "",
                title if found else "Belum ditemukan dalam teks terbaca",
                found,
                note,
                group="Dasar hukum",
                required=key in REQUIRED_LAWS,
            )
        )
    topics = [
        ("Daerah Pengendalian", r"daerah\s+pengendalian|area\s+pengendalian", True),
        (
            "Daerah Pengawasan / Supervisi",
            r"daerah\s+(?:pengawasan|supervisi)|area\s+supervisi",
            True,
        ),
        ("Pembatas Dosis", r"pembatas\s+dosis|nilai\s+batas\s+dosis|batas\s+dosis|\bNBD\b", False),
    ]
    for title, pattern, visual in topics:
        found = snippets(pages, pattern) if visual else dose_statements(pages)
        if visual:
            diagrams = snippets(
                pages,
                r"Gambar\s+\d+[.\s]+(?:Pembagian\s+Daerah\s+Kerja|Daerah\s+(?:Pengendalian|Supervisi|Pengawasan))",
            )
            found = [item for item in diagrams if item["has_visual"]]
        if not visual:
            found = found[:1]
        if "dosis" in title.lower():
            note = "Pastikan angka batas dosis tidak melebihi Nilai Batas Dosis (NBD) ketentuan BAPETEN."
        else:
            note = "Periksa uraian zonasi kerja radiasi dan lampiran denah ruangan pada gambar."
        rows.append(
            make_row(
                title,
                "",
                found[0]["quote"] if found else "Belum ditemukan dalam teks terbaca",
                found,
                note,
                group="Isi program",
                images=visual,
            )
        )
    approval = approval_evidence(pages)
    rows.append(
        make_row(
            "Pengesahan — tanda tangan",
            "",
            "Halaman kandidat pengesahan ditemukan; periksa tanda tangan"
            if approval
            else "Halaman pengesahan belum ditemukan otomatis",
            approval,
            "Periksa keberadaan tanda tangan pimpinan atau penanggung jawab pada gambar (stempel tidak diwajibkan).",
            group="Pengesahan",
            images=True,
        )
    )
    return rows


def approval_evidence(pages):
    approval = []
    for page in pages:
        text = compact(page["text"])
        if toc(text):
            continue
        if re.search(
            r"lembar\s+pengesahan|(?:disetujui\s+oleh|mengesahkan).*?(?:nama|jabatan)|tanda\s+tangan.*?(?:nama|jabatan)",
            text,
            re.I,
        ):
            approval.append({"page": page["page"], "quote": text[:1800]})
    approval.sort(
        key=lambda item: (
            not bool(re.search(r"lembar\s+pengesahan", item["quote"], re.I)),
            item["page"],
        )
    )
    approval = approval[:1]
    return approval
