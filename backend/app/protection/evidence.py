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
    r"Undang[\s\-\u2010-\u2015\u2212]*Undang|UU\.?|Peraturan\s+Pemerintah|PP\.?|"
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
        if re.match(r"UU\.?$|Undang", kind, re.I)
        else "PP"
        if re.fullmatch(r"PP\.?|Peraturan\s+Pemerintah", kind, re.I)
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


_ZONE_HEADING_RE = re.compile(
    r"(?m)^\s*(?:(?:BAB\s+[IVXLCDM\d]+|\d+(?:\.\d+)*|[A-Z]\.|[IVXLCDM]+\.)\s+)?"
    r"(?:(?:desain|penetapan|klasifikasi|pengelompokan)\s+)?"
    r"(?:pembagian|klasifikasi|penetapan|zonasi)\s+(?:daerah|area|zona)\s+(?:kerja|radiasi)\b",
    re.I,
)

_TENTANG_START_RE = re.compile(
    r"^[ \t]*(?:\n[ \t]*)?(?:\([^()\n]{1,35}\)[ \t]*)?(?:[,:-][ \t]*)?tentang\b[ \t]*(?:[:,-][ \t]*)?(?:\n[ \t]*)?",
    re.I,
)
_AMENDMENT_PREFIX_RE = re.compile(r"\b(?:atas|terhadap|penetapan|pencabutan|pelaksanaan)\s+$", re.I)
_TRAILING_NEXT_LAW_NOISE_RE = re.compile(
    r"(?:"
    r"(?:[.;:\n][ \t]*(?:\d+(?:\.\d+)*|[a-zA-Z]|[ivxlcdmIVXLCDM]+)[.)])"
    r"|(?:[ \t\n]+(?:\d+(?:\.\d+)*[.)]|[a-z][.)]|[A-Z]\)|\(\d+\)|\([a-zA-Z]\)|[-•*▪●◦]))"
    r"|(?:,\s*(?:(?i:dan|serta))?|\s+(?i:dan|serta))"
    r")\s*$"
)
_NEW_BLOCK_LINE_RE = re.compile(
    r"^(?:"
    r"(?:\d+(?:\.\d+)*|[a-zA-Z]|[ivxlcdmIVXLCDM]+)[.)]\s+"
    r"|\((?:\d+|[a-zA-Z])\)\s+"
    r"|[-•*▪●◦–—]\s+"
    r"|(?i:BAB)\s+(?:(?i:[IVXLCDM]+)|\d+)\b"
    r"|(?i:Rujukan|Standar\s+Internasional|Dokumen\s+Internal|Manual\s+Book|Daftar\s+)"
    r"|(?i:Page|Halaman|Hal\.?)\s*\d+"
    r"|(?i:No\.?|Nomor|Rev(?:isi|ision)?|Date|Tanggal)\s*:"
    r"|[:|]"
    r")"
)
_EXPLANATORY_LINE_RE = re.compile(
    r"^(?:Mengatur|Merupakan|Menjadi|Menetapkan|Memuat|Menjelaskan|Mencakup|Bertujuan|"
    r"Digunakan|Berisi|Berlaku|Menggantikan|Diubah|Sebagaimana|Meliputi|Menyatakan|"
    r"Memberikan|Peraturan\s+ini|Undang[\s-]*undang\s+ini|Ketentuan\s+ini|Keputusan\s+ini|"
    r"Pedoman\s+ini|Sebagai\s+(?:pedoman|acuan|dasar|landasan|rujukan))\b(?:\s+[a-z]|[,:;])"
)
_DANGLING_CONNECTOR_RE = re.compile(
    r"(?:\b(?:dan|atau|dan/atau|pada|dalam|di|ke|dari|untuk|tentang|atas|terhadap|serta|bagi|oleh|dengan|sektor|bidang|sebagai|menjadi)|[,-])\s*$",
    re.I,
)
_INLINE_STOP_RE = re.compile(
    r"(?:"
    r"[;:|?!]"
    r"|\s+[–—-]\s+"
    r"|(?<!\bNo)(?<!\bTh)(?<!\bThn)(?<!\bUU)(?<!\bPP)(?<!\bPT)(?<!\bCV)(?<!\bRI)(?<!\bSt)(?<!\bdll)(?<!\bdsb)\.(?=\s|$)"
    r"|\(\s*(?:Lembaran\s+Negara|Berita\s+Negara|Tambahan\s+Lembaran|LN\b|BN\b|TLN\b|sebagaimana\b|telah\s+(?:diubah|dicabut)|dicabut\b|diubah\b|menggantikan\b|terakhir\s+diubah)"
    r"|,\s*(?:yang\s+(?:mengatur|memuat|menetapkan|menjadi|merupakan|berlaku|digunakan|mewajibkan|menjelaskan)|sebagaimana\b|(?:dan|serta)\s+(?:standar|pedoman|dokumen|peraturan|ketentuan|undang|keputusan|manual|rekomendasi|publikasi|iaea|icrp|iso)\b|antara\s+lain\b|meliputi\b|termasuk\b|peraturan\s+ini\b|dimana\b|di\s+mana\b)"
    r"|\s+(?:Peraturan\s+ini|Undang[\s-]*undang\s+ini|Ketentuan\s+ini|Keputusan\s+ini|Pedoman\s+ini)\b"
    r")",
    re.I,
)


def _extract_law_subject(raw_text: str, matches: list, idx: int) -> str:
    """Dynamically extract a regulation's 'tentang ...' subject from document text."""
    match = matches[idx]
    tail_start = match.end()
    limit = min(len(raw_text), tail_start + 450)
    cut_at_next_law = False
    for nxt in matches[idx + 1 :]:
        if nxt.start() >= limit:
            break
        if _AMENDMENT_PREFIX_RE.search(raw_text[tail_start : nxt.start()]):
            continue
        limit = nxt.start()
        cut_at_next_law = True
        break

    tail = raw_text[tail_start:limit]
    if cut_at_next_law:
        for _ in range(3):
            cleaned = _TRAILING_NEXT_LAW_NOISE_RE.sub("", tail)
            if cleaned == tail:
                break
            tail = cleaned

    tmatch = _TENTANG_START_RE.match(tail)
    if not tmatch:
        return ""
    rest = tail[tmatch.end() :]
    if rest.startswith("\n"):
        return ""

    kept = []
    lines = rest.splitlines()
    for li, line in enumerate(lines):
        stripped = line.strip()
        if li > 0:
            if not stripped:
                break
            if _NEW_BLOCK_LINE_RE.match(stripped):
                break
            if li + 1 < len(lines) and lines[li + 1].lstrip().startswith(":"):
                break
            if kept and not _DANGLING_CONNECTOR_RE.search(kept[-1]) and _EXPLANATORY_LINE_RE.match(stripped):
                break
        stop = _INLINE_STOP_RE.search(stripped)
        if stop:
            part = stripped[: stop.start()].strip()
            if part:
                kept.append(part)
            break
        if stripped:
            kept.append(stripped)

    if not kept:
        return ""
    joined = ""
    for part in kept:
        if not joined:
            joined = part
        elif joined.endswith("-"):
            joined += part
        else:
            joined += " " + part
    body = re.sub(r"\s+", " ", joined).strip()
    if cut_at_next_law:
        body = re.sub(r"(?:,\s*(?:dan|serta)?|\s+(?:dan|serta))\s*$", "", body, flags=re.I).strip()
    body = body.strip(" \t\r\n,;:.-–—")
    if len(body) >= 2 and (
        (body[0] == '"' and body[-1] == '"')
        or (body[0] == "“" and body[-1] == "”")
        or (body[0] == "'" and body[-1] == "'")
    ):
        body = body[1:-1].strip()
    if body.count("(") > body.count(")"):
        body = body[: body.rfind("(")].rstrip(" ,;:.-–—")
    if len(body) > 240:
        body = body[:240].rsplit(" ", 1)[0].rstrip(" ,;:.-–—")
    if len(re.findall(r"[A-Za-z]", body)) < 3:
        return ""
    return f"tentang {body}"


def _pick_best_law_subject(candidates: list[str]) -> str:
    """Choose the fullest dynamically extracted regulation subject."""
    if not candidates:
        return ""
    return max(candidates, key=lambda s: (len(s), -candidates.index(s)))


def information(pages, make_row, *, semantic=None):
    from .dose import dose_statements

    semantic = semantic or {}
    page_by_num = {p["page"]: p for p in pages}
    laws = {}
    law_subjects = {}
    reference_pages = semantic.get("legal_sections", legal_section(pages))
    for page in reference_pages:
        if toc(page["text"]):
            continue
        raw_text = str(page["text"] or "").replace("\r\n", "\n").replace("\r", "\n")
        matches = list(LAW.finditer(raw_text))
        for idx, match in enumerate(matches):
            key = law_key(*match.groups())
            quote = compact(raw_text[match.start() : match.end() + 300])[: len(compact(match.group(0))) + 220]
            laws.setdefault(key, []).append(
                {
                    "page": page["page"],
                    "quote": quote,
                    "method": page.get("method", "text"),
                }
            )
            if key not in REQUIRED_LAWS:
                subject = _extract_law_subject(raw_text, matches, idx)
                if subject:
                    law_subjects.setdefault(key, []).append(subject)
    rows = []
    for key in [*REQUIRED_LAWS, *(k for k in laws if k not in REQUIRED_LAWS)]:
        found = laws.get(key, [])
        if key in REQUIRED_LAWS:
            title = REQUIRED_LAW_TITLES[key]
        else:
            base_title = f"{key[0]} Nomor {key[1]} Tahun {key[2]}"
            subject = _pick_best_law_subject(law_subjects.get(key, []))
            title = f"{base_title} {subject}" if subject else base_title
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
            specific_subheading_re = re.compile(
                rf"(?im)^\s*(?:(?:BAB\s+[IVXLCDM\d]+|\d+(?:\.\d+)*[.)]?|[A-Za-z][.)]|[IVXLCDM]+[.)])\s+)?"
                rf"(?:{pattern})(?:\s*\([^)\n]{{1,40}}\))?\s*:?\s*$"
            )

            def _zone_meta(item):
                ptext = page_by_num.get(item["page"], {}).get("text", "")
                has_zone_heading = bool(_ZONE_HEADING_RE.search(ptext))
                is_glossary_heading = not has_zone_heading and bool(
                    re.search(
                        r"(?m)^\s*(?:\d+(?:\.\d+)*[.)]?\s+)?(?:definisi|daftar\s+istilah|pengertian|singkatan)\b",
                        ptext,
                        re.I,
                    )
                )
                has_specific_subheading = not is_glossary_heading and bool(
                    specific_subheading_re.search(ptext)
                )
                is_glossary = not has_zone_heading and bool(
                    (
                        re.search(
                            r"^\s*(?:adalah|merupakan)\b|\b(?:pengertian|definisi|daftar\s+istilah|singkatan)\b",
                            item["quote"],
                            re.I,
                        )
                        or is_glossary_heading
                    )
                    and not re.search(
                        r"mSv|µSv|uSv|\d/\d+\s*NBD|pembagian\s+daerah",
                        item["quote"],
                        re.I,
                    )
                )
                has_detail = bool(
                    re.search(
                        r"pembagian\s+daerah|klasifikasi\s+daerah|penetapan\s+daerah|laju\s+dosis|ambang|NBD|mSv|µSv|uSv|Sv|tanda\s+radiasi|tanda\s+(?:peringatan|titik\s+akses|bahaya)|trefoil|akses|pembatas|membatasi|menandai",
                        item["quote"],
                        re.I,
                    )
                )
                return has_specific_subheading, has_zone_heading, is_glossary, has_detail

            def _zone_rank(item):
                has_specific_subheading, has_zone_heading, is_glossary, has_detail = _zone_meta(item)
                return (
                    not has_specific_subheading,
                    not has_zone_heading,
                    is_glossary,
                    not has_detail,
                    not item.get("has_visual"),
                    item["page"],
                )

            def _is_dedicated_zone_text(item):
                has_specific_subheading, has_zone_heading, is_glossary, has_detail = _zone_meta(item)
                return not is_glossary and has_detail and (has_specific_subheading or has_zone_heading)

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
                confirmed.sort(
                    key=lambda item: (
                        not re.search(
                            r"(?:Gambar|Denah|Layout|Peta|Sketsa)\s*(?:[A-Z0-9.-]+[.\s:]+)?(?:Pembagian\s+(?:Daerah|Area|Zona)\s+Kerja|Zonasi)|pembagian\s+(?:daerah|area|zona)\s+kerja",
                            page_by_num.get(item["page"], {}).get("text", item["quote"]),
                            re.I,
                        ),
                        not re.search(
                            pattern,
                            page_by_num.get(item["page"], {}).get("text", item["quote"]),
                            re.I,
                        ),
                        item["page"],
                    )
                )
                for item in candidates:
                    if item["page"] not in confirmed_pages and (item["page"] - 1) in confirmed_pages:
                        confirmed.append(item)
                        confirmed_pages.add(item["page"])
            if confirmed:
                found = confirmed
            elif candidates:
                # Opsi A: if an unlabeled diagram omits this zone, prefer a dedicated subsection if present.
                dedicated_text_zones = [item for item in text_zones if _is_dedicated_zone_text(item)]
                if dedicated_text_zones:
                    found = sorted(dedicated_text_zones, key=_zone_rank)[:1]
                    text_only_fallback = True
                else:
                    found = candidates
            else:
                found = []
            if not found and text_zones:
                text_only_fallback = True
                ranked_zones = sorted(text_zones, key=_zone_rank)
                found = ranked_zones[:1]
                found_pages = {item["page"] for item in found}
                anchor_pages = {ranked_zones[0]["page"]}
                for p in pages:
                    if len(found) >= 2:
                        break
                    if not p.get("has_visual") or p["page"] <= 2 or p["page"] in found_pages or toc(p["text"]):
                        continue
                    ptext = p["text"]
                    if re.search(
                        r"struktur\s+organisasi|sertifikat\s+kalibrasi|lembar\s+pengesahan|halaman\s+pengesahan|peta\s+lokasi",
                        ptext,
                        re.I,
                    ):
                        continue
                    is_adjacent = any(p["page"] in (ap + 1, ap + 2) for ap in anchor_pages) and not re.search(
                        r"^\s*(?:BAB\s+[IVXLCDM\d]+|daftar\s+pustaka|pembatas(?:an)?\s+dosis)",
                        ptext,
                        re.I,
                    )
                    is_explicit_attachment = bool(
                        re.search(
                            r"\b(?:denah|sketsa|layout)\b.{0,40}\b(?:ruang|fasilitas\s+radiasi|area\s+kerja|zonasi|radiasi)\b|"
                            r"\blampiran\b.{0,40}\b(?:denah|zonasi|daerah\s+kerja|ruang)\b",
                            ptext,
                            re.I,
                        )
                    )
                    if is_adjacent or is_explicit_attachment:
                        quote = compact(ptext)[:240] or "Lampiran gambar/denah fasilitas"
                        found.append({"page": p["page"], "quote": quote, "has_visual": True})
                        found_pages.add(p["page"])
                        if len(found) >= 2:
                            break
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
            r"(?im)^\s*(?:(?:\d+(?:\.\d+)*[.)]?|[A-Z][.)])\s+)?"
            r"(?:"
            r"(?:lembar|halaman|catatan|daftar|tabel|kolom|form(?:ulir)?)\s+"
            r"(?:(?:pemeriksaan|tinjauan|review|persetujuan|pengendalian)\s*(?:&|dan|/)\s*)*"
            r"(?:pengesahan|persetujuan)\b[^\n]{0,45}$"
            r"|(?:(?:pemeriksaan|tinjauan|persetujuan)\s*(?:&|dan|/)\s*)?"
            r"(?:pengesahan|persetujuan)\s+(?:dokumen|program|prosedur|sistem\s+manajemen)\b[^\n]{0,40}$"
            r"|(?:document\s+)?(?:review\s*(?:&|and)\s*)?(?:approval|sign[\s-]*off|authorization)"
            r"(?:\s+(?:sheet|page|record|table))?\s*$"
            r")",
            raw_text,
        )
        has_sheet_heading = bool(sheet_match) and not re.search(
            r"\b(?:dalam|pada|di|bagian|revisi|perubahan|lihat|sesuai|tercantum)\s+"
            r"(?:lembar|halaman|catatan)\s+(?:pengesahan|persetujuan)\b",
            sheet_match.group(0),
            re.I,
        )
        has_approval_role_cue = bool(
            re.search(
                r"\b(?:pengesahan|persetujuan|pembuat|penyusun|pemeriksa|peninjau|pengesah|penyetuju|"
                r"dibuat|disusun|diperiksa|disetujui|disahkan|mengetahui|ditetapkan|direktur|director|"
                r"pimpinan|manajer|manager|gm|pemegang\s+izin|penanggung\s+jawab|"
                r"prepared\s+by|checked\s+by|reviewed\s+by|approved\s+by|authorized\s+by)\b",
                text,
                re.I,
            )
        )
        has_sig_marker = bool(
            re.search(r"\b(?:tanda\s+tangan\b|paraf\b|ttd\b\.?|signature\b)", text, re.I)
        )
        is_revision_only_page = (
            bool(re.search(r"(?im)^\s*(?:rekaman|catatan|riwayat|daftar|tabel)\s+revisi\b", raw_text))
            and not has_sig_marker
            and not has_sheet_heading
        )
        has_passive_oleh_block = bool(
            re.search(
                r"(?:disetujui|disahkan|mengetahui|ditetapkan)\s+oleh\b.*?(?:nama|jabatan|direktur|director|pimpinan|kepala|manajer|manager|pemegang\s+izin|penanggung\s+jawab)",
                text,
                re.I,
            )
            or (
                re.search(r"(?:disusun|dibuat|diperiksa)\s+oleh\b", text, re.I)
                and re.search(r"(?:disetujui|disahkan|mengetahui|ditetapkan)\s+oleh\b", text, re.I)
            )
        )
        has_bidirectional_sig_header = bool(
            re.search(r"tanda\s+tangan.{0,120}(?:nama|jabatan)", text, re.I)
            or (
                has_approval_role_cue
                and re.search(r"(?:nama|jabatan).{0,80}tanda\s+tangan", text, re.I)
            )
        )
        has_role_table_block = not is_revision_only_page and bool(
            (
                re.search(r"\b(?:pembuat|penyusun|pemeriksa|peninjau)\b", text, re.I)
                and re.search(r"\b(?:pengesah|penyetuju)\b", text, re.I)
                and (has_sig_marker or re.search(r"\b(?:nama|jabatan|pengesahan|persetujuan)\b", text, re.I))
            )
            or (
                re.search(r"\b(?:prepared|drafted|checked|reviewed|verified)\s+by\b", text, re.I)
                and re.search(r"\b(?:approved|authorized)\s+by\b", text, re.I)
            )
            or (
                re.search(r"\b(?:dibuat|disusun|diperiksa|pembuat|penyusun|pemeriksa)\b", text, re.I)
                and re.search(
                    r"\b(?:disetujui|disahkan|mengetahui|ditetapkan|pengesah|penyetuju)\b",
                    text,
                    re.I,
                )
                and has_sig_marker
            )
        )
        has_sig_block = has_passive_oleh_block or has_bidirectional_sig_header or has_role_table_block
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
        approval.append({"page": page["page"], "quote": text[:1800], "tier": tier, "has_sig": has_sig_block})
    approval.sort(key=lambda item: (item["tier"], not item["has_sig"], item["page"]))
    return [{"page": item["page"], "quote": item["quote"]} for item in approval[:1]]
