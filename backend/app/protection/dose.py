"""Select explicit dose-constraint statements, prioritising current operation."""

import re
from .evidence import compact, toc


def dose_statements(pages):
    candidates = []
    boundary = re.compile(r"(?<!\bPT)(?<!\bCV)(?<!\bNo)[.!?](?=\s|$)", re.I)
    for page in pages:
        if toc(page["text"]):
            continue
        text = compact(
            page["text"] if page.get("method") == "ocr" else page.get("native_text") or page["text"]
        )
        ends = [m.end() for m in boundary.finditer(text)]
        seen = set()
        for hit in re.finditer(r"pembatas\s+dosis", text, re.I):
            start = max((end for end in ends if end <= hit.start()), default=0)
            end = next((end for end in ends if end >= hit.end()), len(text))
            quote = text[start:end].strip()
            if (
                quote in seen
                or len(quote) > 1500
                or not re.search(r"\d[\d.,]*\s*(?:mSv|µSv|μSv|uSv|Sv)\b", quote, re.I)
            ):
                continue
            seen.add(quote)
            score = sum(
                weight
                for pattern, weight in (
                    (r"saat\s+ini|saat\s+sekarang|saat\s+beroperasi", 40),
                    (r"operasional|operasi", 10),
                    (r"digunakan|ditetapkan|sebesar|menggunakan", 5),
                    (r"tahap", 3),
                )
                if re.search(pattern, quote, re.I)
            )
            candidates.append((score, {"page": page["page"], "quote": quote}))
    return [record for _, record in sorted(candidates, key=lambda item: -item[0])]
