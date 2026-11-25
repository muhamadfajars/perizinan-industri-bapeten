"""Hybrid deterministic + bounded Qwen evaluator for calibration certificates (`kalibrasi`)."""

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


def extract_calibration_llm(
    pages: list[dict],
    needed_targets: set[str],
    expected_refs: list[dict] | None = None,
) -> tuple[list[dict], bool]:
    """Run bounded Qwen LLM fallback to extract equipment identity fields from calibration certs."""
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
        "Teks berasal dari dokumen Sertifikat Kalibrasi / Calibration Certificate peralatan "
        "(berbahasa Indonesia atau Inggris). "
        f"Field peralatan yang masih dibutuhkan: {', '.join(sorted(needed_targets))}. "
        "Salin nilai PERSIS seperti tertulis pada dokumen; jangan mengarang atau memperbaiki karakter. "
        'Isi string kosong "" jika field tidak tercantum. '
        "Untuk tipe_unit: ambil kode model/tipe alat yang spesifik pada label Model/Type/Tipe "
        "(mis. 'TrueX G5', 'DXL 800'), JANGAN mengambil kategori umum produk seperti "
        "'Handheld XRF analyzer' atau 'Name of Product'. "
        "JANGAN menyalin data detector/surveymeter/alat ukur pembanding ke field unit maupun tabung. "
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
                "Ekstraksi identitas peralatan pada sertifikat kalibrasi",
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


def _select_calibration_equipment_index(fields: dict, equipments: list[dict]) -> int | None:
    """Select matching form equipment without guessing across conflicting serials."""
    if not equipments:
        return None
    if len(equipments) == 1:
        return 0
    idx = _select_form_index(fields, equipments)
    if idx is not None:
        return idx
    # Never fall back to brand+model guessing if the certificate states a serial number.
    if not _absent(fields.get("nomor_seri_unit")) or not _absent(fields.get("nomor_seri_tabung")):
        return None
    obs_brand = _space(fields.get("merk_unit"))
    obs_model = _space(fields.get("tipe_unit"))
    if _absent(obs_brand) or _absent(obs_model):
        return None
    hits = [
        i
        for i, eq in enumerate(equipments)
        if not _absent(eq.get("merk_unit"))
        and not _absent(eq.get("tipe_unit"))
        and evaluate_exposure_field("merk_unit", eq["merk_unit"], obs_brand)[0] == "MATCH"
        and evaluate_exposure_field("tipe_unit", eq["tipe_unit"], obs_model)[0] == "MATCH"
    ]
    return hits[0] if len(hits) == 1 else None


def evaluate(doc: dict, app: dict, ref: dict) -> list[dict]:
    """Evaluate Sertifikat Kalibrasi (`kalibrasi`): equipment fields only, conditional MATCH display."""
    path = str(storage.file_path(doc))
    pages = read_exposure_pages(path)
    equipments = list(app.get("equipment") or [])

    if not pages or not any(_space(p.get("text")) for p in pages):
        doc["_uncacheable"] = True
        return [
            _row(
                "Sertifikat Kalibrasi",
                "Dokumen sertifikat terbaca",
                "",
                "REVIEW",
                note="Teks/gambar pada sertifikat kalibrasi belum terbaca oleh OCR; periksa visual.",
                document_id=doc["id"],
                detail={"type": "calibration"},
            )
        ]

    det = extract_deterministic(pages)
    fields = {k: v for k, v in det["fields"].items() if k in EQUIPMENT_FIELDS}
    meta = {k: v for k, v in det["meta"].items() if k in EQUIPMENT_FIELDS}

    needed: set[str] = set()
    full_text = "\n".join(p.get("text") or "" for p in pages)
    mentions_tube = bool(re.search(r"(?i)\b(?:tube|tabung|insersi|insert)\b", full_text))
    for key in ("merk_unit", "tipe_unit", "nomor_seri_unit"):
        if any(not _absent(eq.get(key)) for eq in equipments) and key not in fields:
            needed.add(key)
    if mentions_tube:
        for key in ("merk_tabung", "tipe_tabung", "nomor_seri_tabung"):
            if any(not _absent(eq.get(key)) for eq in equipments) and key not in fields:
                needed.add(key)

    llm_warn = False
    llm_used_keys: set[str] = set()
    if needed:
        llm_records, llm_warn = extract_calibration_llm(pages, needed, equipments)
        if llm_warn:
            doc["_uncacheable"] = True
        if llm_records:
            _, chosen = _choose_record_and_form_idx(llm_records, equipments)
            if chosen is None and _select_form_index(fields, equipments) is not None and len(llm_records) == 1:
                chosen = llm_records[0]
            if chosen:
                for key in EQUIPMENT_FIELDS:
                    val = chosen.get(key)
                    if val and key not in fields:
                        fields[key] = val
                        meta[key] = {
                            "page": chosen.get(f"{key}_page") or chosen["page"],
                            "quote": chosen.get(f"{key}_quote") or chosen.get("quote") or val,
                        }
                        llm_used_keys.add(key)

    rows: list[dict] = []
    if equipments:
        eq_idx = _select_calibration_equipment_index(fields, equipments)
        if eq_idx is not None:
            target = equipments[eq_idx]
            for ekey in EQUIPMENT_FIELDS:
                expected_val = _space(target.get(ekey))
                observed_val = _space(fields.get(ekey))
                if _absent(expected_val) or _absent(observed_val):
                    continue
                status, score, note = evaluate_exposure_field(ekey, expected_val, observed_val)
                if status != "MATCH":
                    continue
                info = meta.get(ekey) or {}
                if ekey in llm_used_keys:
                    note = (
                        (note + " (terbaca Qwen)").strip()
                        if note
                        else "Terbaca melalui bantuan Qwen dari teks sertifikat"
                    )
                rows.append(
                    _row(
                        f"Alat {eq_idx + 1}: {DISPLAY_FIELDS[ekey]}",
                        expected_val,
                        observed_val,
                        "MATCH",
                        score,
                        info.get("page"),
                        note,
                        doc["id"],
                        info.get("quote") or observed_val,
                        {"type": "calibration"},
                    )
                )

    if not rows:
        first_page = next((p.get("page") for p in pages if _space(p.get("text"))), None)
        rows.append(
            _row(
                "Data Peralatan",
                "—",
                "Tidak ada data peralatan formulir yang cocok pada sertifikat kalibrasi",
                "INFO",
                page=first_page,
                note="Sertifikat kalibrasi hanya menampilkan data peralatan yang tercantum dan sesuai dengan formulir.",
                document_id=doc["id"],
                detail={"type": "calibration"},
            )
        )

    return rows
