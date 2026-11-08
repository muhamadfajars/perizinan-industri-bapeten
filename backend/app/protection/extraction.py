"""Layout extraction first, local LLM for unstructured passages, source grounding always."""

import re
import pymupdf
from .evidence import compact, toc
from . import llm


def norm(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def table_records(path, pages):
    records = {"personnel": [], "equipment": []}
    with pymupdf.open(path) as pdf:
        for page in pages:
            text = page["text"]
            if toc(text) or not re.search(
                r"SN\s*Unit|(?:Nama|Name)\s+(?:Jenis|Jabatan)|Daftar\s+Nama\s+Person", text, re.I
            ):
                continue
            pg = pdf[page["page"] - 1]
            for table in pg.find_tables().tables:
                cells = [
                    [compact(pg.get_textbox(cell)) if cell else "" for cell in row.cells]
                    for row in table.rows
                ]
                if not cells:
                    continue
                header = [norm(s) for s in cells[0]]
                if "snunit" in header and "sntabung" in header:
                    kind = "equipment"
                    aliases = {
                        "merkunit": "merk_unit",
                        "merekunit": "merk_unit",
                        "tipeunit": "tipe_unit",
                        "snunit": "nomor_seri_unit",
                        "merktabung": "merk_tabung",
                        "merektabung": "merk_tabung",
                        "tipetabung": "tipe_tabung",
                        "sntabung": "nomor_seri_tabung",
                        "alamat": "location",
                    }
                elif "nama" in header and any(x in header for x in ("jenispekerjaan", "jabatan")):
                    kind = "personnel"
                    aliases = {
                        "nama": "name",
                        "jenispekerjaan": "role",
                        "jabatan": "role",
                        "outletcabang": "location",
                        "outlet": "location",
                    }
                else:
                    continue
                for row in cells[1:]:
                    item = {
                        aliases[h]: value for h, value in zip(header, row) if h in aliases and value
                    }
                    if not item.get("name" if kind == "personnel" else "nomor_seri_unit"):
                        continue
                    item.update(
                        page=page["page"], quote=" | ".join(s for s in row if s), method="table"
                    )
                    records[kind].append(item)
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
                r"\b(?:jl|jalan|jln|outlet|cabang|sekayu|kawasan|desa|kelurahan)\b",
                fields[key],
                re.I,
            ):
                fields.pop(key)
        if fields:
            valid.append({**fields, "page": record["page"], "quote": quote, "method": "llm"})
    return valid


def native_identity(pages):
    records = []
    for page in pages[:3]:
        lines = [
            compact(s) for s in page.get("native_text", page["text"]).splitlines() if s.strip()
        ]
        for i, line in enumerate(lines):
            if re.match(r"^(?:PT|CV)\.?\s+[A-Z]", line) and len(line) < 100:
                records.append(
                    {"institution": line, "page": page["page"], "quote": line, "method": "text"}
                )
            if re.match(r"^(?:Jl\.?|Jalan|Jln\.?)\s", line, re.I):
                address = line
                for following in lines[i + 1 : i + 5]:
                    if re.search(r"\b\d{5}\b", address) or re.match(
                        r"No|Page|Tanggal|Date|BAB", following
                    ):
                        break
                    address += " " + following
                records.append(
                    {
                        "project_address": address,
                        "page": page["page"],
                        "quote": address,
                        "method": "text",
                    }
                )
    return records


def extract_records(path, pages):
    warnings = []
    records = table_records(path, pages)
    records["identity"] = native_identity(pages)
    selectors = {
        "identity": lambda p: p["page"] <= 2,
        "personnel": lambda p: bool(
            re.search(
                r"daftar\s+nama\s+person|data\s+person|nama\s+jenis\s+pekerjaan", p["text"], re.I
            )
        ),
        "equipment": lambda p: bool(
            re.search(r"tabel\s+x.ray\s+tube|SN\s+Unit|nomor\s+seri", p["text"], re.I)
        ),
    }
    for kind, select in selectors.items():
        if records[kind]:
            continue
        selected = [p for p in pages if not toc(p["text"]) and select(p)]
        if len(selected) > 6:
            warnings.append(
                f"Ekstraksi Qwen {kind} dibatasi 6 halaman kandidat; bagian lain perlu ditinjau."
            )
        for page in selected[:6]:
            # One page per request: bounded context, no silent truncation.
            text = page["text"]
            if len(text) > 12000:
                warnings.append(
                    f"Halaman {page['page']}: teks terlalu panjang untuk ekstraksi Qwen; perlu tinjauan."
                )
                continue
            try:
                proposed = llm.extract(kind, [{"page": page["page"], "text": text}])
                accepted = grounded(proposed, [page], kind)
                records[kind].extend(accepted)
                if len(accepted) != len(proposed):
                    warnings.append(
                        f"Halaman {page['page']}: sebagian keluaran Qwen tidak didukung kutipan dan diabaikan."
                    )
            except Exception as exc:
                warnings.append(
                    f"Ekstraksi Qwen {kind} belum selesai ({type(exc).__name__}); data yang belum terbaca perlu diperiksa."
                )
                break
    return records, warnings


def metadata(pages):
    number, date = [], []
    for page in pages[:4]:
        text = compact(
            page["text"]
            if page.get("method") == "ocr"
            else (page.get("native_text") or page["text"])
        )
        if toc(text):
            continue
        for match in re.finditer(
            r"\b(?:Nomor(?:\s+Dokumen)?|No\.?|Kode\s+Dokumen)\s*:\s*([A-Z0-9]+(?:\s*[/–—-]\s*[A-Z0-9]+)+)",
            text,
        ):
            value = re.split(r"\b(?:Revision|Revisi|Tanggal|PROGRAM|Departemen)\b", match.group(1))[
                0
            ].strip()
            number.append({"value": value, "page": page["page"], "quote": match.group(0)})
        pattern = r"(?:Date|Tanggal\s+(?:Pengesahan|Dibuat|Dokumen))\s*:?\s*(\d{1,2}(?:[/.-]\d{1,2}[/.-]|\s+[A-Za-z]+\s+)\d{4})"
        for match in re.finditer(pattern, text, re.I):
            date.append({"value": match.group(1), "page": page["page"], "quote": match.group(0)})
    return {"number": number, "date": date}
