"""Layout extraction first, local LLM for unstructured passages, source grounding always."""

import re
import unicodedata
import pymupdf
from .evidence import compact, toc
from . import llm
from .identity import (
    ADDRESS,
    INSTITUTION,
    PROJECT_LABEL,
    OFFICE_LABEL,
    office_address,
    person_similarity,
    ranked_identity_pages,
)
from .context import adjacent_window


def norm(text):
    return re.sub(
        r"[^a-z0-9]",
        "",
        unicodedata.normalize("NFKC", str(text or "")).lower(),
    )


EQUIPMENT_ALIASES = {
    "merkunit": "merk_unit",
    "merekunit": "merk_unit",
    "tipeunit": "tipe_unit",
    "modelunit": "tipe_unit",
    "snunit": "nomor_seri_unit",
    "nomorseriunit": "nomor_seri_unit",
    "noseriunit": "nomor_seri_unit",
    "serialunit": "nomor_seri_unit",
    "serialnumberunit": "nomor_seri_unit",
    "merktabung": "merk_tabung",
    "merektabung": "merk_tabung",
    "tipetabung": "tipe_tabung",
    "modeltabung": "tipe_tabung",
    "sntabung": "nomor_seri_tabung",
    "nomorseritabung": "nomor_seri_tabung",
    "noseritabung": "nomor_seri_tabung",
    "noseriinsersitabung": "nomor_seri_tabung",
    "nomorseriinsersitabung": "nomor_seri_tabung",
    "serialtabung": "nomor_seri_tabung",
    "serialnumbertabung": "nomor_seri_tabung",
    "alamat": "location",
    "alamatproyek": "location",
    "lokasi": "location",
    "lokasikerja": "location",
}

PERSONNEL_ALIASES = {
    "nama": "name",
    "namapetugas": "name",
    "namapekerja": "name",
    "namalengkap": "name",
    "jenispekerjaan": "role",
    "jabatan": "role",
    "profesi": "role",
    "keahlian": "role",
    "klasifikasi": "role",
    "profesikeahlian": "role",
    "outletcabang": "location",
    "outlet": "location",
    "cabang": "location",
    "lokasi": "location",
    "lokasikerja": "location",
    "alamat": "location",
}


def table_records(path, pages):
    records = {"personnel": [], "equipment": []}
    last_table = None
    with pymupdf.open(path) as pdf:
        for page in pages:
            text = page["text"]
            if toc(text):
                last_table = None
                continue
            can_continue = last_table and page["page"] == last_table["page"] + 1
            if not can_continue and not re.search(
                r"SN\s*Unit|No(?:mor)?\.?\s*Seri\s*(?:Unit|Tabung)|Serial\s*(?:No|Number)|(?:Nama|Name)\s+(?:Jenis|Jabatan|Profesi|Keahlian)|Daftar\s+(?:Nama\s+)?Person",
                text,
                re.I,
            ):
                last_table = None
                continue
            pg = pdf[page["page"] - 1]
            page_last = None
            for table in pg.find_tables().tables:
                cells = [
                    [compact(pg.get_textbox(cell)) if cell else "" for cell in row.cells]
                    for row in table.rows
                ]
                if not cells:
                    continue
                header = [norm(s) for s in cells[0]]
                has_unit_sn = any(
                    h
                    in (
                        "snunit",
                        "nomorseriunit",
                        "noseriunit",
                        "serialunit",
                        "serialnumberunit",
                    )
                    for h in header
                )
                has_tube_sn = any(
                    h
                    in (
                        "sntabung",
                        "nomorseritabung",
                        "noseritabung",
                        "noseriinsersitabung",
                        "nomorseriinsersitabung",
                        "serialtabung",
                        "serialnumbertabung",
                    )
                    for h in header
                )
                has_name = any(
                    h in ("nama", "namapetugas", "namapekerja", "namalengkap") for h in header
                )
                has_role = any(
                    h
                    in (
                        "jenispekerjaan",
                        "jabatan",
                        "profesi",
                        "keahlian",
                        "klasifikasi",
                        "profesikeahlian",
                    )
                    for h in header
                )
                if has_unit_sn or has_tube_sn:
                    kind, aliases, data_rows = "equipment", EQUIPMENT_ALIASES, cells[1:]
                elif has_name and has_role:
                    kind, aliases, data_rows = "personnel", PERSONNEL_ALIASES, cells[1:]
                elif (
                    last_table
                    and page["page"] == last_table["page"] + 1
                    and len(header) == len(last_table["header"])
                    and not any(h in ("uraian", "kegiatan", "materi", "parameter") for h in header)
                ):
                    kind = last_table["kind"]
                    aliases = last_table["aliases"]
                    header = last_table["header"]
                    data_rows = cells
                else:
                    continue
                page_last = {
                    "kind": kind,
                    "aliases": aliases,
                    "header": header,
                    "page": page["page"],
                }
                for row in data_rows:
                    item = {
                        aliases[h]: value for h, value in zip(header, row) if h in aliases and value
                    }
                    if kind == "personnel" and not item.get("name"):
                        continue
                    if kind == "equipment" and not (
                        item.get("nomor_seri_unit") or item.get("nomor_seri_tabung")
                    ):
                        continue
                    item.update(
                        page=page["page"], quote=" | ".join(s for s in row if s), method="table"
                    )
                    records[kind].append(item)
            last_table = page_last
    return records


def grounded(records, pages, kind):
    sources = {p["page"]: p for p in pages}
    valid = []
    for record in records:
        if not isinstance(record, dict) or type(record.get("page")) is not int:
            continue
        source = sources.get(record["page"])
        if not source:
            continue
        quote = compact(record.get("quote"))
        if len(norm(quote)) < 8 or norm(quote) not in norm(source["text"]):
            continue
        fields = {
            key: compact(record[key])
            for key in llm.FIELDS[kind]
            if isinstance(record.get(key), str)
            and norm(record[key])
            and norm(record[key]) in norm(quote)
        }
        for key in ("institution_address", "project_address", "location"):
            if key in fields and not re.search(
                ADDRESS,
                fields[key],
                re.I,
            ):
                fields.pop(key)
        for key in ("project_address", "location"):
            if key in fields and (
                re.search(OFFICE_LABEL, record.get("quote", ""), re.I)
                or office_address(fields[key], source["text"])
            ):
                fields.pop(key)
        anchor = kind == "identity" or bool(
            fields.get("name")
            if kind == "personnel"
            else fields.get("nomor_seri_unit") or fields.get("nomor_seri_tabung")
        )
        if fields and anchor:
            valid.append({**fields, "page": record["page"], "quote": quote, "method": "llm"})
    return valid


def native_identity(pages):
    records = []
    for page in pages:
        if toc(page["text"]):
            continue
        source = (
            page["text"]
            if page.get("method") == "ocr"
            else (page.get("native_text") or page["text"])
        )
        lines = [compact(s) for s in source.splitlines() if s.strip()]
        for i, line in enumerate(lines):
            institution = re.sub(
                r"^(?:Nama\s+)?(?:Instansi|Perusahaan)\s*:\s*", "", line, flags=re.I
            )
            identity_context = page["page"] <= 3 or bool(
                re.search(
                    r"identitas|profil|nama\s+(?:instansi|perusahaan)|alamat\s*:", source, re.I
                )
            )
            prose = re.search(
                r"\b(?:merupakan|adalah|saat|telah|akan|memiliki|melakukan|menggunakan|menetapkan|bertanggung|menerapkan)\b",
                institution,
                re.I,
            )
            if (
                identity_context
                and not prose
                and re.match(r"^" + INSTITUTION + r"\.?\s+\S", institution, re.I)
                and len(institution) < 150
            ):
                records.append(
                    {
                        "institution": institution,
                        "page": page["page"],
                        "quote": line,
                        "method": page.get("method", "text"),
                    }
                )
            project = re.search(PROJECT_LABEL + r"\s*:?\s*(.+)$", line, re.I)
            address = (
                project.group(1)
                if project
                else re.sub(
                    r"^(?:Alamat(?:\s+(?:Proyek|Lokasi\s+Pemanfaatan))?|Lokasi\s+(?:Proyek|Pemanfaatan))\s*:\s*",
                    "",
                    line,
                    flags=re.I,
                )
            )
            if re.match(ADDRESS, address, re.I):
                # Explicit office addresses must not become project addresses.
                previous = lines[i - 1] if i else ""
                if re.search(OFFICE_LABEL, line + "\n" + previous, re.I) and not project:
                    continue
                for following in lines[i + 1 : i + 5]:
                    if (
                        re.search(PROJECT_LABEL + "|" + OFFICE_LABEL, following, re.I)
                        or re.search(r"\b\d{5}\b", address)
                        or re.match(
                            r"No|Page|Tanggal|Date|BAB|(?:Nama|Nomor|Telepon|Email|Alamat|Jabatan)\b|\d+\.\d+\s",
                            following,
                            re.I,
                        )
                    ):
                        break
                    address += " " + following
                if office_address(address, source):
                    continue
                records.append(
                    {
                        "project_address": address,
                        "page": page["page"],
                        "quote": address,
                        "method": page.get("method", "text"),
                    }
                )
    return records


def extract_records(path, pages, application=None):
    warnings = []
    records = table_records(path, pages)
    records["identity"] = native_identity(pages)
    records["identity"].extend(
        {
            "project_address": r["location"],
            "page": r["page"],
            "quote": r["quote"],
            "method": r["method"],
        }
        for r in records["equipment"]
        if r.get("location")
    )
    selectors = {
        "personnel": lambda p: bool(
            re.search(
                r"daftar\s+nama\s+person|data\s+person|nama\s+jenis\s+pekerjaan|petugas|operator|personel|personil",
                p["text"],
                re.I,
            )
        ),
        "equipment": lambda p: bool(
            re.search(
                r"tabel\s+x.ray\s+tube|SN\s+Unit|nomor\s+seri|serial\s+(?:number|no)|"
                r"data\s+pesawat|daftar\s+pesawat|pesawat\s+sinar\s*[- ]?x|spesifikasi\s+pesawat",
                p["text"],
                re.I,
            )
        ),
    }
    for kind in ("identity", "personnel", "equipment"):
        required = [key for key in llm.FIELDS[kind] if key != "location"]

        def complete():
            if kind == "identity":
                return all(any(r.get(key) for r in records[kind]) for key in required)
            # Form values only trigger retrieval; they are never sent as document facts to Qwen.
            for expected in (application or {}).get(kind, []):
                if kind == "personnel":
                    linked = [
                        r
                        for r in records[kind]
                        if r.get("name")
                        and person_similarity(expected.get("nama"), r["name"]) >= 0.72
                    ]
                else:
                    linked = [
                        r
                        for r in records[kind]
                        if any(
                            expected.get(k) and norm(expected[k]) == norm(r.get(k))
                            for k in ("nomor_seri_unit", "nomor_seri_tabung")
                        )
                    ]
                if not linked or any(not any(r.get(key) for r in linked) for key in required):
                    return False
            # If the form names records, only those records determine whether another
            # costly LLM pass is needed. Unrelated branch rows may be incomplete.
            if (application or {}).get(kind):
                return True
            return bool(records[kind]) and all(
                all(r.get(key) for key in required) for r in records[kind]
            )

        if complete():
            continue
        if kind == "identity":
            missing_fields = [key for key in required if not any(r.get(key) for r in records[kind])]
            selected = ranked_identity_pages(pages, missing_fields, toc_fn=toc)
            if not selected:
                selected = [p for p in pages if not toc(p["text"]) and p["text"].strip()][:1]
            max_calls = 2
            window_chars = 4500
        else:
            select = selectors[kind]
            selected = [p for p in pages if not toc(p["text"]) and select(p)]
            incomplete_pages = {
                r["page"] for r in records[kind] if any(not r.get(k) for k in required)
            }
            selected.sort(key=lambda p: p["page"] not in incomplete_pages)
            max_calls = 3
            window_chars = 12000
        covered = set()
        calls = 0
        for page in selected:
            if page["page"] in covered:
                continue
            if calls >= max_calls:
                break
            # Bounded source window with independent page evidence; no silent truncation.
            text = page["text"]
            if len(text) > 12000:
                warnings.append(
                    f"Halaman {page['page']}: teks terlalu panjang untuk ekstraksi Qwen; perlu tinjauan."
                )
                continue
            try:
                window = adjacent_window(page, pages, max_chars=window_chars)
                calls += 1
                proposed = llm.extract(kind, window)
                covered.update(p["page"] for p in window)
                accepted = grounded(proposed, window, kind)
                records[kind].extend(accepted)
                if len(accepted) != len(proposed):
                    warnings.append(
                        f"Halaman {page['page']}: sebagian keluaran Qwen tidak didukung kutipan dan diabaikan."
                    )
                if complete():
                    break
            except Exception as exc:
                warnings.append(
                    f"Ekstraksi Qwen {kind} belum selesai ({type(exc).__name__}); data yang belum terbaca perlu diperiksa."
                )
                break
        if any(p["page"] not in covered for p in selected) and not complete():
            warnings.append(
                f"Ekstraksi Qwen {kind} dibatasi {max_calls} halaman kandidat; bagian lain perlu ditinjau."
            )
    return records, warnings


def _metadata_date_key(value):
    months = {
        month: str(index)
        for index, month in enumerate(
            "januari februari maret april mei juni juli agustus september oktober november desember".split(),
            1,
        )
    }
    value = compact(value).lower()
    for month, index in months.items():
        value = re.sub(rf"\b{month}\b", index, value)
    parts = re.findall(r"\d+", value)
    return "-".join(parts[::-1]) if len(parts) == 3 else norm(value)


def _select_metadata(candidates, expected, key):
    if not candidates:
        return []
    for candidate in candidates:
        candidate["identity"] = (
            _metadata_date_key(candidate["value"]) if key == "date" else norm(candidate["value"])
        )
        candidate["score"] = candidate["label_score"]
    best = max(candidate["score"] for candidate in candidates)
    selected = [candidate for candidate in candidates if candidate["score"] == best]
    unique = set()
    return [
        item
        for item in selected
        if not (item["identity"] in unique or unique.add(item["identity"]))
    ]


def metadata(pages, *, expected_number="", expected_date=""):
    number, date = [], []
    scan_pages = []
    seen_pages = set()
    for page in pages:
        if page["page"] not in seen_pages:
            seen_pages.add(page["page"])
            scan_pages.append(page)
    for page in scan_pages:
        text = compact(
            page["text"]
            if page.get("method") == "ocr"
            else (page.get("native_text") or page["text"])
        )
        if toc(text):
            continue
        for match in re.finditer(
            r"\b(?:(?P<label_doc>(?:Nomor|No\.?|Kode)\s+Dokumen)\b\s*(?::|\||–|-)?|"
            r"(?P<label_short>Nomor|No)\b\.?\s*(?::|\||–|-))\s*"
            r"(?P<value>[A-Za-z0-9]+(?:\s*[/–—-]\s*[A-Za-z0-9]+|\.[A-Za-z0-9]+)+)",
            text,
            re.I,
        ):
            value = re.split(
                r"\b(?:Revision|Revisi|Tanggal|Date|Page|Halaman|PROGRAM|DOKUMEN|SISTEM|Departemen)\b",
                match.group("value"),
                flags=re.I,
            )[0].strip(" -–—/:.")
            if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
                continue
            number.append(
                {
                    "value": value,
                    "page": page["page"],
                    "quote": match.group(0),
                    "label_score": 100 if match.group("label_doc") else 70,
                }
            )
        pattern = (
            r"(?P<label>Date|Tanggal\s+(?:Pengesahan|Dibuat|Dokumen|Terbit|Efektif|Berlaku))\s*"
            r"(?::|\||–|-)?\s*(?P<value>\d{1,2}(?:[/.-]\d{1,2}[/.-]|\s+[A-Za-z]+\s+)\d{4})"
        )
        for match in re.finditer(pattern, text, re.I):
            label = match.group("label")
            date.append(
                {
                    "value": match.group("value"),
                    "page": page["page"],
                    "quote": match.group(0),
                    "label_score": 100
                    if re.search(r"dokumen|terbit|efektif|berlaku", label, re.I)
                    else 70,
                }
            )
    return {
        "number": _select_metadata(number, expected_number, "number"),
        "date": _select_metadata(date, expected_date, "date"),
    }
