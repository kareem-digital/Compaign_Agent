"""Aggregates every API router.

New routers get registered here and nowhere else.
"""

from fastapi import APIRouter

from app.api import health, sessions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(sessions.router)

# Routers to come:
#   PLT-18  approvals   - fetch pending approval, submit decision
#   PLT-21  audit       - session decision history
#   Kareem  sessions    - start / continue a planning conversation
