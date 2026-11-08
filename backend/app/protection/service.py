"""Program Proteksi evaluation. Form comparisons and display-only content stay separate."""

from functools import partial
import uuid
from difflib import SequenceMatcher
from .. import storage
from ..analysis.constants import FIELDS
from .reader import read_document
from .extraction import extract_records, metadata, norm
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
    records, extraction_warnings = extract_records(path, pages)
    warnings.extend(extraction_warnings)
    rows = build_rows(doc["id"], application, pages, records)
    if warnings:
        rows.append(
            make_row(
                doc["id"],
                "Catatan pembacaan",
                "",
                "\n".join(warnings),
                [],
                group="Catatan pembacaan",
            )
        )
    return rows


def build_rows(document_id, application, pages, records):
    row = partial(make_row, document_id)
    rows = []
    general = application.get("general") or {}
    administration = (application.get("administration") or {}).get("proteksi") or {}
    meta = metadata(pages)
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
        if best and SequenceMatcher(None, norm(name), norm(best["name"])).ratio() < 0.72:
            best = None
        found = [p for p in people if best and norm(p.get("name")) == norm(best["name"])]
        for field, key, expected, kind in (
            ("Nama", "name", name, "text"),
            ("Profesi / Keahlian", "role", person.get("keahlian_klasifikasi"), "role"),
        ):
            observed = best.get(key, "") if best else ""
            rows.append(
                row(
                    f"Petugas {name}: {field}",
                    expected,
                    observed,
                    found,
                    group="Petugas",
                    kind=kind,
                    conflict=len({norm(p.get(key)) for p in found if p.get(key)}) > 1,
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
        # With multiple unidentified rows, never combine arbitrary field matches.
        if not found and len(equipment) == 1 and len(application.get("equipment", [])) == 1:
            found = equipment[:1]
        best = found[0] if found else {}
        for key, label in FIELDS.items():
            rows.append(
                row(
                    f"Alat {i}: {label}",
                    tool.get(key),
                    best.get(key, ""),
                    found,
                    group="Pesawat Sinar-X",
                    kind="serial" if "seri" in key else "text",
                    conflict=len({norm(x.get(key)) for x in found if x.get(key)}) > 1,
                )
            )
    rows.extend(information(pages, row))
    priority = {"Nama Instansi": 0, "Alamat": 1, "Nomor Dokumen": 2, "Tanggal Dokumen": 3}
    return sorted(rows, key=lambda item: priority.get(item["field"], 4))
