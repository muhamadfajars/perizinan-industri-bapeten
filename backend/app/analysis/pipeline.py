from __future__ import annotations

import time


from .. import storage


from ..reference_evidence import improve_rows as _improve_rows

from ..facility_validation import guard_rows as _guard_rows

from ..identity_consistency import finalize_identity as _finalize_identity

from ..evidence_cohesion import improve as improve_evidence_cohesion

from ..field_evidence import improve as improve_field_evidence

from .reference import _to_form
from .evidence import _identity_postprocess, _personnel_title, _postprocess_evidence
from .constants import NAMES


def analyze_application(aid, progress):
    """Run independent evidence extractors in parallel; preserve original decisions.

    A single process pool is reused across all simultaneous submissions, so
    workers never oversubscribe per-user. Section order remains upload order.
    """
    import concurrent.futures
    import hashlib
    import json
    from .. import performance

    started = time.perf_counter()
    docs = storage.documents(aid)
    forms = [d for d in docs if d["category"] == "formulir"]
    if len(forms) != 1:
        raise ValueError("Wajib tepat satu Formulir Permohonan PDF untuk acuan analisis")
    pool = performance.get_pool()
    form_doc = storage.document(forms[0]["id"], aid)
    application, form_seconds = pool.submit(performance.process_form, form_doc).result()
    if not isinstance(application, dict):
        raise ValueError("Parser formulir tidak mengembalikan data")
    if not (application.get("general") or {}).get("alamat_proyek") and not (
        application.get("general") or {}
    ).get("instansi"):
        raise ValueError("Identitas fasilitas di formulir tidak terbaca; periksa PDF acuan")
    form = _to_form(application)
    reference = {
        "nama_fasilitas": form["facility"],
        "instansi": (application.get("general") or {}).get("instansi"),
        "alamat_proyek": form["address"],
        "personnel": application.get("personnel") or [],
        "equipment": application.get("equipment") or [],
        "general": application.get("general") or {},
        "administration": application.get("administration") or {},
    }
    r_digest = hashlib.sha256(
        json.dumps(reference, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    source_digest = performance.code_digest()
    sections = []
    warnings = list(application.get("warnings") or [])
    errors = []
    supports = [storage.document(d["id"], aid) for d in docs if d["category"] != "formulir"]
    progress(5, f"Formulir selesai ({form_seconds:.1f}s), menyiapkan {len(supports)} dokumen")
    futures = {}
    label_futures = {}
    label_coordinator = None
    label_parallel_future = None
    label_pass_timings = []
    label_documents = [d for d in supports if d["category"] == "label"]
    label_index = next((i for i, d in enumerate(supports) if d["category"] == "label"), None)
    label_key = None
    label_cached = None
    if label_documents:
        label_key = performance.cache_key_label_group(label_documents, r_digest, source_digest)
        label_cached = performance.get_label_cached(label_documents, label_key)
    if label_documents and label_cached is None:
        from concurrent.futures import ThreadPoolExecutor
        from ..label_ocr_scheduler import run_label_group

        label_coordinator = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="bapeten-label-v058"
        )
        label_parallel_future = label_coordinator.submit(
            run_label_group,
            pool,
            label_documents,
            application.get("equipment") or [],
            source_digest,
        )
    for index, d in enumerate(supports):
        if d["category"] == "label":
            if label_cached is None and index == label_index:
                label_futures[label_parallel_future] = (index, d)
            continue
        key = performance.cache_key(d, r_digest, source_digest)
        fut = pool.submit(performance.process_support, d, application, reference, key)
        futures[fut] = (index, d, [d])
    completed = {}
    timings = []
    group_ocr = []
    group_seconds = 0.0
    group_failures = []
    if label_cached is not None:
        completed[label_index] = {
            "id": label_documents[0]["id"],
            "category": "label",
            "name": NAMES["label"] + (" · %d file" % len(label_documents)),
            "document_id": label_documents[0]["id"],
            "source_documents": [
                {"id": d["id"], "filename": d["filename"]} for d in label_documents
            ],
            "rows": label_cached["rows"],
            "info": "Matching gabungan semua label",
        }
        timings.append(
            {
                "category": "label",
                "filename": " + ".join(d["filename"] for d in label_documents),
                "seconds": label_cached["seconds"],
                "cache_hit": True,
            }
        )
    total_jobs = len(futures) + len(label_futures)
    label_started = time.perf_counter()
    label_finished = None
    for number, fut in enumerate(concurrent.futures.as_completed([*futures, *label_futures]), 1):
        if fut in label_futures:
            _, d = label_futures[fut]
            try:
                detail = fut.result()
                group_ocr.append((0, detail["pages"]))
                group_seconds += detail["seconds"]
                label_pass_timings = detail.get("pass_timings", [])
                label_finished = time.perf_counter()
            except Exception as exc:
                group_failures.append((d, f"{type(exc).__name__}: {str(exc)[:240]}"))
        else:
            index, d, group = futures[fut]
            try:
                detail = fut.result()
                rows = (
                    detail["rows"]
                    if d["category"] in ("proteksi", "manajemen")
                    else finalize_legacy_rows(detail["rows"], d)
                )
                timings.append(
                    {
                        "category": d["category"],
                        "filename": " + ".join(item["filename"] for item in group),
                        "seconds": detail["seconds"],
                        "cache_hit": detail["cached"],
                    }
                )
                if not rows:
                    errors.append(
                        {
                            "document_id": d["id"],
                            "category": d["category"],
                            "filename": d["filename"],
                            "error": "Tidak ada bukti ekstraksi yang dapat diverifikasi",
                        }
                    )
                else:
                    completed[index] = {
                        "id": d["id"],
                        "category": d["category"],
                        "name": _personnel_title(d)
                        if d["category"] == "personel"
                        else NAMES[d["category"]] + " · " + d["filename"],
                        "document_id": d["id"],
                        "source_documents": [{"id": d["id"], "filename": d["filename"]}],
                        "rows": rows,
                        "info": "Hasil pemeriksaan file ini",
                    }
            except Exception as exc:
                errors.append(
                    {
                        "document_id": d["id"],
                        "category": d["category"],
                        "filename": d["filename"],
                        "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                    }
                )
        progress(
            round(5 + 85 * number / max(1, total_jobs)),
            f"Pemrosesan {number}/{total_jobs} dokumen selesai",
        )
    for d, problem in group_failures:
        errors.append(
            {
                "document_id": d["id"],
                "category": "label",
                "filename": d["filename"],
                "error": problem,
            }
        )
    if label_documents and label_cached is None and not group_failures:
        try:
            import itertools

            # Deterministic source order, not completion order of parallel workers.
            pages = list(itertools.chain.from_iterable(p for _, p in sorted(group_ocr)))
            detail = performance.finalize_label_group(
                label_documents, application, reference, label_key, pages
            )
            rows = detail["rows"]
            if rows:
                completed[label_index] = {
                    "id": label_documents[0]["id"],
                    "category": "label",
                    "name": NAMES["label"] + (" · %d file" % len(label_documents)),
                    "document_id": label_documents[0]["id"],
                    "source_documents": [
                        {"id": d["id"], "filename": d["filename"]} for d in label_documents
                    ],
                    "rows": rows,
                    "info": "OCR berkualitas paralel; hasil label digabung per kelompok dokumen",
                }
                timings.append(
                    {
                        "category": "label",
                        "filename": " + ".join(d["filename"] for d in label_documents),
                        "seconds": round(
                            (label_finished or time.perf_counter()) - label_started, 2
                        ),
                        "cache_hit": False,
                        "pass_timings": label_pass_timings,
                    }
                )
            else:
                errors.append(
                    {
                        "document_id": label_documents[0]["id"],
                        "category": "label",
                        "filename": " + ".join(d["filename"] for d in label_documents),
                        "error": "Tidak ada hasil label yang dapat diverifikasi",
                    }
                )
        except Exception as exc:
            errors.append(
                {
                    "document_id": label_documents[0]["id"],
                    "category": "label",
                    "filename": " + ".join(d["filename"] for d in label_documents),
                    "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                }
            )
    if label_coordinator is not None:
        label_coordinator.shutdown(wait=True)
    sections = [completed[i] for i in sorted(completed)]
    duration = round(time.perf_counter() - started, 3)
    return {
        "application_id": aid,
        "result_version": "BAPETEN-v052-quality-parallel-label-docx-address",
        "source": "backend",
        "form_reference": form,
        "matching_sections": sections,
        "errors": errors,
        "warnings": warnings,
        "analyzed_documents": len(supports),
        "total_documents": len(docs),
        "finished_at": time.time(),
        "document_fingerprint": sorted((d["id"], d["sha256"]) for d in docs),
        "performance": {
            "wall_seconds": duration,
            "form_seconds": form_seconds,
            "documents": timings,
            "ocr_processes": performance.settings()[0],
            "ocr_cpu_threads": performance.settings()[1],
        },
    }


def finalize_legacy_rows(rows, doc):
    """Legacy heuristics must not rewrite grounded protection or display-only rows."""
    path = storage.file_path(doc)
    rows = _identity_postprocess(_postprocess_evidence(rows, doc), doc)
    rows = _improve_rows(rows, path)
    rows = _guard_rows(rows)
    rows = _finalize_identity(rows, path)
    rows = improve_evidence_cohesion(rows, path)
    return improve_field_evidence(
        rows, path, doc.get("category"), doc.get("subtype"), doc.get("filename")
    )
