"""Bounded hybrid Qwen LLM fallback for radiation exposure & tube leakage reports."""

from __future__ import annotations

from difflib import SequenceMatcher
import os
import re
import unicodedata

from rapidfuzz import fuzz

from .protection import llm
from .protection.extraction import compact, norm

EQUIPMENT_FIELDS = (
    "merk_unit",
    "tipe_unit",
    "nomor_seri_unit",
    "merk_tabung",
    "tipe_tabung",
    "nomor_seri_tabung",
)

FIELD_LABELS = {
    "merk_unit": "Merek unit",
    "tipe_unit": "Tipe unit",
    "nomor_seri_unit": "No. seri unit",
    "merk_tabung": "Merek tabung",
    "tipe_tabung": "Tipe tabung",
    "nomor_seri_tabung": "No. seri insersi tabung",
}

_DETECTOR_CONTEXT_RE = re.compile(
    r"(?i)\b(?:detector(?:\s+(?:model|type|s\s*/\s*n|sn|serial))?|"
    r"surveymeter|survey\s+meter|alat\s+ukur|"
    r"dose\s+rate\s+(?:instrument|meter)|testing\s+equipment|"
    r"calibrator|dosimeter)\b"
)

_TARGET_CONTEXT_RE = re.compile(
    r"(?i)\b(?:instrument(?:\s+(?:model|type|s\s*/\s*n|sn|serial))?|"
    r"equipment(?:\s+(?:model|name|s\s*/\s*n|sn|serial))?|"
    r"pesawat|tabung|x-?ray\s*tube|generator|"
    r"identitas\s+peralatan|data\s+(?:alat|pesawat|unit|tabung)|"
    r"merek|merk|tipe(?:\s+(?:unit|tabung))?|nomor\s+seri(?:\s+(?:unit|alat|tabung|insersi))?|"
    r"manufacturer|portable\s+xrf|analyzer|spectrometer)\b"
)

_SIGNOFF_CUE_RE = re.compile(
    r"(?i)\b(?:conducted\s+by|tested\s+by|surveyed\s+by|verified\s+by|"
    r"checked\s+by|approved\s+by|edited\s+by|authorized(?:\s+by)?|"
    r"mengetahui|menyetujui|disahkan|pengesahan|penguji|ditandatangani|"
    r"manajer|supervisor|pelaksana\s+uji|penanggung\s+jawab)\b"
)

_CONTRACTOR_HINT_RE = re.compile(
    r"(?i)\b(?:tewksbury|radcliff|ma\s+0\d{4}|usa|suzhou|china|"
    r"penguji|laboratorium|laboratory|calibrator|surveymeter|"
    r"nuklindolab|ruisen|radiation\s+technology|importir|entrusting|supplier)\b|www\.|@"
)

_PAGE_CUE_RE = re.compile(
    r"(?i)\b(?:model|serial|s\s*/\s*n|merek|merk|manufacturer|instrument|"
    r"equipment|pesawat|tabung|identitas|instansi|fasilitas|rumah\s+sakit|"
    r"conducted\s+by|approved\s+by|checked\s+by|mengetahui|pengesahan)\b"
)

_GENERIC_DEVICE_NOUN_RE = re.compile(
    r"(?i)\b(?:analyzer|analyzers|spectrometer|radiography|fluoroscopy|x-?ray\s+(?:system|unit|device|machine)|pesawat\s+sinar[- ]?x)\b"
)


def _is_generic_device_noun(value: str) -> bool:
    """True when text describes an apparatus category with no model code/digits."""
    s = _space(value)
    return bool(s) and not any(ch.isdigit() for ch in s) and bool(_GENERIC_DEVICE_NOUN_RE.search(s))


_MODEL_ONLY_LABEL_RE = re.compile(
    r"(?i)\b(?:equipment|instrument|unit|device)?\s*(?:model|tipe|type)\s*:\s*$"
)


def _has_model_only_label(value: str, page_text: str) -> bool:
    """True when value occurs directly after an explicit Model/Type label (not Serial)."""
    toks = _tokens(value)
    if not toks:
        return False
    pat = re.compile(r"(?is)" + r"[^a-z0-9]{0,4}".join(map(re.escape, toks)))
    for m in pat.finditer(page_text):
        before = page_text[max(0, m.start() - 40) : m.start()]
        if _MODEL_ONLY_LABEL_RE.search(before):
            return True
    return False


_EXPLICIT_MODEL_LINE_RE = re.compile(
    r"(?im)\b(?:equipment|instrument|unit|device|pesawat)\s+(?:model|tipe|type)\s*:\s*([A-Za-z0-9][A-Za-z0-9\-./ ]{1,35}?)(?=\s{2,}|\r|\n|$)"
)


def _extract_explicit_labeled_model(page_text: str) -> str:
    """Recover explicit non-detector 'Equipment/Instrument Model: <val>' if Qwen skipped it."""
    for m in _EXPLICIT_MODEL_LINE_RE.finditer(page_text):
        cand = _space(m.group(1)).strip(" :;|")
        if (
            cand
            and not _is_generic_device_noun(cand)
            and not _in_detector_only_context(cand, page_text)
        ):
            return cand
    return ""


def _space(value) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def _absent(value) -> bool:
    s = _space(value)
    return not s or s.casefold() in {
        "—",
        "-",
        "–",
        "n/a",
        "na",
        "none",
        "null",
        "tidak ada",
        "tidak ditemukan",
    }


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", str(value or "")).casefold())


def is_token_subset_model(expected: str, observed: str) -> bool:
    """True when one model is a strict whole-word token subset of the other.

    Examples:
        - 'DXL 800' vs 'DXL 800 Niton' -> True (missing sub-brand word, REVIEW)
        - 'TrueX' vs 'TrueX G5' -> True (missing family suffix token, REVIEW)
        - 'E7894' vs 'E7894X' -> False (altered alphanumeric code, MISMATCH)
        - 'DXL 800' vs 'DXL 900 Niton' -> False (different token '800' != '900', MISMATCH)
    """
    exp_toks = _tokens(expected)
    obs_toks = _tokens(observed)
    if not exp_toks or not obs_toks:
        return False
    exp_set, obs_set = set(exp_toks), set(obs_toks)
    if exp_set == obs_set:
        return False
    # Require the larger phrase to actually have >=2 distinct tokens so single-token
    # alphanumeric alterations like E7894 vs E7894X never pass as subset.
    if max(len(exp_set), len(obs_set)) < 2:
        return False
    return obs_set < exp_set or exp_set < obs_set


def _ocr_serial_key(value: str) -> str:
    trans = str.maketrans({"o": "0", "i": "1", "l": "1", "s": "5", "z": "2", "b": "8"})
    return re.sub(r"[^a-z0-9]", "", _space(value).casefold()).translate(trans)


def evaluate_exposure_field(field_key: str, expected: str, observed: str):
    """Compare expected vs observed equipment field conservatively without hardcoding."""
    if _absent(expected) or _absent(observed):
        return ("REVIEW", None, "")

    exp = _space(expected)
    obs = _space(observed)
    from src.extraction.program_evidence import _same_brand

    exp_norm = norm(exp)
    obs_norm = norm(obs)
    seq_score = round(100.0 * SequenceMatcher(None, exp_norm, obs_norm).ratio(), 1)

    if field_key.startswith("merk"):
        if exp_norm == obs_norm or _same_brand(exp, obs):
            return ("MATCH", 100.0, "")
        exp_set, obs_set = set(_tokens(exp)), set(_tokens(obs))
        common = exp_set & obs_set
        token_set_score = fuzz.token_set_ratio(exp.casefold(), obs.casefold())
        if (
            common
            and (obs_set <= exp_set or exp_set <= obs_set or token_set_score >= 80 or seq_score >= 70)
        ):
            return (
                "REVIEW",
                seq_score,
                "Merek mirip / parsial pada dokumen; perlu verifikasi visual",
            )
        return ("MISMATCH", seq_score, "Merek berbeda.")

    if field_key.startswith("tipe"):
        if exp_norm == obs_norm:
            return ("MATCH", 100.0, "")
        # Trim trailing electrical ratings such as '30kW' when base model is exact.
        from .analysis.equipment import _trim_model_spec

        trimmed = _trim_model_spec(exp, obs)
        if trimmed:
            return ("MATCH", 100.0, f"Spesifikasi kelistrikan {trimmed[1]} dipisahkan dari kode tipe.")
        # Equal-length 0/O or 1/I/l ambiguity -> REVIEW.
        trans = str.maketrans({"o": "0", "i": "1", "l": "1"})
        if len(exp_norm) == len(obs_norm) and exp_norm.translate(trans) == obs_norm.translate(trans):
            return ("REVIEW", seq_score, "Potensi perbedaan karakter OCR (0/O, 1/I); periksa model.")
        if is_token_subset_model(exp, obs):
            return (
                "REVIEW",
                seq_score,
                "Tipe alat parsial pada dokumen; perlu verifikasi visual",
            )
        return ("MISMATCH", seq_score, "Kode model berbeda.")

    if field_key.startswith("nomor_seri"):
        if exp_norm == obs_norm:
            return ("MATCH", 100.0, "")
        if _ocr_serial_key(exp) and _ocr_serial_key(exp) == _ocr_serial_key(obs):
            return ("REVIEW", seq_score, "Kemungkinan ambiguitas karakter OCR pada nomor seri; periksa visual.")
        return ("MISMATCH", seq_score, "Nomor seri berbeda.")

    return ("REVIEW", seq_score, "")


def _quote_grounded(quote: str, page_text: str) -> bool:
    q_comp = compact(quote).casefold()
    p_comp = compact(page_text).casefold()
    if len(q_comp) < 4:
        return False
    if q_comp in p_comp:
        return True
    segments = [
        compact(seg).casefold()
        for seg in re.split(r"\s*(?:\.\.\.+|\||[\r\n]+)\s*", str(quote or ""))
        if len(compact(seg)) >= 4
    ]
    return bool(segments) and all(seg in p_comp for seg in segments)


def _value_grounded(value: str, page_text: str) -> bool:
    v = _space(value)
    if _absent(v):
        return False
    vn = norm(v)
    pn = norm(page_text)
    if len(vn) >= 2 and vn in pn:
        return True
    toks = [t for t in _tokens(v) if len(t) >= 2]
    if not toks:
        return False
    p_low = _space(page_text).casefold()
    return all(t in p_low for t in toks)


def _in_detector_only_context(value: str, page_text: str) -> bool:
    """Reject values that appear ONLY next to detector/surveymeter labels."""
    toks = _tokens(value)
    if not toks:
        return True
    pat = re.compile(r"(?is)" + r"[^a-z0-9]{0,4}".join(map(re.escape, toks)))
    matches = list(pat.finditer(page_text))
    if not matches:
        # Fallback on compact text when spacing/punctuation differs.
        return False
    detector_hits = 0
    target_hits = 0
    for m in matches:
        # Look only backward on a bounded window before the match.
        before = page_text[max(0, m.start() - 80) : m.start()]
        det_matches = list(_DETECTOR_CONTEXT_RE.finditer(before))
        tgt_matches = list(_TARGET_CONTEXT_RE.finditer(before))
        det_pos = det_matches[-1].end() if det_matches else -1
        tgt_pos = tgt_matches[-1].end() if tgt_matches else -1
        if det_pos > tgt_pos:
            detector_hits += 1
        elif tgt_pos >= 0:
            target_hits += 1
    return detector_hits > 0 and target_hits == 0 and detector_hits == len(matches)


def _is_contractor_or_oem(value: str, page_text: str) -> bool:
    val = _space(value)
    if not val:
        return True
    if _CONTRACTOR_HINT_RE.search(val):
        return True
    val_norm = norm(val)
    for line in page_text.splitlines():
        if val_norm and val_norm in norm(line):
            if _CONTRACTOR_HINT_RE.search(line) and not re.search(
                r"(?i)\b(?:pelanggan|pemohon|pemilik|tested\s+unit|hospital|klinik|rumah\s+sakit)\b",
                line,
            ):
                return True
            if re.search(r"(?i)\b(?:nama\s+perusahaan\s*/\s*importir|identitas\s+penguji|entrusting)\b", line):
                return True
    return False


def _run_tesseract_png(png_bytes: bytes) -> str:
    import subprocess

    for psm in ("3", "6"):
        res = subprocess.run(
            [
                os.getenv("BAPETEN_TESSERACT_CMD") or "tesseract",
                "stdin",
                "stdout",
                "-l",
                os.getenv("BAPETEN_TESS_LANG") or "ind+eng",
                "--psm",
                psm,
            ],
            input=png_bytes,
            capture_output=True,
            timeout=30,
            env={**os.environ, "OMP_THREAD_LIMIT": "2"},
        )
        if res.returncode == 0:
            txt = res.stdout.decode("utf-8", errors="replace").strip()
            if len(re.sub(r"\s+", "", txt)) >= 20 or psm == "6":
                return txt
    return ""


def read_exposure_pages(path: str) -> list[dict]:
    """Read exposure/leakage/functional document pages (PDF or image) with OCR fallback."""
    lower = str(path).lower()
    if lower.endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")):
        try:
            import io
            from PIL import Image, ImageOps

            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                txt = _run_tesseract_png(buf.getvalue())
            return [{"page": 1, "text": txt, "source": "ocr"}] if txt else []
        except Exception:
            return []

    if not lower.endswith(".pdf"):
        return []
    import fitz

    from .protection.reader import _merge_native_and_ocr

    pages: list[dict] = []
    ocr_budget = 6
    with fitz.open(path) as doc:
        num = len(doc)
        priority_indices = sorted(set(range(min(num, 4))) | ({num - 1} if num > 0 else set()))
        for idx in range(num):
            page = doc[idx]
            native = (page.get_text("text", sort=True) or "").strip()
            text = native
            source = "text"
            page_area = page.rect.get_area() or 1.0
            images = [
                x
                for x in page.get_image_info()
                if (x["bbox"][2] - x["bbox"][0]) * (x["bbox"][3] - x["bbox"][1]) > page_area * 0.08
            ]
            large_scan = any(
                (x["bbox"][2] - x["bbox"][0]) * (x["bbox"][3] - x["bbox"][1]) >= page_area * 0.30
                for x in images
            )
            native_chars = len(re.sub(r"\s+", "", native))
            needs_ocr = native_chars < 100 or large_scan or (images and native_chars < 600)
            if needs_ocr and (idx in priority_indices or ocr_budget > 0) and ocr_budget > 0:
                ocr_budget -= 1
                try:
                    png = page.get_pixmap(dpi=180, alpha=False).tobytes("png")
                    ocr_txt = _run_tesseract_png(png)
                    if ocr_txt:
                        text = _merge_native_and_ocr(native, ocr_txt)
                        source = "ocr"
                except Exception:
                    pass
            pages.append({"page": idx + 1, "text": text, "source": source})
    return pages


def _prioritize_pages(pages: list[dict], expected_refs: list[dict]) -> list[dict]:
    tokens = []
    for ref in expected_refs or []:
        for k in ("nomor_seri_unit", "tipe_unit", "nomor_seri_tabung"):
            v = norm(ref.get(k))
            if len(v) >= 4:
                tokens.append(v)

    def rank(pg):
        txt = pg.get("text") or ""
        n_txt = norm(txt)
        score = len(_PAGE_CUE_RE.findall(txt)) * 2
        if any(tok in n_txt for tok in tokens):
            score += 20
        if pg.get("page") == 1:
            score += 5
        return (-score, int(pg.get("page") or 0))

    return [p for p in sorted(pages, key=rank) if _space(p.get("text"))]


def extract_exposure_llm(
    pages: list[dict],
    needed_targets: set[str],
    expected_refs: list[dict] | None = None,
) -> tuple[list[dict], bool]:
    """Run bounded local Qwen fallback to extract grounded exposure report fields."""
    if not pages or not needed_targets:
        return [], False

    record_schema = {
        "type": "object",
        "properties": {
            "page": {"type": "integer"},
            "quote": {"type": "string"},
            "facility_name": {"type": "string"},
            "facility_address": {"type": "string"},
            "merk_unit": {"type": "string"},
            "tipe_unit": {"type": "string"},
            "nomor_seri_unit": {"type": "string"},
            "merk_tabung": {"type": "string"},
            "tipe_tabung": {"type": "string"},
            "nomor_seri_tabung": {"type": "string"},
            "approval_quote": {"type": "string"},
        },
        "required": [
            "page",
            "quote",
            "facility_name",
            "facility_address",
            "merk_unit",
            "tipe_unit",
            "nomor_seri_unit",
            "merk_tabung",
            "tipe_tabung",
            "nomor_seri_tabung",
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
        "Teks berasal dari dokumen uji paparan radiasi atau uji kebocoran tabung "
        "(dapat berbahasa Indonesia atau Inggris, baik laporan uji lokal maupun sertifikat survei pabrik). "
        f"Field yang masih perlu dicek: {', '.join(sorted(needed_targets))}. "
        "Salin nilai PERSIS seperti tertulis pada dokumen; jangan mengarang atau mengubah karakter. "
        "Isi string kosong \"\" jika field tidak tercantum pada halaman. "
        "Untuk tipe_unit: ambil kode model/tipe spesifik yang tertulis di kolom atau label 'Instrument Model', 'Equipment Model', 'Tipe/Model', 'Model', atau 'Tipe' "
        "(contoh: 'DXL 800', 'TrueX', 'TrueX G5'), JANGAN mengambil Equipment Name atau kategori umum jenis alat seperti 'Portable XRF Analyzers', 'X-ray fluorescence spectrometer', atau 'Pesawat Sinar-X'. "
        "PENTING - Bedakan PESAWAT/UNIT X-RAY yang diuji vs ALAT UKUR (Detector / Surveymeter / Dose Rate Instrument / Calibrator): "
        "JANGAN PERNAH menyalin model atau nomor seri detector/surveymeter/alat ukur (mis. Detector Model, Detector S/N, Alat Ukur, Testing equipment) ke kolom unit maupun tabung. "
        "PENTING - Bedakan PEMOHON/FASILITAS LOKAL vs PABRIKAN/PENGUJI: jangan menyalin nama atau alamat footer pabrikan maupun laboratorium penguji ke facility_name atau facility_address; bila dokumen adalah sertifikat pabrik tanpa fasilitas pemohon, biarkan facility_name dan facility_address kosong \"\". "
        "Untuk approval_quote: kutip baris penanggung jawab/pelaksana/pengesahan uji (mis. 'Conducted by: ...', 'Checked by: ...', 'Approved by: ...', 'Mengetahui ...', 'Disahkan ...', 'Penguji Paparan Radiasi ...'). "
        "quote wajib merupakan kutipan persis (maksimal 260 karakter) dari halaman tersebut yang mendukung nilai record."
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
                "Ekstraksi identitas alat, fasilitas pemohon, dan pengesahan dokumen uji paparan/kebocoran",
                window,
                instructions,
                output_limit=900,
            )
        except Exception:
            warning = True
            break

        for item in proposed:
            if not isinstance(item, dict):
                continue
            pg_num = item.get("page")
            if pg_num != page["page"]:
                continue
            quote = _space(item.get("quote"))
            if quote and not _quote_grounded(quote, text):
                continue

            cleaned: dict[str, object] = {"page": pg_num, "quote": quote}
            has_any = False

            for eq_key in EQUIPMENT_FIELDS:
                val = _space(item.get(eq_key))
                if not _value_grounded(val, text):
                    continue
                if _in_detector_only_context(val, text):
                    continue
                if eq_key in ("tipe_unit", "tipe_tabung") and _is_generic_device_noun(val):
                    continue
                # Never allow an explicit 'Model: <val>' (e.g. 'Equipment Model: TrueX') into nomor_seri_*.
                if eq_key in ("nomor_seri_unit", "nomor_seri_tabung") and _has_model_only_label(val, text):
                    target_type = "tipe_unit" if eq_key == "nomor_seri_unit" else "tipe_tabung"
                    if not cleaned.get(target_type) and not _is_generic_device_noun(val):
                        cleaned[target_type] = val
                        has_any = True
                    continue
                cleaned[eq_key] = val
                has_any = True

            for fac_key in ("facility_name", "facility_address"):
                val = _space(item.get(fac_key))
                if not _value_grounded(val, text):
                    continue
                if _is_contractor_or_oem(val, text):
                    continue
                cleaned[fac_key] = val
                has_any = True

            app_val = _space(item.get("approval_quote"))
            if _value_grounded(app_val, text) and _SIGNOFF_CUE_RE.search(app_val):
                cleaned["approval_quote"] = app_val
                has_any = True

            if "tipe_unit" in needed_targets and not cleaned.get("tipe_unit"):
                explicit_model = _extract_explicit_labeled_model(text)
                if explicit_model:
                    cleaned["tipe_unit"] = explicit_model
                    has_any = True

            if has_any:
                grounded_records.append(cleaned)

        # Early exit when unit identity or all needed targets are found.
        if grounded_records:
            found_keys = {k for r in grounded_records for k in r if k not in ("page", "quote")}
            if needed_targets <= found_keys:
                break

    return grounded_records, warning


def _match_field_key(field_name: str) -> str | None:
    low = _space(field_name).casefold()
    if "merek unit" in low or "merk unit" in low:
        return "merk_unit"
    if "tipe unit" in low:
        return "tipe_unit"
    if "seri unit" in low:
        return "nomor_seri_unit"
    if "merek tabung" in low or "merk tabung" in low:
        return "merk_tabung"
    if "tipe tabung" in low:
        return "tipe_tabung"
    if "seri insersi" in low or "seri tabung" in low:
        return "nomor_seri_tabung"
    return None


def _choose_record_and_form_idx(
    records: list[dict], equipments: list[dict]
) -> tuple[int, dict | None]:
    if not equipments or not records:
        return 0, records[0] if records else None
    if len(equipments) == 1:
        # Merge fields across grounded pages if spread out.
        merged: dict = {"page": records[0]["page"], "quote": records[0].get("quote", "")}
        for rec in records:
            for k, v in rec.items():
                if k in ("page", "quote"):
                    continue
                if v and not merged.get(k):
                    merged[k] = v
                    merged.setdefault(f"{k}_page", rec["page"])
                    merged.setdefault(f"{k}_quote", rec.get("quote") or v)
        return 0, merged

    # Multiple reference equipments: select ONLY by unique exact unit/tube serial.
    for idx, eq in enumerate(equipments):
        u_sn = norm(eq.get("nomor_seri_unit"))
        t_sn = norm(eq.get("nomor_seri_tabung"))
        hits = [
            rec
            for rec in records
            if (u_sn and norm(rec.get("nomor_seri_unit")) == u_sn)
            or (t_sn and norm(rec.get("nomor_seri_tabung")) == t_sn)
        ]
        if len(hits) == 1:
            return idx, hits[0]
    return 0, None


def enrich_exposure_rows(doc: dict, app: dict, path: str, raw: dict) -> tuple[dict, bool]:
    """Run bounded Qwen fallback if deterministic exposure matching left gaps."""
    raw_rows = list(raw.get("rows") or [])
    equipments = list(app.get("equipment") or [])
    needed: set[str] = set()

    # Track status of facility & approval rows.
    for row in raw_rows:
        fname = _space(row.get("field")).casefold()
        obs = row.get("observed")
        stat = row.get("status")
        if "nama fasilitas" in fname and (_absent(obs) or stat != "MATCH"):
            needed.add("facility_name")
        elif "alamat fasilitas" in fname and (_absent(obs) or stat != "MATCH"):
            needed.add("facility_address")
        elif "pengesahan" in fname and stat != "MATCH":
            needed.add("approval_quote")
        elif fname.startswith("pemilihan peralatan") and _absent(obs):
            needed.update({"merk_unit", "tipe_unit", "nomor_seri_unit"})

    # Track equipment rows from reference form.
    eq_rows_by_key = {}
    for row in raw_rows:
        ekey = _match_field_key(row.get("field") or "")
        if ekey:
            eq_rows_by_key[ekey] = row
    if equipments:
        ref_eq = equipments[0]
        for ekey in EQUIPMENT_FIELDS:
            if not _absent(ref_eq.get(ekey)):
                existing = eq_rows_by_key.get(ekey)
                if existing is None or _absent(existing.get("observed")) or existing.get("status") != "MATCH":
                    needed.add(ekey)

    if not needed:
        return raw, False

    pages = read_exposure_pages(path)
    records, warning = extract_exposure_llm(pages, needed, equipments)
    if not records:
        return raw, warning

    eq_idx, chosen = _choose_record_and_form_idx(records, equipments)

    # Update approval row if still unresolved.
    approval_hit = next((r for r in records if r.get("approval_quote")), None)
    if approval_hit:
        for row in raw_rows:
            if "pengesahan" in _space(row.get("field")).casefold() and row.get("status") != "MATCH":
                pg = approval_hit["page"]
                q = approval_hit.get("approval_quote") or approval_hit.get("quote") or ""
                row.update(
                    {
                        "observed": f"Halaman {pg}",
                        "status": "MATCH",
                        "score": 100,
                        "page": pg,
                        "quote": q,
                        "reason": "Blok pelaksana/pengesahan uji ditemukan (Qwen); tanda tangan tetap diperiksa secara visual",
                        "evidence": [{"page": pg, "quote": q}],
                    }
                )

    # Update facility / address rows only when previously absent.
    if chosen:
        from src.matching.suitability_matcher import compare_institution

        for row in raw_rows:
            fname = _space(row.get("field")).casefold()
            if "nama fasilitas" in fname and _absent(row.get("observed")) and chosen.get("facility_name"):
                obs = chosen["facility_name"]
                exp = row.get("expected") or ""
                comp = compare_institution(exp, obs) if exp else {"status": "REVIEW", "score": None}
                pg = chosen.get("facility_name_page") or chosen["page"]
                q = chosen.get("facility_name_quote") or chosen.get("quote") or obs
                row.update(
                    {
                        "observed": obs,
                        "status": comp.get("status", "REVIEW"),
                        "score": comp.get("score"),
                        "page": pg,
                        "quote": q,
                        "reason": "Terbaca melalui bantuan Qwen dari teks dokumen",
                        "evidence": [{"page": pg, "quote": q}],
                    }
                )
            elif "alamat fasilitas" in fname and _absent(row.get("observed")) and chosen.get("facility_address"):
                obs = chosen["facility_address"]
                pg = chosen.get("facility_address_page") or chosen["page"]
                q = chosen.get("facility_address_quote") or chosen.get("quote") or obs
                row.update(
                    {
                        "observed": obs,
                        "status": "REVIEW",
                        "score": None,
                        "page": pg,
                        "quote": q,
                        "reason": "Terbaca melalui bantuan Qwen dari teks dokumen",
                        "evidence": [{"page": pg, "quote": q}],
                    }
                )

    # Enrich equipment rows if a single device matched cleanly.
    if chosen and equipments:
        target_eq = equipments[eq_idx]
        # Drop ambiguous selection prompt when Qwen resolved unique device by serial.
        raw_rows = [
            r for r in raw_rows if not _space(r.get("field")).casefold().startswith("pemilihan peralatan")
        ]
        # Re-index existing equipment rows for chosen device.
        existing_map = {
            _match_field_key(r.get("field") or ""): r
            for r in raw_rows
            if _match_field_key(r.get("field") or "")
        }
        for ekey in EQUIPMENT_FIELDS:
            expected_val = _space(target_eq.get(ekey))
            if not expected_val:
                continue
            llm_val = _space(chosen.get(ekey))
            if _absent(llm_val):
                continue
            pg = chosen.get(f"{ekey}_page") or chosen["page"]
            q = chosen.get(f"{ekey}_quote") or chosen.get("quote") or llm_val
            existing = existing_map.get(ekey)
            if existing is not None and existing.get("status") == "MATCH":
                continue
            if existing is not None and not _absent(existing.get("observed")):
                if not (
                    ekey in ("tipe_unit", "tipe_tabung")
                    and _is_generic_device_noun(existing.get("observed"))
                ):
                    continue
            status, score, note = evaluate_exposure_field(ekey, expected_val, llm_val)
            reason = note or "Terbaca melalui bantuan Qwen dari teks dokumen"
            if existing is not None:
                existing.update(
                    {
                        "observed": llm_val,
                        "status": status,
                        "score": score,
                        "page": pg,
                        "quote": q,
                        "reason": reason,
                        "evidence": [{"page": pg, "quote": q}],
                    }
                )
            else:
                new_row = {
                    "field": f"Alat {eq_idx + 1}: {FIELD_LABELS[ekey]}",
                    "expected": expected_val,
                    "observed": llm_val,
                    "status": status,
                    "score": score,
                    "page": pg,
                    "quote": q,
                    "reason": reason,
                    "evidence": [{"page": pg, "quote": q}],
                }
                # Insert before Pengesahan row so field ordering stays natural.
                signoff_idx = next(
                    (
                        i
                        for i, r in enumerate(raw_rows)
                        if "pengesahan" in _space(r.get("field")).casefold()
                    ),
                    len(raw_rows),
                )
                raw_rows.insert(signoff_idx, new_row)

    return {**raw, "rows": raw_rows}, warning


def enrich_functional_rows(doc: dict, app: dict, path: str, rows: list[dict]) -> tuple[list[dict], bool]:
    """Run bounded Qwen fallback for functional / acceptance / calibration reports."""
    equipments = list(app.get("equipment") or [])
    needed: set[str] = set()
    rows = list(rows or [])

    for row in rows:
        fname = _space(row.get("field")).casefold()
        obs = row.get("observed")
        stat = row.get("status")
        if "nama fasilitas" in fname and (_absent(obs) or stat != "MATCH"):
            needed.add("facility_name")
        elif "alamat fasilitas" in fname and (_absent(obs) or stat != "MATCH"):
            needed.add("facility_address")

    eq_rows_by_key = {}
    for row in rows:
        ekey = _match_field_key(row.get("field") or "")
        if ekey:
            eq_rows_by_key[ekey] = row

    if equipments:
        ref_eq = equipments[0]
        for ekey in EQUIPMENT_FIELDS:
            if not _absent(ref_eq.get(ekey)):
                existing = eq_rows_by_key.get(ekey)
                if existing is None or _absent(existing.get("observed")) or existing.get("status") != "MATCH":
                    needed.add(ekey)

    if not needed:
        return rows, False

    pages = read_exposure_pages(path)
    records, warning = extract_exposure_llm(pages, needed, equipments)
    if not records:
        return rows, warning

    eq_idx, chosen = _choose_record_and_form_idx(records, equipments)
    if not chosen:
        return rows, warning

    from .analysis.rows import _row as build_row
    from .analysis.constants import FIELDS as DISPLAY_FIELDS
    from src.matching.suitability_matcher import compare_institution

    full_text = "\n".join(p.get("text") or "" for p in pages)

    # Enrich facility name / address only when empty/MISSING or currently pointing to contractor/surveymeter.
    for row_idx, row in enumerate(rows):
        fname = _space(row.get("field")).casefold()
        obs_empty = _absent(row.get("observed")) or row.get("status") == "MISSING"
        if "nama fasilitas" in fname and obs_empty and chosen.get("facility_name"):
            obs = chosen["facility_name"]
            exp = "" if _absent(row.get("expected")) else row["expected"]
            comp = compare_institution(exp, obs) if exp else {"status": "REVIEW", "score": None}
            pg = chosen.get("facility_name_page") or chosen["page"]
            q = chosen.get("facility_name_quote") or chosen.get("quote") or obs
            rows[row_idx] = build_row(
                row["field"],
                exp,
                obs,
                comp.get("status", "REVIEW"),
                comp.get("score"),
                pg,
                "Terbaca melalui bantuan Qwen dari teks dokumen",
                doc["id"],
                q,
            )
        elif "alamat fasilitas" in fname and obs_empty and chosen.get("facility_address"):
            obs = chosen["facility_address"]
            exp = "" if _absent(row.get("expected")) else row["expected"]
            pg = chosen.get("facility_address_page") or chosen["page"]
            q = chosen.get("facility_address_quote") or chosen.get("quote") or obs
            rows[row_idx] = build_row(
                row["field"],
                exp,
                obs,
                "REVIEW",
                None,
                pg,
                "Terbaca melalui bantuan Qwen dari teks dokumen",
                doc["id"],
                q,
            )

    if equipments:
        target_eq = equipments[eq_idx]
        # Replace placeholder fallback row when actual equipment identity is recovered.
        rows = [r for r in rows if _space(r.get("field")).casefold() != "identitas alat"]
        existing_idx_map = {
            _match_field_key(r.get("field") or ""): i
            for i, r in enumerate(rows)
            if _match_field_key(r.get("field") or "")
        }
        for ekey in EQUIPMENT_FIELDS:
            expected_val = _space(target_eq.get(ekey))
            if not expected_val:
                continue
            llm_val = _space(chosen.get(ekey))
            if _absent(llm_val):
                continue
            pg = chosen.get(f"{ekey}_page") or chosen["page"]
            q = chosen.get(f"{ekey}_quote") or chosen.get("quote") or llm_val
            r_idx = existing_idx_map.get(ekey)
            if r_idx is not None:
                cur = rows[r_idx]
                cur_obs = _space(cur.get("observed"))
                is_empty = _absent(cur_obs) or cur.get("status") == "MISSING"
                is_detector_false_hit = (
                    cur.get("status") != "MATCH"
                    and not is_empty
                    and (
                        _in_detector_only_context(cur_obs, full_text)
                        or (ekey in ("tipe_unit", "tipe_tabung") and _is_generic_device_noun(cur_obs))
                    )
                )
                if cur.get("status") == "MATCH" or (not is_empty and not is_detector_false_hit):
                    continue
                status, score, note = evaluate_exposure_field(ekey, expected_val, llm_val)
                rows[r_idx] = build_row(
                    f"Alat {eq_idx + 1}: {DISPLAY_FIELDS[ekey]}",
                    expected_val,
                    llm_val,
                    status,
                    score,
                    pg,
                    note or "Terbaca melalui bantuan Qwen dari teks dokumen",
                    doc["id"],
                    q,
                )
            else:
                status, score, note = evaluate_exposure_field(ekey, expected_val, llm_val)
                rows.append(
                    build_row(
                        f"Alat {eq_idx + 1}: {DISPLAY_FIELDS[ekey]}",
                        expected_val,
                        llm_val,
                        status,
                        score,
                        pg,
                        note or "Terbaca melalui bantuan Qwen dari teks dokumen",
                        doc["id"],
                        q,
                    )
                )

    return rows, warning

