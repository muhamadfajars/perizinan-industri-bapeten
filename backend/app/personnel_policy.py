"""Industrial personnel results: mandatory identity, conditional supporting fields."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .protection.evidence import compact
from .protection.identity import person_key
from .protection.service import make_row


EMPTY = {"", "—", "-", "Belum terbaca"}
EXPIRY_LABEL = re.compile(
    r"berlaku\s+(?:s\.?\s*d\.?|sampai|hingga)|masa\s+berlaku|"
    r"valid\s+(?:until|through)|expiry|expires?\s+on|berakhir",
    re.I,
)
PERMIT_TYPES = {"SIB"}
APPROVAL_TYPES = {"ASSIGNMENT", "SPRINT", "WORK_LETTER"}
USAGE_PERIOD_LABEL = re.compile(
    r"periode\s+(?:pemakaian|penggunaan|pemantauan|pengukuran|evaluasi)|"
    r"masa\s+(?:pemakaian|penggunaan|pemantauan)",
    re.I,
)
MONTH_RANGE = re.compile(
    r"\b(?:januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\b"
    r".{0,35}(?:-|–|—|sampai|hingga|s\.d\.?)\s*"
    r"\b(?:januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\b"
    r"(?:\s+\d{4})?",
    re.I,
)


def source_evidence(pages, value):
    """Keep actual source pages; never default an unknown source to page one."""
    from src.extraction.personnel_document import get_page_text

    value = compact(value)
    if value in EMPTY:
        return []
    return [
        {"page": p["page"], "quote": value}
        for p in pages
        if value.casefold() in compact(get_page_text(p)).casefold()
    ]


def conditional_rows(parsed, original, application, doc, *, today=None):
    """Adapt extracted personnel fields without inferring missing expiry or profession."""
    from src.extraction.personnel_document import get_page_text, find_all_dates

    pages = parsed.get("pages") or []
    today = today or datetime.now(ZoneInfo("Asia/Jakarta")).date()
    people = application.get("personnel") or []
    names = [
        r
        for r in original
        if r["field"].startswith("Nama Petugas") or r["field"] == "Nama + Keahlian"
    ]
    if not names:
        names = [{"expected": "", "observed": "", "status": "REVIEW"}]
    rows = []
    kind = doc.get("subtype") or parsed.get("document_type") or "Belum teridentifikasi"

    def add(field, expected, observed, evidence, note="", **kwargs):
        result = make_row(doc["id"], field, expected, observed, evidence, note, **kwargs)
        result["detail"].update(
            type="personnel", source_label=kind, source_filename=doc["filename"]
        )
        rows.append(result)
        return result

    for name in names:
        expected = name.get("expected") or ""
        observed = name.get("observed") or ""
        evidence = source_evidence(pages, observed)
        result = add(
            "Nama",
            expected if expected not in EMPTY else "",
            observed if evidence else "",
            evidence,
            required=True,
        )
        if not expected or expected in EMPTY or not evidence:
            result.update(
                status="REVIEW",
                score=None,
                note="Nama pemilik dokumen belum dapat dihubungkan ke petugas formulir; periksa sumber.",
            )
        elif name.get("status") != "MATCH":
            result.update(
                status="REVIEW",
                score=name.get("score"),
                note="Kecocokan nama belum pasti; periksa nama pemilik dokumen pada sumber.",
            )
        candidates = [
            p for p in people if person_key(p.get("nama") or p.get("name")) == person_key(expected)
        ]
        person = candidates[0] if len(candidates) == 1 else None
        if len(candidates) > 1:
            result.update(
                status="REVIEW",
                note="Lebih dari satu petugas memiliki nama yang sama; periksa pemilik dokumen.",
            )
        if result["status"] == "MATCH" and person:
            result["detail"].update(person_name=expected, person_id=person_key(expected))

    linked = [r for r in rows if r["status"] == "MATCH" and r["detail"].get("person_id")]
    # Supporting fields on multi-person reports cannot be assigned to one person implicitly.
    owner = linked[0] if len(names) == len(linked) == 1 else None
    person = next(
        (
            p
            for p in people
            if owner and person_key(p.get("nama") or p.get("name")) == owner["detail"]["person_id"]
        ),
        {},
    )
    expected_role = next(
        (
            person.get(k)
            for k in ("keahlian", "keahlian_klasifikasi", "profesi", "jabatan")
            if person.get(k)
        ),
        "",
    )
    role_rows = [r for r in original if r["field"] in ("Keahlian", "Profesi", "Profesi / Keahlian")]
    role = next(
        (r.get("observed") for r in role_rows if source_evidence(pages, r.get("observed"))), ""
    )
    if not role and owner and expected_role:
        from src.matching.personnel_comparison import personnel_role_quote

        role, _ = personnel_role_quote(parsed.get("text") or "", expected_role)
    evidence = source_evidence(pages, role)
    if parsed.get("document_type") != "DOSE" and (
        evidence or parsed.get("document_type") in PERMIT_TYPES
    ):
        result = add(
            "Profesi / Keahlian",
            expected_role if evidence else expected_role,
            role,
            evidence,
            kind="role",
        )
        if not evidence:
            result.update(
                status="REVIEW",
                score=None,
                observed="Belum ditemukan dalam teks terbaca",
                note="Profesi/keahlian wajib diperiksa pada dokumen izin.",
            )
        elif not owner:
            result.update(
                status="INFO",
                score=None,
                note="Profesi terbaca; keterkaitannya dengan petugas perlu diperiksa.",
            )

    # Only a labelled validity statement is eligible. Issue dates and monitoring
    # periods must not become expiry dates through the legacy latest-date fallback.
    validity = []
    for page in pages:
        lines = get_page_text(page).splitlines()
        for index, line in enumerate(lines):
            if not EXPIRY_LABEL.search(line):
                continue
            quote = compact(line)
            dates = find_all_dates(quote)
            if not dates and index + 1 < len(lines):
                quote = compact(line + " " + lines[index + 1])
                dates = find_all_dates(quote)
            validity.append({"page": page["page"], "quote": quote, "dates": dates})
    evidence = [{"page": v["page"], "quote": v["quote"]} for v in validity]
    # Multiple dates (including ranges) are retained for review, never pick latest.
    dates = {d["date"] for v in validity for d in v["dates"]}
    value = " / ".join(dict.fromkeys(v["quote"] for v in validity))
    dtype = parsed.get("document_type")
    if dtype == "DOSE":
        from .personnel_period import usage_periods

        period_evidence = usage_periods(pages)
        period = add(
            "Periode Pemakaian",
            "",
            "; ".join(dict.fromkeys(x["value"] for x in period_evidence))
            or "Belum ditemukan dalam teks terbaca",
            period_evidence,
        )
        period["score"] = None
        if not period_evidence:
            period.update(
                status="REVIEW",
                note="Periode pemakaian atau pemantauan belum ditemukan; periksa dokumen sumber.",
            )
        else:
            period.update(
                status="INFO", note="Periode pemakaian ditampilkan sebagai informasi dokumen."
            )
    elif evidence or dtype in PERMIT_TYPES:
        result = add("Masa Berlaku", "", value, evidence)
        if len(dates) == 1:
            result["observed"] = next(iter(dates)).strftime("%d/%m/%Y")
        if not evidence:
            result.update(
                status="REVIEW",
                observed="Belum ditemukan dalam teks terbaca",
                note="Masa berlaku wajib diperiksa pada dokumen izin.",
            )
        elif len(dates) != 1:
            result.update(
                status="REVIEW",
                note="Masa berlaku terbaca tetapi tanggal akhirnya belum pasti; periksa sumber.",
            )
        elif next(iter(dates)) < today:
            result.update(
                status="REVIEW",
                note=f"Tanggal akhir masa berlaku telah lewat pada tanggal pemeriksaan {today.isoformat()}.",
            )
        else:
            result["note"] = (
                f"Tanggal akhir masa berlaku belum terlewati pada tanggal pemeriksaan {today.isoformat()}."
            )

    if parsed.get("document_type") in APPROVAL_TYPES:
        evidence = []
        for p in pages:
            text = get_page_text(p)
            for line in text.splitlines():
                if re.search(
                    r"ditandatangani|tanda\s+tangan|mengetahui|disahkan|direktur|pimpinan",
                    line,
                    re.I,
                ):
                    evidence.append({"page": p["page"], "quote": compact(line)})
                    break
        add(
            "Pengesahan",
            "",
            "Halaman kandidat pengesahan ditemukan"
            if evidence
            else "Belum ditemukan dalam teks terbaca",
            evidence,
            "Periksa keberadaan tanda tangan pada dokumen sumber.",
            images=True,
        )
    if owner:
        for row in rows:
            row["detail"].update(
                person_id=owner["detail"]["person_id"], person_name=owner["detail"]["person_name"]
            )
    return rows


def group_sections(sections):
    """Merge all personnel documents into one section; tag collective multi-person files."""
    # 1. Normalize document metadata and detect multi-person collective documents
    doc_people = {}
    personnel_sections = []
    for section in sections:
        if section.get("category") != "personel":
            continue
        personnel_sections.append(section)
        sec_doc_id = section.get("document_id") or section.get("id")
        sec_docs = section.get("source_documents") or []
        filename_by_id = {
            d.get("id"): d.get("filename")
            for d in sec_docs
            if isinstance(d, dict) and d.get("id") and d.get("filename")
        }
        sec_label = section.get("name") or ""
        if sec_label.startswith("Dokumen Personel - "):
            sec_label = sec_label[len("Dokumen Personel - ") :]
        for r in section.get("rows", []):
            doc_id = r.setdefault("document_id", sec_doc_id)
            detail = r.get("detail")
            if isinstance(detail, dict):
                if sec_label and sec_label != "Dokumen Personel":
                    detail.setdefault("source_label", sec_label)
                if doc_id in filename_by_id:
                    detail.setdefault("source_filename", filename_by_id[doc_id])
                p_id = detail.get("person_id")
                p_name = detail.get("person_name")
                if p_id and p_name and doc_id:
                    doc_people.setdefault(doc_id, set()).add((p_id, p_name))

    if not personnel_sections:
        return list(sections)

    merged_rows = []
    merged_docs_map = {}
    for section in personnel_sections:
        sec_doc_id = section.get("document_id") or section.get("id")
        sec_docs = section.get("source_documents") or ([{"id": sec_doc_id}] if sec_doc_id else [])
        for sdoc in sec_docs:
            if not isinstance(sdoc, dict) or not sdoc.get("id"):
                continue
            sid = sdoc["id"]
            if sid not in merged_docs_map:
                merged_docs_map[sid] = dict(sdoc)
            elif sdoc.get("filename") and not merged_docs_map[sid].get("filename"):
                merged_docs_map[sid]["filename"] = sdoc["filename"]

        for r in section.get("rows", []):
            doc_id = r.get("document_id")
            if doc_id and doc_id not in merged_docs_map:
                detail = r.get("detail") or {}
                entry = {"id": doc_id}
                if detail.get("source_filename"):
                    entry["filename"] = detail["source_filename"]
                merged_docs_map[doc_id] = entry
            detail = r.get("detail")
            if isinstance(detail, dict) and doc_id and len(doc_people.get(doc_id, set())) > 1:
                cur_pid = detail.get("person_id")
                co = sorted({name for pid, name in doc_people[doc_id] if pid != cur_pid})
                if co:
                    detail["shared_document"] = True
                    detail["co_owners"] = co
            merged_rows.append(r)

    first = personnel_sections[0]
    merged_source_docs = list(merged_docs_map.values())
    doc_count = len(merged_source_docs) or len(personnel_sections)
    merged_section = {
        "id": first.get("id"),
        "category": "personel",
        "name": f"Dokumen Personel · {doc_count} Dokumen",
        "document_id": first.get("document_id") or first.get("id"),
        "source_documents": merged_source_docs,
        "rows": merged_rows,
        "info": "Hasil evaluasi seluruh dokumen personel per berkas",
    }

    result = []
    inserted = False
    for section in sections:
        if section.get("category") != "personel":
            result.append(section)
        elif not inserted:
            result.append(merged_section)
            inserted = True
    return result
