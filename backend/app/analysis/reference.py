from __future__ import annotations

import re


from .rows import _text
from .constants import FIELDS


def _facility_from_general(g):
    address = _text(g.get("alamat_proyek"))
    name = _text(g.get("nama_fasilitas"))
    if not name:
        head = address.split(",")[0].strip()
        if re.search(r"(?i)\b(?:RSUD|RS\.?|rumah\s+sakit|rumkit|klinik)\b", head):
            name = head
    return name or _text(g.get("instansi"))


def _to_form(app):
    g = app.get("general") or {}
    persons = app.get("personnel") or []
    tools = app.get("equipment") or []
    personnel = []
    for p in persons:
        if isinstance(p, dict):
            person = _text(
                next(
                    (
                        p.get(k)
                        for k in ("nama", "nama_petugas", "name", "nama_personel")
                        if p.get(k)
                    ),
                    "",
                )
            )
            role = _text(
                next(
                    (
                        p.get(k)
                        for k in (
                            "keahlian_klasifikasi",
                            "keahlian",
                            "profesi",
                            "jabatan",
                            "role",
                        )
                        if p.get(k)
                    ),
                    "",
                )
            )
        else:
            person, role = _text(p), ""
        if person:
            personnel.append({"name": person, "role": role})
    equipment = []
    for i, t in enumerate(tools):
        if isinstance(t, dict):
            equipment.append(
                {"label": f"Peralatan {i + 1}", **{k: _text(t.get(k)) for k in FIELDS}}
            )
    return {
        "facility": _facility_from_general(g),
        "address": _text(g.get("alamat_proyek")),
        "applicationNumber": _text(g.get("nomor_registrasi")) or None,
        "personnel": personnel,
        "equipment": equipment,
    }
