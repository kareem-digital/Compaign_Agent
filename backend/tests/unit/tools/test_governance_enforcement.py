"""Governance at the VOW boundary.

`MCPClient.call_tool()` is the one method every VOW call passes through, so it
is the only place the check has to be. These tests are about the *wiring* - that
the check is in the path, in the right position, and cannot be gone around.

The distinction that matters: "an exception was raised" and "the request never
left the process" are different claims, and only the second means nothing
happened at VOW.
"""

import pytest

from app.core.exceptions import PolicyDeniedError
from app.tools.mcp import VowTools
from app.tools.mcp.mock import MockMCPClient

ADVERTISER = "adv-123"
ACTIVATE_STRATEGY = "vow.activate_strategy"


async def test_an_allowed_call_reaches_the_transport():
    """Enforcement must not break the working agent."""
    mcp = MockMCPClient(advertiser_id=ADVERTISER)

    await mcp.call_tool(VowTools.LIST_DEALS, {"market": "GB"})

    assert [name for name, _ in mcp.calls] == [VowTools.LIST_DEALS]


async def test_a_refused_call_never_reaches_the_transport():
    """The claim that actually matters.

    Not that an error surfaced - that the request never left the process, so
    nothing could have been created and no budget could have been committed.
    """
    mcp = MockMCPClient(advertiser_id=ADVERTISER)

    with pytest.raises(PolicyDeniedError):
        await mcp.call_tool(
            ACTIVATE_STRATEGY, {"approval_status": "APPROVED", "total_budget": 500_000}
        )

    assert mcp.calls == [], "a refused call must not reach VOW at all"


async def test_a_refusal_is_not_retried():
    """Guards the check's position: before `_retrying`, not inside it.

    Retrying a policy denial is pointless - the answer cannot change - and it
    would triple the log noise while implying a transient fault.
    """
    mcp = MockMCPClient(advertiser_id=ADVERTISER)

    with pytest.raises(PolicyDeniedError):
        await mcp.call_tool("vow.delete_everything", {})

    assert len(mcp.calls) == 0


async def test_the_advertiser_is_passed_as_the_policy_subject(monkeypatch):
    """So a policy can eventually decide differently per tenant."""
    seen: dict[str, str] = {}

    class RecordingGuard:
        def check(self, tool, arguments, agent_id):
            seen["tool"] = tool
            seen["agent_id"] = agent_id

    import app.tools.mcp.client as client_module

    monkeypatch.setattr(client_module, "get_guard", lambda: RecordingGuard())

    mcp = MockMCPClient(advertiser_id="adv-tenant-9")
    await mcp.call_tool(VowTools.LIST_DEALS, {"market": "GB"})

    assert seen == {"tool": VowTools.LIST_DEALS, "agent_id": "adv-tenant-9"}


async def test_the_advertiser_reaches_the_policy_as_an_argument(monkeypatch):
    """Scoping happens before the check, so a rule can read the advertiser from
    the action itself as well as from the subject."""
    captured: dict[str, dict] = {}

    class RecordingGuard:
        def check(self, tool, arguments, agent_id):
            captured["arguments"] = arguments

    import app.tools.mcp.client as client_module

    monkeypatch.setattr(client_module, "get_guard", lambda: RecordingGuard())

    mcp = MockMCPClient(advertiser_id=ADVERTISER)
    await mcp.call_tool(VowTools.LIST_DEALS, {"market": "GB"})

    assert captured["arguments"]["advertiser_id"] == ADVERTISER
