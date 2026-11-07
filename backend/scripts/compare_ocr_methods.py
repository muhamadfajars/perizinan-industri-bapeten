"""Compare OCR image treatments for a developer-supplied label image."""

import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error("Image file does not exist")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
    from src.extraction.image_preprocess import create_ocr_variants
    from src.extraction.label_ocr import extract_ocr, print_ocr_results

    for name, image in create_ocr_variants(str(args.image)).items():
        print_ocr_results(extract_ocr(image), title=name.upper())


if __name__ == "__main__":
    main()
