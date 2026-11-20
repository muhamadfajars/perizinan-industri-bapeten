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
    r"\b(Peraturan\s+Presiden|Perpres|Peraturan\s+Menteri(?:\s+[A-Za-z]+){0,6}?|Permen|Peraturan\s+Daerah|Perda|"
    r"Undang[\s-]*Undang|UU|Peraturan\s+Pemerintah|PP|"
    r"(?:Peraturan|Keputusan)\s+(?:Kepala\s+)?(?:BAPETEN|Badan\s+Pengawas\s+Tenaga\s+Nuklir)|"
    r"(?:PERBA|PERKA|KEPKA)(?:\s+(?:BAPETEN|Badan\s+Pengawas\s+Tenaga\s+Nuklir))?)"
    r"(?:\s*\((?:UU|PP|BAPETEN|PERBA|PERKA|KEPKA|RI)\))*"
    r"\s*(?:(?:Republik\s+Indonesia|RI)\s*)?"
    r"(?:(?:Nomor|No[.,:]?)\s*[:.]?\s*)*(\d{1,3})\s*(?:(?:Tahun|Thn\.?|Th\.?)\s*|/\s*)(\d{4})\b",
    re.I,
)


def compact(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def law_key(kind, number, year):
    kind = (
        "UU"
        if re.match(r"UU|Undang", kind, re.I)
        else "PP"
        if re.fullmatch(r"PP|Peraturan\s+Pemerintah", kind, re.I)
        else "Perba"
        if re.search(r"BAPETEN|Pengawas|PERBA|PERKA|KEPKA", kind, re.I)
        else compact(kind)
    )
    return kind, str(int(number)), year


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


_LEGAL_SUB_REG_HEADING_RE = re.compile(
    r"^\s*(?:[A-Z][.)]|(?:[IVXLCDM]+|\d+)(?:\s*\.\s*\d+)+[.)]?)\s+"
    r"(?:Undang[\s-]*Undang|Peraturan(?:\s+(?:Pemerintah|Kepala|BAPETEN|Badan|Menteri|Presiden|Perundang|Nasional|Terkait))?|"
    r"Perba|Perka|Kepka|Standar|Pedoman|Referensi|Regulasi|Hukum|Keputusan)\b",
    re.I,
)
_LEGAL_END_RE = re.compile(
    r"(?m)^[ \t]*(?:(?i:BAB)\s+(?:(?i:[IVXLCDM]+)|\d+)\b|"
    r"[IVXLCDM]+\s*\.\s*\d+(?:\s*\.\s*\d+)*[.)]?\s+|"
    r"[IVXLCDM]+[.)]\s+|"
    r"\d+\s*\.\s*\d+(?:\s*\.\s*\d+)*[.)]?\s+|"
    r"[A-Z][.)]\s+)"
)


def _find_legal_stop(text: str, start_pos: int = 0, open_sec: str = ""):
    search_pos = start_pos
    open_norm = re.sub(r"\s+", "", open_sec).upper().rstrip(".)") if open_sec else ""
    while True:
        cand = _LEGAL_END_RE.search(text, search_pos)
        if not cand:
            return None
        nl = text.find("\n", cand.start())
        line_end = nl if nl != -1 else len(text)
        nl2 = text.find("\n", line_end + 1) if nl != -1 else -1
        two_lines_end = nl2 if nl2 != -1 else len(text)
        one_line = text[cand.start() : line_end]
        two_lines = compact(text[cand.start() : two_lines_end])
        cand_norm = re.sub(r"\s+", "", cand.group(0)).upper().rstrip(".)")
        is_child = bool(
            open_norm
            and re.match(r"^(?:[IVXLCDM]+|\d+)(?:\.\d+)+$", cand_norm)
            and cand_norm.startswith(open_norm + ".")
        )
        wrapped_law = bool(
            re.search(
                r"\b(?:Undang[\s-]*Undang|Peraturan|Keputusan|UU|PP|Perba|Perka|Kepka|Nomor|No[.,:]?)\b",
                one_line,
                re.I,
            )
            and LAW.search(two_lines)
        )
        if is_child or LAW.search(one_line) or _LEGAL_SUB_REG_HEADING_RE.match(one_line) or wrapped_law:
            search_pos = max(line_end, cand.end())
            continue
        return cand


def _legal_prose_fallback(pages):
    strong_framing_re = re.compile(
        r"(?:dasar\s+hukum|landasan\s+hukum|acuan\s+(?:hukum|peraturan|regulasi)|referensi\s+(?:hukum|peraturan|regulasi))",
        re.I,
    )
    framing_re = re.compile(
        r"(?:dasar\s+hukum|landasan\s+hukum|acuan\s+(?:hukum|peraturan|regulasi)|"
        r"referensi\s+(?:hukum|peraturan|regulasi)|"
        r"mengacu\s+pada\s+(?:berbagai\s+)?(?:dasar\s+hukum|landasan\s+hukum|peraturan|regulasi|referensi|ketentuan)|"
        r"(?:disusun\s+)?berdasarkan\s+(?:ketentuan\s+)?peraturan\s+perundang[\s-]*undangan|"
        r"peraturan\s+perundang[\s-]*undangan\s+yang\s+(?:berlaku|menjadi\s+(?:dasar|acuan|landasan|pedoman|rujukan)))",
        re.I,
    )
    sent_end_re = re.compile(r"(?<!\bPT)(?<!\bCV)(?<!\bNo)(?<!\bUU)(?<!\bPP)[.!?](?=\s)", re.I)

    for idx, page in enumerate(pages):
        text = page["text"]
        if toc(text):
            continue
        for match in framing_re.finditer(text):
            para_break = text.rfind("\n\n", 0, match.start())
            base_start = para_break + 2 if para_break != -1 else 0
            sent_start = base_start
            for sm in sent_end_re.finditer(text, base_start, match.start()):
                sent_start = sm.end()
            while sent_start < match.start() and text[sent_start].isspace():
                sent_start += 1

            stop_cand = _find_legal_stop(text, match.end())
            span_end = stop_cand.start() if stop_cand else len(text)
            raw_span = text[sent_start:span_end]

            # Trim after contiguous law-bearing paragraphs separated by double newlines.
            chunks = re.split(r"\n\s*\n", raw_span)
            if len(chunks) > 1:
                kept = []
                saw_law = False
                for c in chunks:
                    has_law = bool(LAW.search(c))
                    if has_law or not kept:
                        kept.append(c)
                        saw_law = saw_law or has_law
                    elif saw_law:
                        break
                    else:
                        kept.append(c)
                span_text = "\n\n".join(kept).strip()
            else:
                span_text = raw_span.strip()

            if not span_text:
                continue
            collected = [{**page, "text": span_text}]

            # Optionally continue across one page boundary if page ended cleanly mid-section without a stop heading.
            if not stop_cand and len(chunks) <= 1 and idx + 1 < len(pages):
                next_page = pages[idx + 1]
                next_text = next_page["text"]
                if not toc(next_text):
                    next_stop = _find_legal_stop(next_text, 0)
                    next_slice = next_text[: next_stop.start()] if next_stop else next_text
                    next_chunks = re.split(r"\n\s*\n", next_slice.strip())
                    if next_chunks and LAW.search(next_chunks[0]):
                        cont_kept = [next_chunks[0]]
                        for c in next_chunks[1:]:
                            if LAW.search(c):
                                cont_kept.append(c)
                            else:
                                break
                        cont_text = "\n\n".join(cont_kept).strip()
                        if cont_text:
                            collected.append({**next_page, "text": cont_text})

            combined = " ".join(item["text"] for item in collected)
            distinct_laws = {law_key(*m.groups()) for m in LAW.finditer(combined)}
            is_strong = bool(strong_framing_re.search(combined))
            if len(distinct_laws) >= 2 or (len(distinct_laws) >= 1 and is_strong):
                return collected
    return []


def legal_section(pages):
    """Find a legal-reference heading regardless of its section number."""
    result = []
    active = False
    open_sec = ""
    heading = re.compile(
        r"(?m)^[ \t]*"
        r"(?:"
        r"(?P<sec_num>(?:BAB\s+(?:[IVXLCDM]+|\d+)|[IVXLCDM]+\s*\.\s*\d+(?:\s*\.\s*\d+)*|\d+(?:\s*\.\s*\d+)*))[.)]?\s*[-–:.]?\s*"
        r"|Sub\s*Bab\s*\S+\s+"
        r"|(?:[IVXLCDM]+|[A-Z])[.)]\s*[-–.]?\s*"
        r")?"
        r"(?:"
        r"Dasar\s+(?:Hukum|Penyusunan)|Referensi\s+(?:dan\s+)?Dasar\s+Hukum|Landasan\s+Hukum|"
        r"(?:Acuan|Rujukan)\s+(?:Hukum|Peraturan|Regulasi)|"
        r"Acuan\s*/\s*Referensi|"
        r"Ketentuan\s+(?:Hukum|Peraturan)|"
        r"Peraturan\s+(?:Perundang[\s-]*undangan|Terkait|Acuan|yang\s+Digunakan|dan\s+Standar)|"
        r"Regulasi\s+Terkait|Referensi\s+Hukum|Referensi|"
        r"(?:Legal\s+Basis|Legal\s+References?|Regulatory\s+References?)"
        r")"
        r"(?:(?:\s*(?:/|dan|&)\s*(?:Referensi|Peraturan(?:\s+Perundang[\s-]*undangan)?|Regulasi|Standar|Ketentuan))?"
        r"(?:\s+(?:Terkait|Acuan|Umum|Hukum|Peraturan|Program(?:\s+Proteksi)?(?:\s+Radiasi)?|Keselamatan(?:\s+Radiasi)?|Penyusunan|Pelaksanaan))*)"
        r"(?:\s*\([^)]{1,30}\))?"
        r"(?:\s*:[ \t]*$|\s*:[ \t]*(?=(?:\d+[.)]|[A-Za-z][.)]|[-•*]|(?:Undang|Peraturan|Keputusan|UU|PP|Perba|Perka|Kepka)\b))|\s{2,}(?=(?:\d+[.)]|[A-Za-z][.)]|[-•*]|(?:Undang|Peraturan|Keputusan|UU|PP|Perba|Perka|Kepka)\b))|[ \t]*$)",
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
            open_sec = start.group("sec_num") or ""
            text = text[start.end() :]
        stop = _find_legal_stop(text, 0, open_sec=open_sec)
        if stop:
            text = text[: stop.start()]
        if text.strip():
            result.append({**page, "text": text})
        if stop:
            if any(LAW.search(r["text"]) for r in result):
                break
            active = False
            open_sec = ""
            result.clear()
    if any(LAW.search(r["text"]) for r in result):
        return result
    return _legal_prose_fallback(pages)


def information(pages, make_row, *, semantic=None):
    from .dose import dose_statements

    semantic = semantic or {}
    laws = {}
    reference_pages = semantic.get("legal_sections", legal_section(pages))
    for page in reference_pages:
        if toc(page["text"]):
            continue
        text = compact(page["text"])
        for match in LAW.finditer(text):
            laws.setdefault(law_key(*match.groups()), []).append(
                {
                    "page": page["page"],
                    "quote": text[match.start() : match.end() + 220],
                    "method": page.get("method", "text"),
                }
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
        if not found and semantic.get("laws_review"):
            rows[-1]["detail"].update(
                review_required=True,
                review_reason="Bagian referensi belum terbaca lengkap; periksa dokumen sumber.",
            )
    topics = [
        (
            "Daerah Pengendalian",
            r"daerah\s+pengendalian|area\s+pengendalian|area\s+terkendali|controlled\s+area|zona\s+pengendalian",
            True,
        ),
        (
            "Daerah Pengawasan / Supervisi",
            r"daerah\s+(?:pengawasan\s*/\s*supervisi|pengawasan|supervisi)|area\s+(?:pengawasan|supervisi)|supervised\s+area|zona\s+(?:pengawasan|supervisi)",
            True,
        ),
        ("Pembatas Dosis", r"pembatas(?:an)?\s+dosis|kendala\s+dosis|nilai\s+batas\s+dosis|batas\s+dosis|\bNBD\b", False),
    ]
    for title, pattern, visual in topics:
        text_zones = snippets(pages, pattern) if visual else []
        found = text_zones if visual else semantic.get("dose", dose_statements(pages))
        confirmed = []
        text_only_fallback = False
        if visual:
            zone_by_page = {item["page"]: item["quote"] for item in text_zones}
            diagrams = snippets(
                pages,
                r"(?:Gambar|Denah|Layout|Peta|Sketsa)\s*(?:[A-Z0-9.-]+[.\s:]+)?(?:Pembagian\s+(?:Daerah|Area|Zona)\s+Kerja|(?:Daerah|Area|Zona|Zonasi)\s+(?:Pengendalian|Supervisi|Pengawasan|Kerja|Radiasi))|\b(?:Denah|Layout)\s+(?:Ruang(?:an)?|Fasilitas\s+Radiasi|Area\s+Kerja)\b",
            )
            candidates = [item for item in diagrams if item["has_visual"]]
            # A generic floor plan is a candidate, unless the diagram page or immediate context confirms this zone.
            confirmed_pages = set()
            for item in candidates:
                if re.search(pattern, item["quote"], re.I):
                    confirmed.append(item)
                    confirmed_pages.add(item["page"])
                    continue
                zone_quote = zone_by_page.get(item["page"]) or zone_by_page.get(item["page"] - 1)
                if zone_quote:
                    confirmed.append(
                        {**item, "quote": compact(f"{zone_quote} {item['quote']}")[:900]}
                    )
                    confirmed_pages.add(item["page"])
            if confirmed:
                for item in candidates:
                    if item["page"] not in confirmed_pages and (item["page"] - 1) in confirmed_pages:
                        confirmed.append(item)
                        confirmed_pages.add(item["page"])
            found = confirmed or candidates
            if not found and text_zones:
                text_only_fallback = True
                ranked_zones = sorted(
                    text_zones,
                    key=lambda item: (
                        not item.get("has_visual"),
                        not re.search(
                            r"pembagian\s+daerah|klasifikasi\s+daerah|penetapan\s+daerah|laju\s+dosis|ambang|NBD|mSv|µSv|uSv|Sv|tanda\s+radiasi|trefoil|akses|pembatas",
                            item["quote"],
                            re.I,
                        ),
                        bool(
                            re.search(
                                r"^\s*(?:adalah|merupakan)\b|\b(?:pengertian|definisi|daftar\s+istilah|singkatan)\b",
                                item["quote"],
                                re.I,
                            )
                            and not re.search(
                                r"mSv|µSv|uSv|\d/\d+\s*NBD|pembagian\s+daerah",
                                item["quote"],
                                re.I,
                            )
                        ),
                        item["page"],
                    ),
                )
                found = ranked_zones[:3]
        if not visual and not semantic.get("dose_review"):
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
        if visual and found and not confirmed and not text_only_fallback:
            rows[-1]["observed"] = "Denah kandidat ditemukan; jenis daerah belum terkonfirmasi"
            rows[-1]["detail"].update(
                review_required=True,
                review_reason="Periksa apakah gambar sumber memuat " + title.lower() + ".",
            )
        if not visual and semantic.get("dose_review"):
            rows[-1]["detail"].update(
                review_required=True,
                review_reason="Pembatas dosis untuk operasi saat ini belum dapat dipastikan; periksa dokumen sumber.",
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
        raw_text = page["text"]
        text = compact(raw_text)
        if toc(text):
            continue
        sheet_match = re.search(
            r"(?im)^\s*(?:(?:\d+(?:\.\d+)*[.)]?|[A-Z][.)])\s+)?(?:lembar|halaman)\s+pengesahan\b[^\n]{0,40}$",
            raw_text,
        )
        has_sheet_heading = bool(sheet_match) and not re.search(
            r"\b(?:dalam|pada|di|bagian|revisi|perubahan)\s+(?:lembar|halaman)\s+pengesahan\b",
            sheet_match.group(0),
            re.I,
        )
        has_sig_block = bool(
            re.search(
                r"(?:disetujui|disahkan|mengetahui|ditetapkan)\s+oleh\b.*?(?:nama|jabatan|direktur|director|pimpinan|kepala|manajer|manager|pemegang\s+izin|penanggung\s+jawab)"
                r"|tanda\s+tangan.*?(?:nama|jabatan)",
                text,
                re.I,
            )
            or (
                re.search(r"(?:disusun|dibuat|diperiksa)\s+oleh\b", text, re.I)
                and re.search(r"(?:disetujui|disahkan|mengetahui|ditetapkan)\s+oleh\b", text, re.I)
            )
        )
        has_fallback = bool(
            re.search(
                r"(?<!dalam\s)(?<!pada\s)\blembar\s+pengesahan\b"
                r"|mengesahkan\s+(?:dokumen|program|prosedur).*?(?:direktur|director|pimpinan|kepala|manajer|manager)",
                text,
                re.I,
            )
        )
        if has_sheet_heading:
            tier = 0
        elif has_sig_block:
            tier = 1
        elif has_fallback:
            tier = 2
        else:
            continue
        approval.append({"page": page["page"], "quote": text[:1800], "tier": tier})
    approval.sort(key=lambda item: (item["tier"], item["page"]))
    return [{"page": item["page"], "quote": item["quote"]} for item in approval[:1]]
