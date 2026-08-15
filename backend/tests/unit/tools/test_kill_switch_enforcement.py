"""The kill switch at the VOW boundary.

`test_kill_switch.py` proves the guard refuses. This proves the refusal happens
before anything leaves the process - which is the claim that actually matters
during an incident.
"""

from pathlib import Path

import pytest

from app.config import get_settings
from app.core.exceptions import KillSwitchEngagedError
from app.tools.mcp import VowTools
from app.tools.mcp.mock import MockMCPClient

ADVERTISER = "adv-123"


@pytest.fixture
def switch(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "KILL_SWITCH"
    monkeypatch.setenv("KILL_SWITCH_PATH", str(path))
    get_settings.cache_clear()
    return path


async def test_a_halted_call_never_reaches_vow(switch):
    """The whole purpose. Not "an error was raised" - the request did not leave
    the process, so nothing could have happened at VOW."""
    switch.touch()
    mcp = MockMCPClient(advertiser_id=ADVERTISER)

    with pytest.raises(KillSwitchEngagedError):
        await mcp.call_tool(VowTools.LIST_DEALS, {"market": "GB"})

    assert mcp.calls == [], "nothing may reach VOW while the switch is engaged"


async def test_a_halt_is_not_retried(switch):
    """Retrying while halted would multiply the noise during an incident and
    imply a transient fault, which this is not."""
    switch.touch()
    mcp = MockMCPClient(advertiser_id=ADVERTISER)

    with pytest.raises(KillSwitchEngagedError):
        await mcp.call_tool(VowTools.CTV_RATE_CARD, {"market": "GB"})

    assert len(mcp.calls) == 0


async def test_releasing_the_switch_restores_service(switch):
    """No restart, no redeploy - delete the file and the next call goes through."""
    switch.touch()
    mcp = MockMCPClient(advertiser_id=ADVERTISER)

    with pytest.raises(KillSwitchEngagedError):
        await mcp.call_tool(VowTools.LIST_DEALS, {"market": "GB"})

    switch.unlink()
    await mcp.call_tool(VowTools.LIST_DEALS, {"market": "GB"})

    assert [name for name, _ in mcp.calls] == [VowTools.LIST_DEALS]
