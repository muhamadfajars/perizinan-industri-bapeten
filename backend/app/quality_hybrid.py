"""Hybrid deterministic + bounded Qwen evaluator for quality/calibration certificates (`mutu`)."""

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
from .protection.extraction import norm

_CLEAN_UNDERLINE_RE = re.compile(r"[_|]+")

_FIELD_LINE_PATTERNS = {
    "merk_unit": re.compile(
        r"(?i)^(?:manufacturer|merek(?:\s+unit)?|merk(?:\s+unit)?|pabrikan(?:\s+unit)?|pabrik(?:\s+pembuat)?|brand)\s*[:|]\s*(.+)$"
    ),
    "tipe_unit": re.compile(
        r"(?i)^(?:instrument\s+model|(?:unit\s+)?model\s*/?\s*type|model(?:\s+unit)?|tipe(?:\s*/\s*model)?(?:\s+unit)?|type(?:\s*/\s*model)?)\s*[:|]\s*(.+)$"
    ),
    "nomor_seri_unit": re.compile(
        r"(?i)^(?:instrument\s+serial(?:\s+(?:number|no\.?))?|(?:unit\s+)?serial(?:\s+(?:number|no\.?))?|no\.?\s*seri(?:\s+(?:unit|alat))?|nomor\s+seri(?:\s+(?:unit|alat))?|s\s*/\s*n)\s*[:|#]?\s*(.+)$"
    ),
    "merk_tabung": re.compile(
        r"(?i)^(?:tube\s+manufacturer|merek\s+tabung|merk\s+tabung)\s*[:|]\s*(.+)$"
    ),
    "tipe_tabung": re.compile(
        r"(?i)^(?:tube\s+(?:model|type)|tipe\s+tabung|model\s+tabung)\s*[:|]\s*(.+)$"
    ),
    "nomor_seri_tabung": re.compile(
        r"(?i)^(?:tube\s+serial(?:\s+(?:number|no\.?))?|serial(?:\s+(?:number|no\.?))?\s+tabung|no\.?\s*seri\s+(?:insersi|tabung)|nomor\s+seri\s+(?:insersi|tabung))\s*[:|#]?\s*(.+)$"
    ),
}

_DATE_PATTERNS = {
    "manufacture_date": re.compile(
        r"(?i)^(?:manufacture\s+date|tanggal\s+produksi|production\s+date|mfg\.?\s*date)\s*[:|]\s*(.+)$"
    ),
    "calibration_date": re.compile(
        r"(?i)^(?:calibration\s+date|tanggal\s+kalibrasi|test\s+date|tanggal\s+uji|inspection\s+date)\s*[:|]\s*(.+)$"
    ),
}

_APPROVAL_LINE_RE = re.compile(
    r"(?i)\b(?:approved(?:\s+by)?|checked(?:\s+by)?|verified(?:\s+by)?|tested\s+by|"
    r"quality\s+control|disahkan|mengetahui|pengesahan|qc\s*[-]?\s*\d{1,3})\b"
)


def _clean_val(raw: str) -> str:
    val = _CLEAN_UNDERLINE_RE.sub(" ", str(raw or ""))
    return _space(val).strip(" :;,-")


def extract_deterministic(pages: list[dict]) -> dict:
    """Fast deterministic key-value extraction across native/OCR pages."""
    merged: dict[str, str] = {}
    meta: dict[str, dict] = {}
    approval: dict | None = None

    for pg in pages:
        pg_num = pg["page"]
        text = pg.get("text") or ""
        for raw_line in text.splitlines():
            line = _clean_val(raw_line)
            if not line:
                continue

            for key, pat in _FIELD_LINE_PATTERNS.items():
                if key in merged:
                    continue
                m = pat.match(line)
                if not m:
                    continue
                val = _clean_val(m.group(1))
                if _absent(val) or _in_detector_only_context(val, text):
                    continue
                if key in ("tipe_unit", "tipe_tabung") and _is_generic_device_noun(val):
                    continue
                merged[key] = val
                meta[key] = {"page": pg_num, "quote": _space(raw_line)[:220]}

            for dkey, pat in _DATE_PATTERNS.items():
                if dkey in merged:
                    continue
                m = pat.match(line)
                if not m:
                    continue
                val = _clean_val(m.group(1))
                if not _absent(val) and any(ch.isdigit() for ch in val):
                    merged[dkey] = val
                    meta[dkey] = {"page": pg_num, "quote": _space(raw_line)[:220]}

            if approval is None and _APPROVAL_LINE_RE.search(line):
                approval = {"page": pg_num, "quote": _space(raw_line)[:220]}

    return {"fields": merged, "meta": meta, "approval": approval}


def extract_quality_llm(
    pages: list[dict],
    needed_targets: set[str],
    expected_refs: list[dict] | None = None,
) -> tuple[list[dict], bool]:
    """Run bounded Qwen LLM fallback when deterministic quality-cert parsing left gaps."""
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
            "manufacture_date": {"type": "string"},
            "calibration_date": {"type": "string"},
            "approval_quote": {"type": "string"},
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
            "manufacture_date",
            "calibration_date",
            "approval_quote",
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
        "Teks berasal dari dokumen Sertifikat Uji Mutu / Factory QC / Calibration Certificate peralatan radiasi "
        "(berbahasa Indonesia atau Inggris). "
        f"Field yang masih dibutuhkan: {', '.join(sorted(needed_targets))}. "
        "Salin nilai PERSIS seperti tertulis pada dokumen; jangan mengarang atau memperbaiki karakter. "
        "Isi string kosong \"\" jika field tidak tercantum. "
        "Untuk tipe_unit: ambil kode model/tipe alat yang spesifik pada label Model/Type/Tipe "
        "(mis. 'TrueX G5', 'DXL 800'), JANGAN mengambil kategori umum produk seperti 'Handheld XRF analyzer' atau 'Name of Product'. "
        "JANGAN menyalin data detector/surveymeter/alat ukur ke field unit maupun tabung. "
        "Untuk approval_quote: kutip baris atau cap pengesahan/QC (mis. 'Approved QC02', 'Approved by ...', 'Checked by ...', 'Disahkan'). "
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
                "Ekstraksi identitas alat, tanggal uji/produksi, dan pengesahan sertifikat uji mutu",
                window,
                instructions,
                output_limit=800,
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
                if eq_key in ("nomor_seri_unit", "nomor_seri_tabung") and _has_model_only_label(val, text):
                    target_type = "tipe_unit" if eq_key == "nomor_seri_unit" else "tipe_tabung"
                    if not cleaned.get(target_type) and not _is_generic_device_noun(val):
                        cleaned[target_type] = val
                        has_any = True
                    continue
                cleaned[eq_key] = val
                has_any = True

            for dkey in ("manufacture_date", "calibration_date"):
                val = _clean_val(item.get(dkey))
                if _value_grounded(val, text) and any(ch.isdigit() for ch in val):
                    cleaned[dkey] = val
                    has_any = True

            app_val = _clean_val(item.get("approval_quote"))
            if _value_grounded(app_val, text) and _APPROVAL_LINE_RE.search(app_val):
                cleaned["approval_quote"] = app_val
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


def _select_form_index(combined: dict, equipments: list[dict]) -> int | None:
    if not equipments:
        return None
    if len(equipments) == 1:
        return 0
    u_sn = norm(combined.get("nomor_seri_unit"))
    t_sn = norm(combined.get("nomor_seri_tabung"))
    hits = [
        idx
        for idx, eq in enumerate(equipments)
        if (u_sn and norm(eq.get("nomor_seri_unit")) == u_sn)
        or (t_sn and norm(eq.get("nomor_seri_tabung")) == t_sn)
    ]
    return hits[0] if len(hits) == 1 else None


def evaluate(doc: dict, app: dict, ref: dict) -> list[dict]:
    """Evaluate Sertifikat Uji Mutu (`mutu`) with deterministic + bounded Qwen fallback."""
    path = str(storage.file_path(doc))
    pages = read_exposure_pages(path)
    equipments = list(app.get("equipment") or [])

    if not pages or not any(_space(p.get("text")) for p in pages):
        doc["_uncacheable"] = True
        return [
            _row(
                "Sertifikat Uji Mutu",
                "Dokumen sertifikat terbaca",
                "",
                "REVIEW",
                note="Teks/gambar pada sertifikat uji mutu belum terbaca oleh OCR; periksa visual.",
                document_id=doc["id"],
                detail={"type": "quality"},
            )
        ]

    det = extract_deterministic(pages)
    fields = dict(det["fields"])
    meta = dict(det["meta"])
    approval = det["approval"]

    needed: set[str] = set()
    ref_eq = equipments[0] if equipments else {}
    full_text = "\n".join(p.get("text") or "" for p in pages)
    mentions_tube = bool(re.search(r"(?i)\b(?:tube|tabung|insersi|insert)\b", full_text))
    for key in ("merk_unit", "tipe_unit", "nomor_seri_unit"):
        if not _absent(ref_eq.get(key)) and key not in fields:
            needed.add(key)
    if mentions_tube:
        for key in ("merk_tabung", "tipe_tabung", "nomor_seri_tabung"):
            if not _absent(ref_eq.get(key)) and key not in fields:
                needed.add(key)
    if approval is None:
        needed.add("approval_quote")
    if "calibration_date" not in fields:
        needed.add("calibration_date")
    if "manufacture_date" not in fields:
        needed.add("manufacture_date")

    llm_warn = False
    llm_used_keys: set[str] = set()
    if needed:
        llm_records, llm_warn = extract_quality_llm(pages, needed, equipments)
        if llm_warn:
            doc["_uncacheable"] = True
        if llm_records:
            _, chosen = _choose_record_and_form_idx(llm_records, equipments)
            if chosen:
                for key in (*EQUIPMENT_FIELDS, "manufacture_date", "calibration_date"):
                    val = chosen.get(key)
                    if val and key not in fields:
                        fields[key] = val
                        meta[key] = {
                            "page": chosen.get(f"{key}_page") or chosen["page"],
                            "quote": chosen.get(f"{key}_quote") or chosen.get("quote") or val,
                        }
                        llm_used_keys.add(key)
            if approval is None:
                hit = next((r for r in llm_records if r.get("approval_quote")), None)
                if hit:
                    approval = {
                        "page": hit["page"],
                        "quote": hit.get("approval_quote") or hit.get("quote") or "",
                    }
                    llm_used_keys.add("approval_quote")

    rows: list[dict] = []
    if equipments:
        eq_idx = _select_form_index(fields, equipments)
        if eq_idx is None:
            rows.append(
                _row(
                    "Pemilihan Peralatan",
                    "Nomor seri unit unik pada sertifikat uji mutu",
                    "",
                    "REVIEW",
                    note="Formulir memiliki lebih dari 1 peralatan dan nomor seri unik belum terbukti.",
                    document_id=doc["id"],
                    detail={"type": "quality"},
                )
            )
        else:
            target = equipments[eq_idx]
            for ekey in EQUIPMENT_FIELDS:
                expected_val = _space(target.get(ekey))
                observed_val = _space(fields.get(ekey))
                # Do not fabricate tube mismatch rows on unit-only factory QC certificates.
                if ekey.endswith("_tabung") and _absent(observed_val):
                    continue
                if _absent(expected_val) and _absent(observed_val):
                    continue
                info = meta.get(ekey) or {}
                if _absent(observed_val):
                    rows.append(
                        _row(
                            f"Alat {eq_idx + 1}: {DISPLAY_FIELDS[ekey]}",
                            expected_val,
                            "",
                            "REVIEW",
                            note="Belum terbaca pada sertifikat uji mutu; periksa dokumen sumber.",
                            document_id=doc["id"],
                            detail={"type": "quality"},
                        )
                    )
                    continue
                status, score, note = evaluate_exposure_field(ekey, expected_val, observed_val)
                if ekey in llm_used_keys:
                    note = (note + " (terbaca Qwen)").strip() if note else "Terbaca melalui bantuan Qwen dari teks sertifikat"
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
                        {"type": "quality"},
                    )
                )
    else:
        for ekey in EQUIPMENT_FIELDS:
            observed_val = _space(fields.get(ekey))
            if _absent(observed_val):
                continue
            info = meta.get(ekey) or {}
            rows.append(
                _row(
                    DISPLAY_FIELDS[ekey],
                    "",
                    observed_val,
                    "INFO",
                    page=info.get("page"),
                    note="Informasi alat pada sertifikat uji mutu.",
                    document_id=doc["id"],
                    quote=info.get("quote") or observed_val,
                    detail={"type": "quality"},
                )
            )

    for dkey, title in (
        ("manufacture_date", "Tanggal Produksi"),
        ("calibration_date", "Tanggal Kalibrasi / Uji Mutu"),
    ):
        val = _space(fields.get(dkey))
        if val:
            info = meta.get(dkey) or {}
            rows.append(
                _row(
                    title,
                    "",
                    val,
                    "INFO",
                    page=info.get("page"),
                    note="Informasi tanggal dari sertifikat uji mutu.",
                    document_id=doc["id"],
                    quote=info.get("quote") or val,
                    detail={"type": "quality"},
                )
            )

    if approval:
        rows.append(
            _row(
                "Pengesahan",
                "Blok persetujuan / stempel QC pada sertifikat",
                f"Halaman {approval['page']}",
                "MATCH",
                100,
                approval["page"],
                "Blok pengesahan / QC ditemukan; verifikasi visual tetap disarankan.",
                doc["id"],
                approval["quote"],
                {
                    "type": "approval",
                    "pages": [approval["page"]],
                    "heading": "Pengesahan Sertifikat Uji Mutu",
                },
            )
        )
    else:
        rows.append(
            _row(
                "Pengesahan",
                "Blok persetujuan / stempel QC pada sertifikat",
                "",
                "REVIEW",
                note="Belum ditemukan blok pengesahan / stempel QC yang terbaca.",
                document_id=doc["id"],
                detail={"type": "quality"},
            )
        )

    return rows
