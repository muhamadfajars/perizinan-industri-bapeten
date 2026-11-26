"""Bounded upload inspection, separate from full analysis/OCR."""

import io
import os
import re
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image, ImageOps
from docx import Document


def ocr(image):
    requested = os.environ.get("BAPETEN_TESS_LANG", "ind+eng").split("+")
    available = set(pytesseract.get_languages(config=""))
    languages = [lang for lang in requested if lang in available]
    if not languages:
        raise ValueError("Bahasa OCR yang dikonfigurasi tidak tersedia")
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((2400, 2400))
    text = pytesseract.image_to_string(
        image, lang="+".join(languages), config="--psm 3", timeout=10
    )
    if len("".join(text.split())) < 20:
        text = pytesseract.image_to_string(
            image, lang="+".join(languages), config="--psm 11", timeout=8
        )
    return text


def _ocr_embedded_images(doc, page):
    """OCR large embedded images directly when full-page rendering drops photo scans."""
    candidates = []
    seen_xrefs = set()
    for info in page.get_images():
        xref = info[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)
        try:
            raw = doc.extract_image(xref)
        except Exception:
            continue
        if not raw or not raw.get("image"):
            continue
        width = int(raw.get("width") or 0)
        height = int(raw.get("height") or 0)
        if min(width, height) < 200:
            continue
        candidates.append((width * height, raw["image"]))
    candidates.sort(key=lambda item: item[0], reverse=True)
    chunks = []
    for _, img_bytes in candidates[:2]:
        try:
            with Image.open(io.BytesIO(img_bytes)) as img:
                txt = ocr(img.copy()).strip()
        except (RuntimeError, OSError, ValueError):
            continue
        if txt:
            chunks.append(txt)
    return "\n".join(chunks)


def _is_long_single_doc_cover(page_text: str) -> bool:
    head = (page_text or "").strip()[:1200]
    if not head:
        return False
    return bool(
        re.search(
            r"(?im)^\s*(?:FORMULIR\s+PERMOHONAN|"
            r"(?:DOKUMEN\s+)?PROGRAM\s+PROTEKSI(?:\s+DAN\s+KESELAMATAN)?\s+RADIASI|"
            r"(?:DOKUMEN\s+)?SISTEM\s+MANAJEMEN)\b",
            head,
        )
    )


def _read_pdf_page_text(doc, page, budget: int, allow_header_ocr: bool) -> tuple[str, int]:
    native = page.get_text("text", sort=True) or ""
    area = max(page.rect.width * page.rect.height, 1)
    large_scan = any(
        pymupdf.Rect(info["bbox"]).get_area() / area >= 0.25 for info in page.get_image_info()
    )
    sparse = len("".join(native.split())) < 80 or large_scan
    if budget and sparse:
        budget -= 1
        scale = min(150 / 72, 2400 / max(page.rect.width, page.rect.height))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
        try:
            scanned = ocr(Image.open(io.BytesIO(pix.tobytes("png"))))
            if len("".join(scanned.split())) < 10 and page.get_images():
                embedded = _ocr_embedded_images(doc, page)
                if len("".join(embedded.split())) > len("".join(scanned.split())):
                    scanned = embedded
        except (RuntimeError, OSError, ValueError) as exc:
            # Do not silently treat an OCR failure as successful verification.
            raise ValueError("OCR belum berhasil; kategori perlu diperiksa") from exc
        native += "\n" + scanned
    elif not budget and allow_header_ocr and sparse:
        clip = pymupdf.Rect(0, 0, page.rect.width, page.rect.height * 0.38)
        scale = min(110 / 72, 1800 / max(clip.width, clip.height, 1))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip)
        try:
            header_scan = ocr(Image.open(io.BytesIO(pix.tobytes("png"))))
        except (RuntimeError, OSError, ValueError):
            header_scan = ""
        if header_scan:
            native += "\n" + header_scan
    return native[:24000], budget


def extract_document_text(filename, file_bytes, max_pages=6):
    """Inspect opening pages cleanly; adaptive header OCR inspects pages 4-10 on short scans.

    A native letterhead must not suppress OCR of a large embedded scan. Page
    boundaries are retained so a cover is not confused with later references.
    """
    ext = Path(filename).suffix.lower()
    pages = []
    if ext == ".pdf":
        with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
            if doc.needs_pass:
                raise ValueError("PDF terkunci; pilih kategori atau unggah PDF yang dapat dibaca")
            total_pages = len(doc)
            if total_pages == 0:
                return ""
            budget = 3
            adaptive_short_pdf = 4 <= total_pages <= 10
            first_text, budget = _read_pdf_page_text(doc, doc[0], budget, allow_header_ocr=False)
            pages.append(first_text)
            allow_bonus = adaptive_short_pdf and not _is_long_single_doc_cover(first_text)
            limit = total_pages if allow_bonus else min(max_pages, total_pages)
            for index in range(1, limit):
                page_text, budget = _read_pdf_page_text(
                    doc, doc[index], budget, allow_header_ocr=(allow_bonus and index >= 3)
                )
                pages.append(page_text)
    elif ext == ".docx":
        doc = Document(io.BytesIO(file_bytes))
        # Include table-based covers and headers as well as paragraphs.
        from docx.oxml.ns import qn

        for element in doc.element.body:
            text = "\n".join(
                "".join(node.text or "" for node in paragraph.iter(qn("w:t")))
                for paragraph in element.iter(qn("w:p"))
            )
            pages.append(text)
            if sum(map(len, pages)) >= 48000:
                break
        return "\n".join(pages)[:48000]
    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"):
        with Image.open(io.BytesIO(file_bytes)) as image:
            for index in range(min(getattr(image, "n_frames", 1), 3)):
                image.seek(index)
                pages.append(ocr(image.copy()))
    else:
        raise ValueError("Format dokumen tidak didukung")
    return "\f".join(pages)
