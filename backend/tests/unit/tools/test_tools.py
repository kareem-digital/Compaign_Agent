"""Tests for the tool-wrapper framework.

These use mocked HTTP responses so they run without VOW being available.
Integration tests against real VOW staging are separate and marked.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.exceptions import AdvertiserContextMissingError, VowApiError, VowAuthError
from app.tools.auth import StubAuth
from app.tools.base import BaseVOWTool
from app.tools.deals import DealsTool

# --- Helpers ---


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Build a fake httpx response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = ""
    resp.raise_for_status = lambda: None
    return resp


def _mock_client(response) -> AsyncMock:
    """Build a fake httpx client that returns the given response."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request.return_value = response
    return client


# --- Base tool tests ---


@pytest.mark.asyncio
async def test_base_tool_sends_advertiser_header():
    """Every call must carry the Vowmade-Advertiser-Id header."""
    response = _mock_response(200, {"results": []})
    client = _mock_client(response)

    tool = BaseVOWTool(client=client, auth=StubAuth(), advertiser_id="adv-123")
    await tool._get("/deals/")

    call_kwargs = client.request.call_args
    headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert headers["Vowmade-Advertiser-Id"] == "adv-123"


@pytest.mark.asyncio
async def test_base_tool_rejects_missing_advertiser():
    """No call should proceed without an advertiser — fail closed."""
    client = _mock_client(_mock_response())
    tool = BaseVOWTool(client=client, auth=StubAuth(), advertiser_id="")

    with pytest.raises(AdvertiserContextMissingError):
        await tool._get("/deals/")

    # Verify no HTTP call was made
    client.request.assert_not_called()


@pytest.mark.asyncio
async def test_base_tool_raises_on_401():
    """Auth failures should raise VowAuthError, not retry."""
    client = _mock_client(_mock_response(401))
    tool = BaseVOWTool(client=client, auth=StubAuth(), advertiser_id="adv-123")

    with pytest.raises(VowAuthError):
        await tool._get("/deals/")

    # Should NOT retry on auth failure
    assert client.request.call_count == 1


@pytest.mark.asyncio
async def test_base_tool_retries_on_500():
    """Server errors should be retried."""
    error_resp = _mock_response(500)
    success_resp = _mock_response(200, {"data": "ok"})

    client = AsyncMock(spec=httpx.AsyncClient)
    client.request.side_effect = [error_resp, success_resp]

    tool = BaseVOWTool(client=client, auth=StubAuth(), advertiser_id="adv-123")
    result = await tool._get("/deals/")

    assert result == {"data": "ok"}
    assert client.request.call_count == 2  # first failed, second succeeded


@pytest.mark.asyncio
async def test_base_tool_retries_on_timeout():
    """Timeouts should be retried."""
    success_resp = _mock_response(200, {"data": "ok"})

    client = AsyncMock(spec=httpx.AsyncClient)
    client.request.side_effect = [httpx.TimeoutException("slow"), success_resp]

    tool = BaseVOWTool(client=client, auth=StubAuth(), advertiser_id="adv-123")
    result = await tool._get("/deals/")

    assert result == {"data": "ok"}
    assert client.request.call_count == 2


@pytest.mark.asyncio
async def test_base_tool_raises_after_all_retries_exhausted():
    """After max retries, give up and raise."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request.side_effect = httpx.TimeoutException("always slow")

    tool = BaseVOWTool(client=client, auth=StubAuth(), advertiser_id="adv-123")

    with pytest.raises(VowApiError, match="Timeout"):
        await tool._get("/deals/")

    assert client.request.call_count == 3  # default max retries


# --- Pagination tests ---


@pytest.mark.asyncio
async def test_pagination_follows_next():
    """Paginated calls should follow 'next' until it's null."""
    page1 = _mock_response(
        200,
        {
            "count": 3,
            "next": "?page=2",
            "results": [{"id": "deal-1"}, {"id": "deal-2"}],
        },
    )
    page2 = _mock_response(
        200,
        {
            "count": 3,
            "next": None,
            "results": [{"id": "deal-3"}],
        },
    )

    client = AsyncMock(spec=httpx.AsyncClient)
    client.request.side_effect = [page1, page2]

    tool = BaseVOWTool(client=client, auth=StubAuth(), advertiser_id="adv-123")
    results = await tool._get_paginated("/deals/")

    assert len(results) == 3
    assert results[0]["id"] == "deal-1"
    assert results[2]["id"] == "deal-3"
    assert client.request.call_count == 2


# --- Deals tool tests ---


@pytest.mark.asyncio
async def test_deals_tool_list_deals():
    """DealsTool.list_deals should filter to CTV and return deals."""
    deals_response = _mock_response(
        200,
        {
            "count": 1,
            "next": None,
            "results": [
                {
                    "external_deal_id": "EXTQ5",
                    "name": "Prime Video | Action | US - 15, 30",
                    "deal_type": "Private Auction",
                    "deal_price_amount": "22.07",
                    "genre": "Action",
                    "ad_lengths": ["15", "30"],
                }
            ],
        },
    )
    client = _mock_client(deals_response)

    tool = DealsTool(client=client, auth=StubAuth(), advertiser_id="adv-123")
    deals = await tool.list_deals(market="US")

    assert len(deals) == 1
    assert deals[0]["external_deal_id"] == "EXTQ5"
    assert deals[0]["deal_price_amount"] == "22.07"

    # Verify it passed the right query params
    call_kwargs = client.request.call_args
    params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
    assert params["markets"] == "US"
    assert params["formats"] == "streaming_tv"


@pytest.mark.asyncio
async def test_deals_tool_get_rate_card():
    """DealsTool.get_ctv_rate_card should hit the right endpoint."""
    rate_response = _mock_response(
        200,
        {
            "channels": [
                {
                    "name": "Prime Video",
                    "durations": [{"duration": "30", "cpm": "25.00"}],
                }
            ],
        },
    )
    client = _mock_client(rate_response)

    tool = DealsTool(client=client, auth=StubAuth(), advertiser_id="adv-123")
    card = await tool.get_ctv_rate_card(market="GB")

    assert card["channels"][0]["name"] == "Prime Video"

    # Verify it hit /rates/ctv/GB/
    call_kwargs = client.request.call_args
    url = call_kwargs.args[1] if len(call_kwargs.args) > 1 else call_kwargs.kwargs.get("url", "")
    assert "/rates/ctv/GB/" in url
