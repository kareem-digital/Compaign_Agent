"""Integration tests.

Per Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf §1/§2: "Integration —
DB, Redis, Amazon adapter, task system — pytest + test DB / mocks /
Testcontainers where used." Exercise real collaborators within our
control: Postgres (checkpointer, future ORM models), Redis, and the
LangGraph graph compiled end-to-end, against docker-compose services or
Testcontainers rather than the dev stack.

Amazon/VOW adapter integration should be exercised at three levels (PDF
§2): mock (tests/unit — transport mocked), fake/stub (here — an
SDK-compatible fake or local stub server standing in for VOW/Amazon
Ads), and sandbox (an approved external sandbox, marked
`@pytest.mark.live_sandbox` and excluded from default runs — see
pyproject.toml). Never call production Amazon Ads or VOW from here.

Needs docker-compose services (db, redis) running; mark with
@pytest.mark.integration so CI can select/exclude this layer separately
from unit.
"""
