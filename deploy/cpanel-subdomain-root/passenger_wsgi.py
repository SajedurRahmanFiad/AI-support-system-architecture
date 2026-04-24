import os
import sys
from threading import Lock
from http import HTTPStatus
from urllib.parse import quote

from fastapi.testclient import TestClient

# This shim is for LiteSpeed/CloudLinux hosts that do not serve the repo root
# cleanly as a Python app on a full subdomain. Put this file in the subdomain
# document root and point REPO_ROOT at the real project clone.
REPO_ROOT = "/home/yourcpaneluser/repositories/b2b-ai-support-api"

os.chdir(REPO_ROOT)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.main import app as asgi_app

_client = TestClient(asgi_app)
_client_lock = Lock()

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
            name = key[5:].replace("_", "-")
            headers[name] = value
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

    content_length = environ.get("CONTENT_LENGTH")
    body = b""
    if content_length and content_length.isdigit():
        body = environ["wsgi.input"].read(int(content_length))

    with _client_lock:
        response = _client.request(
            method,
            url,
            headers=_build_headers(environ),
            content=body,
            follow_redirects=False,
        )

    reason = (
        HTTPStatus(response.status_code).phrase
        if response.status_code in HTTPStatus._value2member_map_
        else "OK"
    )
    response_headers = [
        (name, value)
        for name, value in response.headers.items()
        if name.lower() not in _HOP_BY_HOP_HEADERS
    ]
    start_response(f"{response.status_code} {reason}", response_headers)
    return [b"" if original_method == "HEAD" else response.content]
