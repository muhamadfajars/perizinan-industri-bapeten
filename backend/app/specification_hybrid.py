"""Hybrid deterministic + bounded Qwen evaluator for equipment specifications (`spesifikasi`)."""

from __future__ import annotations

import re

from . import storage
from .analysis.constants import FIELDS as DISPLAY_FIELDS
from .analysis.rows import _row
from .exposure_hybrid import (
    EQUIPMENT_FIELDS,
    _absent,
    _choose_record_and_form_idx,
    _extract_explicit_labeled_model,
    _has_model_only_label,
    _in_detector_only_context,
    _is_generic_device_noun,
    _prioritize_pages,
    _quote_grounded,
    _space,
    _value_grounded,
    evaluate_exposure_field,
    read_exposure_pages,
)
from .protection import llm
from .quality_hybrid import _clean_val, _select_form_index, extract_deterministic

_TUBE_MENTION_RE = re.compile(r"(?i)\b(?:tube|tabung|insersi|insert|x-?ray\s*tube)\b")


def extract_specification_llm(
    pages: list[dict],
    needed_targets: set[str],
    expected_refs: list[dict] | None = None,
) -> tuple[list[dict], bool]:
    """Run bounded Qwen LLM fallback to extract equipment identity fields from brochures/datasheets."""
    if not pages or not needed_targets:
        return [], False

    record_schema = {
        "type": "object",
        "properties": {
            "page": {"type": "integer"},
            "quote": {"type": "string"},
            "merk_unit": {"type": "string"},
            "tipe_unit": {"type": "string"},
            "nomor_seri_unit": {"type": "string"},
            "merk_tabung": {"type": "string"},
            "tipe_tabung": {"type": "string"},
            "nomor_seri_tabung": {"type": "string"},
        },
        "required": [
            "page",
            "quote",
            "merk_unit",
            "tipe_unit",
            "nomor_seri_unit",
            "merk_tabung",
            "tipe_tabung",
            "nomor_seri_tabung",
        ],
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "properties": {"records": {"type": "array", "items": record_schema}},
        "required": ["records"],
        "additionalProperties": False,
    }

    instructions = (
        "Teks berasal dari dokumen Spesifikasi Alat / Brosur / Datasheet / Manual peralatan "
        "(berbahasa Indonesia atau Inggris). "
        f"Field peralatan yang masih dibutuhkan: {', '.join(sorted(needed_targets))}. "
        "Salin nilai PERSIS seperti tertulis pada dokumen; jangan mengarang atau memperbaiki karakter. "
        'Isi string kosong "" jika field tidak tercantum. '
        "Untuk tipe_unit dan tipe_tabung: ambil kode model/tipe alat yang spesifik "
        "(mis. 'TrueX G5', 'DXL 800', 'uDR 566i'), JANGAN mengambil kategori umum produk seperti "
        "'Handheld XRF Analyzer' atau 'Digital Radiography System'. "
        "JANGAN menyalin data detector/surveymeter/alat ukur ke field unit maupun tabung. "
        "quote wajib merupakan kutipan persis dari halaman tersebut."
    )

    ordered = _prioritize_pages(pages, expected_refs or [])
    grounded_records: list[dict] = []
    warning = False
    calls = 0

    for page in ordered:
        if calls >= 3:
            break
        text = (page.get("text") or "").strip()
        if not text:
            continue
        if len(text) > 12000:
            text = text[:12000]
        window = [{"page": page["page"], "text": text}]
        calls += 1
        try:
            proposed = llm.request_records(
                schema,
                "Ekstraksi identitas peralatan pada dokumen spesifikasi alat",
                window,
                instructions,
                output_limit=600,
            )
        except Exception:
            warning = True
            break

        for item in proposed:
            if not isinstance(item, dict) or item.get("page") != page["page"]:
                continue
            quote = _clean_val(item.get("quote"))
            if quote and not _quote_grounded(quote, text):
                continue

            cleaned: dict = {"page": page["page"], "quote": quote}
            has_any = False

            for eq_key in EQUIPMENT_FIELDS:
                val = _clean_val(item.get(eq_key))
                if not _value_grounded(val, text):
                    continue
                if _in_detector_only_context(val, text):
                    continue
                if eq_key in ("tipe_unit", "tipe_tabung") and _is_generic_device_noun(val):
                    continue
                if eq_key in ("nomor_seri_unit", "nomor_seri_tabung") and _has_model_only_label(
                    val, text
                ):
                    target_type = "tipe_unit" if eq_key == "nomor_seri_unit" else "tipe_tabung"
                    if not cleaned.get(target_type) and not _is_generic_device_noun(val):
                        cleaned[target_type] = val
                        has_any = True
                    continue
                cleaned[eq_key] = val
                has_any = True

            if "tipe_unit" in needed_targets and not cleaned.get("tipe_unit"):
                explicit_model = _extract_explicit_labeled_model(text)
                if explicit_model:
                    cleaned["tipe_unit"] = explicit_model
                    has_any = True

            if has_any:
                grounded_records.append(cleaned)

        if grounded_records:
            found_keys = {k for r in grounded_records for k in r if k not in ("page", "quote")}
            if needed_targets <= found_keys:
                break

    return grounded_records, warning


def _matches_any_equipment(key: str, value: str, equipments: list[dict]) -> bool:
    if _absent(value):
        return False
    return any(
        not _absent(eq.get(key)) and evaluate_exposure_field(key, eq[key], value)[0] == "MATCH"
        for eq in equipments
    )


def _merge_matcher_evidence(
    fields: dict[str, str], meta: dict[str, dict], spec_match: dict
) -> None:
    """Populate missing merk_unit/tipe_unit from exact specification_matcher hits."""
    candidates = spec_match.get("candidates") or []
    if not candidates:
        return
    sel_idx = spec_match.get("selected_equipment_index")
    chosen = None
    if isinstance(sel_idx, int):
        chosen = next((c for c in candidates if c.get("equipment_index") == sel_idx), None)
    elif len(candidates) == 1:
        chosen = candidates[0]
    else:
        matched_cands = [
            c
            for c in candidates
            if (c.get("brand") or {}).get("status") == "MATCH"
            or (c.get("model") or {}).get("status") == "MATCH"
        ]
        if len(matched_cands) == 1:
            chosen = matched_cands[0]
    if not chosen:
        return
    for ekey, mkey in (("merk_unit", "brand"), ("tipe_unit", "model")):
        if ekey in fields:
            continue
        item = chosen.get(mkey) or {}
        if item.get("status") != "MATCH":
            continue
        ev = _space(item.get("evidence"))
        if _absent(ev):
            continue
        fields[ekey] = ev
        meta[ekey] = {"page": chosen.get("best_page"), "quote": ev}


def _pick_spec_llm_record(llm_records: list[dict], equipments: list[dict]) -> dict | None:
    if not llm_records:
        return None
    _, chosen = _choose_record_and_form_idx(llm_records, equipments)
    if chosen is not None:
        return chosen
    # Multiple equipments without serials: pick record uniquely matching brand+model or model.
    paired_hits = []
    model_hits = []
    for rec in llm_records:
        obs_brand = _space(rec.get("merk_unit"))
        obs_model = _space(rec.get("tipe_unit"))
        for eq in equipments:
            brand_ok = (
                not _absent(eq.get("merk_unit"))
                and not _absent(obs_brand)
                and evaluate_exposure_field("merk_unit", eq["merk_unit"], obs_brand)[0] == "MATCH"
            )
            model_ok = (
                not _absent(eq.get("tipe_unit"))
                and not _absent(obs_model)
                and evaluate_exposure_field("tipe_unit", eq["tipe_unit"], obs_model)[0] == "MATCH"
            )
            if brand_ok and model_ok:
                paired_hits.append(rec)
            elif model_ok:
                model_hits.append(rec)
    if len(paired_hits) == 1:
        return paired_hits[0]
    if len(model_hits) == 1:
        return model_hits[0]
    if len(llm_records) == 1:
        return llm_records[0]
    return None


def _select_spec_equipment_index(
    fields: dict, spec_match: dict, equipments: list[dict]
) -> int | None:
    """Select uniquely matching form equipment without guessing across ties."""
    if not equipments:
        return None
    if len(equipments) == 1:
        return 0
    idx = _select_form_index(fields, equipments)
    if idx is not None:
        return idx
    spec_idx = spec_match.get("selected_equipment_index")
    if isinstance(spec_idx, int) and 0 <= spec_idx < len(equipments):
        return spec_idx
    obs_brand = _space(fields.get("merk_unit"))
    obs_model = _space(fields.get("tipe_unit"))
    if not _absent(obs_brand) and not _absent(obs_model):
        paired = [
            i
            for i, eq in enumerate(equipments)
            if not _absent(eq.get("merk_unit"))
            and not _absent(eq.get("tipe_unit"))
            and evaluate_exposure_field("merk_unit", eq["merk_unit"], obs_brand)[0] == "MATCH"
            and evaluate_exposure_field("tipe_unit", eq["tipe_unit"], obs_model)[0] == "MATCH"
        ]
        if len(paired) == 1:
            return paired[0]
        if len(paired) > 1:
            return None
    if not _absent(obs_model):
        model_hits = [
            i
            for i, eq in enumerate(equipments)
            if not _absent(eq.get("tipe_unit"))
            and evaluate_exposure_field("tipe_unit", eq["tipe_unit"], obs_model)[0] == "MATCH"
        ]
        if len(model_hits) == 1:
            return model_hits[0]
    return None


def evaluate(doc: dict, app: dict, ref: dict) -> list[dict]:
    """Evaluate Spesifikasi Alat (`spesifikasi`) with hybrid extraction and conditional fields."""
    from src.matching.specification_matcher import match_equipment_specification

    path = str(storage.file_path(doc))
    pages = read_exposure_pages(path)
    equipments = list(app.get("equipment") or [])

    if not pages or not any(_space(p.get("text")) for p in pages):
        doc["_uncacheable"] = True
        return [
            _row(
                "Spesifikasi Alat",
                "Dokumen spesifikasi terbaca",
                "",
                "REVIEW",
                note="Teks/gambar pada dokumen spesifikasi alat belum terbaca oleh OCR; periksa visual.",
                document_id=doc["id"],
                detail={"type": "specification"},
            )
        ]

    # Layer 1a & 1b: deterministic labeled extraction + unstructured brochure matcher.
    det = extract_deterministic(pages)
    fields = {k: v for k, v in det["fields"].items() if k in EQUIPMENT_FIELDS}
    meta = {k: v for k, v in det["meta"].items() if k in EQUIPMENT_FIELDS}

    spec_input = {
        "pages": [
            {
                "page": p["page"],
                "method": p.get("method") or "TEXT",
                "lines": (p.get("text") or "").splitlines(),
                "text": p.get("text") or "",
            }
            for p in pages
        ]
    }
    spec_match = match_equipment_specification(spec_input, equipments)
    _merge_matcher_evidence(fields, meta, spec_match)

    # Layer 2: bounded Qwen fallback for missing or deterministically unmatched unit/tube fields.
    full_text = "\n".join(p.get("text") or "" for p in pages)
    mentions_tube = bool(_TUBE_MENTION_RE.search(full_text))
    needed: set[str] = set()
    for key in ("merk_unit", "tipe_unit"):
        if any(not _absent(eq.get(key)) for eq in equipments) and not _matches_any_equipment(
            key, fields.get(key, ""), equipments
        ):
            needed.add(key)
    if mentions_tube:
        for key in ("merk_tabung", "tipe_tabung"):
            if any(not _absent(eq.get(key)) for eq in equipments) and not _matches_any_equipment(
                key, fields.get(key, ""), equipments
            ):
                needed.add(key)

    llm_used_keys: set[str] = set()
    if needed:
        llm_records, llm_warn = extract_specification_llm(pages, needed, equipments)
        if llm_warn:
            doc["_uncacheable"] = True
        chosen = _pick_spec_llm_record(llm_records, equipments)
        if chosen:
            for key in EQUIPMENT_FIELDS:
                val = chosen.get(key)
                if _absent(val):
                    continue
                existing_matched = key in fields and _matches_any_equipment(
                    key, fields[key], equipments
                )
                if key not in fields or (
                    not existing_matched and _matches_any_equipment(key, val, equipments)
                ):
                    fields[key] = val
                    meta[key] = {
                        "page": chosen.get(f"{key}_page") or chosen["page"],
                        "quote": chosen.get(f"{key}_quote") or chosen.get("quote") or val,
                    }
                    llm_used_keys.add(key)

    rows: list[dict] = []
    if equipments:
        eq_idx = _select_spec_equipment_index(fields, spec_match, equipments)
        if eq_idx is not None:
            target = equipments[eq_idx]
            for ekey in EQUIPMENT_FIELDS:
                expected_val = _space(target.get(ekey))
                observed_val = _space(fields.get(ekey))
                if _absent(expected_val) or _absent(observed_val):
                    continue
                status, score, note = evaluate_exposure_field(ekey, expected_val, observed_val)
                info = meta.get(ekey) or {}
                if ekey in llm_used_keys:
                    note = (
                        (note + " (terbaca Qwen)").strip()
                        if note
                        else "Terbaca melalui bantuan Qwen dari dokumen spesifikasi"
                    )
                elif not note:
                    note = "Bukti berasal dari dokumen spesifikasi alat"
                rows.append(
                    _row(
                        f"Alat {eq_idx + 1}: {DISPLAY_FIELDS[ekey]}",
                        expected_val,
                        observed_val,
                        status,
                        score,
                        info.get("page"),
                        note,
                        doc["id"],
                        info.get("quote") or observed_val,
                        {"type": "specification"},
                    )
                )

    if not rows:
        first_page = next((p.get("page") for p in pages if _space(p.get("text"))), None)
        rows.append(
            _row(
                "Pemilihan peralatan",
                "Identitas merek dan tipe unik",
                "",
                "REVIEW",
                page=first_page,
                note=(
                    spec_match.get("reason")
                    or "Identitas merek dan tipe alat pada dokumen spesifikasi belum dapat dipasangkan secara unik ke formulir."
                ),
                document_id=doc["id"],
                detail={"type": "specification"},
            )
        )

    return rows
