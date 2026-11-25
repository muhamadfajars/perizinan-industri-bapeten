"""Evidence-only matching for radiation exposure and tube leakage documents.

No test outcome is inferred, and presence of signoff is not signature authenticity.
Parsers are independent of a particular PDF template; avoid comparing the
contractor's address/unit with the licensee's facility or X-ray equipment.
"""

import os
import re
import unicodedata
from difflib import SequenceMatcher
from . import program_evidence as base
from . import program_matching as program
from .program_documents import read_pages

FIELD_LABELS = {
    "merk_unit": "Merek unit",
    "tipe_unit": "Tipe unit",
    "nomor_seri_unit": "No. seri unit",
    "merk_tabung": "Merek tabung",
    "tipe_tabung": "Tipe tabung",
    "nomor_seri_tabung": "No. seri insersi tabung",
}


def space(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", str(value or "")).casefold())


def _fix_tesseract_location():
    """Avoid unrelated OCR modules forcing a Windows executable on Linux HPC."""
    import os, shutil
    import pytesseract

    cmd = pytesseract.pytesseract.tesseract_cmd
    if not (os.path.isfile(cmd) or shutil.which(cmd)):
        valid = shutil.which("tesseract")
        if valid:
            pytesseract.pytesseract.tesseract_cmd = valid
    return pytesseract


def _tess_ocr(pytesseract, image, config):
    lang = os.getenv("BAPETEN_TESS_LANG", "ind+eng")
    try:
        return pytesseract.image_to_string(image, lang=lang, config=config)
    except Exception:
        if lang != "eng":
            try:
                return pytesseract.image_to_string(image, lang="eng", config=config)
            except Exception:
                return ""
        return ""


def _first_page_roi(path, kind):
    """OCR only the identity and equipment blocks, avoiding supplier/footer contamination."""
    if not str(path).lower().endswith(".pdf"):
        return ""
    import fitz
    from PIL import Image, ImageEnhance, ImageOps

    pytesseract = _fix_tesseract_location()
    with fitz.open(path) as pdf:
        if not pdf:
            return ""
        page = pdf[0]
        # Scope to equipment/identity table from radiation exposure / tube leakage reports.
        bounds = (0.09, 0.11, 0.88, 0.49)
        box = fitz.Rect(
            page.rect.width * bounds[0],
            page.rect.height * bounds[1],
            page.rect.width * bounds[2],
            page.rect.height * bounds[3],
        )
        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=box, alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        attempts = [im, ImageEnhance.Contrast(ImageOps.grayscale(im)).enhance(1.7)]
        candidates = []
        for image in attempts:
            for mode in (6, 4):
                content = _tess_ocr(pytesseract, image, config=f"--psm {mode}")
                strength = sum(
                    bool(re.search(p, content, re.I))
                    for p in (
                        r"Rumkit|RS\s+Tentara",
                        r"Kesehatan",
                        r"Pekanbaru",
                        r"No\s+Seri|Serial|S\s*/\s*N",
                        r"Optima",
                    )
                )
                candidates.append((strength, len(content), content))
        return max(candidates, default=(0, 0, ""))[2]


def _roi_field(pages, kind, path):
    if pages and pages[0].get("source") == "pdf" and len(norm(pages[0].get("text"))) > 400:
        return pages
    # Keep original full-page OCR for signoff/roster, but use a separate
    # high-resolution region when extracting institution, address, X-ray data.
    try:
        roi = _first_page_roi(path, kind)
    except Exception:
        return pages
    if not roi:
        return pages
    # Include ROI as first ranked source; no text is hallucinated.
    return [{"page": 1, "text": roi, "source": "ocr_roi"}] + pages


def _pages(path, kind):
    # Read only relevant pages when documents are purely scanned, avoiding
    # dozens of redundant full-page OCR calls for device measurement reports.
    if path.lower().endswith(".pdf"):
        import fitz

        with fitz.open(path) as doc:
            num = len(doc)
            scanned = sum(len(norm(doc[i].get_text())) < 40 for i in range(min(num, 3)))
            if scanned:
                indices = sorted(set(range(min(num, 3))) | {num - 1})
                out = []
                from .program_documents import _ocr_page

                for i in indices:
                    page = doc[i]
                    text = page.get_text(sort=True)
                    if len(norm(text)) < 45:
                        try:
                            text = _ocr_page(page)
                        except Exception:
                            pass
                    if len(norm(text)) < 45:
                        try:
                            pytesseract = _fix_tesseract_location()
                            from PIL import Image

                            pix = page.get_pixmap(
                                matrix=__import__("fitz").Matrix(2, 2), alpha=False
                            )
                            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                            text = _tess_ocr(pytesseract, image, config="--psm 3")
                        except Exception:
                            pass
                    out.append(
                        {
                            "page": i + 1,
                            "text": text,
                            "source": "ocr" if len(norm(page.get_text())) < 45 else "pdf",
                        }
                    )
                return out
    pages, _ = read_pages(path)
    return pages


def _source_hit(pages, phrase, *, limit=160):
    target = norm(phrase)
    if not target:
        return None
    for pg in pages:
        for line in (pg["text"] or "").splitlines():
            if target in norm(line):
                return {
                    "page": pg["page"],
                    "quote": space(line)[:limit],
                    "value": space(phrase),
                }
    return None


def _status(expected, observed, key):
    if not expected or not observed:
        return ("REVIEW", None)
    return base._compare_value(expected, observed, key)


def _field(label, expected="", observed="", status="REVIEW", score=None, page=None, quote=None):
    return {
        "field": label,
        "expected": space(expected),
        "observed": space(observed),
        "status": status,
        "score": score,
        "evidence": [{"page": page, "quote": quote or space(observed)}] if observed else [],
    }


def _find_licensee(pages, expected, kind):
    """Find hospital/clinic in licensee 'Data Instansi' or 'Kepada' block.

    Reject contractor ('Penguji', 'Supplier', 'Importir') identity even when
    both share the generic 'Nama Instansi' field label.
    """
    candidates = []
    pattern = re.compile(
        r"(?i)\b(?:rsud|rs\.?\b|rumkit|rumah\s+sakit|klinik|puskesmas)\s+[\w.\- ]{3,95}"
    )
    for p in pages[:4]:
        text = p.get("text") or ""
        # Head of document has licensee; after `Data Penguji` can contain supplier.
        boundary = re.search(
            r"(?i)\b(?:data\s+penguji|supplier|importir|data\s+alat\s+ukur)\b", text
        )
        licensee = text[: boundary.start()] if boundary else text[:3500]
        for line in licensee.splitlines():
            ln = space(line)
            if not ln:
                continue
            m = re.search(
                r"(?i)^\s*(?:\d+\s*[.]?\s*)?(?:nama\s+(?:instansi|rumah\s+sakit|rs|pelanggan|fasilitas)|hospital\s+name)\s*[:|]?\s*(.+)",
                ln,
            )
            if m:
                val = space(m.group(1)).strip(":| ")
            else:
                k = pattern.search(ln)
                val = space(k.group()) if k else ""
            if not val or len(val) > 120:
                continue
            if re.search(
                r"(?i)(?:penguji|laboratorium|pt\.|kementerian|telp|alamat|pengawas)",
                val,
            ):
                continue
            from src.matching.suitability_matcher import compare_institution

            comparison = compare_institution(expected, val)
            score = comparison.get("score") or 0
            if score < 45:
                continue
            status = (
                "MATCH"
                if norm(expected) == norm(val) or comparison["status"] == "MATCH" and score >= 90
                else "REVIEW"
            )
            candidates.append((score, status, val, p["page"], ln))
    if candidates:
        score, status, val, page, quote = max(candidates, key=lambda x: (x[1] == "MATCH", x[0]))
        return _field("Nama Fasilitas", expected, val, status, score, page, quote)
    # Additional letter format 'Kepada ... RS ...' under recipient.
    fallback = program.facility_result(pages, expected)
    return _field(
        "Nama Fasilitas",
        expected,
        fallback.get("observed"),
        fallback.get("status", "REVIEW"),
        fallback.get("score"),
        (fallback.get("evidence") or [{}])[0].get("page"),
        (fallback.get("evidence") or [{}])[0].get("quote"),
    )


def _address(pages, expected, kind=None):
    # A supplier's address is never the facility address. Restrict candidates
    # to the recipient / DATA INSTANSI region; skip letterhead address.
    scoped = []
    for pg in pages[:4]:
        text = pg.get("text") or ""
        end = re.search(
            r"(?i)\b(?:Data\s+Penguji|Supplier|Importir|Data\s+Alat\s+Ukur)\b", text
        )
        if end:
            text = text[: end.start()]
        if pg.get("source") == "ocr":
            text = re.sub(r"(?i)\bJi\.\s+(?=[A-Z])", "Jl. ", text)
        if text.strip():
            scoped.append(dict(pg, text=text))
    matching = program.address_result(scoped, expected) if scoped else {}
    ev = (matching.get("evidence") or [{}])[0]
    observed = matching.get("observed")
    if observed and kind in ("radiation_exposure_upload", "tube_leakage_upload"):
        observed = re.split(
            r"(?i)\s+(?:[3-9]\s*[.]?\s*)?(?:Nama|Jabatan|Data)\s+(?:Pendamping|Penguji|Pengalih|Alat\s+Ukur)\b",
            observed,
        )[0].strip(" ,;")
    return _field(
        "Alamat Fasilitas",
        expected,
        observed,
        matching.get("status", "REVIEW"),
        matching.get("score"),
        ev.get("page"),
        observed if observed else ev.get("quote"),
    )


def _signoff(pages, kind):
    """Detect an explicit letter sign-off or an approval block; NOT authenticity."""
    phrases = (
        r"(?i)(?:\b(?:mengetahui|pengesahan|ditandatangani|ditandatangani\s+oleh|"
        r"menyetujui|disahkan|manajer\s+unit\s+administrasi|penguji\s+paparan\s+radiasi)\b|"
        r"(?:^|\b)(?:conducted|tested|surveyed|verified|checked|approved|authorized)\s+by\s*:|"
        r"^\s*(?:conducted|tested|surveyed|verified|checked|approved|authorized)\s+by\b)"
    )
    for pg in reversed(pages):
        text = pg.get("text") or ""
        hits = [space(line) for line in text.splitlines() if re.search(phrases, line)]
        if hits:
            return _field(
                "Pengesahan",
                "Blok persetujuan/tanda tangan pada dokumen",
                f"Halaman {pg['page']}",
                "MATCH",
                100,
                pg["page"],
                hits[0][:180],
            )
    return _field("Pengesahan", "Blok persetujuan/tanda tangan pada dokumen")


def _equipment_for_document(path, pages, ref_list, kind):
    """Record-scoped matching with additional exact on-page evidence.

    If a physical device cannot be uniquely selected, never borrow a match
    from another device. No source -> REVIEW; exact X-ray identifier only.
    """
    if not ref_list:
        return []
    # 1. Use the hardened program matcher where equipment labels are explicit.
    groups = program.match_equipment(path, pages, ref_list)
    # 2. Add exact source spans from the same associated physical report.
    # Avoid form-based matching across multiple reference devices.
    if len(ref_list) > 1:
        return groups
    ref = ref_list[0]
    rows = groups[0]
    # Do not assert that a loose mention is equipment evidence; prefer values
    # inside sections with DATA PESAWAT / TABUNG / SUMBER RADIASI.
    for row in rows:
        if row.get("observed"):
            continue
        key = row["field"]
        expected = space(ref.get(key))
        if not expected:
            continue
        for pg in pages[:4]:
            txt = pg["text"] or ""
            starts = [
                m.start()
                for m in re.finditer(
                    r"(?i)\b(?:data\s+(?:pesawat|generator|tabung|insersi|sumber\s+radiasi|kepala\s*tabung|wadah)|\b(?:ii\.|2\.)\s*data\s+pesawat)\b",
                    txt,
                )
            ]
            if not starts:
                continue
            block = txt[starts[0] :]
            # Do not accept a code that is a prefix of a longer observed model.
            regex = (
                r"(?<![A-Za-z0-9])"
                + re.escape(expected).replace(r"\ ", r"\s*")
                + r"(?![A-Za-z0-9])"
            )
            m = re.search(regex, block, re.I)
            if m is None:
                continue
            context = space(block[max(0, m.start() - 110) : min(len(block), m.end() + 80)])
            # A serial may be a component of an unrelated measuring instrument.
            if key.startswith("nomor_seri") and re.search(
                r"(?i)(?:alat\s+ukur|surveymeter|kalibrasi)", context[:75]
            ):
                continue
            # Require role proximity for exact matching, not arbitrary narrative.
            context_tokens = context.casefold()
            if key.startswith("nomor_seri_tabung") and not re.search(
                r"(?i)tabung|tube|insersi|insert|sumber\s+radiasi|model\s+housing",
                block[max(0, m.start() - 280) : m.start()],
            ):
                continue
            if key.startswith(("merk_tabung", "tipe_tabung")) and not re.search(
                r"(?i)tabung|tube|insersi|insert",
                block[max(0, m.start() - 280) : m.start()],
            ):
                continue
            if key.startswith(("merk_unit", "tipe_unit", "nomor_seri_unit")) and not re.search(
                r"(?i)pesawat|generator|data\s+alat|unit",
                block[max(0, m.start() - 450) : m.start()],
            ):
                # Paired-column source PDFs print 'Nomor Seri' on the generator
                # side, but linear PDF extraction may emit the tube side last.
                # An exact unique serial with an adjacent serial label is usable
                # when a single reference device is under review.
                before = block[max(0, m.start() - 95) : m.start()]
                if not (
                    key == "nomor_seri_unit"
                    and re.search(r"(?i)\b(?:nomor|no\.?|serial)\s*(?:seri|number)\b", before)
                ):
                    continue
            actual = m.group()
            row.update(
                {
                    "observed": actual,
                    "status": "MATCH",
                    "score": 100.0,
                    "evidence": [
                        {
                            "page": pg["page"],
                            "quote": context,
                            "value": actual,
                            "method": "v46_exact_equipment_context",
                        }
                    ],
                    "method": "v46_exact_equipment_context",
                    "reason": "",
                }
            )
            break
    # OCR-only pages are prone to `O/0`, `I/1`, and inserted spaces. Expose
    # explicit labeled candidates as REVIEW instead of silently dropping the
    # field or turning a near hit into MATCH/MISMATCH.
    if len(ref_list) == 1:
        for row in rows:
            if row.get("observed"):
                continue
            key = row["field"]
            expected = space(ref.get(key))
            if not expected:
                continue
            candidates = []
            specs = {
                "tipe_unit": r"(?:model\s+alat|tipe\s+unit|(?:\d+[.)]\s*)?tipe\b)",
                "nomor_seri_unit": r"(?:no\.?\s*seri\s*(?:alat|generator|unit)|serial\s*(?:number|no)\s*(?:unit|generator))",
                "tipe_tabung": r"(?:tipe\s+tabung|model\s+(?:tabung|insert)|model\s*/\s*type\s+tabung)",
                "nomor_seri_tabung": r"(?:no\.?\s*seri\s*(?:insert|insersi|tabung)|serial\s+number\s*(?:insert|insersi|tabung))",
                "merk_unit": r"(?:merk\s+unit|merek\s+unit|pabrikan\s+generator|merk\s+pesawat)",
                "merk_tabung": r"(?:nama\s+pabrik|merk\s+tabung|pabrikan\s+tabung)",
            }
            pattern = re.compile(specs.get(key, r"(?!)"), re.I)
            for pg in pages[:4]:
                if pg.get("source") != "ocr":
                    continue
                lines = (pg.get("text") or "").splitlines()
                for i, line in enumerate(lines):
                    m = pattern.search(line)
                    if not m:
                        continue
                    after = space(line[m.end() :]).strip(":|-. ")
                    if len(after) < 3 and i + 1 < len(lines):
                        after = space(lines[i + 1]).strip(":|-. ")
                    if not after:
                        continue
                    # Limit table-merged spillover and model prefixes.
                    value = after[:85]
                    similarity = 100 * SequenceMatcher(None, norm(expected), norm(value)).ratio()
                    # Extract a compact code candidate near the label. Avoid
                    # presenting the entire OCR table line as a field value.
                    pieces = re.findall(r"[A-Za-z0-9][A-Za-z0-9./\-]*", value)
                    candidates.append((similarity, value, pg["page"], space(line)[:180]))
            # In OCR reading order the left-column labels sometimes precede
            # the *entire* right-column value block. Recover only close
            # candidates, marked REVIEW because OCR may confuse 5/S, 0/O.
            if key in ("tipe_unit", "tipe_tabung"):
                for pg in pages[:4]:
                    if pg.get("source") != "ocr":
                        continue
                    for ln in (pg.get("text") or "").splitlines():
                        val = space(ln).lstrip(":- |")
                        if key.startswith("tipe"):
                            val = re.split(
                                r"(?i)\b(?:S\s*/\s*N|serial\s+number|nomor\s+seri)\b",
                                val,
                            )[0].strip(" :;")
                        if len(val) > 70 or len(val) < 4:
                            continue
                        ratio = 100 * SequenceMatcher(None, norm(expected), norm(val)).ratio()
                        if ratio >= 73 and ratio > max((c[0] for c in candidates), default=0):
                            candidates.append((ratio, val, pg["page"], space(ln)[:180]))
            if candidates:
                _, value, page, quote = max(candidates, key=lambda c: c[0])
                # Exact typed model under a recognizable device-data block is
                # verifiable even when it came from OCR. Do not grant that to
                # serials/brands without component-specific evidence.
                ocr_exact = (
                    key in ("tipe_unit", "tipe_tabung")
                    and norm(value) == norm(expected)
                    and "data" in " ".join((pg.get("text") or "").lower()[:850] for pg in pages[:2])
                )
                row.update(
                    {
                        "observed": value,
                        "status": "MATCH" if ocr_exact else "REVIEW",
                        "score": 100.0 if ocr_exact else None,
                        "evidence": [
                            {
                                "page": page,
                                "quote": quote,
                                "method": "v46_ocr_candidate",
                            }
                        ],
                        "method": "v46_ocr_candidate",
                        "reason": "",
                    }
                )
    # The first page is a two-column OCR table. Use its explicit component labels,
    # never substitute tube housing identity for insertion identity.
    if len(ref_list) == 1:
        for row in groups[0]:
            key = row["field"]
            expected = space(ref_list[0].get(key))
            if not expected:
                continue
            if row.get("status") == "MATCH":
                continue
            patterns = {
                "nomor_seri_unit": r"(?i)\b(?:no\.?\s+seri\s+(?:alat|generator)|serial\s+unit)\s*[:>]\s*([\$A-Z0-9-]{7,35})",
                "tipe_tabung": r"(?i)\b(?:no\.?\s+model\s+insert|model\s+insersi)\s*[:>]\s*([A-Z0-9-]{3,25})",
                "nomor_seri_tabung": r"(?i)\b(?:no\.?\s+seri\s+insert|serial\s+insersi)\s*[:>]\s*([A-Z0-9-]{4,30})",
                "merk_tabung": r"(?i)\b(?:nama\s+pabrik|merk\s+tabung)\s*[:>]\s*([A-Z][A-Z ]{2,40})",
            }
            pattern = patterns.get(key)
            if not pattern:
                continue
            for pg in pages[:2]:
                match = re.search(pattern, pg.get("text") or "")
                if not match:
                    continue
                raw = space(match.group(1)).split("  ")[0]
                if key == "merk_tabung":
                    raw = re.split(r"(?i)\b\d+\s*mm|\b(?:fokus|tahun|model)", raw)[0].strip()
                if key == "nomor_seri_unit":
                    # Keep the original OCR glyph visible as evidence. Treat as REVIEW unless
                    # independent exact reading confirms it.
                    stat = "REVIEW"
                elif key == "tipe_tabung":
                    stat = "MATCH" if norm(raw) == norm(expected) else "REVIEW"
                elif key == "merk_tabung":
                    stat = "MATCH" if norm(expected) and norm(expected) in norm(raw) else "REVIEW"
                else:
                    stat = "MATCH" if norm(raw) == norm(expected) else "REVIEW"
                row.update(
                    {
                        "observed": raw,
                        "status": stat,
                        "score": 100 if stat == "MATCH" else None,
                        "evidence": [
                            {
                                "page": pg["page"],
                                "quote": space(match.group(0)),
                                "method": "v054_labeled_roi",
                            }
                        ],
                        "method": "v054_labeled_roi",
                    }
                )
                break
    return groups


def _select_exposure_equipment(path, pages, references, kind):
    """Prefer unique exact unit serial in report to select ONE reference device.

    A report can mention multiple unrelated devices (surveymeter, calibrator).
    Insufficient unique unit serial -> do not silently choose equipment 1.
    """
    if len(references) <= 1:
        return _equipment_for_document(path, pages, references, kind)
    source = " ".join(p.get("text") or "" for p in pages[:4])
    norm_source = norm(source)
    hits = []
    for idx, ref in enumerate(references):
        serial = norm(ref.get("nomor_seri_unit"))
        if len(serial) < 5:
            continue
        if serial in norm_source:
            # serial matching exact alphanumeric boundaries (not a prefix)
            if re.search(
                r"(?<![a-z0-9])" + re.escape(serial) + r"(?![a-z0-9])",
                re.sub(r"[^a-z0-9]+", " ", source.lower()),
            ):
                hits.append(idx)
            # A serial that occurs only as a prefix of a longer code is NOT evidence.
    if len(hits) != 1:
        # The report's first-page OCR can read the leading S as '$'.
        # Select the form DEVICE only when a serial on an explicitly labeled
        # 'No Seri Alat' line maps to exactly one form serial. This does NOT
        # establish that the OCR serial itself is an exact MATCH.
        probable = []
        for pg in pages[:2]:
            for line in (pg.get("text") or "").splitlines():
                anchor = re.search(
                    r"(?i)\b(?:no\.?\s+seri\s+alat|serial\s+(?:no|number)\s+unit)\s*[:>]\s*([\$A-Z0-9-]{7,35})",
                    line,
                )
                if not anchor:
                    continue
                observed = anchor.group(1).upper().strip()
                if not observed.startswith("$"):
                    continue
                corrected = "S" + observed[1:]
                for index, ref in enumerate(references):
                    if norm(ref.get("nomor_seri_unit")).upper() == norm(corrected).upper():
                        probable.append(index)
        distinct = set(probable)
        if len(distinct) != 1:
            return None
        hits = list(distinct)
    idx = hits[0]
    scoped = _equipment_for_document(path, pages, [references[idx]], kind)
    return (idx, scoped[0]) if scoped else None


def analyze(path, kind, reference):
    if kind not in ("radiation_exposure_upload", "tube_leakage_upload"):
        raise ValueError("Jenis dokumen tidak didukung")
    pages = _pages(path, kind)
    scoped_pages = _roi_field(pages, kind, path)
    general = reference.get("general") or {}
    institution = general.get("instansi") or general.get("nama_fasilitas") or ""
    addr = general.get("alamat_proyek") or general.get("alamat") or ""
    rows = [
        _find_licensee(scoped_pages, institution, kind),
        _address(scoped_pages, addr, kind),
    ]
    refs = reference.get("equipment") or []
    chosen = _select_exposure_equipment(path, scoped_pages, refs, kind)
    if isinstance(chosen, tuple):
        groups = [(chosen[0] + 1, chosen[1])]
    elif chosen is None and len(refs) > 1:
        rows.append(_field("Pemilihan Peralatan", "Nomor seri unit unik", "", "REVIEW"))
        groups = []
    else:
        groups = list(enumerate(chosen or [], 1))
    for i, group in groups:
        for item in group:
            rows.append(
                _field(
                    f"Alat {i}: {FIELD_LABELS.get(item['field'], item['field'])}",
                    item.get("expected"),
                    item.get("observed"),
                    item.get("status", "REVIEW"),
                    item.get("score"),
                    (item.get("evidence") or [{}])[0].get("page"),
                    (item.get("evidence") or [{}])[0].get("quote"),
                )
            )
    rows.append(_signoff(pages, kind))
    return {
        "kind": kind,
        "filename": os.path.basename(path),
        "rows": rows,
        "pages": len(pages),
    }
