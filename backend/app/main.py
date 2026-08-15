"""FastAPI application entrypoint.

Run locally:   uvicorn app.main:app --reload
Docs:          http://localhost:8000/docs
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.config import get_settings
from app.core.context import bind, clear
from app.core.logging import configure_logging, kv

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
ADVERTISER_HEADER = "Vowmade-Advertiser-Id"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown."""
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        console_format=settings.log_format,
        log_file=settings.log_file or None,
        total_max_bytes=settings.log_total_max_bytes,
        backup_count=settings.log_file_backup_count,
    )
    logger.info(
        "service.starting",
        extra=kv(
            service=settings.app_name,
            environment=settings.environment,
            mcp="mock" if settings.use_mock_mcp else "live",
            llm=settings.llm_model if settings.openai_api_key else "none (pattern matching)",
        ),
    )

    yield

    logger.info("service.stopping", extra=kv(service=settings.app_name))


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Agentic VOW",
        description="Conversational planning agent for CTV campaigns on Amazon DSP.",
        version=__import__("app").__version__,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # So the browser can read the correlation ID back off the response.
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def correlate(request: Request, call_next):
        """Bind correlation IDs for the life of the request.

        The frontend already sends `X-Request-ID`; honour it so a browser
        network entry and a server log line can be matched up. Generate one
        when it is absent, and echo it back either way.
        """
        clear()
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        bind(
            request_id=request_id,
            advertiser_id=request.headers.get(ADVERTISER_HEADER),
        )

        started = time.monotonic()
        response = await call_next(request)
        elapsed_ms = round((time.monotonic() - started) * 1000)

        response.headers[REQUEST_ID_HEADER] = request_id

        # Health probes fire constantly; logging them buries everything else.
        if not request.url.path.endswith(("/live", "/ready")):
            logger.info(
                "http.request",
                extra=kv(
                    method=request.method,
                    path=request.url.path,
                    status=response.status_code,
                    duration_ms=elapsed_ms,
                ),
            )

        return response

    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
