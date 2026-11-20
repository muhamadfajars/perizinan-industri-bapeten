"""Program Proteksi evaluation. Form comparisons and display-only content stay separate."""

from functools import partial
import uuid
from .identity import person_similarity, person_key
from .. import storage
from ..analysis.constants import FIELDS
from .reader import read_document
from .extraction import extract_records, metadata, norm, _serial_core
from .evidence import information
from .matching import compare, choose, date_key


def make_row(
    document_id,
    field,
    expected,
    observed,
    evidence,
    note="",
    *,
    group="Data acuan",
    required=False,
    images=False,
    kind="text",
    conflict=False,
):
    status, score, reason = compare(expected, observed, kind)
    if expected and conflict:
        status, reason = (
            "REVIEW",
            "Beberapa nilai berbeda ditemukan untuk data yang sama; perlu pemeriksaan.",
        )
    return {
        "id": uuid.uuid4().hex,
        "field": field,
        "expected": str(expected or "—"),
        "observed": str(observed or "Belum terbaca"),
        "status": status,
        "score": score,
        "document_id": document_id,
        "page": evidence[0]["page"] if evidence else None,
        "quote": evidence[0].get("quote", "") if evidence else "",
        "note": " ".join(filter(None, [note, reason])),
        "detail": {
            "type": "protection",
            "group": group,
            "required": required,
            "images": images,
            "heading": field,
            "evidence": evidence,
            "pages": list(dict.fromkeys(e["page"] for e in evidence)),
        },
    }


def evaluate(doc, application, reference):
    path = storage.file_path(doc)
    pages, warnings = read_document(path)
    reading_incomplete = bool(warnings)
    records, extraction_warnings = extract_records(path, pages, application)
    warnings.extend(extraction_warnings)
    from .semantic import protection_fallback

    semantic, semantic_warnings = protection_fallback(pages)
    warnings.extend(semantic_warnings)
    rows = build_rows(doc["id"], application, pages, records, semantic=semantic)
    if reading_incomplete:
        mark_unread_information(rows)
    if warnings:
        doc["_uncacheable"] = True
    return rows


def mark_unread_information(rows):
    """Unreadable pages cannot establish that supporting information is absent."""
    for item in rows:
        if item["status"] == "INFO" and not item["detail"]["pages"]:
            item["detail"].update(
                review_required=True,
                review_reason="Sebagian halaman belum terbaca; periksa informasi ini pada dokumen sumber.",
            )


def build_rows(document_id, application, pages, records, *, semantic=None):
    row = partial(make_row, document_id)
    rows = []
    general = application.get("general") or {}
    administration = (application.get("administration") or {}).get("proteksi") or {}
    meta = metadata(
        pages,
        expected_number=administration.get("number") or "",
        expected_date=administration.get("date") or "",
    )
    for key, title in (("number", "Nomor Dokumen"), ("date", "Tanggal Dokumen")):
        values = meta[key]
        unique = {}
        for value in values:
            identity = date_key(value["value"]) if key == "date" else norm(value["value"])
            unique.setdefault(identity or value["value"], value["value"])
        observed = " / ".join(unique.values())
        rows.append(
            row(
                title,
                administration.get(key),
                observed,
                values,
                kind=key,
                conflict=len(unique) > 1,
            )
        )
        if (
            key == "date"
            and values
            and all("dibuat" in x["quote"].lower() for x in values)
            and administration.get(key)
        ):
            rows[-1]["note"] += (
                " Label sumber: tanggal dibuat; kecocokan nilai tanggal tidak memverifikasi pengesahan."
            )
    identity = list(records.get("identity", []))
    identity.extend(
        {"project_address": r["location"], "page": r["page"], "quote": r["quote"]}
        for r in records.get("equipment", [])
        if r.get("location")
    )
    for field, key, expected, kind in (
        (
            "Nama Instansi",
            "institution",
            general.get("instansi_asli") or general.get("instansi"),
            "institution",
        ),
        (
            "Alamat",
            "project_address",
            general.get("alamat_proyek"),
            "address",
        ),
    ):
        found = [x for x in identity if x.get(key)]
        best = choose(found, key, expected)
        if best:
            found = [best] + [x for x in found if x is not best]
        rows.append(
            row(
                field,
                expected,
                best.get(key) if best else "",
                found,
                "Acuan identitas lokasi adalah Alamat Proyek pada formulir."
                if kind == "address"
                else "",
                kind=kind,
                conflict=kind == "institution" and len({norm(x[key]) for x in found}) > 1,
            )
        )
        # The displayed value and primary source must refer to the same candidate.
        if best:
            rows[-1]["page"], rows[-1]["quote"] = best["page"], best["quote"]
    people = records.get("personnel", [])
    for person_index, person in enumerate(application.get("personnel") or [], 1):
        name = person.get("nama") or ""
        best = choose(people, "name", name)
        if best and person_similarity(name, best["name"]) < 0.72:
            best = None
        found = [
            p for p in people if best and person_key(p.get("name")) == person_key(best["name"])
        ]
        for field, key, expected, kind in (
            ("Nama", "name", name, "text"),
            ("Profesi / Keahlian", "role", person.get("keahlian_klasifikasi"), "role"),
        ):
            field_sources = [p for p in found if p.get(key)]
            if key == "role" and expected and len(field_sources) > 1:
                field_sources.sort(
                    key=lambda p: (
                        compare(expected, p["role"], "role")[0] != "MATCH",
                        -(compare(expected, p["role"], "role")[1] or 0),
                    )
                )
            observed = field_sources[0][key] if field_sources else ""
            if key == "role" and expected and observed and compare(expected, observed, "role")[0] == "MATCH":
                conflict = False
            else:
                conflict = len({norm(p.get(key)) for p in found if p.get(key)}) > 1
            rows.append(
                row(
                    f"Petugas {name}: {field}",
                    expected,
                    observed,
                    field_sources,
                    group="Petugas",
                    kind=kind,
                    conflict=conflict,
                )
            )
            rows[-1]["detail"].update(
                person_id=str(person_index), person_name=name, field_label=field
            )
            if key == "role" and expected and best and norm(name) != norm(best["name"]):
                rows[-1]["note"] += (
                    " Nama pada sumber berbeda; kecocokan profesi tidak mengonfirmasi identitas orang."
                )
    equipment = records.get("equipment", [])
    for i, tool in enumerate(application.get("equipment") or [], 1):
        serial = norm(tool.get("nomor_seri_unit"))
        found = [x for x in equipment if serial and norm(x.get("nomor_seri_unit")) == serial]
        if not found:
            found = [
                x
                for x in equipment
                if tool.get("nomor_seri_tabung")
                and norm(x.get("nomor_seri_tabung")) == norm(tool["nomor_seri_tabung"])
            ]
        if not found:
            unit_core = _serial_core(tool.get("nomor_seri_unit"))
            tube_core = _serial_core(tool.get("nomor_seri_tabung"))
            if len(unit_core) >= 4:
                found = [x for x in equipment if _serial_core(x.get("nomor_seri_unit")) == unit_core]
            if not found and len(tube_core) >= 4:
                found = [x for x in equipment if _serial_core(x.get("nomor_seri_tabung")) == tube_core]
        # With multiple unidentified rows, never combine arbitrary field matches.
        if not found and len(equipment) == 1 and len(application.get("equipment", [])) == 1:
            found = equipment[:1]
        for key, label in FIELDS.items():
            field_sources = [item for item in found if item.get(key)]
            rows.append(
                row(
                    f"Alat {i}: {label}",
                    tool.get(key),
                    field_sources[0][key] if field_sources else "",
                    field_sources,
                    group="Pesawat Sinar-X",
                    kind="serial" if "seri" in key else "text",
                    conflict=len({norm(x.get(key)) for x in found if x.get(key)}) > 1,
                )
            )
    rows.extend(information(pages, row, semantic=semantic))
    priority = {"Nama Instansi": 0, "Alamat": 1, "Nomor Dokumen": 2, "Tanggal Dokumen": 3}
    return sorted(rows, key=lambda item: priority.get(item["field"], 4))
