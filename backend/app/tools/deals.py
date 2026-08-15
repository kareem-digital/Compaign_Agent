"""Deals tool — retrieves CTV deals and rate cards from VOW.

Used by the inventory-selection node to show available deals
with their providers, genres, durations, and CPMs.

Endpoints:
    GET /deals/              — available deals (paginated)
    GET /deals/filter-properties/ — filter options
    GET /rates/ctv/{market}/ — CTV rate card
"""

from app.tools.base import BaseVOWTool


class DealsTool(BaseVOWTool):
    async def list_deals(
        self,
        market: str,
        format: str = "streaming_tv",
    ) -> list[dict]:
        """List available CTV deals for a market.

        Returns deals with: external_deal_id, name, deal_type,
        deal_price_amount (CPM), genre, ad_lengths, devices.
        """
        return await self._get_paginated(
            "/deals/",
            params={"markets": market, "formats": format},
        )

    async def get_filter_properties(self) -> dict:
        """Available filter options for deals (markets, formats, etc)."""
        return await self._get("/deals/filter-properties/")

    async def get_ctv_rate_card(self, market: str) -> dict:
        """CTV rate card for a market.

        Returns channels with durations and CPMs, e.g.:
        { "channels": [{ "name": "Prime Video",
          "durations": [{ "duration": "30", "cpm": "25.00" }] }] }
        """
        return await self._get(f"/rates/ctv/{market}/")
