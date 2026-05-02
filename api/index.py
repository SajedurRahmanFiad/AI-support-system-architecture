from pathlib import Path
import traceback
import sys

# Ensure the backend repo root is importable in Vercel's function runtime.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from app.main import app  # noqa: E402
except Exception as exc:  # noqa: BLE001
    from fastapi import FastAPI

    app = FastAPI()
    startup_trace = traceback.format_exc()

    @app.get("/{path:path}")
    def startup_failure(path: str):
        return {
            "status": "startup_failure",
            "path": path,
            "error": str(exc),
            "traceback": startup_trace[-3500:],
        }
