"""What a refused action looks like to the client.

The rule under test: the client learns *that* it was refused, never *why*. Tool
names, rule names and the engine's reasoning are internal. They stay in the
server log, reachable via the correlation ID the response carries.
"""

import pytest

from app.config import get_settings
from app.governance.agt import get_guard

CHAT = "/api/v1/sessions/chat"
HEADERS = {
    "Authorization": "Bearer test-access-token",
    "Vowmade-Advertiser-Id": "adv-123",
}
BRIEF = "Plan a UK CTV campaign for August 2026, budget 50,000, 30 second creatives"


@pytest.fixture
def everything_refused(tmp_path, monkeypatch):
    """Point the guard at a policy that permits nothing.

    A normal planning turn is then refused at its first VOW call, which is how
    we observe the response without needing an action that does not exist yet.

    The LLM is disabled too: extraction runs before any tool call, and a live
    API key would make these tests slow and non-deterministic (TMP-18).
    """
    policy = tmp_path / "deny_all.yaml"
    policy.write_text(
        "apiVersion: governance.toolkit/v1\nname: deny-all\ndefault_action: deny\nrules: []\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GOVERNANCE_POLICY_PATH", str(policy))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    get_guard.cache_clear()


def _refused(client):
    return client.post(CHAT, json={"message": BRIEF}, headers=HEADERS)


def test_a_refused_action_returns_403(client, everything_refused):
    """Not 500. Nothing broke - the system refused, correctly.

    Not 502 either: VOW was never contacted.
    """
    assert _refused(client).status_code == 403


def test_the_client_is_told_nothing_internal(client, everything_refused):
    """Exactly this string, and nothing else."""
    assert _refused(client).json() == {"detail": "This action is not permitted."}


@pytest.mark.parametrize("leak", ["vow.", "rule", "policy", "deny-all", "default"])
def test_no_internal_detail_leaks_into_the_body(client, everything_refused, leak):
    """Belt and braces: a future change to the message must not start echoing
    the engine's reasoning back to the client."""
    assert leak not in _refused(client).text.lower()


def test_a_refusal_is_traceable(client, everything_refused):
    """Why a generic message costs nothing operationally.

    The response carries the correlation ID, so "it refused me" becomes a
    lookup that finds the exact decision, the rule and the advertiser.
    """
    response = _refused(client)

    assert response.status_code == 403
    assert response.headers.get("X-Request-ID"), "a refusal must be traceable"


def test_normal_planning_is_not_refused(client):
    """The counter-test. Without the deny-all policy the shipped policy applies,
    the four planning tools are allow-listed, and a turn succeeds.

    Without this, every assertion above would still pass if governance refused
    absolutely everything.
    """
    response = client.post(CHAT, json={"message": BRIEF}, headers=HEADERS)

    assert response.status_code == 200
