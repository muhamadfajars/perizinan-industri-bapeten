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
            if not match or not re.search(r"\b\d{4}\b", match.group()):
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
            found.append({"page": page["page"], "quote": compact(line[:label.end()] + " " + " ".join(parts)), "value": value})
    return list({(r["page"], r["value"].casefold()): r for r in found}.values())
