"""Read identities and explanatory culture passages with page-level evidence."""

import re
from ..protection.extraction import native_identity, grounded
from ..protection.evidence import compact, toc
from ..protection import llm
from ..protection.identity import ADDRESS, office_address, ranked_identity_pages
from ..protection.context import adjacent_window

_MGMT_PROSE_LOC_RE = re.compile(
    r"\b(?:berlokasi|beralamat|terletak|bertempat)\s+di\s+"
    r"(?=(?:jl|jln|jalan|kawasan|komplek[s]?|komp|desa|kelurahan|kel|gedung|ruko)\b)"
    r"((?:[^.\n]|(?<=\b(?:Jl|No|PT|CV|Gd|Gg|Lt))\.|(?<=\b(?:Jln|Kec|Kab|Kel|Gdg|Kav))\.|(?<=\bKomp)\.|\.(?=[a-z0-9]))+)",
    re.I,
)


def _management_prose_addresses(pages):
    found = []
    for page in pages:
        if toc(page["text"]):
            continue
        source = (
            page["text"]
            if page.get("method") == "ocr"
            else (page.get("native_text") or page["text"])
        )
        for line in source.splitlines():
            clean = compact(line)
            if not clean:
                continue
            for match in _MGMT_PROSE_LOC_RE.finditer(clean):
                addr = compact(match.group(1)).strip(" ,.;:")
                parts = {re.sub(r"[^a-z]", "", m.lower()) for m in re.findall(ADDRESS, addr, re.I)}
                if len(addr) < 12 or len(addr) > 220 or len(parts) < 2:
                    continue
                if office_address(addr, source):
                    continue
                found.append(
                    {
                        "project_address": addr,
                        "page": page["page"],
                        "quote": clean,
                        "method": page.get("method", "text"),
                    }
                )
    return found


def identities(pages):
    records = []
    warnings = []
    for page in pages:
        if not toc(page["text"]):
            records.extend(native_identity([page]))
    if not any(r.get("project_address") for r in records):
        records.extend(_management_prose_addresses(pages))
    missing = [
        key for key in ("institution", "project_address") if not any(r.get(key) for r in records)
    ]
    if not missing:
        return records, warnings
    # Rank pages with structured identity/address cues ahead of generic mentions.
    candidates = ranked_identity_pages(pages, missing, toc_fn=toc)
    # One front-matter window when no cue exists, instead of scanning body prose.
    if not candidates:
        candidates = [p for p in pages if not toc(p["text"]) and p["text"].strip()][:1]
    covered = set()
    calls = 0
    for page in candidates:
        if page["page"] in covered:
            continue
        if calls >= 2:
            break
        if len(page["text"]) > 12000:
            warnings.append(
                f"Halaman {page['page']}: teks terlalu panjang untuk ekstraksi identitas tambahan."
            )
            continue
        try:
            window = adjacent_window(page, pages, max_chars=4500)
            calls += 1
            proposed = llm.extract("identity", window, only_fields=missing)
            covered.update(p["page"] for p in window)
            accepted = grounded(proposed, window, "identity")
            records.extend(accepted)
            missing = [key for key in missing if not any(r.get(key) for r in records)]
            if len(accepted) != len(proposed):
                warnings.append(f"Halaman {page['page']}: keluaran tanpa bukti sumber diabaikan.")
            if not missing:
                break
        except Exception as exc:
            warnings.append(
                f"Pembacaan identitas tambahan belum selesai ({type(exc).__name__}); periksa dokumen sumber."
            )
            break
    if any(p["page"] not in covered for p in candidates) and missing:
        warnings.append(
            "Pembacaan identitas dibatasi 2 kandidat terbaik; bagian lain perlu ditinjau."
        )
    return records, warnings


def culture_sections(pages):
    """Prefer dedicated culture sections; keep separate safety/security headings."""
    bare_heading = (
        r"Budaya[ \t]+(?:Keselamatan|Keamanan)"
        r"(?:[ \t]+dan[ \t]+(?:Budaya[ \t]+)?(?:Keselamatan|Keamanan))?"
        r"(?:[ \t]+(?:Radiasi|Sumber(?:[ \t]+Radiasi)?|Kerja|Perusahaan))*"
        r"[ \t]*:?[ \t]*$"
    )
    heading = re.compile(
        rf"(?im)^[ \t]*(?:BAB\s+(?:[IVXLCDM]+|\d+)[ \t]*\n+[ \t]*{bare_heading}|(?:BAB\s+(?:[IVXLCDM]+|\d+)\s*[-–:.]?|[IVXLCDM]+\.\d+(?:\.\d+)*\.?|\d+(?:\.\d+)*\.?|[A-Z][.)])\s+Budaya[ \t]+(?:Keselamatan|Keamanan)(?![^\n]*\b(?:adalah|merupakan|telah|akan|wajib)\b)[^\n]{{0,60}}$|{bare_heading})"
    )
    boundary = re.compile(
        rf"(?im)^[ \t]*(?:BAB\s+(?:[IVXLCDM]+|\d+)\b|[IVXLCDM]+\.\d+(?:\.\d+)*\.?\s+|\d+(?:\.\d+)+\.?\s+|[A-Z][.)]\s+|{bare_heading})"
    )
    sections = []
    active = False
    chapter_active = False
    for page in pages:
        if toc(page["text"]):
            continue
        text = page["text"]
        active_start = 0 if active else None
        for event in boundary.finditer(text):
            is_bab = bool(re.match(r"(?i)\s*BAB\b", text[event.start() : event.end()]))
            matched_heading = bool(heading.match(text, event.start()))
            next_active = (
                matched_heading
                if is_bab
                else (True if matched_heading or chapter_active else False)
            )
            if is_bab:
                chapter_active = matched_heading
            if active and not next_active:
                chunk = text[active_start : event.start()]
                if chunk.strip():
                    sections.append({**page, "text": chunk})
                active_start = None
            elif not active and next_active:
                active_start = event.start()
            active = next_active
        if active and active_start is not None and text[active_start:].strip():
            sections.append({**page, "text": text[active_start:]})
    return sections or pages


def culture_evidence(pages):
    pages = culture_sections(pages)
    topics = []
    for label, pattern in (
        ("Budaya Keselamatan", r"budaya\s+keselamatan"),
        (
            "Budaya Keamanan",
            r"budaya\s+keamanan|budaya\s+keselamatan\s+(?:dan|&|dan/atau)\s+(?:budaya\s+)?keamanan",
        ),
    ):
        evidence = []
        for page in pages:
            if toc(page["text"]):
                continue
            text = compact(page["text"])
            for match in re.finditer(pattern, text, re.I):
                quote = text[match.start() : match.end() + 1100]
                # A title or a passing mention alone is not an explanation.
                explanation = re.search(
                    r"\b(?:merupakan|adalah|diterapkan|dilaksanakan|menerapkan|meliputi|mencakup|dilakukan|dengan\s+cara|diwujudkan|mengacu|bertujuan|berkomitmen|membangun|membentuk|memastikan|pencegahan|bertanggung[\s-]*jawab|berkewajiban|komitmen)\b",
                    quote[:380],
                    re.I,
                )
                if len(quote.split()) < 35 or not explanation:
                    continue
                if re.search(r"\b(?:[IVXLCDM]+\.\d+|\d+\.\d+)\.?\s", quote[: explanation.start()]):
                    continue
                evidence.append({"page": page["page"], "quote": quote})
                break
        topics.append({"label": label, "found": bool(evidence), "evidence": evidence})
    return topics
