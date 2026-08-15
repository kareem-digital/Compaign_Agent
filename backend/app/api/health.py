"""Health and readiness endpoints.

/health/live  - is the process up?      (Kubernetes liveness probe)
/health/ready - can it serve traffic?   (Kubernetes readiness probe)

Keep these fast and dependency-light. A liveness probe that checks the
database will restart the pod when the database blips - which is wrong.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    version: str


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Process is running. No external dependencies checked."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
        version=__import__("app").__version__,
    )


@router.get("/ready", response_model=HealthResponse)
async def readiness() -> HealthResponse:
    """Ready to serve. Extend with real dependency checks as they arrive.

    TODO(PLT-03): check the database connection once the checkpointer lands.
    TODO(PLT-04): check VOW API reachability once wrappers land.
    """
    settings = get_settings()
    return HealthResponse(
        status="ready",
        service=settings.app_name,
        environment=settings.environment,
        version=__import__("app").__version__,
    )
