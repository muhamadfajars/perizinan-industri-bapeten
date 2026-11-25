"""Bounded adaptive OCR retry and blind Vision LLM fallback for scanned personnel documents."""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

import cv2
import numpy as np

_LOGGER = logging.getLogger("uvicorn.error")

_DOSE_REPORT_RE = re.compile(
    r"(?i)\b(?:hp\s*\(\s*(?:10|0[.,]07|3)\s*\)|evaluasi\s+dosis|pemantauan\s+dosis|"
    r"pembacaan\s+dosis|laporan\s+dosis|zero\s+ch?ec?k|no\.?\s*lencana|dosis\s+ekuivalen)\b"
)
_CERT_ANCHOR_RE = re.compile(
    r"(?i)certify\s+that|menyatakan\s+bahwa|menerangkan\s+bahwa|diberikan\s+kepada|"
    r"awarded\s+to|presented\s+to|granted\s+to|conferred\s+(?:upon|to)"
)
_CERT_FOLLOWER_RE = re.compile(
    r"(?i)telah\s+mengikuti|telah\s+menyelesaikan|telah\s+lulus|"
    r"dinyatakan\s+(?:lulus|kompeten|berhasil)|lulus\s+(?:ujian|pelatihan|kompetensi)|"
    r"has\s+participated|has\s+completed|has\s+successfully|declared\s+competent|"
    r"dengan\s+kualifikasi|sebagai\s+(?:petugas|ppr|radiografer|pekerja)"
)
_NAME_LABEL_RE = re.compile(
    r"(?i)^\s*(?:nama(?:\s+(?:lengkap|pekerja(?:\s+radiasi)?|petugas|personel))?"
    r"(?:\s*/\s*name)?|name)\s*:?\s*$"
)
_SIGNER_CONTEXT_RE = re.compile(
    r"(?i)\b(?:yang\s+bertanda\s+tangan|mengetahui|disahkan|a\.?\s*n\.?\s+kepala|"
    r"atas\s+nama|direktur|pimpinan)\b"
)
_NON_NAME_FIELD_LABEL_RE = re.compile(
    r"(?i)^\s*(?:nik|no\.?\s*(?:sib|ktp|identitas|registrasi)|tempat|tanggal|"
    r"alamat|jabatan|keahlian|profesi|instansi|unit|bagian)\b"
)
_INVALID_RECIPIENT_PATTERNS = re.compile(
    r"(?i)\b(?:sertifikat|certificate|direktur|director|pimpinan|jabatan|tanggal|"
    r"identitas|alamat|petugas|telah\s+mengikuti|this\s+is\s+to\s+certify|"
    r"menyatakan|menerangkan|bapeten|dipindai|camscanner|training)\b"
)


def _box_bounds(box) -> tuple[int, int, int, int] | None:
    """Normalize 4-scalar [x1, y1, x2, y2] or polygon [[x, y], ...] into (x1, y1, x2, y2)."""
    if not box:
        return None
    if isinstance(box, (list, tuple)) and len(box) == 4 and all(
        isinstance(v, (int, float)) for v in box
    ):
        x1, y1, x2, y2 = (float(v) for v in box)
        return int(round(min(x1, x2))), int(round(min(y1, y2))), int(round(max(x1, x2))), int(round(max(y1, y2)))
    if isinstance(box, (list, tuple)) and all(
        isinstance(pt, (list, tuple)) and len(pt) >= 2 for pt in box
    ):
        xs = [float(pt[0]) for pt in box]
        ys = [float(pt[1]) for pt in box]
        if not xs or not ys:
            return None
        return int(round(min(xs))), int(round(min(ys))), int(round(max(xs))), int(round(max(ys)))
    return None


def _is_dose_report(records) -> bool:
    text = " ".join(str(r.get("text", "")) for r in records)
    return bool(_DOSE_REPORT_RE.search(text))


def _strip_horizontal_rules_binary(gray: np.ndarray) -> np.ndarray:
    """Binarize (inverted) and remove long thin horizontal lines while healing vertical strokes."""
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = binary.shape[:2]
    if w >= 20 and h >= 5:
        line_w = max(40, int(w * 0.28))
        horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (line_w, 1))
        horiz_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horiz_kernel)
        if np.any(horiz_lines):
            # Remove thin 1-2px anti-aliased rule halo, then heal descenders vertically.
            mask = cv2.dilate(horiz_lines, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3)))
            binary = cv2.subtract(binary, mask)
            binary = cv2.morphologyEx(
                binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 2))
            )
    return binary


def _has_ink(crop: np.ndarray) -> bool:
    """Detect genuine foreground ink (excluding clean paper noise and tilted horizontal rules)."""
    if crop is None or crop.size == 0:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    h, w = gray.shape[:2]
    if h < 6 or w < 12:
        return False
    if float(np.percentile(gray, 90) - np.percentile(gray, 1)) < 25.0:
        return False
    if h >= 10:
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        cleaned = cv2.morphologyEx(
            binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5))
        )
    else:
        cleaned = _strip_horizontal_rules_binary(gray)
    # Count only ink that is genuinely darker than surrounding paper background.
    thresh = min(195, max(90, int(np.percentile(gray, 50)) - 35))
    foreground = np.logical_and(cleaned > 0, gray < thresh)
    return int(np.count_nonzero(foreground)) >= max(24, int(gray.size * 0.0015))


def _tight_text_crop(crop: np.ndarray) -> np.ndarray:
    """Isolate actual text region on original image, ignoring thin horizontal rules even when tilted."""
    if crop is None or crop.size == 0:
        return crop
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    h, w = gray.shape[:2]
    if h < 10 or w < 12 or float(np.percentile(gray, 90) - np.percentile(gray, 1)) < 15.0:
        return crop
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    no_thin_rules = cv2.morphologyEx(
        bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5))
    )
    xs = np.where(np.count_nonzero(no_thin_rules, axis=0) >= 3)[0]
    ys = np.where(np.count_nonzero(no_thin_rules, axis=1) >= 3)[0]
    if xs.size < 4 or ys.size < 4:
        return crop
    x1, x2 = int(xs[0]), int(xs[-1]) + 1
    y1, y2 = int(ys[0]), int(ys[-1]) + 1
    pad = max(16, int((y2 - y1) * 0.2))
    tx1, ty1 = max(0, x1 - pad), max(0, y1 - pad)
    tx2, ty2 = min(w, x2 + pad), min(h, y2 + pad)
    tight = crop[ty1:ty2, tx1:tx2]
    return tight if tight.size else crop


def _is_valid_recipient_text(value: str) -> str | None:
    """Validate single-line person name sanity; strip edge quotes/punctuation only."""
    cleaned = " ".join(str(value or "").split()).strip(" \"'`.,;:-")
    if "\n" in str(value or "").strip():
        return None
    if not (3 <= len(cleaned) <= 80):
        return None
    if not cleaned[0].isalpha():
        return None
    if sum(ch.isalpha() for ch in cleaned) < 3:
        return None
    if re.search(r"[\d:|]", cleaned):
        return None
    if _INVALID_RECIPIENT_PATTERNS.search(cleaned):
        return None
    if _NON_NAME_FIELD_LABEL_RE.match(cleaned):
        return None
    return cleaned


def _is_confident_name_record(rec: dict) -> bool:
    txt = str(rec.get("text", "")).strip()
    conf = rec.get("confidence")
    if conf is not None:
        try:
            if float(conf) < 0.78:
                return False
        except (TypeError, ValueError):
            pass
    if len(re.findall(r"[^\W\d_]", txt)) < 4:
        return False
    return _is_valid_recipient_text(txt) is not None


def _clean_crop_for_ocr(crop: np.ndarray) -> np.ndarray | None:
    """Preprocess name crop by removing horizontal rules, tight-cropping, and padding."""
    if crop is None or crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    if float(np.percentile(gray, 90) - np.percentile(gray, 1)) < 15.0:
        return None
    cleaned = _strip_horizontal_rules_binary(gray)
    coords = cv2.findNonZero(cleaned)
    if coords is None or len(coords) < 12:
        return None
    x, y, cw, ch = cv2.boundingRect(coords)
    if cw < 6 or ch < 6:
        return None
    tight = 255 - cleaned[y : y + ch, x : x + cw]
    padded = cv2.copyMakeBorder(tight, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
    ph, pw = padded.shape[:2]
    if ph < 48:
        scale = 48.0 / float(ph)
        padded = cv2.resize(
            padded, (max(1, int(round(pw * scale))), 48), interpolation=cv2.INTER_CUBIC
        )
    return padded


def _classical_ocr_crop(crop: np.ndarray) -> str | None:
    """Layer 1: preprocessed classical OCR requiring cross-PSM agreement."""
    import pytesseract

    processed = _clean_crop_for_ocr(crop)
    if processed is None:
        return None
    try:
        languages = set(pytesseract.get_languages(config=""))
    except (RuntimeError, OSError):
        return None
    lang = "+".join(
        l for l in os.getenv("BAPETEN_TESS_LANG", "ind+eng").split("+") if l in languages
    )
    if not lang:
        return None
    variants = []
    for mode in (7, 6):
        try:
            raw = pytesseract.image_to_string(
                processed, lang=lang, config=f"--psm {mode}", timeout=8
            ).strip()
        except (RuntimeError, OSError):
            continue
        valid = _is_valid_recipient_text(raw)
        if valid:
            variants.append(valid)
    # Agreement is required; never use form names to steer OCR.
    if len(variants) == 2 and variants[0].casefold() == variants[1].casefold():
        return variants[0]
    return None


def _transcribe_with_vlm(image_bytes: bytes) -> str:
    try:
        from app.protection.llm import transcribe_image_text
    except ImportError:
        backend_dir = str(Path(__file__).resolve().parents[3])
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from app.protection.llm import transcribe_image_text
    return transcribe_image_text(image_bytes)


def _vlm_transcribe_crop(crop: np.ndarray) -> str | None:
    """Layer 2: targeted blind Vision LLM transcription for unreadable/cursive crops."""
    if crop is None or crop.size == 0:
        return None
    tight = _tight_text_crop(crop)
    padded = cv2.copyMakeBorder(
        tight,
        12,
        12,
        12,
        12,
        cv2.BORDER_CONSTANT,
        value=(255, 255, 255) if tight.ndim == 3 else 255,
    )
    h, w = padded.shape[:2]
    scale = min(1.0, 448.0 / float(max(h, w)), 160.0 / float(h))
    if scale < 1.0:
        padded = cv2.resize(
            padded,
            (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
            interpolation=cv2.INTER_AREA,
        )
    ok, buf = cv2.imencode(".png", padded)
    if not ok:
        return None
    try:
        raw = _transcribe_with_vlm(bytes(buf))
    except Exception as exc:
        _LOGGER.debug("VLM recipient transcription fallback failed: %s", type(exc).__name__)
        return None
    return _is_valid_recipient_text(raw)


def _records_inside_box(records: list[dict], box: tuple[int, int, int, int]) -> list[dict]:
    x1, y1, x2, y2 = box
    inside = []
    for rec in records:
        bounds = _box_bounds(rec.get("box"))
        if not bounds:
            continue
        rx1, ry1, rx2, ry2 = bounds
        cx, cy = (rx1 + rx2) / 2.0, (ry1 + ry2) / 2.0
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            inside.append(rec)
    return inside


def _find_certificate_gap(image: np.ndarray, records: list[dict]):
    img_h, img_w = image.shape[:2]
    anchors = [
        r for r in records if _CERT_ANCHOR_RE.search(str(r.get("text", ""))) and _box_bounds(r.get("box"))
    ]
    following = [
        r
        for r in records
        if _CERT_FOLLOWER_RE.search(str(r.get("text", ""))) and _box_bounds(r.get("box"))
    ]
    for anchor in reversed(anchors):
        ax1, ay1, ax2, ay2 = _box_bounds(anchor["box"])
        top = ay2 + 2
        ends = [
            (r, _box_bounds(r["box"]))
            for r in following
            if _box_bounds(r["box"])[1] > top
        ]
        if not ends:
            continue
        end_rec, (ex1, ey1, ex2, ey2) = min(ends, key=lambda item: item[1][1])
        bottom = ey1 - 2
        if not 15 < bottom - top < img_h * 0.35:
            continue
        pad_x = int(round(img_w * 0.05))
        left = max(0, min(ax1, ex1) - pad_x)
        right = min(img_w, max(ax2, ex2) + pad_x)
        if right <= left:
            continue
        existing = _records_inside_box(records, (left, top, right, bottom))
        if any(_is_confident_name_record(r) for r in existing):
            return "confident", anchor, (left, top, right, bottom), existing
        crop = image[top:bottom, left:right]
        if _has_ink(crop):
            return "retry", anchor, (left, top, right, bottom), existing
        return "empty", anchor, (left, top, right, bottom), existing
    return None


def _find_label_value_gap(image: np.ndarray, records: list[dict]):
    img_h, img_w = image.shape[:2]
    label_boxes = []
    for rec in records:
        txt = str(rec.get("text", ""))
        bounds = _box_bounds(rec.get("box"))
        if bounds and _NAME_LABEL_RE.match(txt):
            label_boxes.append((rec, bounds))
    for label_rec, (lx1, ly1, lx2, ly2) in label_boxes:
        label_h = max(12, ly2 - ly1)
        label_cy = (ly1 + ly2) / 2.0
        # Skip signer blocks above the label.
        signer_above = any(
            _box_bounds(r.get("box")) is not None
            and (ly1 - img_h * 0.18) <= _box_bounds(r["box"])[1] <= ly1
            and _SIGNER_CONTEXT_RE.search(str(r.get("text", "")))
            for r in records
        )
        if signer_above:
            continue
        # Check if confident name already exists to the right or immediately below the label.
        has_confident = False
        for r in records:
            if r is label_rec:
                continue
            rb = _box_bounds(r.get("box"))
            if not rb:
                continue
            rx1, ry1, rx2, ry2 = rb
            rcy = (ry1 + ry2) / 2.0
            to_right = abs(rcy - label_cy) <= max(label_h * 1.1, 18) and rx1 >= lx2 - 10
            below = (
                ly2 - 4 <= ry1 <= ly2 + max(label_h * 3.0, 45)
                and min(rx2, max(lx2, lx1 + int(img_w * 0.45))) > max(rx1, lx1 - 10)
            )
            if (to_right or below) and _is_confident_name_record(r):
                has_confident = True
                break
        if has_confident:
            continue

        # Propose right-hand value box first.
        pad_y = max(6, int(label_h * 0.45))
        right_box = (
            min(img_w, lx2 + 2),
            max(0, ly1 - pad_y),
            min(img_w, lx2 + int(img_w * 0.45)),
            min(img_h, ly2 + pad_y),
        )
        if right_box[2] > right_box[0] + 10 and right_box[3] > right_box[1] + 6:
            right_existing = _records_inside_box(records, right_box)
            right_crop = image[right_box[1] : right_box[3], right_box[0] : right_box[2]]
            if not any(
                _NON_NAME_FIELD_LABEL_RE.match(str(r.get("text", ""))) for r in right_existing
            ) and _has_ink(right_crop):
                return "retry", label_rec, right_box, right_existing

        # Otherwise check directly below the label if it doesn't collide with another field label.
        below_box = (
            max(0, lx1 - 10),
            min(img_h, ly2 + 2),
            min(img_w, max(lx2, lx1 + int(img_w * 0.45))),
            min(img_h, ly2 + max(int(label_h * 2.8), 55)),
        )
        if below_box[2] > below_box[0] + 10 and below_box[3] > below_box[1] + 6:
            below_existing = _records_inside_box(records, below_box)
            if any(
                _NON_NAME_FIELD_LABEL_RE.match(str(r.get("text", "")))
                or _NAME_LABEL_RE.match(str(r.get("text", "")))
                for r in below_existing
            ):
                continue
            below_crop = image[below_box[1] : below_box[3], below_box[0] : below_box[2]]
            if _has_ink(below_crop):
                return "retry", label_rec, below_box, below_existing
    return None


def _replace_with_recovered(
    records: list[dict],
    anchor: dict,
    existing: list[dict],
    box: tuple[int, int, int, int],
    value: str,
    engine: str,
    confidence: float | None,
) -> list[dict]:
    left, top, right, bottom = box
    inserted = {
        "text": value,
        "box": [[left, top], [right, top], [right, bottom], [left, bottom]],
        "engine": engine,
    }
    if confidence is not None:
        inserted["confidence"] = confidence
    existing_ids = {id(r) for r in existing}
    result = [r for r in records if id(r) not in existing_ids]
    try:
        position = result.index(anchor) + 1
    except ValueError:
        position = len(result)
    result.insert(position, inserted)
    return result


def retry_recipient(image, records):
    if image is None or not getattr(image, "size", 0) or not records:
        return records, False
    if _is_dose_report(records):
        return records, False

    candidate = _find_certificate_gap(image, records)
    if candidate is not None:
        state, anchor, box, existing = candidate
        if state == "confident":
            return records, False
        if state == "empty":
            return records, True
    else:
        candidate = _find_label_value_gap(image, records)
        if candidate is None:
            return records, False
        _state, anchor, box, existing = candidate

    left, top, right, bottom = box
    crop = image[top:bottom, left:right]
    if not crop.size:
        return records, False

    value = _classical_ocr_crop(crop)
    if value:
        return (
            _replace_with_recovered(
                records, anchor, existing, box, value, "tesseract-recipient-retry", None
            ),
            False,
        )

    vlm_value = _vlm_transcribe_crop(crop)
    if vlm_value:
        return (
            _replace_with_recovered(
                records, anchor, existing, box, vlm_value, "vlm-recipient-retry", 0.92
            ),
            False,
        )

    return records, True
