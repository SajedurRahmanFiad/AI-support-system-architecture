import os
import sys
from pathlib import Path

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

# Debugging hang
import logging
logging.basicConfig(filename='/home/zomesnze/ai.sajedurrahmanfiad.me/passenger_debug.log', level=logging.DEBUG)
logging.debug("passenger_wsgi.py loaded")

from app.main import app as asgi_app

try:
    from a2wsgi import ASGIMiddleware
except Exception as exc:
    logging.error("Failed to import a2wsgi", exc_info=True)
    raise RuntimeError("a2wsgi is required for Passenger WSGI hosting.") from exc

logging.debug("Creating application with ASGIMiddleware")
application = ASGIMiddleware(asgi_app)
logging.debug("application created successfully")

# wrap the application to log requests
original_app = application
def application(environ, start_response):
    logging.debug(f"Received request: {environ.get('PATH_INFO')}")
    try:
        return original_app(environ, start_response)
    except Exception as e:
        logging.error("Error processing request", exc_info=True)
        raise
