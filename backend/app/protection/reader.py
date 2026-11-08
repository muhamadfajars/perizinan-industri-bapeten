"""Read every page; retain layout and report unreadable evidence explicitly."""

import os
import subprocess
import re
import pymupdf


def read_document(path):
    pages, warnings = [], []
    with pymupdf.open(path) as pdf:
        for i, page in enumerate(pdf):
            native = page.get_text(sort=True).strip()
            method, text = "text", native
            images = [
                x
                for x in page.get_image_info()
                if (x["bbox"][2] - x["bbox"][0]) * (x["bbox"][3] - x["bbox"][1])
                > page.rect.get_area() * 0.08
            ]
            # Early approval pages may contain native headers over a scanned body.
            if len(re.sub(r"\s", "", native)) < 100 or (i < 3 and images):
                try:
                    png = page.get_pixmap(dpi=160, alpha=False).tobytes("png")
                    result = subprocess.run(
                        ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "11"],
                        input=png,
                        capture_output=True,
                        timeout=45,
                        env={**os.environ, "OMP_THREAD_LIMIT": "2"},
                    )
                    if result.returncode:
                        raise RuntimeError("OCR gagal")
                    ocr = result.stdout.decode("utf-8", errors="replace").strip()
                    if ocr:
                        text = native + "\n" + ocr if native else ocr
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
