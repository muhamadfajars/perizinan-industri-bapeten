from __future__ import annotations


from .programs import _supp
from .equipment import _functional, _import, _specification
from .personnel import _personnel
from .labels import _label
from .constants import SUPP
from ..protection.service import evaluate as evaluate_protection

from ..management.service import evaluate as evaluate_management
from ..quality_hybrid import evaluate as evaluate_quality
from ..calibration_hybrid import evaluate as evaluate_calibration

HANDLERS = {
    **{k: _supp for k in SUPP},
    "fungsi": _functional,
    "mutu": evaluate_quality,
    "kalibrasi": evaluate_calibration,
    "personel": _personnel,
    "spesifikasi": _specification,
    "impor": _import,
    "label": _label,
    "proteksi": evaluate_protection,
    "manajemen": evaluate_management,
}
