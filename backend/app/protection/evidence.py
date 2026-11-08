"""Display-only content: regulations, dose limits, controlled areas and approval."""

import re

REQUIRED_LAWS = [
    ("UU", "10", "1997"),
    ("PP", "45", "2023"),
    ("PP", "28", "2025"),
    ("Perba", "4", "2024"),
    ("Perba", "5", "2025"),
]
LAW = re.compile(
    r"\b(Undang[\s-]*Undang|UU|Peraturan\s+Pemerintah|PP|"
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


def information(pages, make_row):
    from .dose import dose_statements

    laws = {}
    for page in pages:
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
            )
            laws.setdefault((kind, str(int(number)), year), []).append(
                {"page": page["page"], "quote": text[match.start() : match.end() + 220]}
            )
    rows = []
    for key in [*REQUIRED_LAWS, *(k for k in laws if k not in REQUIRED_LAWS)]:
        found = laws.get(key, [])
        title = f"{key[0]} No. {key[1]} Tahun {key[2]}"
        rows.append(
            make_row(
                "Dasar hukum: " + title,
                "",
                title if found else "Belum ditemukan dalam teks terbaca",
                found,
                "Dasar hukum ditampilkan sesuai isi dokumen; tidak dibandingkan dengan formulir.",
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
            found = diagrams + [x for x in found if x["page"] not in {d["page"] for d in diagrams}]
        # Prefer explanatory body over incidental mentions; keep all sources available.
        note = "Informasi dokumen; tidak dinilai cocok/tidak cocok dengan formulir."
        if visual:
            note += " Gambar halaman sumber ditampilkan untuk memeriksa penjelasan dan denah; keberadaan gambar belum membuktikan cakupan wilayahnya."
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
    approval = []
    for page in pages:
        text = compact(page["text"])
        if toc(text):
            continue
        if re.search(
            r"lembar\s+pengesahan|disetujui\s+oleh|mengesahkan|tanda\s+tangan", text, re.I
        ):
            approval.append({"page": page["page"], "quote": text[:1800]})
    rows.append(
        make_row(
            "Pengesahan — tanda tangan",
            "",
            "Halaman kandidat pengesahan ditemukan; periksa tanda tangan"
            if approval
            else "Halaman pengesahan belum ditemukan otomatis",
            approval,
            "Minimal tanda tangan; stempel tidak diwajibkan. Teks nama/jabatan tidak membuktikan adanya tanda tangan. Verifikasi pada gambar halaman.",
            group="Pengesahan",
            images=True,
        )
    )
    return rows
