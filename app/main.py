"""ESCAPE — AI Travel Escape Planner, built on Tutu MCP.

Entry point: builds the app, mounts the API and serves the static frontend from
the same origin so there is no CORS, no second process and no build step on the
server. One `uvicorn app.main:app` is the whole deployment.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api.deps import build_container
from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import EscapeError
from app.core.logging import new_request_id, request_id_var, setup_logging

logger = logging.getLogger("tutu_ryadom")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
INDEX_PATH = FRONTEND_DIR / "index.html"
BASKET_PATH = FRONTEND_DIR / "basket.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the container on startup, warm up MCP, tear down on exit."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)

    container = build_container(settings)
    app.state.container = container
    logger.info(
        "escape starting",
        extra={"env": settings.environment, "demo_mode": settings.demo_mode},
    )

    if settings.mcp_enabled and not settings.demo_mode:
        # Warm the tool catalog so the first user search is not the one that
        # pays for the handshake. A failure here is logged, never fatal.
        try:
            await container.travel.connect()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("mcp warmup failed", extra={"error": str(exc)})

    try:
        yield
    finally:
        await container.aclose()
        logger.info("escape stopped")


def create_app() -> FastAPI:
    """Application factory — used by uvicorn and by the test suite."""
    settings = get_settings()
    app = FastAPI(
        title="Туту Рядом",
        description="Короткие поездки по бюджету, времени и настроению на базе Tutu MCP.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def correlate(request: Request, call_next):
        """Attach a short request id to every log line and response header."""
        token = request_id_var.set(new_request_id())
        try:
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id_var.get()
            return response
        finally:
            request_id_var.reset(token)

    @app.exception_handler(EscapeError)
    async def escape_error_handler(request: Request, exc: EscapeError):
        """Known failure: log the detail, show the user a sentence."""
        logger.warning(
            "handled error",
            extra={"code": exc.code, "path": request.url.path, "detail": exc.detail},
        )
        return JSONResponse(
            status_code=exc.status_code if exc.status_code != 200 else 200,
            content={"error": {"code": exc.code, "message": exc.user_message}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        """Invalid input: never echo a pydantic traceback at the user."""
        logger.info("validation failed", extra={"path": request.url.path})
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_input",
                    "message": "Проверьте введённые значения — что-то не сходится.",
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        """Last line of defence. The user sees one sentence, we see everything."""
        logger.exception("unhandled error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Что-то сломалось на нашей стороне. Попробуйте ещё раз.",
                }
            },
        )

    app.include_router(router)

    if FRONTEND_DIR.exists():
        app.mount(
            "/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static"
        )

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            """Serve the main frontend."""
            return FileResponse(INDEX_PATH)

        @app.get("/basket", include_in_schema=False)
        async def basket() -> FileResponse:
            """Serve the purchase basket page."""
            return FileResponse(BASKET_PATH)

    return app


app = create_app()
