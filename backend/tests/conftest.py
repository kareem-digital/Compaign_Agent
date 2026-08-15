"""Shared test fixtures."""

import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.agent.llm import get_llm
from app.config import get_settings
from app.core.context import clear as clear_context
from app.governance.agt import get_guard
from app.main import create_app


@pytest.fixture(autouse=True)
def _isolate_cached_singletons(monkeypatch):
    """Settings, the policy guard and the LLM client are all `lru_cache`d.

    Without this, a test that changes configuration leaks into every test that
    follows - the next one silently reuses a guard built from the previous
    test's settings, and the failure appears somewhere unrelated.

    Also clears the correlation context and ensures deterministic offline execution.
    """
    if "LIVE_LLM_TEST" not in os.environ:
        monkeypatch.setenv("OPENAI_API_KEY", "")
    for reset in (get_settings.cache_clear, get_guard.cache_clear, get_llm.cache_clear):
        reset()
    clear_context()
    yield
    for reset in (get_settings.cache_clear, get_guard.cache_clear, get_llm.cache_clear):
        reset()
    clear_context()



@pytest.fixture
def client() -> TestClient:
    """A test client against a fresh app instance."""
    return TestClient(create_app())


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
