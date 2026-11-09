"""Compare management identities to the form; show culture and approval as information."""

from .. import storage
from ..protection.reader import read_document
from ..protection.extraction import metadata, norm
from ..protection.matching import choose
from ..protection.service import make_row
from ..protection.evidence import approval_evidence
from .extraction import identities, culture_evidence


def build_rows(document_id, application, pages, records):
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
    numbers = metadata(pages)["number"]
    values = {norm(item["value"]): item["value"] for item in numbers}
    expected_number = ((application.get("administration") or {}).get("manajemen") or {}).get(
        "number"
    )
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
    topics = culture_evidence(pages)
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
    culture["detail"]["topics"] = [{"label": t["label"], "found": t["found"]} for t in topics]
    rows.append(culture)
    return rows


def evaluate(doc, application, reference):
    pages, warnings = read_document(storage.file_path(doc))
    records, extraction_warnings = identities(pages)
    rows = build_rows(doc["id"], application, pages, records)
    warnings.extend(extraction_warnings)
    if warnings:
        note = make_row(
            doc["id"], "Catatan pembacaan", "", "\n".join(warnings), [], group="Catatan pembacaan"
        )
        note["detail"]["type"] = "management"
        rows.append(note)
    return rows
