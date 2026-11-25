from __future__ import annotations

from .. import storage


from .rows import _row, _text
from .equipment import _absent_value
from .constants import SUPP


def _supp(doc, app, ref):
    from src.extraction.supplementary_matching import analyze

    path = str(storage.file_path(doc))
    raw = analyze(path, SUPP[doc["category"]], ref)
    if doc["category"] in ("paparan", "kebocoran"):
        from ..exposure_hybrid import enrich_exposure_rows

        raw, llm_warn = enrich_exposure_rows(doc, app, path, raw)
        if llm_warn:
            doc["_uncacheable"] = True
    rows = []
    for x in raw.get("rows") or []:
        evidence = (x.get("evidence") or [{}])[0]
        page = x.get("page") or evidence.get("page")
        is_approval = "pengesahan" in _text(x.get("field")).casefold()
        field_name = _text(x.get("field"))
        status = x.get("status")
        score = x.get("score")
        reason = x.get("reason") or ""
        # A model suffix is material, never silently accept E7894X as E7894.
        # Partial multi-word model families (e.g. DXL 800 vs DXL 800 Niton) remain REVIEW + score.
        if "tipe" in field_name.lower() and (x.get("expected") and x.get("observed")):
            from ..exposure_hybrid import is_token_subset_model
            from src.matching.import_approval_matcher import compare_field

            kind = "tipe_tabung" if "tabung" in field_name.lower() else "tipe_unit"
            check = compare_field(kind, x["expected"], x["observed"])
            if check["status"] == "MISMATCH":
                if is_token_subset_model(x["expected"], x["observed"]):
                    status = "REVIEW"
                    score = check["score"]
                else:
                    status = "MISMATCH"
                    score = check["score"]
        if (
            "alamat fasilitas" in field_name.lower()
            and status == "REVIEW"
            and not _absent_value(x.get("expected"))
            and not _absent_value(x.get("observed"))
        ):
            from ..protection.matching import compare_address

            addr_status, addr_score, addr_note = compare_address(x["expected"], x["observed"])
            if addr_status == "MISMATCH":
                status = "MISMATCH"
                score = addr_score
                reason = addr_note
        # Paparan / kebocoran: only show fields that are actually evidenced in the document
        # (omit empty/dash Nama Fasilitas, Alamat Fasilitas, Alat N, and Pengesahan rows).
        if doc["category"] in ("paparan", "kebocoran") and _absent_value(x.get("observed")):
            continue
        display_field = x.get("field")
        expected = x.get("expected")
        detail = None
        if is_approval:
            display_field = "Lembar Pengesahan"
            expected = ""
            status = "INFO"
            score = None
            reason = (
                reason
                or "Halaman pengesahan ditemukan; tanda tangan tetap memerlukan verifikasi visual."
            )
            detail = {
                "type": "exposure",
                "group": "Pengesahan",
                "pages": [page] if isinstance(page, int) and page > 0 else [],
            }
        built = _row(
            display_field,
            expected,
            x.get("observed"),
            status,
            score,
            page,
            reason,
            doc["id"],
            x.get("quote") or evidence.get("quote"),
            detail,
        )
        if doc["category"] in ("paparan", "kebocoran") and _absent_value(built["observed"]):
            continue
        rows.append(built)
    if not rows:
        rows.append(
            _row(
                "Ringkasan Dokumen",
                "—",
                "Belum terbaca",
                "REVIEW",
                None,
                1,
                "Tidak ada informasi fasilitas, pesawat, atau pengesahan yang berhasil dibaca otomatis; periksa dokumen sumber.",
                doc["id"],
            )
        )
    return rows
