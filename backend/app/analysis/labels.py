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
        from src.extraction import label_ocr as _label_ocr_mod

        _, _ocr_mode = _label_ocr_mod.create_ocr()
        if (
            prefetched_pages is None
            and label_profile == "fast"
            and _ocr_mode.startswith("paddle")
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
                pages = quality_pages
    finally:
        if profile_before is None:
            os.environ.pop("BAPETEN_OCR_PROFILE", None)
        else:
            os.environ["BAPETEN_OCR_PROFILE"] = profile_before
    cur_result = selected.get("match") or selected.get("suggested_match") or {}
    cur_matches = (cur_result.get("summary") or {}).get("match", 0)
    expected_present = 6
    cur_idx = selected.get("selected_equipment_index")
    if isinstance(cur_idx, int) and 0 <= cur_idx < len(equipments):
        expected_present = sum(
            1
            for k in (
                "merk_unit",
                "tipe_unit",
                "nomor_seri_unit",
                "merk_tabung",
                "tipe_tabung",
                "nomor_seri_tabung",
            )
            if (equipments[cur_idx].get(k) or "").strip()
        )
    if selected.get("status") != "AUTO_SELECTED" or cur_matches < expected_present:
        from ..label_hybrid import rescue_label_pages

        before_rows = sum(len(p.get("ocr") or []) for p in pages)
        rescued_pages = rescue_label_pages(documents, pages)
        after_rows = sum(len(p.get("ocr") or []) for p in rescued_pages)
        if after_rows > before_rows:
            pages = rescued_pages
            rescued = auto_match_equipment(pages, equipments)
            rescued_cur = rescued.get("match") or rescued.get("suggested_match") or {}
            rescued_matches = (rescued_cur.get("summary") or {}).get("match", 0)

            def _evidence_count(match_dict):
                count = 0
                for sec in ("unit", "tabung"):
                    sec_data = match_dict.get(sec) or {}
                    for k in ("manufacturer", "type", "serial_number"):
                        fld = sec_data.get(k) or {}
                        if fld.get("evidence") or any(
                            isinstance(c, dict) and c.get("evidence")
                            for c in (fld.get("components") or [])
                        ):
                            count += 1
                return count

            if (
                rescued.get("status") == "AUTO_SELECTED",
                rescued_matches,
                rescued.get("best_score", 0),
                _evidence_count(rescued_cur),
            ) > (
                selected.get("status") == "AUTO_SELECTED",
                cur_matches,
                selected.get("best_score", 0),
                _evidence_count(cur_result),
            ):
                selected = rescued
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
    if not result.get("document_identity_conflict") and not result.get("cross_device_conflict"):
        from src.matching.label_fields import (
            match_serial_field_on_page,
            match_simple_field_on_page,
            match_type_field_on_page,
        )

        # Multi-angle / multi-page label albums often place brand logo on one photo
        # and warning/serial plates on another page of the same unit/batch.
        eq_item = equipments[idx]
        field_fn = {
            "manufacturer": (
                match_simple_field_on_page,
                {"unit": "merk_unit", "tabung": "merk_tabung"},
            ),
            "type": (
                match_type_field_on_page,
                {"unit": "tipe_unit", "tabung": "tipe_tabung"},
            ),
            "serial_number": (
                match_serial_field_on_page,
                {"unit": "nomor_seri_unit", "tabung": "nomor_seri_tabung"},
            ),
        }
        def _is_tube_page(p):
            ocr_blob = " ".join(str(r.get("text") or "") for r in (p.get("ocr") or [])).lower()
            if "disassemble unit" in ocr_blob or "precious metal" in ocr_blob:
                return False
            return any(k in ocr_blob for k in ("x-ray tube", "xray tube", "insert", "firmware", "cosp/n", "cospn"))

        def _ordered_pages_for(sec: str):
            if sec == "tabung":
                return sorted(pages, key=lambda p: (0 if _is_tube_page(p) else 1))
            return sorted(pages, key=lambda p: (1 if _is_tube_page(p) else 0))

        def _cand_rank(cand):
            ev_txt = cand.get("evidence") or next(
                (str(c.get("evidence")) for c in (cand.get("components") or []) if isinstance(c, dict) and c.get("evidence")),
                "",
            )
            is_labeled = 1 if ("model" in str(cand.get("reason") or "").lower() or "model" in str(ev_txt).lower()) else 0
            sc = cand.get("score")
            if sc is None:
                comps = [c.get("score") for c in (cand.get("components") or []) if isinstance(c, dict) and isinstance(c.get("score"), (int, float))]
                sc = min(comps) if comps else 0.0
            return (1 if cand.get("status") == "MATCH" else 0, is_labeled, float(sc), len(str(ev_txt)))

        for section in ("unit", "tabung"):
            sec_res = result.setdefault(section, {})
            ordered_pages = _ordered_pages_for(section)
            for key, (matcher, form_map) in field_fn.items():
                expected_str = (eq_item.get(form_map[section]) or "").strip()
                if not expected_str:
                    continue
                cur_entry = sec_res.get(key) or {}
                cur_status = cur_entry.get("status")
                cur_ev = cur_entry.get("evidence") or any(
                    isinstance(c, dict) and c.get("evidence")
                    for c in (cur_entry.get("components") or [])
                )
                if cur_status == "MATCH":
                    continue
                best_cand = None
                for p in ordered_pages:
                    cand = matcher(expected_str, p)
                    c_status = cand.get("status")
                    c_has_ev = bool(cand.get("evidence")) or any(
                        isinstance(c, dict) and c.get("evidence")
                        for c in (cand.get("components") or [])
                    )
                    if c_status == "MATCH" and c_has_ev:
                        best_cand = cand
                        break
                    if c_status == "REVIEW" and c_has_ev:
                        if best_cand is None or _cand_rank(cand) > _cand_rank(best_cand):
                            best_cand = cand
                if best_cand is not None:
                    if best_cand.get("status") == "MATCH" or not cur_ev or _cand_rank(best_cand) > _cand_rank(cur_entry):
                        sec_res[key] = best_cand

    fields = [
        ("unit", "manufacturer", "merk_unit", "Merek Unit"),
        ("unit", "type", "tipe_unit", "Tipe Unit"),
        ("unit", "serial_number", "nomor_seri_unit", "Nomor Seri Unit"),
        ("tabung", "manufacturer", "merk_tabung", "Merek Tabung"),
        ("tabung", "type", "tipe_tabung", "Tipe Tabung"),
        ("tabung", "serial_number", "nomor_seri_tabung", "No. Seri Insersi Tabung"),
    ]
    missing_fields = {
        formkey
        for section, key, formkey, _ in fields
        if (equipments[idx].get(formkey) or "").strip()
        and ((result.get(section) or {}).get(key) or {}).get("status") != "MATCH"
    }
    llm_hits = {}
    if missing_fields:
        from ..label_hybrid import extract_label_equipment_llm

        llm_hits, llm_warn = extract_label_equipment_llm(pages, missing_fields)
        if llm_warn:
            for d in documents:
                d["_uncacheable"] = True

    source_by_name = {d["filename"]: d["id"] for d in documents}
    source_by_id = {d["id"]: d["id"] for d in documents}
    rows = []
    pending_entries = []
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
        doc_id = (
            source_by_id.get(matched.get("source_id"))
            or source_by_name.get(matched.get("source_name"))
            or source_by_id.get(group.get("selected_source_id"))
            or source_by_name.get(group.get("selected_source_name"))
        )
        page = matched.get("page") or group.get("selected_page") or matched.get("selected_page")

        if status != "MATCH" and formkey in llm_hits:
            from rapidfuzz import fuzz as _fuzz

            hit = llm_hits[formkey]
            llm_obs = hit["value"]
            expected_val = (equipments[idx].get(formkey) or "").strip()
            sibling_key = f"tipe_{formkey.split('_', 1)[1]}" if formkey.startswith("merk_") else None
            sibling_val = (equipments[idx].get(sibling_key) or "").strip() if sibling_key else ""
            unit_brand_val = (equipments[idx].get("merk_unit") or "").strip() if formkey == "merk_tabung" else ""
            tube_brand_val = (equipments[idx].get("merk_tabung") or "").strip() if formkey == "merk_unit" else ""
            unit_type_val = (equipments[idx].get("tipe_unit") or "").strip() if formkey.endswith("_tabung") else ""
            unit_serial_val = (equipments[idx].get("nomor_seri_unit") or "").strip() if formkey == "nomor_seri_tabung" else ""
            expected_score = _fuzz.token_set_ratio(llm_obs.lower(), expected_val.lower()) if expected_val else 0
            unit_overlap_short = (
                formkey == "tipe_tabung"
                and unit_type_val
                and len(llm_obs) < 0.5 * len(expected_val)
                and _fuzz.token_set_ratio(llm_obs.lower(), unit_type_val.lower()) >= 85
            )
            swapped_model = unit_overlap_short or any(
                other
                and _fuzz.token_set_ratio(llm_obs.lower(), other.lower()) >= 70
                and expected_score < 55
                for other in (sibling_val, unit_brand_val, tube_brand_val, unit_type_val, unit_serial_val)
            )
            if not swapped_model:
                llm_view, llm_exact = _label_evidence_view(
                    equipments[idx].get(formkey), llm_obs, "MATCH", formkey
                )
                if llm_exact == 100.0:
                    evidence = llm_view
                    status = "MATCH"
                    doc_id = source_by_id.get(hit.get("source_id")) or doc_id
                    page = hit.get("page") or page
                    correction_note = "Terbaca melalui bantuan Qwen dari teks OCR label"
                elif not evidence or (
                    status != "MISMATCH"
                    and "baris label Model/Type" not in str(matched.get("reason") or "")
                    and expected_val
                    and _fuzz.token_sort_ratio(llm_obs.lower(), expected_val.lower())
                    > _fuzz.token_sort_ratio(evidence.lower(), expected_val.lower()) + 5
                ):
                    evidence = llm_obs
                    status = "REVIEW"
                    doc_id = source_by_id.get(hit.get("source_id")) or doc_id
                    page = hit.get("page") or page
                    correction_note = "Terbaca melalui bantuan Qwen dari teks OCR label; perlu verifikasi visual"
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
                    or doc_id
                )
                target_doc = next((d for d in documents if d["id"] == origin), None)
                proof = (
                    verify_image_serial(
                        str(storage.file_path(target_doc)),
                        wanted,
                        evidence,
                        page or 1,
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
        if status in ("MATCH", "REVIEW") and formkey in llm_hits and llm_hits[formkey].get("quote"):
            if correction_note.startswith("Terbaca melalui bantuan Qwen"):
                raw_evidence = llm_hits[formkey]["quote"]
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
        if status == "REVIEW":
            expected_raw = str(equipments[idx].get(formkey) or "").strip()
            if not raw_evidence or evidence == "-" or not expected_raw:
                score = None
            else:
                from rapidfuzz import fuzz as _fuzz_score

                if score is None or score >= 100.0:
                    exp_up = " ".join(expected_raw.upper().split())
                    obs_up = " ".join(str(evidence).upper().split())
                    char_score = max(
                        _fuzz_score.ratio(exp_up, obs_up),
                        _fuzz_score.token_sort_ratio(exp_up, obs_up),
                    )
                    score = round(min(char_score, 99.9), 1)
                if raw_evidence and not correction_note and not matched.get("reason"):
                    correction_note = "Kecocokan parsial dari label foto; perlu verifikasi visual"
        pending_entries.append(
            {
                "section": section,
                "field": "Alat %d: %s" % (idx + 1, display),
                "expected": equipments[idx].get(formkey),
                "evidence": evidence,
                "status": status,
                "score": score,
                "page": page,
                "note": correction_note or matched.get("reason") or "",
                "doc_id": doc_id,
                "raw_evidence": raw_evidence if isinstance(raw_evidence, str) else "",
            }
        )

    # Guard against cross-section leakage in multi-document uploads:
    # if separate label documents exist, do not keep a partial (REVIEW) match for
    # unit copied from a tube-only document, or for tabung copied from a unit-anchor document.
    doc_ocr_blobs: dict[str, str] = {}
    for p in pages:
        sid = source_by_id.get(p.get("source_id")) or source_by_name.get(p.get("source_name"))
        if sid:
            doc_ocr_blobs[sid] = (
                doc_ocr_blobs.get(sid, "")
                + " "
                + " ".join(str(r.get("text") or "") for r in (p.get("ocr") or []))
            ).lower()
    tube_only_docs = {
        sid
        for sid, blob in doc_ocr_blobs.items()
        if any(k in blob for k in ("x-ray tube", "xray tube", "insert", "firmware", "cosp/n", "cospn"))
        and not any(k in blob for k in ("disassemble unit", "precious metal", "generator"))
    }
    unit_anchor_docs = {
        item["doc_id"]
        for item in pending_entries
        if item["section"] == "unit"
        and item["field"].endswith(("Tipe Unit", "Nomor Seri Unit"))
        and item["doc_id"]
        and item["evidence"]
        and item["evidence"] != "-"
    } - tube_only_docs
    tube_anchor_docs = (
        {
            item["doc_id"]
            for item in pending_entries
            if item["section"] == "tabung"
            and item["field"].endswith(("Tipe Tabung", "No. Seri Insersi Tabung"))
            and item["doc_id"]
            and item["evidence"]
            and item["evidence"] != "-"
        }
        | tube_only_docs
    ) - unit_anchor_docs

    if len(documents) > 1:
        other_for_tube = any(d["id"] not in unit_anchor_docs for d in documents)
        if unit_anchor_docs and other_for_tube:
            for item in pending_entries:
                if (
                    item["section"] == "tabung"
                    and item["field"].endswith(("Tipe Tabung", "No. Seri Insersi Tabung"))
                    and item["status"] != "MATCH"
                    and item["doc_id"] in unit_anchor_docs
                ):
                    item["evidence"] = "-"
                    item["raw_evidence"] = ""
                    item["score"] = None
                    item["note"] = "Field tidak ditemukan pada label"
        other_for_unit = any(d["id"] not in tube_only_docs for d in documents)
        if tube_only_docs and other_for_unit:
            for item in pending_entries:
                if (
                    item["section"] == "unit"
                    and item["field"].endswith(("Tipe Unit", "Nomor Seri Unit"))
                    and item["status"] != "MATCH"
                    and item["doc_id"] in tube_only_docs
                ):
                    item["evidence"] = "-"
                    item["raw_evidence"] = ""
                    item["score"] = None
                    item["note"] = "Field tidak ditemukan pada label"

    # Symmetric proven-document & section-context fallback for missing ('-') fields:
    # prefer documents proven by that section AND not anchored by the opposite section.
    proven_section_source: dict[str, tuple[str, int | None]] = {}
    for sec in ("unit", "tabung"):
        opposite = unit_anchor_docs if sec == "tabung" else tube_anchor_docs
        sec_items = [
            item
            for item in pending_entries
            if item["section"] == sec
            and item["doc_id"]
            and item["evidence"]
            and item["evidence"] != "-"
        ]
        # Prefer non-opposite proven doc first, then any proven doc in section.
        sec_items.sort(key=lambda it: (1 if it["doc_id"] in opposite else 0))
        if sec_items:
            proven_section_source[sec] = (sec_items[0]["doc_id"], sec_items[0]["page"])
        if sec not in proven_section_source and documents:
            # General OCR context fallback when 0 fields in that section matched.
            doc_scores: dict[str, int] = {d["id"]: 0 for d in documents}
            for sid, blob in doc_ocr_blobs.items():
                if sid not in doc_scores:
                    continue
                if sec == "tabung":
                    if sid in tube_only_docs:
                        doc_scores[sid] += 3
                    if sid in unit_anchor_docs:
                        doc_scores[sid] -= 2
                else:
                    if sid in unit_anchor_docs or any(
                        k in blob for k in ("disassemble unit", "generator", "precious metal")
                    ):
                        doc_scores[sid] += 3
                    if sid in tube_only_docs:
                        doc_scores[sid] -= 2
            best_sid, best_ctx = max(doc_scores.items(), key=lambda kv: kv[1])
            if best_ctx > 0:
                proven_section_source[sec] = (best_sid, 1)
            elif len(documents) > 1:
                non_opposite = [d["id"] for d in documents if d["id"] not in opposite]
                if len(non_opposite) == 1:
                    proven_section_source[sec] = (non_opposite[0], 1)

    for item in pending_entries:
        sec = item["section"]
        if (not item["raw_evidence"] or item["evidence"] == "-") and sec in proven_section_source:
            item["doc_id"], item["page"] = proven_section_source[sec]
        rows.append(
            _row(
                item["field"],
                item["expected"],
                item["evidence"],
                item["status"],
                item["score"],
                item["page"],
                item["note"],
                item["doc_id"],
                item["raw_evidence"],
            )
        )
    return rows


def _label(doc, app, ref):
    """Compatibility only; worker orchestrator calls _label_group once per set."""
    return _label_group([doc], app, ref)
