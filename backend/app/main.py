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

from app.api.errors import register_error_handlers
from app.api.routes import api_router
from app.config import Settings, get_settings
from app.core.auth import JWTAccessTokenVerifier
from app.core.context import bind, clear
from app.core.logging import configure_logging, kv

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
ADVERTISER_HEADER = "Vowmade-Advertiser-Id"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown."""
    settings = app.state.settings
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
            auth=settings.auth_mode,
            mcp="mock" if settings.use_mock_mcp else "live",
            llm=settings.llm_model if settings.openai_api_key else "none (pattern matching)",
        ),
    )
    if settings.auth_mode == "local":
        logger.warning(
            "authentication.local_bypass_enabled",
            extra=kv(subject=settings.local_auth_subject),
        )

    yield

    await app.state.access_token_verifier.close()
    logger.info("service.stopping", extra=kv(service=settings.app_name))


def create_app(
    settings: Settings | None = None,
    *,
    access_token_verifier: JWTAccessTokenVerifier | None = None,
) -> FastAPI:
    settings = settings or get_settings()

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
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            ADVERTISER_HEADER,
        ],
        # So the browser can read the correlation ID back off the response.
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.state.settings = settings
    app.state.access_token_verifier = access_token_verifier or JWTAccessTokenVerifier(settings)

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
        try:
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
        finally:
            # Includes bearer and delegated tokens, which must not outlive the
            # request even if the ASGI worker reuses its execution task.
            clear()

    app.include_router(api_router, prefix=settings.api_prefix)
    # Safety net beneath the routes: a typed failure that no route caught still
    # becomes the right status code with the request id attached, rather than an
    # untyped 500 with the cause dropped. Routes that want a specific message
    # still catch it themselves - see `sessions.chat`.
    register_error_handlers(app)

    return app


app = create_app()
