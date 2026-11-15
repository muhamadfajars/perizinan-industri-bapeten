"""Bounded upload inspection, separate from full analysis/OCR."""

import io
import os
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


def extract_document_text(filename, file_bytes, max_pages=6):
    """Inspect up to six opening pages; at most three OCR calls per upload.

    A native letterhead must not suppress OCR of a large embedded scan. Page
    boundaries are retained so a cover is not confused with later references.
    """
    ext = Path(filename).suffix.lower()
    pages = []
    if ext == ".pdf":
        with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
            if doc.needs_pass:
                raise ValueError("PDF terkunci; pilih kategori atau unggah PDF yang dapat dibaca")
            budget = 3
            for index in range(min(max_pages, len(doc))):
                page = doc[index]
                native = page.get_text("text", sort=True) or ""
                area = max(page.rect.width * page.rect.height, 1)
                large_scan = any(
                    pymupdf.Rect(info["bbox"]).get_area() / area >= 0.25
                    for info in page.get_image_info()
                )
                if budget and (len("".join(native.split())) < 80 or large_scan):
                    budget -= 1
                    scale = min(150 / 72, 2400 / max(page.rect.width, page.rect.height))
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
                    try:
                        scanned = ocr(Image.open(io.BytesIO(pix.tobytes("png"))))
                    except (RuntimeError, OSError, ValueError) as exc:
                        # Do not silently treat an OCR failure as successful verification.
                        raise ValueError("OCR belum berhasil; kategori perlu diperiksa") from exc
                    native += "\n" + scanned
                pages.append(native[:24000])
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
