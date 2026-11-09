"""Read identities and explanatory culture passages with page-level evidence."""

import re
from ..protection.extraction import native_identity, grounded
from ..protection.evidence import compact, toc
from ..protection import llm


def identities(pages):
    records = []
    warnings = []
    for page in pages:
        if not toc(page["text"]):
            records.extend(native_identity([page]))
    missing = [
        key for key in ("institution", "project_address") if not any(r.get(key) for r in records)
    ]
    # Only ask Qwen when there is a plausible source passage for a missing value.
    candidates = [
        p
        for p in pages
        if not toc(p["text"])
        and (
            (
                "project_address" in missing
                and re.search(r"\b(?:alamat|jalan|jl\.?|jln\.?)\s", p["text"], re.I)
            )
            or (
                "institution" in missing
                and re.search(r"\b(?:instansi|perusahaan|PT|CV)\b", p["text"], re.I)
            )
        )
    ]
    for page in candidates[:6]:
        if len(page["text"]) > 12000:
            warnings.append(
                f"Halaman {page['page']}: teks terlalu panjang untuk ekstraksi identitas tambahan."
            )
            continue
        try:
            proposed = llm.extract("identity", [{"page": page["page"], "text": page["text"]}])
            accepted = grounded(proposed, [page], "identity")
            records.extend(accepted)
            if len(accepted) != len(proposed):
                warnings.append(f"Halaman {page['page']}: keluaran tanpa bukti sumber diabaikan.")
        except Exception as exc:
            warnings.append(
                f"Pembacaan identitas tambahan belum selesai ({type(exc).__name__}); periksa dokumen sumber."
            )
            break
    return records, warnings


def culture_sections(pages):
    """Prefer dedicated culture sections; keep separate safety/security headings."""
    heading = re.compile(r"(?im)^\s*\d+(?:\.\d+)+\.?\s+Budaya\s+(?:Keselamatan|Keamanan)[^\n]*")
    boundary = re.compile(r"(?im)^\s*(?:BAB\s+(?:[IVXLCDM]+|\d+)\b|\d+(?:\.\d+)+\.?\s+)")
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
                    r"\b(?:merupakan|adalah|diterapkan|dilaksanakan|menerapkan|meliputi|mencakup|dilakukan|dengan\s+cara)\b",
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
