"""Document handlers and evidence-based analysis pipeline."""

import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))
