from __future__ import annotations


from .programs import _program, _supp
from .equipment import _functional, _import, _specification, _suitability
from .personnel import _personnel
from .labels import _label
from .constants import PROG, SUPP

HANDLERS = {
    **{k: _program for k in PROG},
    **{k: _supp for k in SUPP},
    "kesesuaian": _suitability,
    "fungsi": _functional,
    "personel": _personnel,
    "spesifikasi": _specification,
    "impor": _import,
    "label": _label,
}
