"""Read every page; retain layout and report unreadable evidence explicitly."""

import os
import subprocess
import re
import pymupdf


def _merge_native_and_ocr(native, ocr):
    if not native:
        return ocr
    native_norm = re.sub(r"[^a-z0-9]", "", native.lower())
    extra = [
        line
        for line in ocr.splitlines()
        if line.strip() and re.sub(r"[^a-z0-9]", "", line.lower()) not in native_norm
    ]
    return native + "\n" + "\n".join(extra) if extra else native


def read_document(path):
    pages, warnings = [], []
    with pymupdf.open(path) as pdf:
        for i, page in enumerate(pdf):
            native = page.get_text(sort=True).strip()
            method, text = "text", native
            page_area = page.rect.get_area() or 1
            images = [
                x
                for x in page.get_image_info()
                if (x["bbox"][2] - x["bbox"][0]) * (x["bbox"][3] - x["bbox"][1]) > page_area * 0.08
            ]
            large_scan = any(
                (x["bbox"][2] - x["bbox"][0]) * (x["bbox"][3] - x["bbox"][1]) >= page_area * 0.30
                for x in images
            )
            native_chars = len(re.sub(r"\s", "", native))
            # Scan pages may still carry native headers; skip OCR only on dense text with small figures.
            if native_chars < 100 or large_scan or (images and native_chars < 600):
                try:
                    png = page.get_pixmap(dpi=160, alpha=False).tobytes("png")
                    result = subprocess.run(
                        [
                            os.getenv("BAPETEN_TESSERACT_CMD") or "tesseract",
                            "stdin",
                            "stdout",
                            "-l",
                            os.getenv("BAPETEN_TESS_LANG") or "ind+eng",
                            "--psm",
                            "3",
                        ],
                        input=png,
                        capture_output=True,
                        timeout=45,
                        env={**os.environ, "OMP_THREAD_LIMIT": "2"},
                    )
                    if result.returncode:
                        raise RuntimeError("OCR gagal")
                    ocr = result.stdout.decode("utf-8", errors="replace").strip()
                    if ocr:
                        text = _merge_native_and_ocr(native, ocr)
                        method = "ocr"
                    else:
                        warnings.append(
                            f"Halaman {i + 1}: OCR belum menghasilkan teks yang terbaca."
                        )
                except (OSError, subprocess.TimeoutExpired, RuntimeError):
                    warnings.append(
                        f"Halaman {i + 1}: OCR tidak tersedia atau melewati batas waktu."
                    )
            pages.append(
                {
                    "page": i + 1,
                    "text": text,
                    "method": method,
                    "native_text": page.get_text(sort=False),
                    "has_visual": bool(images) or len(page.get_drawings()) > 8,
                }
            )
    return pages, warnings
