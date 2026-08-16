"""A mock MCP server, in-process.

Returns VOW-shaped payloads so nodes and the grounded registry are exercised
against realistic structures rather than invented ones. The payloads themselves
live in `mock_data.py`; this module is routing only.

Deliberately covers all three inventory tiers, because the interesting
behaviour is the honesty rule: Amazon inventory forecasts, third-party
inventory does not.

Test affordances:
    calls            every (tool, arguments) pair, in order
    fail_times       raise MCPTransientError on the first N calls
    unknown_tool     raise MCPToolNotFoundError for an unmapped name (default)
"""

from __future__ import annotations

from app.core.exceptions import MCPToolNotFoundError, MCPTransientError
from app.tools.mcp import VowTools
from app.tools.mcp import mock_data as data
from app.tools.mcp.client import MCPClient


class MockMCPClient(MCPClient):
    """In-process stand-in for VOW's MCP server."""

    def __init__(self, advertiser_id: str, fail_times: int = 0, **kwargs):
        super().__init__(advertiser_id=advertiser_id, **kwargs)
        self.calls: list[tuple[str, dict]] = []
        self._fail_times = fail_times

    async def _list_tools_raw(self) -> list[dict]:
        self.calls.append(("list_tools", {}))
        return [
            {"name": VowTools.LIST_DEALS, "description": "Available deals for a market and format"},
            {
                "name": VowTools.CTV_RATE_CARD,
                "description": "CTV rate card: channels, durations, CPMs",
            },
            {
                "name": VowTools.SUGGEST_AUDIENCES,
                "description": "Suggest audience sets from a brief",
            },
            {
                "name": VowTools.REACH_FORECAST,
                "description": "Reach forecast (Amazon inventory only)",
            },
            {
                "name": VowTools.DEAL_FILTER_PROPERTIES,
                "description": "Valid markets, currencies, durations, formats and genres",
            },
            {
                "name": VowTools.INVENTORY_SOURCES,
                "description": "Inventory providers and the tier each belongs to",
            },
            {
                "name": VowTools.PRODUCT_CATEGORIES,
                "description": "Contextual product categories for a market",
            },
            {
                "name": VowTools.CHECK_STRATEGY_NAME,
                "description": "Whether a strategy name is still available",
            },
            {"name": VowTools.LOCATIONS, "description": "Targetable locations for a market"},
            {
                "name": VowTools.TARGETING_OPTIONS,
                "description": "Values available for one targeting type",
            },
        ]

    async def _call_tool_raw(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))

        if self._fail_times > 0:
            self._fail_times -= 1
            raise MCPTransientError("mock transient failure", tool=name)

        # A table rather than an if-chain: the mock answers ten tools now, and a
        # new one should be one line rather than another branch here.
        handlers = {
            VowTools.LIST_DEALS: self._deals,
            VowTools.CTV_RATE_CARD: self._rate_card,
            VowTools.SUGGEST_AUDIENCES: self._audiences,
            VowTools.REACH_FORECAST: self._forecast,
            VowTools.DEAL_FILTER_PROPERTIES: self._filter_properties,
            VowTools.INVENTORY_SOURCES: self._inventory_sources,
            VowTools.PRODUCT_CATEGORIES: self._product_categories,
            VowTools.CHECK_STRATEGY_NAME: self._check_strategy_name,
            VowTools.LOCATIONS: self._locations,
            VowTools.TARGETING_OPTIONS: self._targeting_options,
        }

        handler = handlers.get(name)
        if handler is None:
            raise MCPToolNotFoundError(f"mock server exposes no tool named {name!r}", tool=name)

        return handler(arguments)

    # --- response builders ---

    @staticmethod
    def _deals(arguments: dict) -> dict:
        market = arguments.get("market", "GB")
        results = data.deals_for(market, arguments.get("durations") or [])
        return {"count": len(results), "results": results}

    @staticmethod
    def _rate_card(arguments: dict) -> dict:
        return {"channels": [dict(c) for c in data.RATE_CARD["channels"]]}

    @staticmethod
    def _audiences(arguments: dict) -> dict:
        return {"suggestions": [dict(a) for a in data.AUDIENCE_SUGGESTIONS]}

    @staticmethod
    def _filter_properties(arguments: dict) -> dict:
        return data.filter_properties()

    @staticmethod
    def _inventory_sources(arguments: dict) -> dict:
        return {"results": [dict(s) for s in data.INVENTORY_SOURCES]}

    @staticmethod
    def _product_categories(arguments: dict) -> dict:
        market = arguments.get("market", "GB")
        return {"results": [dict(c) for c in data.PRODUCT_CATEGORIES.get(market, [])]}

    @staticmethod
    def _check_strategy_name(arguments: dict) -> dict:
        """Name uniqueness, case-insensitively - VOW treats names that way.

        Returns the rules alongside the answer so the registry can apply the
        cheap local checks (length, charset) without a round trip per keystroke.
        """
        name = str(arguments.get("name") or "").strip().lower()
        rules = dict(data.STRATEGY_NAME_RULES)
        return {
            "name": arguments.get("name"),
            "is_unique": name not in data.TAKEN_STRATEGY_NAMES,
            "rules": rules,
        }

    @staticmethod
    def _locations(arguments: dict) -> dict:
        market = arguments.get("market", "GB")
        return {"results": [dict(loc) for loc in data.LOCATIONS.get(market, [])]}

    @staticmethod
    def _targeting_options(arguments: dict) -> dict:
        targeting_type = arguments.get("type") or ""
        return {"results": [dict(o) for o in data.TARGETING_OPTIONS.get(targeting_type, [])]}

    @staticmethod
    def _forecast(arguments: dict) -> dict:
        """Amazon inventory forecasts; third-party does not.

        The mock refuses to invent reach for non-Amazon inventory on purpose -
        if it faked a number, nothing downstream would ever exercise the
        honesty path.

        The `"AMAZON_OWNED"` literal is deliberate: `app.tools` must not import
        `app.knowledge`, so the tier enum is unavailable here.
        `tests/contract/test_registry_contract.py` asserts they agree.
        """
        budget = float(arguments.get("budget") or 0)
        cpm = float(arguments.get("effective_cpm") or 0)
        impressions = int((budget / cpm) * 1000) if cpm else 0

        if arguments.get("inventory_tier") != "AMAZON_OWNED":
            return {
                "is_available": False,
                "reason": "Reach forecasting is available for Amazon inventory only.",
                "estimated_impressions": impressions,
                "indicative_cpm": f"{cpm:.2f}",
            }

        reach = int(impressions / 3.2) if impressions else 0
        return {
            "is_available": True,
            "estimated_impressions": impressions,
            "estimated_unique_reach": reach,
            "average_frequency": 3.2,
            "indicative_cpm": f"{cpm:.2f}",
            "reach_curve": [
                {"budget": round(budget * f, 2), "reach": int(reach * r)}
                for f, r in ((0.25, 0.38), (0.5, 0.64), (0.75, 0.85), (1.0, 1.0))
            ],
        }
