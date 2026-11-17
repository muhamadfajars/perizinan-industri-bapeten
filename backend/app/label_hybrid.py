"""Hybrid sticker/photo OCR rescue and bounded Qwen extraction for equipment labels."""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import storage
from .analysis.constants import FIELDS
from .protection import llm
from .protection.extraction import compact, norm

_FIELD_KEYS = tuple(FIELDS.keys())
_RESCUE_TIMEOUT_SECONDS = 8

_BANNED_STOP_COMPACT = {
    "EQUIPMENT",
    "THISEQUIPMENT",
    "RADIATION",
    "CAUTION",
    "CAUTIONRADIATION",
    "WARNING",
    "DANGER",
    "WHENENERGIZED",
    "PRODUCESRADIATION",
    "PRODUCESRADIATIONWHENENERGIZED",
    "THISEQUIPMENTPRODUCESRADIATIONWHENENERGIZED",
    "DONOT",
    "DISASSEMBLE",
    "DISASSEMBLEUNIT",
    "DONOTDISASSEMBLE",
    "DONOTDISASSEMBLEUNIT",
    "ANALYZER",
    "PRECIOUSMETAL",
    "PRECIOUSMETALANALYZER",
    "PRECIOUSMETALANAIYZER",
    "PRECIOUSMETALANAIYZES",
    "XRAY",
    "XRAYON",
    "XRAYUNIT",
    "XRAYTUBE",
    "SERIAL",
    "SERNO",
    "SERIALNO",
    "SERIALNUMBER",
    "SN",
    "MODEL",
    "TYPE",
    "TIPE",
    "DATE",
    "FIRMWARE",
    "FIRMWAREREV",
    "THIS",
    "UNIT",
    "TUBE",
    "COSPIN",
    "COSPN",
    "PN",
}


def _is_meaningful_line(text: str) -> bool:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text or "")
    return len(cleaned) >= 2


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    return inter / float(aw * ah + bw * bh - inter)


def _sticker_crops(image) -> list[Any]:
    """Locate candidate bright-white or caution-yellow sticker/housing regions."""
    import cv2
    import numpy as np

    if image is None or not hasattr(image, "shape"):
        return []
    h, w = image.shape[:2]
    total = max(1, h * w)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    specs = (
        (cv2.inRange(hsv, (0, 0, 175), (180, 45, 255)), 0.45),
        (cv2.inRange(hsv, (15, 70, 110), (38, 255, 255)), 0.55),
    )
    k_open = np.ones((7, 7), np.uint8)
    k_close = np.ones((15, 15), np.uint8)
    boxes = []
    for mask, max_frac in specs:
        cleaned = cv2.morphologyEx(
            cv2.morphologyEx(mask, cv2.MORPH_OPEN, k_open),
            cv2.MORPH_CLOSE,
            k_close,
        )
        _, _, stats, _ = cv2.connectedComponentsWithStats(cleaned)
        for x, y, cw, ch, area in stats[1:]:
            box_area = cw * ch
            if not (0.004 * total <= box_area <= max_frac * total):
                continue
            if area < 0.45 * box_area or min(cw, ch) < 28:
                continue
            boxes.append((int(x), int(y), int(cw), int(ch), int(box_area)))

    # Keep top distinct sticker regions by size to bound CPU time.
    boxes.sort(key=lambda b: b[4], reverse=True)
    crops = []
    for x, y, cw, ch, _ in boxes[:4]:
        ya, yb = max(0, y - 8), min(h, y + ch + 8)
        xa, xb = max(0, x - 8), min(w, x + cw + 8)
        crops.append(image[ya:yb, xa:xb])
    return crops


def _text_region_crops(image) -> list[tuple[Any, float, str]]:
    """General detector for metallic plates, tilted housing logos, and dark bezels."""
    import cv2
    import numpy as np

    if image is None or not hasattr(image, "shape"):
        return []
    h, w = image.shape[:2]
    total = max(1, h * w)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    max_rgb = np.max(image, axis=2) if image.ndim == 3 else gray

    results: list[tuple[Any, float, str]] = []
    seen_boxes: list[tuple[int, int, int, int]] = []

    def _keep_box(box: tuple[int, int, int, int]) -> bool:
        if any(_iou(box, s) > 0.55 for s in seen_boxes):
            return False
        seen_boxes.append(box)
        return True

    # 1. Dark text on metallic/gray/light plates and equipment housings (blackhat).
    bh = cv2.morphologyEx(
        gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (19, 19))
    )
    _, bw_bh = cv2.threshold(bh, 26, 255, cv2.THRESH_BINARY)
    closed_bh = cv2.morphologyEx(
        bw_bh, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (29, 19))
    )
    contours, _ = cv2.findContours(closed_bh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    compact_plates = []
    tilted_strips = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        box_area = cw * ch
        if box_area < 0.0008 * total or box_area > 0.38 * total:
            continue
        density = float(np.count_nonzero(bw_bh[y : y + ch, x : x + cw])) / max(1, box_area)
        if density < 0.04:
            continue
        aspect = max(cw, ch) / max(1.0, min(cw, ch))
        if 0.003 * total <= box_area and min(cw, ch) >= 24 and aspect <= 5.5:
            compact_plates.append((x, y, cw, ch, box_area * density))
        rect = cv2.minAreaRect(cnt)
        (cx, cy), (rw, rh), angle = rect
        if rw < rh:
            angle += 90.0
            rw, rh = rh, rw
        if (
            rw / max(1.0, rh) >= 2.1
            and 0.0008 * total <= box_area <= 0.08 * total
            and 14 <= rh <= 0.18 * max(h, w)
        ):
            angled_bonus = 2.0 if 3.0 <= abs(angle) <= 45.0 else 1.0
            tilted_strips.append((x, y, cw, ch, box_area * density * angled_bonus, cx, cy, rw, rh, angle))

    compact_plates.sort(key=lambda b: b[4], reverse=True)
    for x, y, cw, ch, _ in compact_plates[:2]:
        if _keep_box((x, y, cw, ch)):
            xa, xb = max(0, x - 12), min(w, x + cw + 12)
            ya, yb = max(0, y - 12), min(h, y + ch + 12)
            plate_crop = gray[ya:yb, xa:xb]
            blur = cv2.GaussianBlur(plate_crop, (0, 0), 1.5)
            sharp_plate = cv2.addWeighted(plate_crop, 1.5, blur, -0.5, 0)
            results.append((sharp_plate, 2.5, "plate"))

    tilted_strips.sort(key=lambda b: b[4], reverse=True)
    for x, y, cw, ch, _, cx, cy, rw, rh, angle in tilted_strips[:2]:
        if 3.0 <= abs(angle) <= 45.0:
            rot_mat = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
            rotated = cv2.warpAffine(
                gray, rot_mat, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
            )
            px, py = int(rw * 0.14) + 10, int(rh * 0.38) + 10
            xa, xb = max(0, int(cx - rw / 2 - px)), min(w, int(cx + rw / 2 + px))
            ya, yb = max(0, int(cy - rh / 2 - py)), min(h, int(cy + rh / 2 + py))
            if xb > xa + 15 and yb > ya + 10:
                results.append((rotated[ya:yb, xa:xb], 2.6, "deskew"))
        elif _keep_box((x, y, cw, ch)):
            xa, xb = max(0, x - 12), min(w, x + cw + 12)
            ya, yb = max(0, y - 12), min(h, y + ch + 12)
            results.append((gray[ya:yb, xa:xb], 2.5, "strip"))

    # 2. Bright or saturated-color text on dark housings/bezels (tophat on max RGB channel).
    th = cv2.morphologyEx(
        max_rgb, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    )
    _, bw_th = cv2.threshold(th, 28, 255, cv2.THRESH_BINARY)
    closed_th = cv2.morphologyEx(
        bw_th, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (27, 21))
    )
    _, _, stats, _ = cv2.connectedComponentsWithStats(closed_th)
    th_boxes = []
    for x, y, cw, ch, _ in stats[1:]:
        box_area = cw * ch
        if not (0.0015 * total <= box_area <= 0.35 * total) or min(cw, ch) < 16:
            continue
        density = float(np.count_nonzero(bw_th[y : y + ch, x : x + cw])) / max(1, box_area)
        if density < 0.04:
            continue
        th_boxes.append((int(x), int(y), int(cw), int(ch), box_area * density))
    th_boxes.sort(key=lambda b: b[4], reverse=True)
    for x, y, cw, ch, _ in th_boxes[:2]:
        xa, xb = max(0, x - 18), min(w, x + cw + 18)
        pad_top = max(32, int(0.45 * ch) + 12)
        ya, yb = max(0, y - pad_top), min(h, y + ch + 24)
        sub_max = max_rgb[ya:yb, xa:xb]
        if float(np.median(sub_max)) < 115.0:
            results.append((255 - sub_max, 2.8, "dark_logo"))

    return results


def _upscale_gray(image, target_scale: float = 2.0, max_side_cap: float = 1500.0):
    import cv2

    h, w = image.shape[:2]
    max_side = max(h, w, 1)
    scale = min(target_scale, max_side_cap / max_side)
    if scale > 1.05:
        resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    else:
        resized = image
    return cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) if resized.ndim == 3 else resized


def _keep_ocr_line(words: list[str], confs: list[float], strict_noise: bool = False) -> str | None:
    line = compact(" ".join(words))
    alnum = re.sub(r"[^A-Za-z0-9]", "", line)
    if len(alnum) < 3:
        return None
    if len(alnum) / max(1, len(line.replace(" ", ""))) < 0.60:
        return None
    if len(words) >= 4 and sum(len(x) <= 2 for x in words) / len(words) > 0.5:
        return None
    avg_conf = sum(confs) / len(confs)
    if avg_conf < 42 and len(alnum) < 5:
        return None
    if strict_noise:
        has_digit = bool(re.search(r"\d", alnum))
        has_upper = bool(re.search(r"[A-Z]", alnum))
        if not has_digit and len(alnum) <= 4 and not has_upper and avg_conf < 68:
            return None
        if len(words) >= 3 and not has_digit and avg_conf < 58:
            short_lower = sum(1 for x in words if len(re.sub(r"[^A-Za-z]", "", x)) <= 3)
            if short_lower / len(words) > 0.6:
                return None
    return line


def _orientations_for_crop(gray, kind: str) -> list[Any]:
    import cv2

    # Deskewed strips were already rotated to horizontal via minAreaRect.
    if "deskew" in kind:
        return [gray, cv2.rotate(gray, cv2.ROTATE_180)]
    return [
        gray,
        cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE),
        cv2.rotate(gray, cv2.ROTATE_180),
        cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE),
    ]


def _append_adjacent_pairs(lines: list[str]) -> list[str]:
    """Preserve consecutive two-line phrases (e.g. stacked 'Thermo' + 'SCIENTIFIC')."""
    combined = list(lines)
    clean_indices = [
        i
        for i, ln in enumerate(lines)
        if re.fullmatch(r"[A-Za-z0-9#./\- ]{3,24}", ln)
        and "X-RAY ON" not in ln.upper()
        and "RAYON" not in ln.upper()
    ]
    for pos, i in enumerate(clean_indices):
        for nxt in clean_indices[pos + 1 : pos + 3]:
            if nxt - i > 2:
                break
            left, right = lines[i], lines[nxt]
            la = re.sub(r"[^A-Za-z0-9]", "", left)
            rb = re.sub(r"[^A-Za-z0-9]", "", right)
            if not (3 <= len(la) <= 22 and 3 <= len(rb) <= 22):
                continue
            if norm(left) == norm(right):
                continue
            if re.search(r"[A-Za-z]{3}", left) and re.search(r"[A-Za-z0-9]{3}", right):
                combined.append(f"{left} {right}")
    return combined


def _ocr_single_rotation_tesseract(rot, psms: tuple[int, ...], tess_cmd: str) -> list[str]:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = tess_cmd
    out: list[str] = []
    lang = os.getenv("BAPETEN_TESS_LANG", "eng")
    for psm in psms:
        try:
            data = pytesseract.image_to_data(
                rot,
                lang=lang,
                config=f"--psm {psm}",
                output_type=pytesseract.Output.DICT,
                timeout=_RESCUE_TIMEOUT_SECONDS,
            )
        except Exception:
            continue
        grouped_words: dict[tuple[int, int, int], list[str]] = {}
        grouped_confs: dict[tuple[int, int, int], list[float]] = {}
        for i in range(len(data.get("text", []))):
            word = str(data["text"][i] or "").strip()
            if not word:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                continue
            if conf < 38:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            grouped_words.setdefault(key, []).append(word)
            grouped_confs.setdefault(key, []).append(conf)
        rot_lines: list[str] = []
        for key, words in grouped_words.items():
            txt = _keep_ocr_line(words, grouped_confs[key], strict_noise=True)
            if txt:
                rot_lines.append(txt)
        out.extend(_append_adjacent_pairs(rot_lines))
    return out


def _ocr_gray_rotations(gray, psms: tuple[int, ...] = (6, 11), kind: str = "sticker_rescue") -> list[str]:
    from src.extraction import label_ocr

    _, mode = label_ocr.create_ocr()
    lines: list[str] = []
    seen: set[str] = set()
    rotations = _orientations_for_crop(gray, kind)
    if mode.startswith("paddle"):
        for rot in rotations:
            bgr = label_ocr.ensure_bgr(rot)
            rot_lines = []
            for row in label_ocr.extract_ocr(bgr):
                txt = compact(row.get("text"))
                if _is_meaningful_line(txt):
                    rot_lines.append(txt)
            for txt in _append_adjacent_pairs(rot_lines):
                nkey = norm(txt)
                if nkey and nkey not in seen:
                    seen.add(nkey)
                    lines.append(txt)
        return lines

    tess_cmd = label_ocr._tess_cmd()
    for rot in rotations:
        for txt in _ocr_single_rotation_tesseract(rot, psms, tess_cmd):
            nkey = norm(txt)
            if nkey and nkey not in seen:
                seen.add(nkey)
                lines.append(txt)
    return lines


def _extract_document_images(path: Path) -> list[tuple[int, Any, bool]]:
    """Return list of (page_number, bgr_image, is_embedded_photo) for an image or PDF."""
    import cv2
    import numpy as np

    ext = path.suffix.lower()
    if ext != ".pdf":
        raw = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        return [(1, image, True)] if image is not None else []

    import pymupdf

    items: list[tuple[int, Any, bool]] = []
    with pymupdf.open(str(path)) as doc:
        for page_index, page in enumerate(doc[:6], 1):
            seen_xrefs: set[int] = set()
            embedded_count = 0
            for info in page.get_images():
                xref = info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                try:
                    extracted = doc.extract_image(xref)
                except Exception:
                    continue
                if not extracted or not extracted.get("image"):
                    continue
                if min(int(extracted.get("width") or 0), int(extracted.get("height") or 0)) < 200:
                    continue
                arr = np.frombuffer(extracted["image"], dtype=np.uint8)
                im = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if im is not None:
                    items.append((page_index, im, True))
                    embedded_count += 1
            if embedded_count == 0:
                zoom = 200 / 72
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                items.append((page_index, cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), False))
    return items


def rescue_label_pages(
    documents: list[dict[str, Any]], pages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Augment existing OCR pages with embedded photo & rotated sticker/plate/logo crops."""
    from src.extraction import label_ocr

    augmented = [{**p, "ocr": list(p.get("ocr") or [])} for p in pages]
    page_lookup: dict[tuple[Any, int], dict[str, Any]] = {}
    for p in augmented:
        key = (p.get("source_id"), int(p.get("page") or 1))
        page_lookup.setdefault(key, p)

    existing_norms: dict[tuple[Any, int], set[str]] = {}
    for key, p in page_lookup.items():
        existing_norms[key] = {
            norm(row.get("text")) for row in p.get("ocr") or [] if row.get("text")
        }

    _, mode = label_ocr.create_ocr()
    tess_cmd = label_ocr._tess_cmd() if not mode.startswith("paddle") else ""

    pending_tasks: list[tuple[tuple[Any, int], Any, tuple[int, ...], str]] = []
    for doc in documents:
        path = storage.file_path(doc)
        if not Path(path).is_file():
            continue
        for page_no, image, is_photo in _extract_document_images(Path(path)):
            key = (doc["id"], page_no)
            target = page_lookup.get(key)
            if target is None:
                target = {
                    "source_id": doc["id"],
                    "source_name": doc["filename"],
                    "source_type": "pdf" if Path(path).suffix.lower() == ".pdf" else "image",
                    "page": page_no,
                    "ocr": [],
                }
                page_lookup[key] = target
                existing_norms[key] = set()
                augmented.append(target)

            candidates: list[tuple[Any, float, str]] = []
            for crop in _sticker_crops(image):
                scale = 3.2 if max(crop.shape[:2]) <= 350 else 2.8
                candidates.append((crop, scale, "sticker_rescue"))
            for crop, scale, kind in _text_region_crops(image):
                candidates.append((crop, scale, f"sticker_rescue_{kind}"))
            if is_photo and max(image.shape[:2]) <= 1200 and not candidates:
                candidates.append((image, 1.8, "sticker_rescue_full"))

            for crop, scale, kind in candidates:
                gray = _upscale_gray(crop, target_scale=scale)
                psms = (6, 11) if max(gray.shape[:2]) <= 1350 else (11,)
                if mode.startswith("paddle"):
                    for line in _ocr_gray_rotations(gray, psms=psms, kind=kind):
                        line_norm = norm(line)
                        if line_norm and line_norm not in existing_norms[key]:
                            existing_norms[key].add(line_norm)
                            target["ocr"].append(
                                {
                                    "text": line,
                                    "confidence": 0.72,
                                    "variant": kind,
                                    "engine": "rescue",
                                }
                            )
                else:
                    for rot in _orientations_for_crop(gray, kind):
                        pending_tasks.append((key, rot, psms, kind))

    if pending_tasks:
        workers = min(4, len(pending_tasks))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                (key, kind, executor.submit(_ocr_single_rotation_tesseract, rot, psms, tess_cmd))
                for key, rot, psms, kind in pending_tasks
            ]
            for key, kind, fut in futures:
                try:
                    found_lines = fut.result()
                except Exception:
                    continue
                target = page_lookup[key]
                for line in found_lines:
                    line_norm = norm(line)
                    if line_norm and line_norm not in existing_norms[key]:
                        existing_norms[key].add(line_norm)
                        target["ocr"].append(
                            {
                                "text": line,
                                "confidence": 0.74,
                                "variant": kind,
                                "engine": "rescue",
                            }
                        )
    return augmented


def _collect_label_ocr_blocks(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build deduplicated, clean OCR text blocks grouped by (source_id, source_name, page)."""
    grouped: dict[tuple[Any, str, int], list[str]] = {}
    seen: dict[tuple[Any, str, int], set[str]] = {}
    for p in pages:
        key = (p.get("source_id"), str(p.get("source_name") or ""), int(p.get("page") or 1))
        bucket = grouped.setdefault(key, [])
        bucket_seen = seen.setdefault(key, set())
        # Prioritize clean rescue crop lines ahead of noisy raw full-page OCR lines.
        ordered_rows = sorted(
            p.get("ocr") or [],
            key=lambda r: (
                0 if str(r.get("variant") or "").startswith("sticker_rescue") or r.get("engine") == "rescue" else 1,
                -float(r.get("confidence") or 0.0),
            ),
        )
        for row in ordered_rows:
            is_rescue = (
                str(row.get("variant") or "").startswith("sticker_rescue")
                or row.get("engine") == "rescue"
            )
            conf = row.get("confidence")
            txt = compact(row.get("text"))
            has_digit = bool(re.search(r"\d", txt))
            min_conf = 0.42 if (is_rescue or has_digit) else 0.56
            if isinstance(conf, (int, float)) and conf < min_conf:
                continue
            words = txt.split()
            if not words:
                continue
            conf_score = float(conf * 100) if isinstance(conf, (int, float)) else 80.0
            cleaned = _keep_ocr_line(words, [conf_score] * len(words), strict_noise=True)
            if not cleaned:
                continue
            n = norm(cleaned)
            if n and n not in bucket_seen:
                bucket_seen.add(n)
                bucket.append(cleaned)

    blocks = []
    for index, ((source_id, source_name, page_no), lines) in enumerate(grouped.items()):
        if not lines:
            continue
        blocks.append(
            {
                "block_id": index,
                "source_id": source_id,
                "source_name": source_name,
                "page": page_no,
                "text": "\n".join(lines),
            }
        )
    return blocks


def _chunk_blocks(blocks: list[dict[str, Any]], max_chars: int = 3400) -> list[list[dict[str, Any]]]:
    windows: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    chars = 0
    for block in blocks:
        block_chars = len(block["text"])
        if block_chars > 10000:
            block = {**block, "text": block["text"][:10000]}
            block_chars = len(block["text"])
        if current and chars + block_chars > max_chars:
            windows.append(current)
            current = [block]
            chars = block_chars
        else:
            current.append(block)
            chars += block_chars
    if current:
        windows.append(current)
    return windows


def _is_sane_llm_value(field: str, value: str) -> bool:
    """Reject generic warning words, label headers, and malformed serials."""
    comp = compact(value).upper()
    if not comp:
        return False
    alnum = re.sub(r"[^A-Za-z0-9]", "", comp)
    if alnum in _BANNED_STOP_COMPACT:
        return False
    upper = value.upper()
    if any(
        bad in upper
        for bad in (
            "PRODUCES RADIATION",
            "WHEN ENERGIZED",
            "THIS EQUIPMENT",
            "DISASSEMBLE",
            "PRECIOUS METAL",
        )
    ):
        if not (field.startswith("tipe") and re.search(r"\d", alnum)):
            return False
    if field.startswith("nomor_seri"):
        if len(alnum) < 4 or not re.search(r"\d", alnum):
            return False
        if re.fullmatch(r"\d{1,4}[/-]\d{1,2}[/-]\d{2,4}", value.strip()):
            return False
        if re.fullmatch(r"(?:REV|FIRMWARE)[\s:.-]*\d{1,3}", value.strip(), re.I):
            return False
    if field.startswith("merk") and len(alnum) < 2:
        return False
    return True


def _compact_quote_for_value(block_text: str, value: str, raw_quote: str) -> str:
    """Prefer only the 1-3 relevant OCR lines over multi-paragraph whole-block quotes."""
    if len(raw_quote) <= 220:
        return raw_quote
    val_norm = norm(value)
    lines = [ln.strip() for ln in block_text.splitlines() if ln.strip()]
    matched = [ln for ln in lines if val_norm in norm(ln)]
    if matched:
        return " | ".join(matched[:2])[:220]
    return raw_quote[:220]


def extract_label_equipment_llm(
    pages: list[dict[str, Any]],
    missing_fields: set[str],
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Use bounded Qwen call to recover label equipment fields strictly grounded in OCR lines."""
    if not missing_fields:
        return {}, None
    blocks = _collect_label_ocr_blocks(pages)
    if not blocks:
        return {}, None

    ordered_fields = sorted(k for k in missing_fields if k in _FIELD_KEYS)
    record_schema = {
        "type": "object",
        "properties": {
            "block_id": {"type": "integer"},
            "page": {"type": "integer"},
            "quote": {"type": "string"},
            **{key: {"type": "string"} for key in _FIELD_KEYS},
        },
        "required": ["block_id", "page", "quote", *_FIELD_KEYS],
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "properties": {"records": {"type": "array", "items": record_schema}},
        "required": ["records"],
        "additionalProperties": False,
    }
    instructions = (
        "Teks berikut adalah hasil OCR dari foto label fisik unit dan/atau tabung pesawat sinar-X "
        "(sering berupa potongan baris pendek atau mengandung variasi awalan seperti 'MODEL:', 'MODEL#', 'TYPE:', 'S/N:', 'SN#', 'SER. NO:', 'MFG:'). "
        f"Field yang masih dibutuhkan: {', '.join(ordered_fields)}. Field lain isi string kosong. "
        "Salin nilai mentah persis dari baris OCR pada block tersebut; JANGAN mengarang atau melengkapi teks yang tidak tertulis di OCR. "
        "Jika merek tercetak dua baris berturut-turut pada logo (misal baris 'Thermo' diikuti 'SCIENTIFIC'), gunakan baris gabungannya ('Thermo SCIENTIFIC') bila tersedia. "
        "DILARANG keras mengisi field dengan kata peringatan, deskripsi umum, atau nama kolom label seperti: "
        "'EQUIPMENT', 'THIS EQUIPMENT', 'RADIATION', 'CAUTION', 'WARNING', 'WHEN ENERGIZED', 'DISASSEMBLE UNIT', 'PRECIOUS METAL ANALYZER', 'X-RAY ON', 'SERIAL', 'SN', 'MODEL', 'DATE'. "
        "Untuk nomor_seri_*, hanya ambil kode nomor seri unik (minimal 4 karakter & ada angka), BUKAN tanggal (mis. 4/12/2023) dan BUKAN nomor revisi firmware. "
        "Pisahkan unit vs tabung dengan ketat: JANGAN menyalin merek/model/seri unit luar ke field *_tabung kecuali block memang menunjukkan label komponen tabung (mis. kata tube/insert/firmware/COSP/N). Jika field tidak ada di OCR, kosongkan. "
        "Setiap record wajib menyertakan block_id, page, dan quote ringkas (HANYA 1-3 baris OCR terdekat yang memuat nilai tersebut, maksimal 200 karakter). "
        "Abaikan artefak OCR tanpa makna."
    )

    block_by_id = {b["block_id"]: b for b in blocks}
    recovered: dict[str, dict[str, Any]] = {}

    for window in _chunk_blocks(blocks, max_chars=3400):
        payload_pages = [
            {
                "block_id": b["block_id"],
                "page": b["page"],
                "source_name": b["source_name"],
                "text": b["text"],
            }
            for b in window
        ]
        try:
            records = llm.request_records(
                schema,
                "Jenis ekstraksi: label peralatan (foto unit dan tabung sinar-X)",
                payload_pages,
                instructions,
                output_limit=800,
            )
        except Exception as exc:
            return recovered, f"Ekstraksi Qwen label belum selesai ({type(exc).__name__})."

        for rec in records:
            if not isinstance(rec, dict):
                continue
            block = block_by_id.get(rec.get("block_id"))
            if not block:
                continue
            quote = compact(rec.get("quote"))
            quote_norm = norm(quote)
            if len(quote_norm) < 2 or quote_norm not in norm(block["text"]):
                continue
            for key in ordered_fields:
                if key in recovered:
                    continue
                val = compact(rec.get(key))
                val_norm = norm(val)
                if not val_norm or val_norm not in quote_norm:
                    continue
                if not _is_sane_llm_value(key, val):
                    continue
                recovered[key] = {
                    "value": val,
                    "quote": _compact_quote_for_value(block["text"], val, quote),
                    "source_id": block["source_id"],
                    "source_name": block["source_name"],
                    "page": block["page"],
                }
        if len(recovered) >= len(ordered_fields):
            break

    return recovered, None
