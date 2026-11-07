from __future__ import annotations

import os


from .. import storage


from .rows import _row
from .equipment import _trim_model_spec


def _label_group(documents, app, ref, prefetched_pages=None):
    """Read all label files and match the combined evidence once.

    In particular, do NOT classify the six fields for a unit-only photo as
    six mismatches. A tube-only photo supplies evidence to the SAME result.
    """
    from src.extraction.label_document_ocr import ocr_label_documents
    from src.matching.guided_label_matcher import auto_match_equipment
    from ..label_results import _label_evidence_view

    equipments = app.get("equipment") or []
    if not equipments:
        return [_row("Label", "Peralatan pada formulir", "", "REVIEW")]
    if not documents:
        return []
    # source_id remains unique for independent files; display provenance from
    # selected_source_id in the actual matcher (never guess source from text).
    inputs = [
        dict(path=str(storage.file_path(d)), name=d["filename"], source_id=d["id"])
        for d in documents
    ]
    # Adaptive OCR: start with mobile models to avoid several-minute full-page
    # quality passes. Escalate only when identities remain insufficient.
    profile_before = os.environ.get("BAPETEN_OCR_PROFILE")
    label_profile = os.environ.get("BAPETEN_LABEL_OCR_PROFILE", "fast").lower().strip()
    if label_profile not in {"quality", "fast"}:
        raise ValueError("BAPETEN_LABEL_OCR_PROFILE harus quality atau fast")
    try:
        os.environ["BAPETEN_OCR_PROFILE"] = label_profile
        pages = (
            prefetched_pages
            if prefetched_pages is not None
            else ocr_label_documents(inputs, equipment_list=equipments)
        )
        selected = auto_match_equipment(pages, equipments)
        current = selected.get("match") or selected.get("suggested_match") or {}
        current_matches = (current.get("summary") or {}).get("match", 0)
        if (
            prefetched_pages is None
            and label_profile == "fast"
            and os.getenv("BAPETEN_LABEL_QUALITY_RESCUE", "1") == "1"
            and (selected.get("status") != "AUTO_SELECTED" or current_matches < 6)
        ):
            # Isolated process worker: no state or model leaks between jobs.
            os.environ["BAPETEN_OCR_PROFILE"] = "quality"
            quality_pages = ocr_label_documents(inputs, equipment_list=equipments)
            quality = auto_match_equipment(quality_pages, equipments)
            quality_result = quality.get("match") or quality.get("suggested_match") or {}
            quality_matches = (quality_result.get("summary") or {}).get("match", 0)
            if (quality_matches, quality.get("best_score", 0)) > (
                current_matches,
                selected.get("best_score", 0),
            ):
                selected = quality
    finally:
        if profile_before is None:
            os.environ.pop("BAPETEN_OCR_PROFILE", None)
        else:
            os.environ["BAPETEN_OCR_PROFILE"] = profile_before
    idx = selected.get("selected_equipment_index")
    if (
        selected.get("status") != "AUTO_SELECTED"
        or not isinstance(idx, int)
        or idx >= len(equipments)
    ):
        return [
            _row(
                "Pemilihan Peralatan Label",
                "Satu peralatan yang teridentifikasi",
                "",
                "REVIEW",
                note="Dokumen label telah digabung, tetapi kandidat alat masih ambigu",
            )
        ]
    result = selected.get("match") or {}
    source_by_name = {d["filename"]: d["id"] for d in documents}
    source_by_id = {d["id"]: d["id"] for d in documents}
    rows = []
    fields = [
        ("unit", "manufacturer", "merk_unit", "Merek Unit"),
        ("unit", "type", "tipe_unit", "Tipe Unit"),
        ("unit", "serial_number", "nomor_seri_unit", "Nomor Seri Unit"),
        ("tabung", "manufacturer", "merk_tabung", "Merek Tabung"),
        ("tabung", "type", "tipe_tabung", "Tipe Tabung"),
        ("tabung", "serial_number", "nomor_seri_tabung", "No. Seri Insersi Tabung"),
    ]
    for section, key, formkey, display in fields:
        group = result.get(section) or {}
        matched = group.get(key) or {}
        evidence = matched.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            components = matched.get("components") or []
            evidence = " / ".join(
                str(c.get("evidence") or "")
                for c in components
                if isinstance(c, dict) and c.get("evidence")
            )
        # Use the field-level decision returned by
        # guided_match_label_document. MISSING evidence cannot become MISMATCH.
        status = matched.get("status", "REVIEW")
        if not evidence and status == "MATCH":
            status = "REVIEW"
        correction_note = ""
        if key == "serial_number" and evidence and status in ("REVIEW", "MATCH"):
            from ..serial_verification import _ambiguity_only, verify_image_serial

            wanted = equipments[idx].get(formkey)
            if _ambiguity_only(wanted, evidence):
                # Different O/0 glyph: only independent image OCR can prove MATCH.
                origin = (
                    source_by_id.get(matched.get("source_id"))
                    or source_by_name.get(matched.get("source_name"))
                    or source_by_id.get(group.get("selected_source_id"))
                    or source_by_name.get(group.get("selected_source_name"))
                )
                target_doc = next((d for d in documents if d["id"] == origin), None)
                proof = (
                    verify_image_serial(
                        str(storage.file_path(target_doc)),
                        wanted,
                        evidence,
                        matched.get("page") or 1,
                    )
                    if target_doc
                    else None
                )
                if proof:
                    evidence = proof["observed"]
                    status = "MATCH"
                    correction_note = proof["note"]
                else:
                    # Normalized possible reading displayed, but not automatic MATCH.
                    status = "REVIEW"
                    correction_note = f"Kemungkinan 0/O pada OCR: {evidence}; periksa label asli"
        # Do not accept a different alphanumeric model just because fuzzy ratio is 90%+.
        if key == "type" and evidence and status == "MATCH":
            from src.matching.import_approval_matcher import compact as model_code

            expected_model = equipments[idx].get(formkey)
            if (
                expected_model
                and model_code(evidence).startswith(model_code(expected_model))
                and len(model_code(evidence)) > len(model_code(expected_model))
            ):
                status = "REVIEW"
                correction_note = "Kode tipe memiliki karakter tambahan pada bukti"
        raw_evidence = evidence
        # Optical OCR can include extra electrical capacity after the unit model.
        # Trim ONLY when the complete expected model matches and the suffix has
        # a clear numeric physical unit (e.g. 30KW). Preserve the full raw quote.
        model_spec = (
            _trim_model_spec(equipments[idx].get(formkey), evidence)
            if formkey == "tipe_unit"
            else None
        )
        if model_spec:
            evidence = model_spec[0]
            status = "MATCH"
            correction_note = (
                f"Nilai OCR asli: {raw_evidence}; spesifikasi tambahan: {model_spec[1]}"
            )
        field_name = formkey
        evidence, exact_score = _label_evidence_view(
            equipments[idx].get(formkey), evidence, status, field_name
        )
        score = 100.0 if model_spec else exact_score
        if score is None:
            score = matched.get("score")
            if score is None and key == "type":
                scores = [
                    x.get("score")
                    for x in matched.get("components") or []
                    if isinstance(x, dict) and isinstance(x.get("score"), (int, float))
                ]
                score = min(scores) if scores else None
        if status == "REVIEW" and (not raw_evidence or correction_note):
            score = None
        doc_id = (
            source_by_id.get(matched.get("source_id"))
            or source_by_name.get(matched.get("source_name"))
            or source_by_id.get(group.get("selected_source_id"))
            or source_by_name.get(group.get("selected_source_name"))
        )
        page = matched.get("page") or group.get("selected_page") or matched.get("selected_page")
        rows.append(
            _row(
                "Alat %d: %s" % (idx + 1, display),
                equipments[idx].get(formkey),
                evidence,
                status,
                score,
                page,
                correction_note or matched.get("reason") or "",
                doc_id,
                raw_evidence if isinstance(raw_evidence, str) else "",
            )
        )
    return rows


def _label(doc, app, ref):
    """Compatibility only; worker orchestrator calls _label_group once per set."""
    return _label_group([doc], app, ref)
