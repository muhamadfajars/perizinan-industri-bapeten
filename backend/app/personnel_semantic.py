"""Semantic ownership checks for personnel documents, with literal source evidence."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .protection import llm
from .protection.evidence import compact
from .protection.identity import person_key, person_similarity
from .protection.service import make_row

INSTRUCTION = """Baca dokumen personel yang diberi nomor baris L1, L2, dst.
Identifikasi HANYA PEMILIK/PENERIMA sertifikat, pemegang izin bekerja (SIB), orang yang ditunjuk/diangkat, atau pekerja radiasi yang dipantau dosisnya.
JANGAN keluarkan penandatangan, direktur/pimpinan perusahaan di bagian 'Yang bertanda tangan di bawah ini' atau tanda tangan bawah, pejabat penerbit BAPETEN ('a.n. Kepala BAPETEN', 'Direktur Perizinan', atau nama ber-NIP), kepala lab, instruktur/penguji, atau 'Director' penandatangan di bagian bawah tanggal/kota penerbitan.
Pada SIB/Sertifikat BAPETEN dua kolom, baris jabatan penandatangan sering terselip di antara 'Nama / Name' dan nama pemilik tepat di bawahnya; pemilik adalah nama tepat di bawah 'Nama / Name', bukan pejabat ber-NIP di bagian bawah.
Isi per record:
- person: salin nama mentah pemilik saja (tanpa jabatan atau kalimat).
- role: profesi/keahlian/klasifikasi/jabatan pemilik yang tertulis di rentang bukti (kosongkan string jika tidak ada). Jangan ambil jabatan penandatangan atau daftar materi pelatihan.
- Pada dokumen izin, profesi/klasifikasi dapat ditulis sebagai satu baris tepat di bawah nomor izin tanpa label 'profesi'; ambil jika tata letaknya menghubungkannya dengan pemilik dan sertakan seluruh konteks itu dalam rentang bukti.
- expiry: salin teks mentah tanggal akhir masa berlaku sertifikat/izin milik pemilik (kosongkan string jika tidak ada, jika hanya tanggal terbit/lahir/ujian/pelatihan, jika hanya durasi seperti '5 tahun sejak ...', atau jika hanya periode pemantauan dosis TLD/zero check). Bila ada rentang tanggal berlaku, salin rentang lengkap.
- start_line dan end_line (inklusif): rentang nomor baris sumber yang HARUS menyertakan baris label konteks pemilik (mis. 'Nama / Name', 'Nama Pekerja Radiasi', 'Dengan ini menugaskan kepada', 'memberikan sertifikat kepada', 'herewith CERTIFY that', 'Dengan ini menyatakan bahwa', 'Awarded/Presented to', atau bila tanpa label, sertakan baris keterangan penerima seperti 'Telah mengikuti' / 'has participated') SAMPAI baris nama pemilik (serta baris role dan expiry bila diisi). Untuk tabel pemantauan dosis, mulailah start_line dari baris header kolom 'Nama Pekerja Radiasi' sampai baris nama pekerjanya. Nomor baris hanya penanda, bukan isi dokumen.
Jika ada beberapa pemilik berbeda pada halaman yang sama, keluarkan semua pemiliknya. Jika benar-benar tidak ada pemilik yang terbaca, kembalikan records kosong."""

VALIDITY = re.compile(r"berlaku|berakhir|valid\s*(?:until|through|to)|expir\w*|hingga|sampai", re.I)
HOLDER_ANCHOR = re.compile(
    r"(?<!atas\s)\bnama\b|\bname\b|kepada|certif(?:y|ies|ied)|menyatakan|menerangkan|"
    r"menunjuk|mengangkat|menugaskan|menetapkan|pemegang|penerima|pekerja|karyawan|"
    r"\bpeserta\b|\bholder\b|\brecipient\b|"
    r"(?:awarded|presented|granted|issued)\s+to\b|conferred\s+(?:upon|to)\b",
    re.I,
)
HOLDER_PREDICATE = re.compile(
    r"\btelah\s+(?:mengikuti|menyelesaikan|menjalani|lulus|menempuh)\b|"
    r"\bhas\s+(?:participated|completed|attended|passed|successfully\s+(?:completed|passed))\b|"
    r"\bhave\s+(?:participated|completed|attended|passed)\b|"
    r"\bdinyatakan\s+(?:lulus|kompeten|berhasil)\b|"
    r"\bdeclared\s+competent\b|"
    r"\blulus\s+(?:ujian|pelatihan|sertifikasi|kompetensi)\b|"
    r"\b(?:bertugas|ditugaskan|bekerja|diangkat|ditetapkan|menjabat)\s+sebagai\b",
    re.I,
)
HOLDER_CONTEXT_BARRIER = re.compile(
    r"\bat[ae]s\s+nama\b|\bon\s+behalf\s+of\b|\byang\s+bertanda\s+tangan\b|"
    r"\bditandatangani\b|\bmengetahui\b|\bdisahkan\b|"
    r"\b(?:direktur|director|pimpinan|ketua|penguji)\b|\bnip\.?\s*\d|\ba\.?\s*n\.?\s+kepala\b|"
    r"\b(?:januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember|"
    r"january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\b|"
    r"\b(?:dipindai\s+dengan|scanned\s+with)\b",
    re.I,
)
SIGNER_TITLE_NEAR_NAME = re.compile(
    r"\b(?:direktur|director|pimpinan|ketua|penguji|manajer|manager|"
    r"kepala\s+(?:bapeten|lab|balai|instalasi)|mengetahui|ditandatangani|nip\.?\s*\d)\b",
    re.I,
)
TABLE_HOLDER_HEADER = re.compile(
    r"\bnama\s+(?:pekerja(?:\s+radiasi)?|personel|petugas|pemakai|peserta|karyawan)\b",
    re.I,
)
TABLE_SECTION_BARRIER = re.compile(
    r"\bmetode\s+uji\b|\bcatatan\b|\blimit\s+deteksi\b|\bnilai\s+batas\s+dosis\b|"
    r"\bkepala\b|\bdirektur\b|\bdirector\b|\bpimpinan\b|\bketua\b|\bpenguji\b|"
    r"\byang\s+bertanda\s+tangan\b|\bditandatangani\b|\bmengetahui\b|\bdisahkan\b|"
    r"\bat[ae]s\s+nama\b|\bon\s+behalf\s+of\b|\bnip\.?\s*\d",
    re.I,
)
PERMIT_NUMBER_LABEL = re.compile(
    r"(?:no\.?|nomor)\s*(?:sib|sip|izin)|working\s+permit\s+number|licen[cs]e\s+number",
    re.I,
)
NAME_LABEL = re.compile(r"\bnama\s*(?:/\s*name)?\b|\bname\b", re.I)


def _clean_nonempty_lines(text):
    lines = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if line and re.search(r"[a-zA-Z0-9]", line):
            lines.append(line)
    return "\n".join(lines)


def _semantic_page_text(page):
    """Prefer clean native PDF text; avoid appending noisy OCR duplicates of the same page."""
    native = _clean_nonempty_lines(re.sub(r"[^\S\n]+", " ", page.get("native_text") or ""))
    ocr_lines = [compact(item.get("text")) for item in (page.get("ocr") or []) if item.get("text")]
    if len(native) < 80:
        from src.extraction.personnel_document import get_page_text

        return _clean_nonempty_lines(re.sub(r"[^\S\n]+", " ", get_page_text(page)))
    native_key = re.sub(r"[^a-z0-9]", "", native.casefold())
    native_tokens = set(re.findall(r"[a-z0-9]{3,}", native.casefold()))
    significant = 0
    matched = 0
    extra = []
    for line in ocr_lines:
        key = re.sub(r"[^a-z0-9]", "", line.casefold())
        if len(key) < 6:
            continue
        significant += 1
        tokens = set(re.findall(r"[a-z0-9]{3,}", line.casefold()))
        if key in native_key or (tokens and len(tokens & native_tokens) / len(tokens) >= 0.4):
            matched += 1
            continue
        extra.append(line)
    # Suppress scattered seal/watermark OCR typos when native text already covers the page.
    if len(native) >= 150 and (matched >= max(3, significant // 2) or len(extra) <= 5):
        return native
    return native if not extra else native + "\n" + "\n".join(extra)


def permit_role_evidence(pages, owner_name):
    """Read an unlabeled permit classification placed between permit number and holder name."""
    owner = compact(owner_name)
    for page in pages:
        lines = [compact(line) for line in page["text"].splitlines() if compact(line)]
        for name_index, line in enumerate(lines):
            if not NAME_LABEL.search(line):
                continue
            owner_index = next(
                (
                    i
                    for i in range(name_index, min(len(lines), name_index + 4))
                    if owner.casefold() in lines[i].casefold()
                ),
                None,
            )
            if owner_index is None:
                continue
            permit_index = next(
                (
                    i
                    for i in range(name_index - 1, max(-1, name_index - 9), -1)
                    if PERMIT_NUMBER_LABEL.search(lines[i])
                ),
                None,
            )
            if permit_index is None:
                continue
            between = lines[permit_index + 1 : name_index]
            candidates = [
                value
                for value in between
                if re.search(r"[A-Za-z]", value)
                and not re.fullmatch(r"[\d./\-–—\s]+", value)
                and not PERMIT_NUMBER_LABEL.search(value)
            ]
            if not candidates:
                continue
            value = compact(" ".join(candidates))
            if not (3 <= len(value) <= 240):
                continue
            return {
                "kind": "role",
                "page": page["page"],
                "person": owner,
                "value": value,
                "quote": compact(" ".join(lines[permit_index : owner_index + 1])),
                "method": "layout",
            }
    return None


def _has_holder_evidence(raw_quote, person):
    """Verify source quote links person as document holder/recipient, not signer."""
    text = compact(raw_quote)
    if HOLDER_ANCHOR.search(text):
        return True
    target = compact(person)
    if not target:
        return False
    match = re.search(re.escape(target), text, re.I)
    if not match:
        return False
    after = text[match.end() :]
    pred = HOLDER_PREDICATE.search(after)
    if not pred:
        return False
    return not SIGNER_TITLE_NEAR_NAME.search(after[: pred.start()])


def _extend_holder_lines(lines, start, end, person):
    """Include immediate intro/predicate lines when the model clipped right around the name."""
    base = "\n".join(lines[start - 1 : end])
    target = compact(person)
    if not target or target.casefold() not in compact(base).casefold():
        return base
    # Step up at most 3 contiguous non-empty lines only when no explicit label/intro
    # already sits inside start..end, stopping at any signer/date/predicate barrier.
    if not HOLDER_ANCHOR.search(compact(base)):
        best_start = start
        scanned = 0
        for idx in range(start - 2, -1, -1):
            line = compact(lines[idx])
            if not line:
                continue
            scanned += 1
            if scanned > 3:
                break
            if HOLDER_CONTEXT_BARRIER.search(line) or HOLDER_PREDICATE.search(line):
                break
            if HOLDER_ANCHOR.search(line):
                best_start = idx + 1
                continue
            if best_start < start:
                break
        if best_start < start:
            candidate = "\n".join(lines[best_start - 1 : end])
            if len(compact(candidate)) <= 2500:
                return candidate
    if _has_holder_evidence(base, person):
        return base
    # If unlabelled above, peek up to 2 contiguous lines below for a recipient predicate.
    scanned_after = 0
    for idx in range(end, len(lines)):
        line = compact(lines[idx])
        if not line:
            continue
        scanned_after += 1
        if scanned_after > 2:
            break
        if HOLDER_CONTEXT_BARRIER.search(line):
            break
        candidate = "\n".join(lines[start - 1 : idx + 1])
        if len(compact(candidate)) <= 2500 and _has_holder_evidence(candidate, person):
            return candidate
    if not SIGNER_TITLE_NEAR_NAME.search(compact(base)) and not TABLE_SECTION_BARRIER.search(
        compact(base)
    ):
        scanned_table = 0
        for idx in range(start - 2, -1, -1):
            line = compact(lines[idx])
            if not line:
                continue
            scanned_table += 1
            if scanned_table > 18:
                break
            if TABLE_SECTION_BARRIER.search(line):
                break
            if TABLE_HOLDER_HEADER.search(line):
                candidate = "\n".join(lines[idx:end])
                if len(compact(candidate)) <= 2500:
                    return candidate
                break
    return base


def windows(pages):
    """Split on whole lines and retain absolute line numbers for source validation."""
    batch, size = [], 0
    for page in pages:
        lines = page["text"].splitlines()
        start = 0
        while start < len(lines):
            end, chars = start, 0
            while end < len(lines) and (chars + len(lines[end]) + 1 <= 6500 or end == start):
                chars += len(lines[end]) + 1
                end += 1
            chunk = "\n".join(lines[start:end])
            if batch and (
                size + len(chunk) > 9000 or any(p["page"] == page["page"] for p in batch)
            ):
                yield batch
                batch, size = [], 0
            batch.append({"page": page["page"], "text": chunk, "start_line": start + 1})
            size += len(chunk)
            if end >= len(lines):
                break
            # Preserve a small whole-line overlap so ownership context is not split.
            start = max(start + 1, end - 8)
    if batch:
        yield batch


def recover(pages):
    properties = {
        "page": {"type": "integer"},
        "person": {"type": "string"},
        "role": {"type": "string"},
        "expiry": {"type": "string"},
        "start_line": {"type": "integer"},
        "end_line": {"type": "integer"},
    }
    schema = {
        "type": "object",
        "properties": {
            "records": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["records"],
        "additionalProperties": False,
    }
    evidence, warnings, candidate_warnings = [], [], []
    page_lookup = {p["page"]: p["text"].splitlines() for p in pages}
    batches = list(windows(pages))
    if len(batches) > 2:
        warnings.append("Konteks personel melebihi dua permintaan LLM; cakupan belum lengkap.")
    if not batches:
        return [], ["Teks belum terbaca; LLM tidak dapat memverifikasi pemilik dokumen."]
    for batch in batches[:2]:
        try:
            numbered = [
                {
                    "page": p["page"],
                    "text": "\n".join(
                        f"L{i}: {line}"
                        for i, line in enumerate(p["text"].splitlines(), p["start_line"])
                    ),
                }
                for p in batch
            ]
            records = llm.request_records(
                schema,
                "Pemilik dan informasi dokumen personel",
                numbered,
                INSTRUCTION,
                output_limit=450,
            )
        except Exception as exc:
            warnings.append(f"Pembacaan LLM personel belum selesai ({type(exc).__name__}).")
            break
        expanded = []
        for record in records:
            if not isinstance(record, dict):
                warnings.append("Record LLM personel tidak valid.")
                continue
            item = dict(record)
            item.setdefault("kind", "holder")
            if "value" not in item:
                item["value"] = item.get("person", "")
            if "start_line" in item or "end_line" in item:
                start, end = item.get("start_line"), item.get("end_line")
                lines = page_lookup.get(item.get("page"), [])
                item["quote"] = (
                    _extend_holder_lines(lines, start, end, item.get("person", ""))
                    if (type(start) is int and type(end) is int and 1 <= start <= end <= len(lines))
                    else ""
                )
            expanded.append(item)
            if item["kind"] == "holder":
                for field in ("role", "expiry"):
                    if isinstance(item.get(field), str) and item[field].strip():
                        expanded.append({**item, "kind": field, "value": item[field]})
        for record in expanded:
            kind, page = record.get("kind"), record.get("page")
            values = [record.get(key) for key in ("person", "value", "quote")]
            if not all(isinstance(v, str) and v.strip() for v in values):
                if kind == "holder":
                    candidate_warnings.append("Nilai LLM personel tidak lengkap.")
                continue
            person, value, quote = map(compact, values)
            sources = ["\n".join(page_lookup[page])] if type(page) is int and page in page_lookup else []
            valid = (
                kind in ("holder", "role", "expiry")
                and 8 <= len(quote) <= 2500
                and any(quote.casefold() in compact(s).casefold() for s in sources)
                and person.casefold() in quote.casefold()
                and value.casefold() in quote.casefold()
            )
            if kind == "holder":
                valid = (
                    valid
                    and person_key(person) == person_key(value)
                    and _has_holder_evidence(quote, person)
                )
            if kind == "expiry":
                labels = list(VALIDITY.finditer(quote))
                valid = valid and any(
                    value.casefold() in quote[label.start() : label.end() + 250].casefold()
                    for label in labels
                )
            if not valid:
                if kind == "holder":
                    candidate_warnings.append(
                        "Nama pada dokumen belum disertai keterangan pemilik atau penerima yang terverifikasi."
                    )
                continue
            evidence.append(
                {
                    "kind": kind,
                    "page": page,
                    "person": person,
                    "value": value,
                    "quote": quote,
                    "method": "llm",
                }
            )
    if not any(item["kind"] == "holder" for item in evidence):
        warnings.extend(candidate_warnings)
    return list(
        {(r["kind"], r["page"], r["person"], r["value"], r["quote"]): r for r in evidence}.values()
    ), list(dict.fromkeys(warnings))


def assigned_holder(pages):
    """Narrow fallback: labelled recipient following an explicit assignment statement.

    Never search the signer's block or use application names to fill missing text.
    """
    found = []
    for page in pages:
        pattern = re.compile(
            r"(?:dengan\s+ini\s+)?(?:menugaskan|menunjuk|mengangkat)\s+(?:kepada\s*)?:?\s*"
            r"\n\s*Nama\s*(?:/\s*Name)?\s*:?\s*\n?\s*:?\s*([^\n:]+)", re.I
        )
        for match in pattern.finditer(page['text']):
            name = compact(match[1])
            if not re.fullmatch(r"[^\W\d_][^\d:;|]{2,100}", name) or re.search(
                r"jabatan|direktur|tanggal|identitas|petugas|alamat", name, re.I
            ):
                continue
            found.append(dict(kind='holder', page=page['page'], person=name,
                              value=name, quote=compact(match.group()), method='layout'))
    return found


def enrich(parsed, rows, application, doc, *, today=None):
    """Rules provide candidates; LLM verifies semantic ownership before automatic matching.

    Existing rule matches have literal evidence, but no verified holder/signer
    relationship. They therefore require this fallback even when their score is 100.
    """
    from src.extraction.personnel_document import find_all_dates
    from .personnel_policy import PERMIT_TYPES

    if parsed.get("document_type") == "DOSE":
        rows = [r for r in rows if r["field"] != "Profesi / Keahlian"]

    pages = [
        {"page": p["page"], "text": _semantic_page_text(p)}
        for p in parsed.get("pages", [])
    ]
    pages = [p for p in pages if p["text"].strip()]
    records, warnings = recover(pages)
    if any(p.get('recipient_unreadable') for p in parsed.get('pages', [])):
        warnings.append('Nama penerima pada gambar belum terbaca setelah OCR ulang; periksa dokumen sumber.')
    if not any(r['kind'] == 'holder' for r in records):
        fallback = assigned_holder(pages)
        if fallback:
            records.extend(fallback)
            warnings.append('Nama penerima terbaca pada blok penugasan; verifikasi LLM belum tuntas.')
    holders = {person_key(r["person"]): r["person"] for r in records if r["kind"] == "holder"}
    # Multiple owners/documents require splitting; never attach a global role/expiry to one person.
    if len(holders) == 0:
        warnings.append(
            "Nama pemilik dokumen belum dapat dipastikan secara otomatis; silakan periksa dokumen sumber."
        )
    elif len(holders) > 1:
        warnings.append(
            "Terdeteksi lebih dari satu nama pemilik pada dokumen; silakan periksa atau pisahkan bila merupakan dokumen gabungan."
        )
    if warnings:
        doc["_uncacheable"] = True
    if len(holders) != 1 or warnings:
        linked_person = None
        if len(holders) == 1:
            candidate_name = next(iter(holders.values()))
            ranked = sorted(
                (
                    (person_similarity(candidate_name, p.get("nama") or p.get("name")), p)
                    for p in application.get("personnel", [])
                    if p.get("nama") or p.get("name")
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            if ranked and ranked[0][0] >= 0.88 and (
                len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.08
            ):
                linked_person = ranked[0][1]
        for row in rows:
            if row["field"] in ("Nama", "Profesi / Keahlian", "Masa Berlaku", "Periode Pemakaian"):
                if row["field"] == "Nama" or row["status"] == "MATCH" or (
                    row["field"] == "Masa Berlaku" and row.get("detail", {}).get("pages")
                ):
                    row["status"] = "REVIEW"
                if (
                    row["field"] == "Periode Pemakaian"
                    and row.get("detail", {}).get("pages")
                ):
                    row["note"] = (
                        "Periode pemakaian terbaca pada dokumen; silakan periksa keterkaitannya dengan pemilik dokumen."
                    )
                else:
                    row["note"] = " ".join(dict.fromkeys(warnings))
                row.setdefault("detail", {})["review_required"] = True
            if linked_person:
                linked_name = linked_person.get("nama") or linked_person.get("name")
                row.setdefault("detail", {}).update(
                    person_id=person_key(linked_name), person_name=linked_name
                )
                if row['field'] == 'Nama':
                    holder = next(r for r in records if r['kind'] == 'holder')
                    row.update(expected=linked_name, observed=holder['person'],
                               score=round(person_similarity(holder['person'], linked_name) * 100, 1),
                               page=holder['page'], quote=holder['quote'])
                    row['detail'].update(pages=[holder['page']], evidence=[holder])
            else:
                row.get("detail", {}).pop("person_id", None)
                row.get("detail", {}).pop("person_name", None)
        return rows

    owner_key, owner_name = next(iter(holders.items()))
    if not any(r["kind"] == "role" and person_key(r["person"]) == owner_key for r in records):
        layout_role = permit_role_evidence(pages, owner_name)
        if layout_role:
            records.append(layout_role)
    ranked_people = sorted(
        (
            (person_similarity(owner_name, p.get("nama") or p.get("name")), p)
            for p in application.get("personnel", [])
            if p.get("nama") or p.get("name")
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    # Accept minor OCR/title variation only when the best form candidate is strong and unique.
    best_score = ranked_people[0][0] if ranked_people else 0
    runner_up = ranked_people[1][0] if len(ranked_people) > 1 else 0
    people = (
        [ranked_people[0][1]]
        if best_score >= 0.88 and (len(ranked_people) == 1 or best_score - runner_up >= 0.08)
        else []
    )
    person = people[0] if len(people) == 1 else {}
    expected_name = person.get("nama") or person.get("name") or ""
    expected_role = next(
        (
            person[k]
            for k in ("keahlian", "keahlian_klasifikasi", "profesi", "jabatan")
            if person.get(k)
        ),
        "",
    )
    result = [r for r in rows if r["field"] not in ("Nama", "Profesi / Keahlian", "Masa Berlaku")]
    today = today or datetime.now(ZoneInfo("Asia/Jakarta")).date()
    dtype = parsed.get("document_type")
    for field, kind, expected in (
        ("Nama", "holder", expected_name),
        ("Profesi / Keahlian", "role", expected_role),
        ("Masa Berlaku", "expiry", ""),
    ):
        evidence = [
            r for r in records if r["kind"] == kind and person_key(r["person"]) == owner_key
        ]
        values = list(dict.fromkeys(r["value"] for r in evidence))
        if kind in ("role", "expiry") and dtype == "DOSE":
            continue
        if kind == "role" and not evidence and dtype not in PERMIT_TYPES:
            continue
        if kind == "expiry" and not evidence and dtype not in PERMIT_TYPES:
            continue
        row = make_row(
            doc["id"],
            field,
            expected,
            " / ".join(values),
            evidence,
            kind="role" if kind == "role" else "text",
            required=kind == "holder",
            conflict=len(values) > 1,
        )
        row["detail"].update(
            type="personnel",
            source_label=doc.get("subtype") or parsed.get("document_type"),
            source_filename=doc["filename"],
            method="llm",
            ownership_verified=True,
        )
        if kind == "holder" and not person:
            row.update(
                status="REVIEW",
                score=None,
                note="Nama pemilik terbaca, tetapi belum cocok unik dengan petugas formulir.",
            )
        elif kind == "holder" and person and len({person_key(v) for v in values}) == 1:
            row.update(
                status="MATCH",
                note="Nama pemilik sesuai setelah normalisasi gelar dan tanda baca; bukti sumber terverifikasi.",
            )
        if kind != "holder" and not evidence:
            row.update(
                status="REVIEW" if dtype in PERMIT_TYPES else "INFO",
                score=None,
                observed="Belum ditemukan dalam teks terbaca",
                note=(
                    "Informasi wajib pada dokumen izin belum memiliki bukti yang terhubung dengan pemilik."
                    if dtype in PERMIT_TYPES
                    else "Informasi kondisional belum memiliki bukti yang terhubung dengan pemilik."
                ),
            )
        if kind == "expiry" and evidence:
            dates = {d["date"] for value in values for d in find_all_dates(value)}
            duration = any(
                re.search(
                    r"\b\d+\s*(?:tahun|bulan|hari|years?|months?|days?)\b|\b(?:sejak|terhitung|from)\b",
                    e["quote"][label.start() : label.end() + 250],
                    re.I,
                )
                for e in evidence
                for label in VALIDITY.finditer(e["quote"])
            )
            row["score"] = None
            if len(dates) != 1 or len(values) > 1 or duration:
                row.update(
                    status="REVIEW",
                    note="Tanggal akhir belum tunggal atau berupa durasi/rentang; periksa sumber.",
                )
            else:
                end = next(iter(dates))
                row.update(
                    observed=end.strftime("%d/%m/%Y"),
                    status="REVIEW" if end < today else "INFO",
                    note=f"Tanggal akhir {'telah' if end < today else 'belum'} terlewati pada {today.isoformat()}.",
                )
        result.append(row)
    if person and next(r for r in result if r["field"] == "Nama")["status"] == "MATCH":
        for row in result:
            row["detail"].update(person_id=owner_key, person_name=expected_name)
    order = {"Nama": 0, "Profesi / Keahlian": 1, "Masa Berlaku": 2}
    return sorted(result, key=lambda r: order.get(r["field"], 3))
