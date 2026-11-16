"""Extract monitoring intervals after a usage label, never adjacent dose headings."""

import re

from .protection.evidence import compact


def usage_periods(pages):
    from .personnel_policy import USAGE_PERIOD_LABEL
    from src.extraction.personnel_document import MONTHS, get_page_text

    month = r"(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b"
    endpoint = rf"(?:\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{4}}|(?:\d{{1,2}}\s+)?{month}(?:\s+\d{{4}})?)"
    interval = re.compile(rf"\b{endpoint}\s*(?:s\s*\.?\s*d\s*\.?|[-–—]|sampai|hingga|to|until)\s*{endpoint}", re.I)
    stop = re.compile(r"divisi|metode|tanggal\s+(?:pelayanan|penerimaan|terbit)|catatan|nomor|nama\s+pekerja", re.I)
    other_date_label = re.compile(
        r"tanggal\s+(?:pelayanan|penerimaan|terbit|uji|baca|pembacaan)|berlaku|valid", re.I
    )
    found = []
    for page in pages:
        lines = [compact(line) for line in get_page_text(page).splitlines() if compact(line)]
        for index, line in enumerate(lines):
            label = USAGE_PERIOD_LABEL.search(line)
            if not label:
                continue
            parts = [line[label.end():].lstrip(" :|=")]
            # OCR can split label, dates and range separator into separate lines.
            for following in lines[index + 1:index + 5]:
                if stop.search(following) or USAGE_PERIOD_LABEL.search(following):
                    break
                parts.append(following)
            match = interval.search(" ".join(parts))
            quote_parts = parts
            if not match or not re.search(r"\b\d{4}\b", match.group()):
                # OCR table skew can place the right-hand interval 1-2 lines above the label.
                match = None
                for prev_idx in range(index - 1, max(-1, index - 3), -1):
                    prev_line = lines[prev_idx]
                    if (
                        stop.search(prev_line)
                        or USAGE_PERIOD_LABEL.search(prev_line)
                        or re.search(r"kode\s+instansi", prev_line, re.I)
                    ):
                        break
                    if prev_idx > 0 and other_date_label.search(lines[prev_idx - 1]):
                        break
                    pre_parts = lines[prev_idx:index]
                    candidate = interval.search(" ".join(pre_parts))
                    if candidate and re.search(r"\b\d{4}\b", candidate.group()):
                        match = candidate
                        quote_parts = pre_parts
                        break
                if not match:
                    continue
            value = compact(match.group())
            # Reject impossible numeric dates rather than displaying them as a period.
            from datetime import datetime
            numeric = re.findall(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b", value)
            try:
                dates = [datetime.strptime(re.sub(r"[.-]", "/", d), "%d/%m/%Y") for d in numeric]
            except ValueError:
                continue
            if len(dates) == 2 and dates[0] > dates[1]:
                continue
            found.append(
                {
                    "page": page["page"],
                    "quote": compact(line[:label.end()] + " " + " ".join(quote_parts)),
                    "value": value,
                }
            )
    return list({(r["page"], r["value"].casefold()): r for r in found}.values())
