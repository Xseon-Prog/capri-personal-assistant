"""Compatibility entry point. The application implementation lives in capri_app/."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capri_app.main import run  # noqa: E402


if __name__ == "__main__":
    run()
