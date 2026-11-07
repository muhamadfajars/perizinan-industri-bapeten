import re
import unicodedata


OCR_AMBIGUITY_GROUPS = [
    {"0", "O"},
    {"1", "I", "L"},
    {"5", "S"},
    {"8", "B"},
    {"2", "Z"},
]


def normalize_text(value):
    if value is None:
        return ""

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    value = value.upper()

    value = re.sub(
        r"[^A-Z0-9]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def compact_text(value):
    return re.sub(
        r"[^A-Z0-9]",
        "",
        normalize_text(value),
    )


def normalize_serial_candidate(
    value,
):
    if value is None:
        return ""

    value = str(value).strip()

    value = re.sub(
        r"^\s*\(\s*21\s*\)\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^\s*"
        r"(?:"
        r"SER(?:IAL)?\.?\s*NO\.?"
        r"|SERIAL(?:\s+NUMBER)?"
        r"|S/N"
        r"|SN"
        r")"
        r"\s*[:#.\-]?\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return compact_text(value)


def is_serial_labeled_line(
    value,
):
    if not value:
        return False

    value = str(value).strip()

    return bool(
        re.search(
            r"^\s*"
            r"(?:"
            r"\(\s*21\s*\)"
            r"|SER(?:IAL)?\.?\s*NO\.?"
            r"|SERIAL(?:\s+NUMBER)?"
            r"|S/N"
            r"|SN"
            r")",
            value,
            flags=re.IGNORECASE,
        )
    )


def split_expected_type(value):
    if not value:
        return []

    parts = re.split(
        r"\s*/\s*",
        str(value),
    )

    return [part.strip() for part in parts if part.strip()]


def same_ocr_ambiguity_group(
    left,
    right,
):
    for group in OCR_AMBIGUITY_GROUPS:
        if left in group and right in group:
            return True

    return False


def serial_ocr_ambiguity(
    expected,
    candidate,
):
    expected = compact_text(expected)

    candidate = compact_text(candidate)

    if not expected or not candidate or len(expected) != len(candidate):
        return False

    ambiguity_groups = [
        {"0", "O"},
        {"1", "I", "L"},
        {"5", "S"},
        {"8", "B"},
        {"2", "Z"},
        {"6", "G"},
    ]

    differences = 0

    for left, right in zip(
        expected,
        candidate,
    ):
        if left == right:
            continue

        is_ambiguous = any(left in group and right in group for group in ambiguity_groups)

        if is_ambiguous:
            differences += 1
            continue

        return False

    return differences > 0


def normalize_type_candidate(
    value,
):
    if value is None:
        return ""

    value = str(value).strip()

    value = re.sub(
        r"^\s*"
        r"(?:"
        r"INSERT\s+MODEL"
        r"|UNIT\s+MODEL"
        r"|MODEL"
        r"|TYPE"
        r"|TIPE"
        r")"
        r"\s*[:#\-]?\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return normalize_text(value)


def is_type_labeled_line(
    value,
):
    if not value:
        return False

    return bool(
        re.search(
            r"^\s*"
            r"(?:"
            r"INSERT\s+MODEL"
            r"|UNIT\s+MODEL"
            r"|MODEL"
            r"|TYPE"
            r"|TIPE"
            r")"
            r"\s*[:#\-]?",
            str(value),
            flags=re.IGNORECASE,
        )
    )
