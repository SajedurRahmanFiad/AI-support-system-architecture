import os
import sys
from pathlib import Path

# VERCEL="1" prevents the background daemon thread from starting in the WSGI worker,
# as Passenger freezes background threads when there are no active requests.
# For cPanel, we set VERCEL="" to allow background job runner to work
# Also use PERSIST_BACKGROUND_JOB_RUNNER="1" for detached subprocess
is_vercel = os.environ.get("VERCEL", "").strip()
if is_vercel in {"1", "true", "yes", "on"}:
    os.environ["VERCEL"] = ""
os.environ["PERSIST_BACKGROUND_JOB_RUNNER"] = "1"

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

    raise RuntimeError("Could not resolve the Passenger repo root.")

REPO_ROOT = _resolve_repo_root()
os.chdir(REPO_ROOT)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import app as asgi_app
try:
    from a2wsgi import ASGIMiddleware
except Exception as exc:
    raise RuntimeError("a2wsgi is required for Passenger WSGI hosting.") from exc

_application = None

def application(environ, start_response):
    global _application
    if _application is None:
        _application = ASGIMiddleware(asgi_app)
    return _application(environ, start_response)
