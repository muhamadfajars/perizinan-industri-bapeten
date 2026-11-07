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


def _import(doc, app, ref):
    from src.extraction.import_approval import parse_import_approval
    from src.matching.import_approval_matcher import match_import_approval

    parsed = parse_import_approval(str(storage.file_path(doc)))
    result = match_import_approval(app, parsed)
    rows = []
    imported_rows = parsed.get("equipment") or []
    for item in result.get("results", []):
        cmp = item.get("best_candidate") or {}
        idx = item.get("form_equipment_index", 0)
        source_idx = item.get("import_row_index")
        src = (
            imported_rows[source_idx]
            if isinstance(source_idx, int) and 0 <= source_idx < len(imported_rows)
            else {}
        )
        # An ordinary Tube S/N is not proof of an *insert* S/N; never compare them.
        # This also prevents fabricated REVIEW percentages for unrelated components.
        insert_explicit = bool(
            re.search(
                r"(?i)\b(?:insert|insersi|insertion)\b",
                " ".join(_text(src.get(k)) for k in ("raw_unit", "raw_tabung")),
            )
        )
        for key in FIELDS:
            expected = (item.get("expected") or {}).get(key)
            actual = (item.get("actual") or {}).get(key)
            if _absent_value(actual) or _absent_value(expected):
                continue  # Not comparable, do not show or score.
            if key == "nomor_seri_tabung" and not insert_explicit:
                continue  # 20G225 is Tube S/N, not insert S/N 0F1376.
            f = (cmp.get("fields") or {}).get(key) or {}
            status = f.get("status", "REVIEW")
            score = f.get("score")
            rows.append(
                _row(
                    f"Alat {idx + 1}: {FIELDS[key]}",
                    expected,
                    actual,
                    status,
                    score,
                    item.get("source_page"),
                    f.get("reason", ""),
                    document_id=doc["id"],
                )
            )
    return rows or [
        _row(
            "Peralatan impor pada formulir",
            "Nomor seri unit yang sama",
            "",
            "REVIEW",
            note="Tidak ada baris impor dengan bukti identitas yang dapat dibandingkan",
            document_id=doc["id"],
        )
    ]
