from pathlib import Path
import sys

# Ensure the backend repo root is importable in Vercel's function runtime.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
