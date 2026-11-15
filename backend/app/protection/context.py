"""Retrieve bounded source windows, prioritising explicit section headings."""

import re
from .evidence import toc

PHRASES = {
    "laws": [r"(?:dasar|landasan|acuan)\s+(?:hukum|regulasi|peraturan)", r"referensi|rujukan"],
    "culture": [
        r"budaya\s+keselamatan",
        r"budaya\s+keamanan|budaya\s+keselamatan\s+dan\s+(?:budaya\s+)?keamanan",
    ],
    "dose": [
        r"(?:penetapan\s+)?pembatas\s+dosis|dose\s+constraint|kendala\s+dosis",
        r"(?:operasi|operasional|saat\s+ini).*?\d.*?Sv",
    ],
}


def adjacent_window(page, pages, *, max_chars=12000):
    """Include the following page for context; preserve independent page evidence."""
    result = [{"page": page["page"], "text": page["text"]}]
    following = next((p for p in pages if p["page"] == page["page"] + 1), None)
    if (
        following
        and not toc(following["text"])
        and len(page["text"]) + len(following["text"]) <= max_chars
    ):
        result.append({"page": following["page"], "text": following["text"]})
    return result


def ranked_pages(task, pages, broad_pattern):
    candidates = [
        p for p in pages if not toc(p["text"]) and re.search(broad_pattern, p["text"], re.I)
    ]
    phrases = PHRASES[task]

    def score(page, phrase=None):
        text = page["text"]
        patterns = [phrase] if phrase else phrases
        headings = sum(
            any(re.search(pattern, line, re.I) for pattern in patterns)
            for line in text.splitlines()
            if len(line.strip()) <= 100
            and not re.search(
                r"\b(?:adalah|merupakan|diterapkan|ditetapkan|digunakan|dilakukan|meliputi|mencakup)\b",
                line,
                re.I,
            )
        )
        exact = sum(bool(re.search(pattern, text, re.I)) for pattern in patterns)
        return headings * 100 + exact * 20 + min(10, len(re.findall(broad_pattern, text, re.I)))

    candidates.sort(key=lambda p: -score(p))
    # Reserve coverage for both culture aspects, rather than spending every call on safety.
    selected = []
    if task == "culture":
        for phrase in phrases:
            matches = [p for p in candidates if re.search(phrase, p["text"], re.I)]
            if matches:
                best = max(matches, key=lambda p: score(p, phrase))
                if best not in selected:
                    selected.append(best)
    return selected + [p for p in candidates if p not in selected]
