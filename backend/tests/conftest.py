"""Shared test fixtures."""

import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.agent.llm import get_llm, get_voice_llm
from app.config import Settings, get_settings
from app.core.auth import AuthenticatedUser, JWTAccessTokenVerifier
from app.core.context import clear as clear_context
from app.governance.agt import get_guard
from app.main import create_app

TEST_ACCESS_TOKEN = "test-access-token"
# Named because it is part of the checkpointer key: threads are namespaced
# `subject:advertiser:session`, so a test reading state back needs this value.
TEST_SUBJECT = "test-user"


class StubAccessTokenVerifier(JWTAccessTokenVerifier):
    """Deterministic authentication for tests outside the security suite."""

    def __init__(self, subject: str = TEST_SUBJECT) -> None:
        self.settings = Settings(debug=False)
        self.subject = subject

    async def verify(self, token: str) -> AuthenticatedUser:
        if token != TEST_ACCESS_TOKEN:
            raise AssertionError("Unexpected test bearer token")
        return AuthenticatedUser(
            subject=self.subject,
            client_id="vow-agent-mfe",
            scopes=frozenset({"openid", "read"}),
            claims={"sub": self.subject},
        )

    async def close(self) -> None:
        return None


# Everything process-wide that a test can change. All `lru_cache`d, so all of it
# survives a test unless something clears it. `get_voice_llm` is here as well as
# `get_llm` because the two clients are built on different budgets and cached
# separately - clearing only one leaves the other holding the previous test's
# settings.
_CACHED_SINGLETONS = (get_settings, get_guard, get_llm, get_voice_llm)


def _reset_all() -> None:
    for cached in _CACHED_SINGLETONS:
        cached.cache_clear()
    clear_context()


@pytest.fixture(autouse=True)
def _isolate_process_state():
    """Reset the two kinds of state that outlive a test.

    **Cached singletons.** Settings, the policy guard and both LLM clients are
    `lru_cache`d, so a test that changes configuration leaks into every test
    that follows - the next one silently reuses a guard built from the previous
    test's settings, and the failure appears somewhere unrelated.

    **Correlation context.** Context variables belong to the task, not the
    fixture, so a `session_id` bound in one test would otherwise follow the next
    into its assertions, and a bearer token would outlive the request that set
    it.

    Autouse because both failures are silent and surface as cross-test
    contamination somewhere else entirely. Cleared on the way in as well as out,
    so a test is isolated even from something that ran outside a fixture.
    """
    _reset_all()
    yield
    _reset_all()


@pytest.fixture
def client() -> TestClient:
    """A test client against a fresh app instance.

    Note this does not enter the app's lifespan, so `configure_logging` does not
    run and records go to pytest's own capture. That is deliberate - the suite
    asserts behaviour, not log formatting - but it does mean logging config is
    exercised by its own unit tests rather than here.
    """
    return TestClient(create_app(access_token_verifier=StubAccessTokenVerifier()))


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_ACCESS_TOKEN}"}


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Run pylint after the local test session so a plain `pytest` run
    produces all four reports (coverage/junit/html + lint) in one shot.

    Skipped in CI, where pylint already runs as its own dedicated lint step
    in ci-backend.yml (so it isn't run twice per pipeline run).
    """
    if os.environ.get("CI"):
        return

    rootpath = session.config.rootpath
    reports_dir = rootpath / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    try:
        with open(reports_dir / "backend-Pylint_report.txt", "w") as report_file:
            subprocess.run(
                [sys.executable, "-m", "pylint", "app", "--output-format=text"],
                cwd=rootpath,
                stdout=report_file,
                stderr=subprocess.STDOUT,
                check=False,
            )
    except OSError as exc:
        print(f"Skipped pylint report (pylint not runnable: {exc})")
