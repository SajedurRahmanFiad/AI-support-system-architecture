from pathlib import Path
import traceback
import sys

from fastapi import FastAPI

# Ensure the backend repo root is importable in Vercel's function runtime.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

app = FastAPI(title="B2B AI Support API (vercel entrypoint)")

try:
    from app.main import app as main_app  # noqa: E402

    app = main_app
except Exception as exc:  # noqa: BLE001
    startup_trace = traceback.format_exc()[-3500:]

    @app.get("/{path:path}")
    def startup_failure(path: str):
        return {
            "status": "startup_failure",
            "path": path,
            "error": str(exc),
            "traceback": startup_trace,
        }
