from __future__ import annotations

import re


from .. import storage


from .rows import _from_match, _row, _text
from .constants import FIELDS


def _suitability(doc, app, ref):
    from src.extraction.suitability_test import parse_suitability_test
    from src.matching.suitability_matcher import match_suitability

    parsed = parse_suitability_test(str(storage.file_path(doc)))
    if not app.get("equipment"):
        return [
            _row(
                "Data peralatan",
                "Ada peralatan pada formulir",
                "",
                "REVIEW",
                document_id=doc["id"],
            )
        ]
    # One suitability certificate may describe only one device. Do not fabricate rows for other devices.
    results = [match_suitability(app, parsed, i) for i in range(len(app.get("equipment") or []))]
    statuses = {"MATCH": 3, "REVIEW": 2, "MISMATCH": 1, "MISSING": 0}
    # Conservative: select strong serial match only, else first device with REVIEW label.
    confirmed = [
        i for i, r in enumerate(results) if r["unit"]["nomor_seri"].get("status") == "MATCH"
    ]
    idx = confirmed[0] if len(confirmed) == 1 else 0
    result = results[idx]
    equipment = app["equipment"][idx]
    rows = [
        _from_match(
            "Nama Fasilitas",
            result["instansi"].get("expected"),
            result["instansi"],
            doc["id"],
        ),
        _from_match(
            "Alamat Fasilitas",
            ref["alamat_proyek"],
            {**result["alamat"], "observed": parsed.get("alamat")},
            doc["id"],
        ),
    ]
    for section, prefix in [("unit", "unit"), ("tabung", "tabung")]:
        for f, key in [
            ("merk", "merk"),
            ("tipe", "tipe"),
            ("nomor_seri", "nomor_seri"),
        ]:
            formkey = {"merk": "merk", "tipe": "tipe", "nomor_seri": "nomor_seri"}[f] + "_" + prefix
            match = result[section][f]
            rows.append(
                _from_match(
                    f"Alat {idx + 1}: {FIELDS.get(formkey, formkey)}",
                    equipment.get(formkey),
                    {**match, "observed": (parsed.get(section) or {}).get(f)},
                    doc["id"],
                )
            )
    if len(confirmed) != 1 and len(results) > 1:
        for row in rows[2:]:
            row.update(
                status="REVIEW",
                note="Pemilihan peralatan ambigu; nomor seri unit tidak unik",
                score=None,
            )
    return rows


def _functional(doc, app, ref):
    from src.extraction.functional_test import parse_functional_test
    from src.matching.functional_test_matcher import match_functional_test

    parsed = parse_functional_test(str(storage.file_path(doc)), include_checkboxes=False)
    matched = match_functional_test(app, parsed)
    idx = matched.get("selected_equipment_index")
    data = matched.get("fields") or {}
    rows = []
    labels = {
        "nama_rs": "Nama Fasilitas",
        "alamat": "Alamat Fasilitas",
        "merk_unit": "Merek Unit",
        "tipe_unit": "Tipe Unit",
        "nomor_seri_unit": "Nomor Seri Unit",
        "merk_tabung": "Merek Tabung",
        "tipe_tabung": "Tipe Tabung",
        "nomor_seri_tabung": "No. Seri Insersi Tabung",
    }
    for key, item in data.items():
        if not isinstance(item, dict):
            continue
        label = labels.get(key, key)
        if key not in ("nama_rs", "alamat"):
            label = f"Alat {(idx + 1) if isinstance(idx, int) else '?'}: {label}"
        rows.append(
            _row(
                label,
                item.get("expected"),
                item.get("actual"),
                item.get("status"),
                item.get("score"),
                item.get("page"),
                item.get("reason") or "",
                doc["id"],
                item.get("evidence"),
            )
        )
    if not rows:
        rows.append(
            _row(
                "Identitas alat",
                "Identitas dari formulir",
                "",
                "REVIEW",
                document_id=doc["id"],
            )
        )
    return rows


def _specification(doc, app, ref):
    from src.extraction.equipment_specification import parse_equipment_specification
    from src.matching.specification_matcher import match_equipment_specification

    parsed = parse_equipment_specification(str(storage.file_path(doc)))
    match = match_equipment_specification(parsed, app.get("equipment") or [])
    idx = match.get("selected_equipment_index")
    candidates = match.get("candidates") or []
    if not isinstance(idx, int) or idx >= len(app.get("equipment") or []):
        return [
            _row(
                "Pemilihan peralatan",
                "Identitas merek dan tipe unik",
                "",
                "REVIEW",
                note=match.get("reason"),
                document_id=doc["id"],
            )
        ]
    chosen = next((c for c in candidates if c.get("equipment_index") == idx), {})
    rows = []
    for key, matchkey in [("merk_unit", "brand"), ("tipe_unit", "model")]:
        field = chosen.get(matchkey) or {}
        proof = field.get("evidence") or field.get("actual") or ""
        if isinstance(proof, (dict, list)):
            proof = str(proof)[:160]
        rows.append(
            _row(
                f"Alat {idx + 1}: {FIELDS[key]}",
                (app["equipment"][idx]).get(key),
                proof,
                field.get("status", "REVIEW"),
                field.get("score"),
                chosen.get("best_page"),
                "Bukti berasal dari halaman spesifikasi",
                doc["id"],
            )
        )
    return rows


def _absent_value(value):
    """Only empty evidence, never a real conflicting value, is omitted."""
    value = _text(value)
    return not value or value.casefold() in {
        "—",
        "-",
        "–",
        "n/a",
        "na",
        "none",
        "null",
        "tidak ada",
        "tidak ditemukan",
    }


def _trim_model_spec(expected, observed):
    """Split an *explicit electrical rating* from a unit model; no fuzzy model edits.

    E7894X != E7894. OPTIMA XR200AMX 30KW is model OPTIMA XR200AMX plus 30KW rating.
    Preserve the original OCR text outside the displayed value for evidence traceability.
    """
    if _absent_value(expected) or _absent_value(observed):
        return None
    full = _text(observed)
    # Accept one/two clearly separated electrical specification tokens at the end.
    # Each rating must have a numeric amount and a *unit*, not just a model suffix.
    match = re.fullmatch(
        r"(?is)(?P<model>.+?)\s+(?P<ratings>\d+(?:[.,]\d+)?\s*(?:kW|kVp|kV|mAs|mA|Hz|W|V)"
        r"(?:\s*[/,;]\s*\d+(?:[.,]\d+)?\s*(?:kW|kVp|kV|mAs|mA|Hz|W|V))?)\s*",
        full,
    )
    if not match:
        return None
    from src.matching.import_approval_matcher import compact

    model = match.group("model").strip(" :;,")
    # Exact model characters must be preserved; only punctuation/spacing normalization.
    if compact(expected) != compact(model):
        return None
    return model, match.group("ratings").strip()


def _ocr_serial_key(value):
    trans = str.maketrans({"o": "0", "i": "1", "l": "1", "s": "5", "z": "2", "b": "8"})
    return re.sub(r"[^a-z0-9]", "", _text(value).casefold()).translate(trans)


def _normalize_import_cell(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def _import_page_text(mdoc, pdoc, raw_page):
    """Build contiguous table/stream text for a PDF page without interleaving columns."""
    from ..protection.extraction import norm

    page = dict(raw_page)
    idx = int(page.get("page") or 1) - 1
    if not (0 <= idx < len(mdoc) and idx < len(pdoc.pages)):
        return page

    stream = unicodedata.normalize("NFKC", mdoc[idx].get_text("text", sort=False) or "").strip()
    tbl_lines = []
    for tbl in pdoc.pages[idx].extract_tables() or []:
        for row in tbl or []:
            cells = [_normalize_import_cell(c) for c in row if _normalize_import_cell(c)]
            if cells:
                tbl_lines.append(" | ".join(cells))

    # Preserve OCR text when a page has sparse native text or scanned tables without PDF table boxes.
    if len(re.sub(r"\s+", "", stream)) >= 80 and (tbl_lines or page.get("method") == "text"):
        if tbl_lines:
            tbl_norm = norm("\n".join(tbl_lines))
            extra = [
                line.strip()
                for line in stream.splitlines()
                if line.strip() and norm(line) not in tbl_norm
            ]
            page["text"] = "\n".join(tbl_lines + extra)
        else:
            page["text"] = stream
    else:
        page["text"] = unicodedata.normalize("NFKC", str(page.get("text") or ""))
    return page


def _read_import_pages(path):
    from pathlib import Path

    path_obj = Path(path)
    if path_obj.suffix.lower() == ".pdf":
        from ..protection.reader import read_document

        pages, warnings = read_document(path)
        if not path_obj.is_file():
            return pages, warnings

        import pdfplumber
        import pymupdf

        with pymupdf.open(str(path_obj)) as mdoc, pdfplumber.open(str(path_obj)) as pdoc:
            return [_import_page_text(mdoc, pdoc, p) for p in pages], warnings
    import cv2
    import numpy as np
    from src.extraction.label_ocr import extract_ocr

    raw = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        return [], ["Gambar persetujuan impor tidak dapat dibuka."]
    lines = [str(item.get("text") or "").strip() for item in extract_ocr(image) if item.get("text")]
    return [{"page": 1, "text": "\n".join(lines), "method": "ocr", "has_visual": True}], []


def _import_page_rank(page):
    text = page.get("text") or ""
    if not text.strip():
        return (1, 0, int(page.get("page") or 0))
    score = 0
    if re.search(
        r"spesifikasi\s+teknis(?:\s+sumber)?|merk\s+unit|nama\s+sumber|tipe\s*/?\s*no",
        text,
        re.I,
    ):
        score += 20
    if re.search(r"tabung|nomor\s+seri|lampiran", text, re.I):
        score += 5
    if re.search(r"sesuai\s+dengan\s+lampiran", text, re.I):
        score -= 25
    return (0 if score > 0 else 1, -score, int(page.get("page") or 0))


def _extract_import_equipment(path, app):
    from pathlib import Path
    from src.extraction.import_approval import parse_import_approval
    from ..protection.extraction import grounded, norm, table_records
    from ..protection import llm

    parsed = parse_import_approval(str(path))
    records = []
    for item in parsed.get("equipment") or []:
        rec = {k: _text(item.get(k)) for k in FIELDS}
        if all(_absent_value(rec.get(k)) for k in FIELDS):
            continue
        rec.update(
            page=item.get("page") or 1,
            quote=_text(item.get("quote"))
            or " | ".join(
                v
                for v in (
                    rec.get("merk_unit"),
                    _text(item.get("raw_unit")),
                    rec.get("merk_tabung"),
                    _text(item.get("raw_tabung")),
                )
                if v
            ),
            method=str(item.get("method") or "PDF_TABLE").lower(),
            needs_review=bool(item.get("needs_review")),
        )
        records.append(rec)

    required = ("merk_unit", "tipe_unit", "nomor_seri_unit", "merk_tabung", "tipe_tabung")

    def complete(items):
        forms = app.get("equipment") or []
        if not forms:
            return bool(items) and all(
                all(r.get(k) for k in ("merk_unit", "tipe_unit", "nomor_seri_unit"))
                and not r.get("needs_review")
                for r in items
            )
        for tool in forms:
            u_sn = norm(tool.get("nomor_seri_unit"))
            t_sn = norm(tool.get("nomor_seri_tabung"))
            linked = [
                r
                for r in items
                if (u_sn and norm(r.get("nomor_seri_unit")) == u_sn)
                or (t_sn and norm(r.get("nomor_seri_tabung")) == t_sn)
            ]
            if not linked or any(r.get("needs_review") for r in linked):
                return False
            for k in required:
                if _absent_value(tool.get(k)):
                    continue
                if not any(not _absent_value(r.get(k)) for r in linked):
                    return False
        return True

    warnings = []
    if complete(records):
        return records, warnings

    pages, read_warnings = _read_import_pages(path)
    warnings.extend(read_warnings)
    if Path(path).suffix.lower() == ".pdf" and pages:
        for item in table_records(path, pages).get("equipment", []):
            rec = {k: _text(item.get(k)) for k in FIELDS}
            if all(_absent_value(rec.get(k)) for k in FIELDS):
                continue
            rec.update(
                page=item.get("page") or 1,
                quote=_text(item.get("quote")),
                method="table",
                needs_review=False,
            )
            records.append(rec)

    if complete(records):
        return records, warnings

    ordered = [p for p in sorted(pages, key=_import_page_rank) if (p.get("text") or "").strip()]
    primary = [p for p in ordered if _import_page_rank(p)[0] == 0]
    selected = primary or ordered

    only_fields = set(FIELDS)
    calls = 0
    for page in selected:
        if calls >= 3:
            break
        if len(page.get("text") or "") > 12000:
            warnings.append(
                f"Halaman {page['page']}: teks terlalu panjang untuk ekstraksi Qwen; perlu tinjauan."
            )
            continue
        try:
            window = [{"page": page["page"], "text": page["text"]}]
            calls += 1
            proposed = llm.extract("equipment", window, only_fields=only_fields)
            accepted = grounded(proposed, window, "equipment")
            records.extend(accepted)
            if len(accepted) != len(proposed):
                warnings.append(
                    f"Halaman {page['page']}: sebagian keluaran Qwen tidak didukung kutipan dan diabaikan."
                )
            if complete(records):
                break
        except Exception as exc:
            warnings.append(
                f"Ekstraksi Qwen equipment belum selesai ({type(exc).__name__}); data yang belum terbaca perlu diperiksa."
            )
            break

    return records, warnings


def _import(doc, app, ref):
    from ..protection.extraction import norm
    from ..protection.service import make_row

    forms = app.get("equipment") or []
    if not forms:
        return [
            _row(
                "Data peralatan",
                "Ada peralatan pada formulir",
                "",
                "REVIEW",
                note="Tidak ada peralatan acuan pada formulir permohonan.",
                document_id=doc["id"],
            )
        ]

    equipment, warnings = _extract_import_equipment(storage.file_path(doc), app)
    if warnings:
        doc["_uncacheable"] = True

    rows = []
    for i, tool in enumerate(forms, 1):
        u_sn = norm(tool.get("nomor_seri_unit"))
        t_sn = norm(tool.get("nomor_seri_tabung"))
        found = [
            x for x in equipment if u_sn and norm(x.get("nomor_seri_unit")) == u_sn
        ]
        if not found and t_sn:
            found = [
                x for x in equipment if norm(x.get("nomor_seri_tabung")) == t_sn
            ]
        if not found:
            u_ocr = _ocr_serial_key(tool.get("nomor_seri_unit"))
            t_ocr = _ocr_serial_key(tool.get("nomor_seri_tabung"))
            found = [
                x
                for x in equipment
                if (u_ocr and _ocr_serial_key(x.get("nomor_seri_unit")) == u_ocr)
                or (t_ocr and _ocr_serial_key(x.get("nomor_seri_tabung")) == t_ocr)
            ]
        if not found and len(equipment) == 1 and len(forms) == 1:
            found = equipment[:1]

        for key, label in FIELDS.items():
            expected = _text(tool.get(key))
            field_sources = [item for item in found if not _absent_value(item.get(key))]
            observed = _text(field_sources[0][key]) if field_sources else ""
            note = ""
            if key in ("tipe_unit", "tipe_tabung") and observed:
                trimmed = _trim_model_spec(expected, observed)
                if trimmed:
                    observed, rating = trimmed
                    note = f"Spesifikasi kelistrikan {rating} dipisahkan dari kode tipe."
            row = make_row(
                doc["id"],
                f"Alat {i}: {label}",
                expected,
                observed,
                field_sources,
                note,
                group="Pesawat Sinar-X",
                kind="serial" if "seri" in key else "text",
                conflict=len(
                    {norm(x.get(key)) for x in field_sources if not _absent_value(x.get(key))}
                )
                > 1,
            )
            row["detail"]["type"] = "import"
            rows.append(row)

    return rows
