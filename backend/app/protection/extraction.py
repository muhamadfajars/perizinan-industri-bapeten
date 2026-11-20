"""Layout extraction first, local LLM for unstructured passages, source grounding always."""

from collections import Counter
from difflib import SequenceMatcher
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


def _serial_core(value: str) -> str:
    text = re.sub(
        r"^(?:serial\s*(?:number|no\.?)|no(?:mor)?\.?\s*seri|s/?n|no\.?)\s*[:.]?\s*",
        "",
        compact(value),
        flags=re.I,
    )
    cleaned = norm(text)
    cleaned = re.sub(r"^sn(?=\d{4,})", "", cleaned)
    return cleaned.lstrip("0") or cleaned


EQUIPMENT_ALIASES = {
    "merk": "merk_unit",
    "merek": "merk_unit",
    "pabrikan": "merk_unit",
    "manufacturer": "merk_unit",
    "merkunit": "merk_unit",
    "merekunit": "merk_unit",
    "merkpesawat": "merk_unit",
    "merekpesawat": "merk_unit",
    "merkalat": "merk_unit",
    "merekalat": "merk_unit",
    "tipe": "tipe_unit",
    "type": "tipe_unit",
    "model": "tipe_unit",
    "tipemodel": "tipe_unit",
    "modeltipe": "tipe_unit",
    "tipeunit": "tipe_unit",
    "modelunit": "tipe_unit",
    "tipepesawat": "tipe_unit",
    "modelpesawat": "tipe_unit",
    "tipealat": "tipe_unit",
    "modelalat": "tipe_unit",
    "sn": "nomor_seri_unit",
    "noseri": "nomor_seri_unit",
    "nomorseri": "nomor_seri_unit",
    "serial": "nomor_seri_unit",
    "serialno": "nomor_seri_unit",
    "serialnumber": "nomor_seri_unit",
    "snunit": "nomor_seri_unit",
    "nomorseriunit": "nomor_seri_unit",
    "noseriunit": "nomor_seri_unit",
    "serialunit": "nomor_seri_unit",
    "serialnumberunit": "nomor_seri_unit",
    "snpesawat": "nomor_seri_unit",
    "noseripesawat": "nomor_seri_unit",
    "nomorseripesawat": "nomor_seri_unit",
    "snalat": "nomor_seri_unit",
    "noserialat": "nomor_seri_unit",
    "nomorserialat": "nomor_seri_unit",
    "merktabung": "merk_tabung",
    "merektabung": "merk_tabung",
    "merktube": "merk_tabung",
    "merkxraytube": "merk_tabung",
    "merktabungsinarx": "merk_tabung",
    "merektabungsinarx": "merk_tabung",
    "tipetabung": "tipe_tabung",
    "modeltabung": "tipe_tabung",
    "tipetube": "tipe_tabung",
    "modeltube": "tipe_tabung",
    "tipexraytube": "tipe_tabung",
    "modelxraytube": "tipe_tabung",
    "tipetabungsinarx": "tipe_tabung",
    "modeltabungsinarx": "tipe_tabung",
    "sntabung": "nomor_seri_tabung",
    "nomorseritabung": "nomor_seri_tabung",
    "noseritabung": "nomor_seri_tabung",
    "noseriinsersitabung": "nomor_seri_tabung",
    "nomorseriinsersitabung": "nomor_seri_tabung",
    "serialtabung": "nomor_seri_tabung",
    "serialnumbertabung": "nomor_seri_tabung",
    "sntube": "nomor_seri_tabung",
    "noseritube": "nomor_seri_tabung",
    "nomorseritube": "nomor_seri_tabung",
    "serialtube": "nomor_seri_tabung",
    "serialnumbertube": "nomor_seri_tabung",
    "snxraytube": "nomor_seri_tabung",
    "noserixraytube": "nomor_seri_tabung",
    "nomorserixraytube": "nomor_seri_tabung",
    "noseritabungsinarx": "nomor_seri_tabung",
    "nomorseritabungsinarx": "nomor_seri_tabung",
    "alamat": "location",
    "alamatproyek": "location",
    "lokasi": "location",
    "lokasikerja": "location",
    "lokasipemanfaatan": "location",
    "lokasipenempatan": "location",
    "tempatpemanfaatan": "location",
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
    "lokasipemanfaatan": "location",
    "alamat": "location",
}


def _parse_combined_equipment_cell(value: str) -> dict:
    """Extract brand, type, and serial from combined SRP table cells."""
    text = compact(value)
    if not text:
        return {}
    # Pattern 1: <Merk>, <Tipe>/<Serial>
    m = re.match(
        r"^([^,/]+?),\s*([^/]+?)\s*/\s*([A-Za-z0-9][A-Za-z0-9._-]{2,})\b",
        text,
    )
    if m:
        return {
            "merk_unit": compact(m.group(1)),
            "tipe_unit": compact(m.group(2)),
            "nomor_seri_unit": compact(m.group(3)),
        }
    # Pattern 2: 3-part <Merk> / <Tipe> / <Serial>
    parts = [compact(p) for p in text.split("/") if compact(p)]
    if len(parts) == 3 and re.search(r"\d", parts[2]):
        return {
            "merk_unit": parts[0],
            "tipe_unit": parts[1],
            "nomor_seri_unit": parts[2],
        }
    # Pattern 3: <Tipe> Sn./SN/No. Seri <Serial>
    m_sn = re.match(
        r"^(.+?)\s+(?:Sn\.?|SN|No(?:mor)?\.?\s*Seri)\s*:?\s*([A-Za-z0-9][A-Za-z0-9._-]{2,})\b",
        text,
        re.I,
    )
    if m_sn:
        return {
            "tipe_unit": compact(m_sn.group(1)),
            "nomor_seri_unit": compact(m_sn.group(2)),
        }
    return {}


def _clean_table_location(value: str) -> str:
    """Remove usage notes and list numbering from table location cells."""
    text = compact(value)
    if not text:
        return ""
    text = re.sub(
        r"(?:\b\d+\.\s*)?\(?(?:X-?Ray|XRF)\s+digunakan\s+sesuai\s+kebutuhan[^)]*\)?",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b\d+\.\s*", "", text)
    text = compact(text).strip(" ,.;")
    return text


_MEASURING_TOOL_RE = re.compile(
    r"\b(?:surveymeter|survey\s*meter|pendose|pen\s*dose|dosimeter(?:\s*saku)?|"
    r"personal\s+dosimeter|tld|film\s+badge|alat\s+ukur(?:\s+radiasi)?|kalibrasi)\b",
    re.I,
)
_XRAY_DEVICE_RE = re.compile(
    r"\b(?:pesawat|sinar[\s-]*x|x[\s-]*ray|xrf|xrd|radiografi|fluoroskopi|ct[\s-]*scan|ndt|tube|tabung|srp)\b",
    re.I,
)
_TIPE_SN_HEADERS = {
    "tipenoseri",
    "tipesn",
    "tipenomorseri",
    "modelnoseri",
    "modelsn",
    "modelnomorseri",
}
_MERK_TIPE_HEADERS = {"merktipe", "merektipe", "merkmodel", "merekmodel"}
_MERK_TIPE_SN_HEADERS = {"merktipenoseri", "merktipesn", "merktipenomorseri"}


def _is_measuring_tool_text(text: str) -> bool:
    return bool(_MEASURING_TOOL_RE.search(text) and not _XRAY_DEVICE_RE.search(text))


def _split_type_serial_cell(value: str, *, include_brand: bool = False) -> dict:
    """Split combined type/serial or brand/type/serial cells cleanly."""
    text = compact(value)
    if not text:
        return {}
    if include_brand:
        parsed = _parse_combined_equipment_cell(text)
        if parsed.get("nomor_seri_unit") or (parsed.get("merk_unit") and parsed.get("tipe_unit")):
            return parsed
    sn_match = re.search(
        r"(?:S/?N|No(?:mor)?\.?\s*Seri|Serial(?:\s*(?:No|Number))?)\s*[:.]?\s*([A-Za-z0-9][A-Za-z0-9._/-]*)",
        text,
        re.I,
    )
    if sn_match:
        left = compact(text[: sn_match.start()]).strip(" ,/(-:")
        out = {"nomor_seri_unit": sn_match.group(1).strip(" )],.;:")}
        if left:
            out["tipe_unit"] = left
        return out
    parts = [compact(p) for p in re.split(r"\s*/\s*", text) if compact(p)]
    if len(parts) == 2 and re.search(r"\d", parts[1]):
        return {"tipe_unit": parts[0], "nomor_seri_unit": parts[1]}
    if len(parts) >= 3:
        parsed = _parse_combined_equipment_cell(text)
        if parsed.get("nomor_seri_unit"):
            return parsed
    return {}


def _merge_equipment_row(cells: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Handle 2-row merged table headers such as Pesawat Sinar-X / Tabung Sinar-X subcolumns."""
    if len(cells) < 3:
        return [norm(s) for s in cells[0]], cells[1:]
    row0 = [compact(s) for s in cells[0]]
    row1 = [compact(s) for s in cells[1]]
    sub_cues = {
        "merk",
        "merek",
        "pabrikan",
        "tipe",
        "type",
        "model",
        "noseri",
        "nomorseri",
        "sn",
        "serial",
        "unit",
        "tabung",
        "nama",
        "jabatan",
        "profesi",
        "nosib",
        "sib",
    }
    if not any(norm(c) in sub_cues for c in row1):
        return [norm(s) for s in row0], cells[1:]
    filled_row0 = []
    carry = ""
    for val in row0:
        if val:
            carry = val
        filled_row0.append(carry)
    merged = []
    for top, sub in zip(filled_row0, row1):
        n_top, n_sub = norm(top), norm(sub)
        if not n_sub:
            merged.append(n_top)
        elif "tabung" in n_top or "tube" in n_top:
            merged.append(n_sub if ("tabung" in n_sub or "tube" in n_sub) else f"{n_sub}tabung")
        elif "unit" in n_top or "pesawat" in n_top or "srp" in n_top:
            merged.append(n_sub)
        else:
            merged.append(n_sub or n_top)
    return merged, cells[2:]


def _apply_equipment_cell(item: dict, h: str, value: str, *, allow_overwrite: bool = False) -> None:
    if not value:
        return
    if h in _TIPE_SN_HEADERS:
        for k, v in _split_type_serial_cell(value, include_brand=not item.get("merk_unit")).items():
            if allow_overwrite or not item.get(k):
                item[k] = v
        return
    if h in _MERK_TIPE_HEADERS:
        parts = [compact(p) for p in re.split(r"\s*[,/]\s*", value, maxsplit=1) if compact(p)]
        if len(parts) == 2:
            if allow_overwrite or not item.get("merk_unit"):
                item["merk_unit"] = parts[0]
            if allow_overwrite or not item.get("tipe_unit"):
                item["tipe_unit"] = parts[1]
        return
    if h in _MERK_TIPE_SN_HEADERS:
        for k, v in _parse_combined_equipment_cell(value).items():
            if allow_overwrite or not item.get(k):
                item[k] = v
        return
    field = EQUIPMENT_ALIASES.get(h)
    if field and (allow_overwrite or not item.get(field)):
        item[field] = value


def _extract_kv_table_records(cells: list[list[str]], page_num: int) -> list[dict]:
    """Extract equipment records from vertical 2-3 column key-value tables."""
    if not cells or not all(2 <= len(r) <= 3 for r in cells):
        return []
    header0 = [norm(s) for s in cells[0]]
    start_idx = 0
    if any(
        h in ("parameter", "spesifikasi", "uraian", "komponen", "data", "atribut", "item", "field", "no")
        for h in header0
    ) or any("nilai" in h or "keterangan" in h for h in header0):
        start_idx = 1

    section = "unit"
    current: dict = {}
    current_quotes: list[str] = []
    results: list[dict] = []

    def flush():
        nonlocal current, current_quotes
        if current and (current.get("nomor_seri_unit") or current.get("nomor_seri_tabung")):
            quote = " | ".join(current_quotes)
            if not _is_measuring_tool_text(quote):
                current.update(page=page_num, quote=quote, method="table")
                results.append(current)
        current = {}
        current_quotes = []

    for row in cells[start_idx:]:
        clean_row = [compact(c) for c in row]
        if not any(clean_row):
            continue
        k_raw, v_raw = "", ""
        if len(clean_row) == 2:
            k_raw, v_raw = clean_row[0], clean_row[1]
        else:
            c0, c1, c2 = clean_row
            if c1 in (":", "-", "=") or not c1:
                k_raw, v_raw = c0, c2
            elif c0.rstrip(".").isdigit():
                k_raw, v_raw = c1, c2
            else:
                # e.g. ["Tabung Sinar-X", "Nomor Seri", "T-999"]
                k_raw, v_raw = f"{c0} {c1}".strip(), c2
        v_raw = re.sub(r"^[:=\s-]+", "", v_raw).strip()
        if not k_raw:
            continue
        nk = norm(k_raw)
        if not v_raw or nk in ("dataunit", "datatabung", "spesifikasiunit", "spesifikasitabung", "pesawatsinarx", "tabungsinarx", "xraytube"):
            if "tabung" in nk or "tube" in nk:
                section = "tabung"
            elif "unit" in nk or "pesawat" in nk or "alat" in nk:
                if current.get("nomor_seri_unit"):
                    flush()
                section = "unit"
            continue
        if v_raw in ("-", "—", "N/A", "n/a"):
            continue
        if _is_measuring_tool_text(f"{k_raw} {v_raw}"):
            flush()
            continue
        if section == "tabung" and nk in ("merk", "merek", "pabrikan", "tipe", "type", "model", "noseri", "nomorseri", "sn", "serial", "serialno", "serialnumber"):
            nk = f"{nk}tabung"
        field = EQUIPMENT_ALIASES.get(nk)
        if not field and nk not in _TIPE_SN_HEADERS and nk not in _MERK_TIPE_HEADERS and nk not in _MERK_TIPE_SN_HEADERS:
            continue
        if field in ("merk_unit", "nomor_seri_unit") and current.get(field) and norm(current[field]) != norm(v_raw):
            flush()
        _apply_equipment_cell(current, nk, v_raw, allow_overwrite=False)
        current_quotes.append(f"{k_raw}: {v_raw}")
    flush()
    return results


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
                r"SN\s*Unit|No(?:mor)?\.?\s*Seri(?:\s*(?:Unit|Tabung))?|Serial(?:\s*(?:No|Number))?|\bS/?N\b|"
                r"(?:Nama|Name)\s+(?:Jenis|Jabatan|Profesi|Keahlian)|Daftar\s+(?:Nama\s+)?Person|"
                r"Daftar\s+Person[ei]l|Daftar\s+Pengguna|SRP\s+X|Lokasi\s+Pemanfaatan|"
                r"(?:Data|Daftar|Spesifikasi|Identitas|Tabel)\s+(?:Pesawat|Peralatan|Alat|SRP|Sumber|X-?Ray)|"
                r"Pesawat\s+Sinar\s*[- ]?X|Tabung\s+Sinar\s*[- ]?X|\b(?:Merk|Merek)\b.*\b(?:Tipe|Type|Model)\b",
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
                header, body_rows = _merge_equipment_row(cells)
                has_unit_sn = any(
                    h
                    in (
                        "snunit",
                        "nomorseriunit",
                        "noseriunit",
                        "serialunit",
                        "serialnumberunit",
                        "snpesawat",
                        "noseripesawat",
                        "nomorseripesawat",
                        "snalat",
                        "noserialat",
                        "nomorserialat",
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
                        "sntube",
                        "noseritube",
                        "nomorseritube",
                        "serialtube",
                        "serialnumbertube",
                        "snxraytube",
                        "noserixraytube",
                        "nomorserixraytube",
                        "noseritabungsinarx",
                        "nomorseritabungsinarx",
                    )
                    for h in header
                )
                has_generic_sn = any(
                    h in ("sn", "noseri", "nomorseri", "serial", "serialno", "serialnumber")
                    or h in _TIPE_SN_HEADERS
                    for h in header
                )
                has_brand_or_type = any(
                    EQUIPMENT_ALIASES.get(h) in ("merk_unit", "tipe_unit") or h in _MERK_TIPE_HEADERS
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
                has_sib = any(
                    h in ("nosib", "sib", "nomorsib", "noktun", "validuntil", "masaberlaku")
                    for h in header
                )
                combined_col_idx = next(
                    (
                        idx
                        for idx, h in enumerate(header)
                        if h in ("srp", "srpxrf", "srpxray", "pesawatsinarx", "pesawat", "alatkerja", "merktipenoseri")
                        or h.startswith("srpx")
                    ),
                    None,
                )
                has_measuring_col = any(
                    "alatukur" in h or "surveymeter" in h or "dosimeter" in h
                    for h in header
                )
                if has_unit_sn or has_tube_sn or (
                    has_generic_sn
                    and has_brand_or_type
                    and combined_col_idx is None
                    and not has_measuring_col
                ):
                    kind, aliases, data_rows = "equipment", EQUIPMENT_ALIASES, body_rows
                elif has_name and (has_role or has_sib):
                    kind, aliases, data_rows = "personnel", PERSONNEL_ALIASES, body_rows
                elif combined_col_idx is not None:
                    kind, aliases, data_rows = "combined", EQUIPMENT_ALIASES, body_rows
                elif (
                    last_table
                    and page["page"] == last_table["page"] + 1
                    and len(cells[0]) == len(last_table["header"])
                    and not any(
                        h in ("uraian", "kegiatan", "materi", "parameter")
                        for h in (norm(s) for s in cells[0])
                    )
                ):
                    kind = last_table["kind"]
                    aliases = last_table["aliases"]
                    header = last_table["header"]
                    combined_col_idx = last_table.get("combined_col_idx")
                    data_rows = cells
                else:
                    kv_recs = _extract_kv_table_records(cells, page["page"])
                    records["equipment"].extend(kv_recs)
                    continue
                page_last = {
                    "kind": kind,
                    "aliases": aliases,
                    "header": header,
                    "combined_col_idx": combined_col_idx,
                    "page": page["page"],
                }
                current_role = ""
                for row in data_rows:
                    if kind == "personnel":
                        non_empty = [v for v in row if v]
                        if (
                            non_empty
                            and len(set(non_empty)) == 1
                            and not (row[0] or "").strip().isdigit()
                            and re.search(
                                r"\b(?:ppr|petugas\s+proteksi|operator|radiografer|ahli\s+radiografi|pksr|pekerja\s+radiasi|teknisi)\b",
                                non_empty[0],
                                re.I,
                            )
                        ):
                            current_role = non_empty[0]
                            continue
                        item = {
                            aliases[h]: value
                            for h, value in zip(header, row)
                            if h in aliases and value
                        }
                        if not item.get("name"):
                            continue
                        if not item.get("role") and current_role:
                            item["role"] = current_role
                        item.update(
                            page=page["page"],
                            quote=" | ".join(s for s in row if s),
                            method="table",
                        )
                        records["personnel"].append(item)
                    elif kind == "combined":
                        quote_line = " | ".join(s for s in row if s)
                        if not quote_line:
                            continue
                        raw_equip = row[combined_col_idx] if combined_col_idx < len(row) else ""
                        equip_item = _parse_combined_equipment_cell(raw_equip)
                        for h, value in zip(header, row):
                            if h != header[combined_col_idx] and value and (
                                h in _TIPE_SN_HEADERS or h in _MERK_TIPE_HEADERS or h in _MERK_TIPE_SN_HEADERS or (
                                    aliases.get(h) in ("merk_unit", "tipe_unit", "nomor_seri_unit", "merk_tabung", "tipe_tabung", "nomor_seri_tabung")
                                )
                            ):
                                _apply_equipment_cell(equip_item, h, value, allow_overwrite=False)
                        # Extract location (guard against swapped Lokasi Pemanfaatan / Alat Ukur headers)
                        loc_raw = ""
                        for h, value in zip(header, row):
                            if aliases.get(h) == "location" and value:
                                if re.match(r"^\s*(?:surveymeter|pendose)\b", value, re.I):
                                    # Check alatukur column in case headers were swapped
                                    alat_val = next(
                                        (v for hh, v in zip(header, row) if hh == "alatukur" and v),
                                        "",
                                    )
                                    if alat_val and not re.match(r"^\s*(?:surveymeter|pendose)\b", alat_val, re.I):
                                        loc_raw = alat_val
                                else:
                                    loc_raw = value
                                break
                        loc_clean = _clean_table_location(loc_raw)
                        if equip_item.get("nomor_seri_unit") or equip_item.get("nomor_seri_tabung"):
                            if loc_clean:
                                equip_item["location"] = loc_clean
                            equip_item.update(page=page["page"], quote=quote_line, method="table")
                            records["equipment"].append(equip_item)
                        for h, value in zip(header, row):
                            if h in ("personel", "personil", "petugas") and value:
                                for pm in re.finditer(
                                    r"(?:^|\b\d+\.\s*)([A-Za-z][A-Za-z .'-]{2,60}?)\s*\(([^()]+)\)",
                                    value,
                                ):
                                    pname = compact(pm.group(1))
                                    prole = compact(pm.group(2))
                                    if pname and prole:
                                        records["personnel"].append(
                                            {
                                                "name": pname,
                                                "role": prole,
                                                "page": page["page"],
                                                "quote": quote_line,
                                                "method": "table",
                                            }
                                        )
                    else:
                        quote_line = " | ".join(s for s in row if s)
                        if not quote_line or _is_measuring_tool_text(quote_line):
                            continue
                        item = {}
                        for h, value in zip(header, row):
                            if value:
                                _apply_equipment_cell(item, h, value, allow_overwrite=False)
                        if not (item.get("nomor_seri_unit") or item.get("nomor_seri_tabung")):
                            continue
                        if item.get("location"):
                            item["location"] = _clean_table_location(item["location"])
                        item.update(
                            page=page["page"],
                            quote=quote_line,
                            method="table",
                        )
                        records["equipment"].append(item)
            last_table = page_last
    return records


def _kv_equipment_records(pages: list[dict], existing: list[dict] | None = None) -> list[dict]:
    """Deterministic key-value text block extractor for equipment specs without table borders."""
    existing_keys = {
        (r.get("page"), _serial_core(r.get("nomor_seri_unit") or ""), _serial_core(r.get("nomor_seri_tabung") or ""))
        for r in (existing or [])
        if r.get("nomor_seri_unit") or r.get("nomor_seri_tabung")
    }
    inline_split_re = re.compile(
        r"\s+(?=(?:Merk(?:\s+(?:Unit|Tabung|Pesawat|Alat))?|Merek(?:\s+(?:Unit|Tabung|Pesawat|Alat))?|"
        r"Pabrikan|Tipe(?:\s+(?:Unit|Tabung|Pesawat|Alat))?|Model(?:\s+(?:Unit|Tabung|Pesawat|Alat))?|"
        r"No(?:mor)?\.?\s*Seri(?:\s+(?:Unit|Tabung|Pesawat|Alat|Insersi\s+Tabung))?|"
        r"S/?N(?:\s+(?:Unit|Tabung))?|Serial(?:\s*(?:No|Number))?(?:\s+(?:Unit|Tabung))?|"
        r"Lokasi(?:\s+(?:Pemanfaatan|Kerja|Penempatan))?)\s*[:=])",
        re.I,
    )
    kv_line_re = re.compile(
        r"^\s*(?:[-•*]|\d+[.)])?\s*([A-Za-z][A-Za-z0-9 /&().-]{1,48}?)\s*(?::|=|\|)\s*(.+?)\s*$"
    )
    kv_space_re = re.compile(
        r"^\s*(?:[-•*]|\d+[.)])?\s*([A-Za-z][A-Za-z0-9 /&().-]{1,40}?)(?:\t|\s{2,})(.+?)\s*$"
    )
    results = []
    for page in pages:
        raw_text = page["text"]
        if toc(raw_text):
            continue
        section = "unit"
        ignore_section = False
        current: dict = {}
        quote_lines: list[str] = []
        non_kv_streak = 0

        def flush():
            nonlocal current, quote_lines
            if current and (current.get("nomor_seri_unit") or current.get("nomor_seri_tabung")):
                quote = compact(" ".join(quote_lines))
                key_sig = (
                    page["page"],
                    _serial_core(current.get("nomor_seri_unit") or ""),
                    _serial_core(current.get("nomor_seri_tabung") or ""),
                )
                if quote and not _is_measuring_tool_text(quote) and key_sig not in existing_keys:
                    existing_keys.add(key_sig)
                    current.update(page=page["page"], quote=quote[:900], method="kv")
                    results.append(current)
            current = {}
            quote_lines = []

        def consume_kv(k_raw: str, v_raw: str, raw_line: str) -> bool:
            v_clean = compact(v_raw).strip(" -–—:")
            if not v_clean or len(v_clean) > 120 or v_clean in ("-", "—", "N/A", "n/a"):
                return False
            if ignore_section or _is_measuring_tool_text(f"{k_raw} {v_clean}"):
                return False
            nk = norm(k_raw)
            if section == "tabung" and nk in ("merk", "merek", "pabrikan", "tipe", "type", "model", "noseri", "nomorseri", "sn", "serial", "serialno", "serialnumber"):
                nk = f"{nk}tabung"
            field = EQUIPMENT_ALIASES.get(nk)
            if not field and nk not in _TIPE_SN_HEADERS and nk not in _MERK_TIPE_HEADERS and nk not in _MERK_TIPE_SN_HEADERS:
                return False
            if field in ("merk_unit", "nomor_seri_unit") and current.get(field) and norm(current[field]) != norm(v_clean):
                flush()
            _apply_equipment_cell(current, nk, v_clean, allow_overwrite=False)
            if raw_line.strip() and compact(raw_line) not in quote_lines:
                quote_lines.append(compact(raw_line))
            return True

        for raw_line in raw_text.splitlines():
            raw_stripped = raw_line.strip()
            line = compact(raw_line)
            if not line:
                non_kv_streak += 1
                if non_kv_streak >= 3:
                    flush()
                    ignore_section = False
                continue
            if re.search(r"^\s*(?:\d+(?:\.\d+)*\s+|[-•*]\s+)?(?:Daftar|Tabel|Data)\s+Alat\s+Ukur", line, re.I):
                flush()
                ignore_section = True
                continue
            if re.search(r"^\s*(?:[-•*]|\d+(?:\.\d+)*[.)]?)\s*(?:Data\s+|Spesifikasi\s+|Identitas\s+)?(?:Pesawat\s+Sinar[\s-]*X|Unit\s+\d+|Pesawat\s+\d+)", line, re.I):
                if current.get("nomor_seri_unit"):
                    flush()
                section = "unit"
                ignore_section = False
            elif re.search(r"^\s*(?:[-•*]|\d+(?:\.\d+)*[.)]?|[A-Za-z][.)]\s+)?(?:Data\s+|Spesifikasi\s+)?(?:Tabung\s+Sinar[\s-]*X|X[\s-]*Ray\s+Tube|Insersi\s+Tabung)\b", line, re.I):
                section = "tabung"
                ignore_section = False

            segments = inline_split_re.split(line)
            matched_any = False
            for seg in segments:
                m = kv_line_re.match(seg)
                if m and consume_kv(compact(m.group(1)), m.group(2), raw_line):
                    matched_any = True
            if not matched_any:
                sm = kv_space_re.match(raw_stripped)
                if sm and consume_kv(compact(sm.group(1)), sm.group(2), raw_line):
                    matched_any = True
            if matched_any:
                non_kv_streak = 0
            else:
                non_kv_streak += 1
                if non_kv_streak >= 3:
                    flush()
        flush()
    return results


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


_PROSE_LOC_RE = re.compile(
    r"\b(?:alamat|lokasi\s+(?:pemanfaatan|proyek|penyimpanan|fasilitas|kegiatan))\b"
    r"(?:[^:\n.]|(?<=\b(?:PT|CV))\.)"
    r"{0,80}?\b(?:berada|berlokasi|terletak)\s+di\s+(?=(?:jl|jln|jalan)\b)"
    r"((?:[^.\n]|(?<=\b(?:Jl|No|PT|CV|Gd|Gg|Lt))\.|(?<=\b(?:Jln|Kec|Kab|Kel|Gdg|Kav))\.|(?<=\bKomp)\.|\.(?=[a-z0-9]))+)",
    re.I,
)


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
        found_page_addr = False
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
            prose_loc = None
            if project:
                address = project.group(1)
                has_addr_label = True
            else:
                stripped = re.sub(
                    r"^(?:Alamat(?:\s+(?:Proyek|Lokasi\s+Pemanfaatan))?|Lokasi\s+(?:Proyek|Pemanfaatan))\s*:\s*",
                    "",
                    line,
                    flags=re.I,
                )
                has_addr_label = stripped != line
                address = stripped
                if not has_addr_label:
                    prose_loc = _PROSE_LOC_RE.search(line)
                    if prose_loc and re.search(ADDRESS, prose_loc.group(1), re.I):
                        address = compact(prose_loc.group(1)).strip(" .")
                        has_addr_label = True
            if re.search(r"\bradiografer\s+tingkat\b", address, re.I):
                continue
            unlabeled_ok = (
                identity_context
                and bool(
                    re.match(
                        r"^(?:jl|jalan|jln|komplek[s]?|komp|kawasan|gedung|ruko|outlet|cabang)\b\.?\s+[A-Za-z0-9]",
                        address,
                        re.I,
                    )
                )
                and not re.search(
                    r"\b(?:merupakan|adalah|saat|telah|akan|memiliki|melakukan|menggunakan|menetapkan|bertanggung|menerapkan|harus|wajib|evakuasi|personel|personil|pekerja|radiografer|apabila)\b|[•●]",
                    address,
                    re.I,
                )
            )
            if re.match(ADDRESS, address, re.I) and (has_addr_label or unlabeled_ok):
                # Explicit office addresses must not become project addresses.
                previous = lines[i - 1] if i else ""
                if re.search(OFFICE_LABEL, line + "\n" + previous, re.I) and not project:
                    continue
                if not prose_loc:
                    for following in lines[i + 1 : i + 5]:
                        if (
                            re.search(PROJECT_LABEL + "|" + OFFICE_LABEL, following, re.I)
                            or re.search(r"\b\d{5}\b", address)
                            or re.match(
                                r"No|Page|Tanggal|Date|BAB|(?:Nama|Nomor|Telepon|Email|Alamat|Jabatan)\b|\d+\.\d+\s",
                                following,
                                re.I,
                            )
                            or re.search(
                                r"\b(?:merupakan|adalah|harus|wajib|evakuasi|personel|radiografer|prosedur|dokumen\s+sistem|program\s+proteksi|ndt\s+inspection)\b|[•●]",
                                following,
                                re.I,
                            )
                            or re.match(r"^" + INSTITUTION + r"\b", following, re.I)
                        ):
                            break
                        address += " " + following
                if office_address(address, source):
                    continue
                found_page_addr = True
                records.append(
                    {
                        "project_address": address,
                        "page": page["page"],
                        "quote": address,
                        "method": page.get("method", "text"),
                    }
                )
        if not found_page_addr:
            compact_source = compact(source)
            wrapped_loc = _PROSE_LOC_RE.search(compact_source)
            if wrapped_loc:
                addr = compact(wrapped_loc.group(1)).strip(" .")
                if (
                    re.search(ADDRESS, addr, re.I)
                    and not re.search(r"\bradiografer\s+tingkat\b", addr, re.I)
                    and not office_address(addr, source)
                ):
                    records.append(
                        {
                            "project_address": addr,
                            "page": page["page"],
                            "quote": addr,
                            "method": page.get("method", "text"),
                        }
                    )
    return records


def _candidate_page_score(kind: str, text: str) -> int:
    score = 0
    if re.search(
        r"lampiran\b|daftar\s+(?:nama\s+)?(?:person[ei]l|pengguna|alat|pesawat)",
        text,
        re.I,
    ):
        score += 100
    if re.search(
        r"no\.?\s*sib\b|srp\s+x\b|tabel\s+x.ray\s+tube|sn\s*(?:unit|tabung)\b|no(?:mor)?\.?\s*seri\b|"
        r"(?:spesifikasi|data)\s+pesawat|pesawat\s+sinar\s*[- ]?x\b",
        text,
        re.I,
    ):
        score += 60
    if kind == "equipment" and re.search(
        r"\b(?:merk|merek)\b.{0,80}\b(?:tipe|type|model)\b",
        text,
        re.I,
    ):
        score += 40
    if kind == "equipment" and re.search(
        r"daftar\s+alat\s+ukur|sertifikat\s+kalibrasi",
        text,
        re.I,
    ):
        score -= 150
    return score


def _has_real_tube_cue(text: str) -> bool:
    """Detect real tube equipment specifications while ignoring generic prose and glossary entries."""
    filtered_lines = []
    for line in str(text or "").splitlines():
        if re.search(r"s-tube|guide\s+tube", line, re.I):
            continue
        if re.match(r"^\s*X-?Ray\s+Tube\s*(?:\([^)]*\))?\s*:", line, re.I):
            continue
        filtered_lines.append(line)
    return bool(
        re.search(
            r"\b(?:merk|merek|tipe|type|model|no(?:mor)?\.?\s*seri|s/?n|serial)\s+(?:insersi\s+)?(?:tabung|tube)\b|"
            r"\btabel\s+x[- ]?ray\s+tube\b|\binsersi\s+tabung\b|\bx-?tube\b|"
            r"\b(?:tabung|tube)\s*(?:sinar[- ]?x\s*)?(?::|\|)\s*[A-Za-z0-9]",
            "\n".join(filtered_lines),
            re.I,
        )
    )


def _equipment_linked(expected, record):
    for k in ("nomor_seri_unit", "nomor_seri_tabung"):
        if expected.get(k) and norm(expected[k]) == norm(record.get(k)):
            return True
    for k in ("nomor_seri_unit", "nomor_seri_tabung"):
        exp_core = _serial_core(expected.get(k))
        rec_core = _serial_core(record.get(k))
        if len(exp_core) >= 4 and exp_core == rec_core:
            return True
    return False


def extract_records(path, pages, application=None):
    warnings = []
    records = table_records(path, pages)
    records["equipment"].extend(_kv_equipment_records(pages, records["equipment"]))
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
                r"tabel\s+x.ray\s+tube|SN\s*(?:Unit|Tabung)|no(?:mor)?\.?\s*seri|serial(?:\s*(?:number|no))?|"
                r"\bS/?N\b|(?:data|daftar|spesifikasi|identitas|tabel|inventaris|lampiran)\s+(?:pesawat|peralatan|alat\s+kerja|x-?ray|srp|sumber)|"
                r"pesawat\s+sinar\s*[- ]?x|\b(?:merk|merek)\b.{0,80}\b(?:tipe|type|model)\b.{0,120}\b(?:seri|s/?n|serial)\b",
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
                    linked = [r for r in records[kind] if _equipment_linked(expected, r)]
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
            expected_serials = []
            if kind == "equipment" and (application or {}).get("equipment"):
                expected_serials = [
                    sc
                    for e in application["equipment"]
                    for k in ("nomor_seri_unit", "nomor_seri_tabung")
                    for sc in (_serial_core(e.get(k)),)
                    if len(sc) >= 4
                ]
                # If all unit fields are already complete for every expected device and only tube
                # fields are missing, skip candidate pages without real tube cues.
                unit_complete = True
                for expected in application["equipment"]:
                    linked = [r for r in records["equipment"] if _equipment_linked(expected, r)]
                    if not linked or any(
                        not any(r.get(uk) for r in linked)
                        for uk in ("merk_unit", "tipe_unit", "nomor_seri_unit")
                    ):
                        unit_complete = False
                        break
                if unit_complete:
                    selected = [p for p in selected if _has_real_tube_cue(p["text"])]
            incomplete_pages = {
                r["page"] for r in records[kind] if any(not r.get(k) for k in required)
            }
            selected.sort(
                key=lambda p: (
                    p["page"] not in incomplete_pages,
                    not (
                        kind == "equipment"
                        and expected_serials
                        and any(sc in norm(p["text"]) for sc in expected_serials)
                    ),
                    -_candidate_page_score(kind, p["text"]),
                    p["page"],
                )
            )
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
    return "-".join(str(int(p)) for p in parts[::-1]) if len(parts) == 3 else norm(value)


_OCR_DIGIT_TRANS = str.maketrans("OoIl|", "00111")


def _ocr_digit_tokens_normalize(value: str) -> str:
    def repl(match):
        token = match.group(0)
        return token.translate(_OCR_DIGIT_TRANS) if re.search(r"\d", token) else token

    return re.sub(r"(?<![A-Za-z0-9])[0-9OoIl|]+(?![A-Za-z0-9])", repl, str(value or ""))


def _ocr_number_digits(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+", _ocr_digit_tokens_normalize(value)))


def _ocr_glitch_count(value: str) -> int:
    count = 0
    for match in re.finditer(r"(?<![A-Za-z0-9])[0-9OoIl|]+(?![A-Za-z0-9])", str(value or "")):
        token = match.group(0)
        if re.search(r"\d", token):
            count += sum(1 for ch in token if ch in "OoIl|")
    return count


def _same_number_cluster(a: str, b: str) -> bool:
    da, db = _ocr_number_digits(a), _ocr_number_digits(b)
    if not da or da != db:
        return False
    na, nb = norm(_ocr_digit_tokens_normalize(a)), norm(_ocr_digit_tokens_normalize(b))
    if not na or not nb:
        return False
    return na == nb or SequenceMatcher(None, na, nb).ratio() >= 0.82


def _select_metadata(candidates, expected, key):
    if not candidates:
        return []
    if key != "number":
        for candidate in candidates:
            candidate["identity"] = _metadata_date_key(candidate["value"])
            candidate["score"] = candidate["label_score"]
        best = max(candidate["score"] for candidate in candidates)
        selected = [candidate for candidate in candidates if candidate["score"] == best]
        unique = set()
        return [
            item
            for item in selected
            if not (item["identity"] in unique or unique.add(item["identity"]))
        ]

    per_page = {}
    for candidate in candidates:
        identity = norm(candidate["value"])
        if not identity:
            continue
        pk = (candidate["page"], identity)
        prev = per_page.get(pk)
        cand_rank = (candidate["label_score"], bool(candidate.get("from_native")))
        if not prev or cand_rank > (prev["label_score"], bool(prev.get("from_native"))):
            per_page[pk] = {**candidate, "identity": identity, "score": candidate["label_score"]}
    deduped = list(per_page.values())
    if not deduped:
        return []

    best = max(c["score"] for c in deduped)
    top = [c for c in deduped if c["score"] == best]
    clusters = []
    for item in top:
        matched = next(
            (cl for cl in clusters if any(_same_number_cluster(item["value"], m["value"]) for m in cl)),
            None,
        )
        if matched is not None:
            matched.append(item)
        else:
            clusters.append([item])

    # Pull in lower-scored native cluster mates only if the top cluster itself has no native variant.
    for cluster in clusters:
        if any(m.get("from_native") for m in cluster):
            continue
        for item in deduped:
            if item["score"] < best and item.get("from_native") and any(
                _same_number_cluster(item["value"], m["value"]) for m in cluster
            ):
                cluster.append(item)

    exp_norm = norm(expected) if expected else ""
    selected = []
    for cluster in clusters:
        freq = Counter(m["identity"] for m in cluster)
        rep = max(
            cluster,
            key=lambda c: (
                bool(c.get("from_native")),
                bool(exp_norm) and c["identity"] == exp_norm,
                freq[c["identity"]],
                len(re.findall(r"[/.-]", c["value"])) - _ocr_glitch_count(c["value"]),
                -c["page"],
            ),
        )
        selected.append(rep)
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
    header_context_re = re.compile(
        r"PROGRAM\s+PROTEKSI|DOKUMEN\s+SISTEM\s+MANAJEMEN|SISTEM\s+MANAJEMEN",
        re.I,
    )
    for page in scan_pages:
        sources = []
        if page.get("method") == "ocr":
            native_part = compact(page.get("native_text"))
            ocr_part = compact(page["text"])
            if native_part:
                sources.append((native_part, True))
            if ocr_part and ocr_part != native_part:
                sources.append((ocr_part, False))
        else:
            text_part = compact(page.get("native_text") or page["text"])
            if text_part:
                sources.append((text_part, True))
        for text, from_native in sources:
            if toc(text):
                continue
            for match in re.finditer(
                r"\b(?:(?P<label_doc>(?:Nomor|No\.?|Kode)\s+Dokumen)\b\s*(?::|\||–|-)?|"
                r"(?P<label_short>Nomor|No)\b\.?\s*(?::|\||–|-))\s*"
                r"(?P<value>[A-Za-z0-9]+(?:\s*[/–—-]\s*[A-Za-z0-9]+|\.[A-Za-z0-9]+)+"
                r"(?:[\s./–—-]*\bRev(?:isi)?\.?\s*\d+[A-Za-z]?)?)",
                text,
                re.I,
            ):
                value = re.split(
                    r"\b(?:(?:Revision|Revisi)(?!\s*\.?\s*\d)|Tanggal|Date|Page|Halaman|PROGRAM|DOKUMEN|SISTEM|Departemen)\b",
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
                        "from_native": from_native,
                    }
                )
            if page["page"] <= 3:
                for match in re.finditer(
                    r"\b(?P<value>[A-Z]{2,}(?:\s*[-/]\s*(?:(?!Rev(?:isi)?\b)[A-Za-z]{2,}|\d+[A-Za-z]*)){2,}"
                    r"(?:\s*[-/]\s*Rev(?:isi)?\.?\s*\d+[A-Za-z]?)?)\b(?![-/][A-Za-z0-9])",
                    text,
                ):
                    if re.search(r"[\dA-Za-z]\s*/\s*$", text[max(0, match.start() - 12) : match.start()]):
                        continue
                    value = compact(match.group("value")).strip(" -–—/:.")
                    if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
                        continue
                    nearby = text[max(0, match.start() - 160) : min(len(text), match.end() + 160)]
                    if not header_context_re.search(nearby):
                        continue
                    number.append(
                        {
                            "value": value,
                            "page": page["page"],
                            "quote": match.group(0),
                            "label_score": 60,
                            "from_native": from_native,
                        }
                    )
            pattern = (
                r"(?<!Tempat,\s)(?<!Tempat\s)"
                r"(?P<label>Date|Tanggal\s+(?:Pengesahan|Dibuat|Dokumen|Terbit|Efektif|Berlaku)|Tanggal(?=\s*:))\s*"
                r"(?::|\||–|-)?\s*(?P<value>\d{1,2}(?:[/.-]\d{1,2}[/.-]|\s+[A-Za-z]+\s+)\d{4})"
            )
            for match in re.finditer(pattern, text, re.I):
                label = match.group("label")
                score = (
                    100
                    if re.search(r"dokumen|terbit|efektif|berlaku", label, re.I)
                    else 70
                    if re.search(r"date|pengesahan|dibuat", label, re.I)
                    else 65
                )
                date.append(
                    {
                        "value": match.group("value"),
                        "page": page["page"],
                        "quote": match.group(0),
                        "label_score": score,
                    }
                )
    return {
        "number": _select_metadata(number, expected_number, "number"),
        "date": _select_metadata(date, expected_date, "date"),
    }
