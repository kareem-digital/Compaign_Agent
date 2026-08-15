"""API / Protocol tests.

Per Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf §1: "API / Protocol —
AdCP, MCP/A2A contracts — pytest + HTTP/protocol client." Exercise
FastAPI routes through TestClient/httpx AsyncClient: status codes,
response schemas, error shapes, happy-path + validation + security +
state/persistence coverage per endpoint (PDF's create_media_buy
TC01-TC12 matrix is the template: valid input, unknown ID ->
PRODUCT_NOT_FOUND-style error, wrong option, unsupported field, missing
auth -> AUTH_REQUIRED, invalid auth -> AUTH_INVALID, wrong permission ->
INSUFFICIENT_PERMISSIONS, over-authority -> approval/block, duplicate
idempotency key -> no duplicate, unsupported request shape, missing
dependency -> waiting state, upstream unavailable -> transient/submitted).

This is the layer for tests/api/test_health.py today, and for the
ADCP-facing surface (sessions/chat, and the future approvals + audit
routers referenced in app/api/routes.py) as they land. Protocol-schema
conformance specifically (ADCP task-lifecycle shape, context_id/task_id
preservation) lives in tests/contract, sharing the same tools.
"""
