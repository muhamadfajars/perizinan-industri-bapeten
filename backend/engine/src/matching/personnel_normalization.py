import re
import unicodedata
from rapidfuzz import fuzz


NAME_PREFIXES = {
    "dr",
    "drg",
    "prof",
    "dokter",
}

NAME_SUFFIX_PATTERNS = [
    r"\bsp\s*rad\b",
    r"\bsp\s*a\b",
    r"\bsp\s*og\b",
    r"\bsp\s*pd\b",
    r"\bsp\s*b\b",
    r"\bsp\s*jp\b",
    r"\bm\s*kes\b",
    r"\bs\s*ked\b",
    r"\bs\s*km\b",
    r"\bs\s*si\b",
    r"\bs\s*kom\b",
    r"\ba\s*md\b",
]

GENERAL_REPLACEMENTS = {
    "rs": "rumah sakit",
    "rumkit": "rumah sakit",
    "r s": "rumah sakit",
    "rsud": "rumah sakit umum daerah",
    "rsp": "rumah sakit pusat",
    "jl": "jalan",
    "jln": "jalan",
    "jlnn": "jalan",
    "jlnt": "jalan",
    "no": "nomor",
    "nomor": "nomor",
    "kec": "kecamatan",
    "kel": "kelurahan",
    "kab": "kabupaten",
    "kota": "kota",
    "prov": "provinsi",
}

EXPERTISE_REPLACEMENTS = {
    "ppr": "petugas proteksi radiasi",
    "radiographer": "radiografer",
    "radiography": "radiografer",
    "radiologi diagnostik": "radiologi diagnostik",
    "radiodiagnostik": "radiologi diagnostik",
    "fisikawan medik": "fisikawan medik",
    "fisika medik": "fisikawan medik",
    "dokter spesialis radiologi": "radiologi",
    "sp rad": "radiologi",
}


def normalize_basic(
    value,
):
    if value is None:
        return ""

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    value = value.lower()

    value = value.replace("\n", " ")

    value = re.sub(
        r"([a-z])-\s+([a-z])",
        r"\1\2",
        value,
    )

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def apply_replacements(
    value,
    replacements,
):
    value = normalize_basic(value)

    for source, target in sorted(
        replacements.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        value = re.sub(
            r"\b" + re.escape(source) + r"\b",
            target,
            value,
        )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_name(
    value,
):
    value = normalize_basic(value)

    if not value:
        return ""

    tokens = value.split()

    while tokens and tokens[0] in NAME_PREFIXES:
        tokens.pop(0)

    value = " ".join(tokens)

    for pattern in NAME_SUFFIX_PATTERNS:
        value = re.sub(
            pattern,
            " ",
            value,
        )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_expertise(
    value,
):
    return apply_replacements(
        value,
        EXPERTISE_REPLACEMENTS,
    )


def normalize_hospital(
    value,
):
    return apply_replacements(
        value,
        GENERAL_REPLACEMENTS,
    )


def normalize_address(
    value,
):
    value = apply_replacements(
        value,
        GENERAL_REPLACEMENTS,
    )

    value = re.sub(
        r"\b(rt|rw)\s*\d+[a-z]?\b",
        " ",
        value,
    )

    value = re.sub(
        r"\bkode pos\s*\d+\b",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def token_set(
    value,
):
    return set(normalize_basic(value).split())


def token_overlap(
    left,
    right,
):
    left_tokens = token_set(left)

    right_tokens = token_set(right)

    if not left_tokens or not right_tokens:
        return 0.0

    intersection = left_tokens & right_tokens

    return (
        len(intersection)
        / min(
            len(left_tokens),
            len(right_tokens),
        )
        * 100
    )


def flexible_similarity(
    expected,
    actual,
):
    expected = normalize_basic(expected)

    actual = normalize_basic(actual)

    if not expected or not actual:
        return 0.0

    if expected in actual:
        return 100.0

    return round(
        max(
            fuzz.token_set_ratio(
                expected,
                actual,
            ),
            fuzz.token_sort_ratio(
                expected,
                actual,
            ),
            fuzz.partial_ratio(
                expected,
                actual,
            ),
            token_overlap(
                expected,
                actual,
            ),
        ),
        2,
    )


def name_similarity(
    expected,
    document_text,
):
    expected = normalize_name(expected)

    document = normalize_name(document_text)

    if not expected:
        return 0.0

    if expected in document:
        return 100.0

    return round(
        max(
            fuzz.token_set_ratio(
                expected,
                document,
            ),
            fuzz.partial_ratio(
                expected,
                document,
            ),
        ),
        2,
    )


def expertise_similarity(
    expected,
    document_text,
):
    expected = normalize_expertise(expected)

    actual = normalize_expertise(document_text)

    if not expected:
        return 0.0

    if expected in actual:
        return 100.0

    return round(
        max(
            fuzz.token_set_ratio(
                expected,
                actual,
            ),
            fuzz.partial_ratio(
                expected,
                actual,
            ),
            token_overlap(
                expected,
                actual,
            ),
        ),
        2,
    )
