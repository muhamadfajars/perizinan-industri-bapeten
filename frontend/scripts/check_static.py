"""Check UI structure and server-backed analysis wiring after source changes."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
sources = "\n".join(p.read_text(encoding="utf-8") for p in (root / "src").rglob("*.tsx"))
api = (root / "src/api.ts").read_text(encoding="utf-8")
categories = (root / "src/data/categories.ts").read_text(encoding="utf-8")
css = "\n".join(p.read_text(encoding="utf-8") for p in (root / "src/styles").glob("*.css"))
ids = re.findall(r"id:\s*['\"]([^'\"]+)['\"]", categories)
assert len(ids) == 14 and len(set(ids)) == 14
for page in ["ringkasan", "upload", "formulir", "matching", "dokumen"]:
    assert re.search(rf'id="{page}"\s+hidden=', sources), page
assert all(name in sources for name in ("runAnalysis", "jobResults", "jobStatus", "newApplication"))
assert "visibleMatchingSections.map" in sources
assert "DEMO_MATCHING" not in sources and "DEMO_FORM" not in sources
assert "application_id" in api and "Bearer " in api
assert re.search(r"\.page-section\[hidden\]\s*\{\s*display:\s*none\s*!important;", css)
print("PASS: five pages, fourteen categories, server analysis and hidden-page styling")
