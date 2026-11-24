"""Select explicit dose-constraint statements, prioritising current operation."""

import re
from .evidence import compact, toc

_DOSE_UNIT_RE = re.compile(r"\d[\d.,]*\s*(?:mSv|µSv|μSv|uSv|Sv)\b", re.I)
_DOSE_CUE_RE = re.compile(r"pembatas(?:an)?\s+dosis|kendala\s+dosis|dose\s+constraint", re.I)
_NBD_TERM_RE = re.compile(
    r"nilai\s+batas\s+dosis|\bNBD\b|(?<!pem)batas(?:an)?\s+dosis\s+(?:umum|tahunan|pekerja|masyarakat|nasional)",
    re.I,
)
_FRACTION_NBD_RE = re.compile(
    r"(?:\b\d+\s*/\s*\d+|\b\d+(?:[.,]\d+)?\s*%|\bsetengah\b|\bseper\w+)\s*(?:dari\s+)?(?:nilai\s+batas\s+dosis|\bNBD\b)",
    re.I,
)
_ABBREV_PREFIX_RE = re.compile(
    r"(?:^|\s|\()(?:PT|CV|No|Dr|Ir|St|Jl|dkk|dsb|dll|tsb)\.$",
    re.I,
)
_LIST_PREFIX_RE = re.compile(r"(?:^|\s|\()(?:\d{1,2}|[A-Za-z])\.$")


def _sentence_ends(text: str) -> list[int]:
    ends = []
    for match in re.finditer(r"[.!?](?=\s|$)", text):
        if match.group(0) == ".":
            prefix = text[max(0, match.start() - 15) : match.start() + 1]
            if _ABBREV_PREFIX_RE.search(prefix) or _LIST_PREFIX_RE.search(prefix):
                continue
        ends.append(match.end())
    return ends


def _has_constraint_dose(quote: str) -> bool:
    for unit_match in _DOSE_UNIT_RE.finditer(quote):
        before = quote[max(0, unit_match.start() - 100) : unit_match.start()]
        nbd_pos = max((m.start() for m in _NBD_TERM_RE.finditer(before)), default=-1)
        if nbd_pos < 0:
            return True
        cue_pos = max((m.start() for m in _DOSE_CUE_RE.finditer(before)), default=-1)
        if cue_pos > nbd_pos or _FRACTION_NBD_RE.search(before):
            return True
    return False


def dose_statements(pages):
    candidates = []
    for page in pages:
        if toc(page["text"]):
            continue
        text = compact(
            page["text"] if page.get("method") == "ocr" else page.get("native_text") or page["text"]
        )
        ends = _sentence_ends(text)
        seen = set()
        for hit in _DOSE_CUE_RE.finditer(text):
            start = max((end for end in ends if end <= hit.start()), default=0)
            end = next((end for end in ends if end >= hit.end()), len(text))
            quote = text[start:end].strip()
            if not _DOSE_UNIT_RE.search(quote) and end < len(text):
                tail = text[end : min(len(text), end + 380)]
                stop = len(tail)
                for stopper in (
                    re.search(
                        r"(?:^|[.!?]\s+)(?:nilai\s+batas\s+dosis|\bNBD\b)|\bnilai\s+batas\s+dosis\s+(?:pekerja|masyarakat|tahunan|umum|adalah|sebesar)\b|\bBAB\s+(?:[IVXLCDM]+|\d+)\b",
                        tail,
                        re.I,
                    ),
                    re.search(r"\b\d+\.\d+(?:\.\d+)?\s+(?!(?:mSv|µSv|μSv|uSv|Sv)\b)[A-Z][A-Za-z]{2,}", tail),
                ):
                    if stopper:
                        stop = min(stop, stopper.start())
                tail = tail[:stop]
                unit_matches = list(_DOSE_UNIT_RE.finditer(tail))
                if unit_matches:
                    last_unit_end = end + unit_matches[-1].end()
                    final_end = next(
                        (e for e in ends if e >= last_unit_end and e <= end + stop),
                        min(len(text), end + stop),
                    )
                    quote = text[start:final_end].strip()
            if (
                quote in seen
                or len(quote) > 1500
                or not _DOSE_UNIT_RE.search(quote)
                or not _has_constraint_dose(quote)
            ):
                continue
            seen.add(quote)
            score = sum(
                weight
                for pattern, weight in (
                    (r"saat\s+ini|saat\s+sekarang|saat\s+beroperasi", 40),
                    (r"operasional|operasi", 10),
                    (r"digunakan|ditetapkan|sebesar|menggunakan|tidak\s+melebihi|maksimal", 5),
                    (r"pekerja\s+radiasi|anggota\s+masyarakat", 3),
                    (r"tahap", 3),
                )
                if re.search(pattern, quote, re.I)
            )
            candidates.append((score, {"page": page["page"], "quote": quote}))
    return [record for _, record in sorted(candidates, key=lambda item: -item[0])]
