"""Compare management identities to the form; show culture and approval as information."""

from .. import storage
from ..protection.reader import read_document
from ..protection.extraction import metadata, norm
from ..protection.matching import choose
from ..protection.service import make_row, mark_unread_information
from ..protection.evidence import approval_evidence
from .extraction import identities, culture_evidence, culture_sections


def build_rows(document_id, application, pages, records, *, topics=None):
    def row(*args, **kwargs):
        result = make_row(document_id, *args, **kwargs)
        result["detail"]["type"] = "management"
        return result

    general = application.get("general") or {}
    rows = []
    for title, key, expected, kind in (
        (
            "Nama Instansi",
            "institution",
            general.get("instansi_asli") or general.get("instansi"),
            "institution",
        ),
        ("Alamat", "project_address", general.get("alamat_proyek"), "address"),
    ):
        candidates = [r for r in records if r.get(key)]
        best = choose(candidates, key, expected)
        evidence = [best] + [r for r in candidates if r is not best] if best else []
        rows.append(row(title, expected, best.get(key) if best else "", evidence, kind=kind))
    expected_number = ((application.get("administration") or {}).get("manajemen") or {}).get(
        "number"
    )
    numbers = metadata(pages, expected_number=expected_number or "")["number"]
    values = {norm(item["value"]): item["value"] for item in numbers}
    rows.append(
        row(
            "Nomor Dokumen",
            expected_number,
            " / ".join(values.values()),
            numbers,
            kind="number",
            conflict=len(values) > 1,
        )
    )
    approval = approval_evidence(pages)
    rows.append(
        row(
            "Lembar Pengesahan",
            "",
            "Halaman pengesahan ditemukan" if approval else "Belum ditemukan",
            approval,
            "Periksa tanda tangan pada dokumen sumber; stempel tidak diwajibkan.",
            group="Pengesahan",
            images=True,
        )
    )
    topics = culture_evidence(pages) if topics is None else topics
    found = all(topic["found"] for topic in topics)
    evidence = [item for topic in topics for item in topic["evidence"]]
    unique = {(item["page"], item["quote"]): item for item in evidence}
    culture = row(
        "Budaya Keselamatan dan Keamanan",
        "",
        "Ditemukan" if found else "Belum lengkap" if evidence else "Belum ditemukan",
        list(unique.values()),
        "Status menunjukkan ditemukannya uraian, bukan penilaian kecukupan penerapan budaya.",
        group="Budaya",
    )
    if evidence:
        sections = culture_sections(pages)
        if sections:
            start_page = sections[0]["page"]
            culture["page"] = start_page
            culture["detail"]["pages"] = [
                start_page,
                *[p for p in culture["detail"]["pages"] if p != start_page],
            ]
    culture["detail"]["topics"] = [{"label": t["label"], "found": t["found"]} for t in topics]
    if any(t.get("review_required") for t in topics):
        culture["detail"].update(
            review_required=True,
            review_reason="Uraian kedua aspek budaya belum terkonfirmasi; periksa dokumen sumber.",
        )
    rows.append(culture)
    return rows


def evaluate(doc, application, reference):
    pages, warnings = read_document(storage.file_path(doc))
    reading_incomplete = bool(warnings)
    records, extraction_warnings = identities(pages)
    from ..protection.semantic import culture_fallback

    topics, semantic_warnings = culture_fallback(pages, culture_evidence(pages))
    rows = build_rows(doc["id"], application, pages, records, topics=topics)
    if reading_incomplete:
        mark_unread_information(rows)
    if warnings or extraction_warnings or semantic_warnings:
        doc["_uncacheable"] = True
    return rows
