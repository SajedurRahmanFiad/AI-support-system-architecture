from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import sys
import time

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.database import init_db
from app.services.jobs import BackgroundJobRunner


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    runner = BackgroundJobRunner()
    runner.start()
    try:
        yield
    finally:
        runner.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    init_db()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
        root_path=settings.root_path,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started = time.perf_counter()
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query or None,
            "client_ip": request.client.host if request.client else None,
        }
        try:
            response = await call_next(request)
        except Exception as exc:
            event["level"] = "ERROR"
            event["status_code"] = 500
            event["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            event["error"] = repr(exc)
            print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)
            raise

        event["level"] = "INFO"
        event["status_code"] = response.status_code
        event["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)
        return response

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
            "health": "api/health",
            "docs": "docs",
        }

    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
