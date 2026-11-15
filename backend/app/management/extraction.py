"""Read identities and explanatory culture passages with page-level evidence."""

import re
from ..protection.extraction import native_identity, grounded
from ..protection.evidence import compact, toc
from ..protection import llm
from ..protection.identity import ranked_identity_pages
from ..protection.context import adjacent_window


def identities(pages):
    records = []
    warnings = []
    for page in pages:
        if not toc(page["text"]):
            records.extend(native_identity([page]))
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
        rf"(?im)^[ \t]*(?:(?:BAB\s+[IVXLCDM\d]+|\d+(?:\.\d+)*\.?|[A-Z][.)])\s+Budaya[ \t]+(?:Keselamatan|Keamanan)(?![^\n]*\b(?:adalah|merupakan|telah|akan|wajib)\b)[^\n]{{0,60}}$|{bare_heading})"
    )
    boundary = re.compile(
        rf"(?im)^[ \t]*(?:BAB\s+(?:[IVXLCDM]+|\d+)\b|\d+(?:\.\d+)+\.?\s+|[A-Z][.)]\s+|{bare_heading})"
    )
    sections = []
    active = False
    for page in pages:
        if toc(page["text"]):
            continue
        text = page["text"]
        cursor = 0
        for event in boundary.finditer(text):
            if active and text[cursor : event.start()].strip():
                sections.append({**page, "text": text[cursor : event.start()]})
            active = bool(heading.match(text, event.start()))
            cursor = event.start()
        if active and text[cursor:].strip():
            sections.append({**page, "text": text[cursor:]})
    return sections or pages


def culture_evidence(pages):
    pages = culture_sections(pages)
    topics = []
    for label, pattern in (
        ("Budaya Keselamatan", r"budaya\s+keselamatan"),
        ("Budaya Keamanan", r"budaya\s+keamanan|budaya\s+keselamatan\s+dan\s+keamanan"),
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
                    r"\b(?:merupakan|adalah|diterapkan|dilaksanakan|menerapkan|meliputi|mencakup|dilakukan|dengan\s+cara|diwujudkan|mengacu|bertujuan|berkomitmen|membangun|membentuk|memastikan|pencegahan)\b",
                    quote[:240],
                    re.I,
                )
                if len(quote.split()) < 35 or not explanation:
                    continue
                if re.search(r"\b\d+\.\d+\s", quote[: explanation.start()]):
                    continue
                evidence.append({"page": page["page"], "quote": quote})
                break
        topics.append({"label": label, "found": bool(evidence), "evidence": evidence})
    return topics
