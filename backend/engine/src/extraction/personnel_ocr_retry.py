"""Bounded OCR retry in the recipient area of scanned training certificates."""

import os
import re


def retry_recipient(image, records):
    import pytesseract

    text = " ".join(str(r.get('text', '')) for r in records)
    if not re.search(r"sertifikat|certificate", text, re.I):
        return records, False
    anchors = [r for r in records if re.search(
        r"certify\s+that|menyatakan\s+bahwa|diberikan\s+kepada|awarded\s+to", r.get('text', ''), re.I
    ) and r.get('box')]
    following = [r for r in records if re.search(
        r"telah\s+mengikuti|has\s+participated|has\s+completed", r.get('text', ''), re.I
    ) and r.get('box')]
    for anchor in reversed(anchors):
        top = int(max(p[1] for p in anchor['box'])) + 2
        ends = [r for r in following if min(p[1] for p in r['box']) > top]
        if not ends:
            continue
        end = min(ends, key=lambda r: min(p[1] for p in r['box']))
        bottom = int(min(p[1] for p in end['box'])) - 2
        if not 15 < bottom - top < image.shape[0] * .3:
            continue
        existing = [r for r in records if r.get('box') and
                    min(p[1] for p in r['box']) >= top and max(p[1] for p in r['box']) <= bottom]
        if any(len(re.sub(r'[^a-z]', '', r.get('text', '').lower())) >= 4 for r in existing):
            return records, False
        left = max(0, int(min(p[0] for p in end['box'])))
        right = min(image.shape[1], int(max(p[0] for p in end['box'])))
        crop = image[top:bottom, left:right]
        if not crop.size:
            continue
        languages = set(pytesseract.get_languages(config=''))
        lang = '+'.join(l for l in os.getenv('BAPETEN_TESS_LANG', 'ind+eng').split('+') if l in languages)
        if not lang:
            return records, True
        variants = []
        for mode in (6, 13):
            try:
                value = pytesseract.image_to_string(crop, lang=lang, config=f'--psm {mode}', timeout=8).strip()
            except (RuntimeError, OSError):
                continue
            if re.fullmatch(r"[^\W\d_][^\d\n:|]{3,80}", value):
                variants.append(value)
        # Agreement is required; never use form names to steer OCR.
        if len(variants) == 2 and variants[0].casefold() == variants[1].casefold():
            inserted = dict(text=variants[0], box=[[left, top], [right, top], [right, bottom], [left, bottom]], engine='tesseract-recipient-retry')
            result = [r for r in records if r not in existing]
            position = result.index(anchor) + 1
            result.insert(position, inserted)
            return result, False
        return records, True
    return records, False
