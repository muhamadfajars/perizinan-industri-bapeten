"""Environment configuration loaded before application services."""

import os
from pathlib import Path

# Auto-load backend/.env if running uvicorn directly without shell wrapper
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
if _ENV_FILE.is_file():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _k, _v = _k.strip(), _v.strip().strip("'\"")
            if _k and _k not in os.environ:
                os.environ[_k] = _v

CATEGORIES = {
    "formulir",
    "proteksi",
    "perawatan",
    "manajemen",
    "teknis",
    "personel",
    "tld",
    "spesifikasi",
    "label",
    "impor",
    "kesesuaian",
    "fungsi",
    "paparan",
    "kebocoran",
}
EXT = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".docx"}
MAX_FILE = int(os.environ.get("BAPETEN_MAX_FILE_MB", "40")) * 1024 * 1024
MAX_DOCS = int(os.environ.get("BAPETEN_MAX_DOCUMENTS", "120"))
TOKEN = os.environ.get("BAPETEN_API_TOKEN", "")
