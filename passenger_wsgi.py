import os
import sys
from http import HTTPStatus
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient


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
os.environ.setdefault("PERSIST_BACKGROUND_JOB_RUNNER", "1")

from app.main import app as asgi_app
from app.services.jobs import ensure_background_job_runner_started


ensure_background_job_runner_started()

_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _build_headers(environ: dict[str, str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            headers[key[5:].replace("_", "-")] = value
    if environ.get("CONTENT_TYPE"):
        headers["Content-Type"] = environ["CONTENT_TYPE"]
    if environ.get("CONTENT_LENGTH"):
        headers["Content-Length"] = environ["CONTENT_LENGTH"]
    return headers


def application(environ, start_response):
    original_method = environ.get("REQUEST_METHOD", "GET")
    method = "GET" if original_method == "HEAD" else original_method
    path = quote(environ.get("PATH_INFO", "/") or "/", safe="/%:@")
    query_string = environ.get("QUERY_STRING", "")
    url = path + (f"?{query_string}" if query_string else "")

    body = b""
    content_length = environ.get("CONTENT_LENGTH")
    if content_length and content_length.isdigit():
        body = environ["wsgi.input"].read(int(content_length))

    client = TestClient(asgi_app)
    try:
        response = client.request(
            method,
            url,
            headers=_build_headers(environ),
            content=body,
            follow_redirects=False,
        )
    finally:
        client.close()

    reason = HTTPStatus(response.status_code).phrase if response.status_code in HTTPStatus._value2member_map_ else "OK"
    response_headers = [
        (name, value)
        for name, value in response.headers.items()
        if name.lower() not in _HOP_BY_HOP_HEADERS
    ]
    start_response(f"{response.status_code} {reason}", response_headers)
    return [b"" if original_method == "HEAD" else response.content]
