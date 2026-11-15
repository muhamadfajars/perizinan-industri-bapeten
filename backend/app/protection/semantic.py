"""Bounded semantic fallback. A model answer is usable only with a literal source span.

Absence in selected passages is not proof of absence in the document. Callers retain
INFO rows and expose review_required separately from form matching statuses.
"""

import re
from . import llm
from .evidence import LAW, compact
from .context import ranked_pages, adjacent_window

TASKS = {
    "laws": (
        ["legal_section"],
        r"referensi|rujukan|regulasi|peraturan|landasan|dasar\s+hukum|acuan\s+hukum",
        "Temukan bagian yang menyatakan daftar dasar hukum/referensi regulasi dokumen, "
        "termasuk judul alternatif seperti Acuan Regulasi. Salin rentang bagian itu ke quote. "
        "Jangan ambil penyebutan peraturan insidental dalam uraian atau daftar isi. "
        "category legal_section; satu record per rentang, maksimal 4500 karakter. "
        "Jangan sertakan subbab berikutnya. Jangan tambahkan peraturan dari pengetahuan sendiri.",
    ),
    "culture": (
        ["safety", "security"],
        r"budaya|keselamatan|keamanan|komitmen|pelaporan|akses|safety|security",
        "Cari penjelasan substantif budaya keselamatan radiasi (safety) dan budaya keamanan "
        "sumber radiasi (security). Keduanya berbeda: safety menyangkut sikap, komitmen, "
        "tanggung jawab, pembelajaran atau pelaporan keselamatan; security menyangkut "
        "kesadaran, tanggung jawab, kewaspadaan, akses atau pelaporan ancaman keamanan sumber. "
        "Judul, daftar isi, definisi singkat, daftar peraturan, perintah umum 'wajib menerapkan', "
        "atau budaya K3 umum saja tidak cukup. Harus ada uraian tindakan/perilaku organisasi. "
        "Tidak harus memakai judul 'Budaya'. Satu record per topik yang benar-benar dijelaskan, "
        "quote utuh maksimal 1800 karakter. Jangan simpulkan keamanan dari keselamatan saja.",
    ),
    "dose": (
        ["dose"],
        r"pembatas|kendala\s+dosis|dose\s+constraint|target.*?dosis",
        "Pilih pernyataan pembatas dosis yang diterapkan untuk operasi instansi saat ini. "
        "Bukan Nilai Batas Dosis umum, dosis terukur, target konstruksi atau rencana masa depan. "
        "Harus jelas angka, satuan dan kaitannya dengan pembatas dosis operasional. "
        "Jika tahap aktif tidak dapat ditentukan, records kosong. Jika ada dua pernyataan aktif "
        "yang bertentangan, keluarkan keduanya; jangan menyelesaikan konflik sendiri. "
        "category dose; quote kalimat utuh maksimal 1800 karakter. Jangan menghitung angka baru.",
    ),
}


def recover(task, pages):
    from .evidence import law_key, REQUIRED_LAWS

    categories, pattern, instruction = TASKS[task]
    candidates = ranked_pages(task, pages, pattern)
    warnings, evidence = [], []
    record = {
        "type": "object",
        "properties": {
            "page": {"type": "integer"},
            "category": {"type": "string", "enum": categories},
            "quote": {"type": "string"},
        },
        "required": ["page", "category", "quote"],
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "properties": {"records": {"type": "array", "items": record}},
        "required": ["records"],
        "additionalProperties": False,
    }

    def task_satisfied():
        if task == "culture":
            return set(categories) <= {e["category"] for e in evidence}
        if task == "laws":
            found_laws = {law_key(*m.groups()) for e in evidence for m in LAW.finditer(e["quote"])}
            return set(REQUIRED_LAWS) <= found_laws
        return False

    covered = set()
    calls = 0
    for page in candidates:
        if page["page"] in covered:
            continue
        if calls >= 3:
            break
        if len(page["text"]) > 12000:
            warnings.append(
                f"Halaman {page['page']}: konteks terlalu panjang; perlu pemeriksaan sumber."
            )
            continue
        try:
            window = adjacent_window(page, pages)
            calls += 1
            proposed = llm.request_records(
                schema,
                f"Analisis bagian {task}",
                window,
                instruction,
            )
            covered.update(p["page"] for p in window)
        except Exception as exc:
            warnings.append(f"Pembacaan semantik {task} belum selesai ({type(exc).__name__}).")
            break
        for item in proposed:
            if not isinstance(item, dict):
                warnings.append("Keluaran semantik tidak valid; diabaikan.")
                continue
            quote = compact(item.get("quote"))
            source = next((p for p in window if p["page"] == item.get("page")), None)
            valid = (
                type(item.get("page")) is int
                and source is not None
                and item.get("category") in categories
                and 30 <= len(quote) <= 4500
                and quote.casefold() in compact(source["text"]).casefold()
            )
            if task == "laws":
                valid = valid and bool(LAW.search(quote))
            elif task == "culture":
                valid = valid and len(quote.split()) >= 20
            else:
                valid = valid and bool(
                    re.search(r"\d[\d.,]*\s*(?:mSv|µSv|μSv|uSv|Sv)\b", quote, re.I)
                )
                valid = valid and bool(re.search(TASKS["dose"][1], quote, re.I))
            if not valid:
                warnings.append(
                    f"Halaman {page['page']}: hasil semantik tanpa bukti yang valid diabaikan."
                )
                continue
            evidence.append(
                {
                    "page": item["page"],
                    "quote": quote,
                    "category": item["category"],
                    "method": "llm",
                }
            )
        if task_satisfied():
            break
    if any(p["page"] not in covered for p in candidates) and not task_satisfied():
        warnings.append(
            f"Pembacaan semantik {task} dibatasi 3 halaman kandidat; cakupan belum lengkap."
        )
    unique = {(e["page"], e["category"], e["quote"]): e for e in evidence}
    return list(unique.values()), warnings


def culture_fallback(pages, topics):
    if all(t["found"] for t in topics):
        return topics, []
    evidence, warnings = recover("culture", pages)
    result = []
    for topic, category in zip(topics, ("safety", "security")):
        found = topic["evidence"] or [e for e in evidence if e["category"] == category]
        result.append(
            {**topic, "found": bool(found), "evidence": found, "review_required": not bool(found)}
        )
    if not all(t["found"] for t in result):
        warnings.append(
            "Penjelasan budaya belum terkonfirmasi; hasil ini tidak membuktikan uraian tidak ada."
        )
    return result, warnings


def protection_fallback(pages):
    from .evidence import legal_section, law_key, REQUIRED_LAWS
    from .dose import dose_statements

    result, warnings = {}, []
    sections = legal_section(pages)
    # Exact reference identity triggers retrieval, never a compliance decision.
    text = " ".join(p["text"] for p in sections)
    complete = set(REQUIRED_LAWS) <= {law_key(*m.groups()) for m in LAW.finditer(text)}
    if not complete:
        evidence, notes = recover("laws", pages)
        result["legal_sections"] = sections + [
            {"page": e["page"], "text": e["quote"], "method": "llm"} for e in evidence
        ]
        result["laws_review"] = not bool(sections or evidence) or bool(notes)
        warnings.extend(notes)
        if result["laws_review"]:
            warnings.append(
                "Bagian referensi belum terkonfirmasi lengkap; periksa sumber sebelum menyimpulkan kelengkapan peraturan."
            )
    doses = dose_statements(pages)
    active = [
        e
        for e in doses
        if re.search(r"saat\s+ini|saat\s+sekarang|saat\s+beroperasi", e["quote"], re.I)
    ]
    if len({e["quote"] for e in active}) != 1:
        evidence, notes = recover("dose", pages)
        for item in evidence:
            statements = dose_statements([{"page": item["page"], "text": item["quote"]}])
            if statements:
                item["context_quote"] = item["quote"]
                item["quote"] = statements[0]["quote"]
        result["dose"] = evidence or active or doses[:1]
        if len({e["quote"] for e in active}) > 1:
            result["dose"] = list(
                {(e["page"], e["quote"]): e for e in [*result["dose"], *active]}.values()
            )
        # Multiple candidates cannot be resolved by arbitrarily choosing the first.
        result["dose_review"] = (
            len({e["quote"] for e in evidence}) != 1
            or len({e["quote"] for e in active}) > 1
            or bool(notes)
        )
        warnings.extend(notes)
        if result["dose_review"]:
            warnings.append(
                "Pembatas dosis operasional belum dapat dipastikan; diperlukan pemeriksaan sumber."
            )
    return result, warnings
