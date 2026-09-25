"""Keep the original product UI; its data adapter uses the V2 API."""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[1] / "debug_dashboard.py"), run_name="__main__")
