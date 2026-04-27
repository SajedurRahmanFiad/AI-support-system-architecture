import os
import sys
from pathlib import Path

from a2wsgi import ASGIMiddleware


def _resolve_repo_root() -> Path:
    configured = os.environ.get("REPO_ROOT", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if (candidate / "app").exists():
            return candidate

    current_dir = Path(__file__).resolve().parent
    if (current_dir / "app").exists():
        return current_dir

    fallback = Path("/home/zomesnze/repositories/AI-support-system-architecture")
    if (fallback / "app").exists():
        return fallback

    raise RuntimeError("Could not resolve the Passenger repo root. Set REPO_ROOT to the backend clone path.")


REPO_ROOT = _resolve_repo_root()
os.chdir(REPO_ROOT)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import app
from app.services.jobs import ensure_background_job_runner_started


ensure_background_job_runner_started()
application = ASGIMiddleware(app)
