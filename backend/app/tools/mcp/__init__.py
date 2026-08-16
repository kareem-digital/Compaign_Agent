"""MCP access to VOW's platform APIs.

`VowTools` is the single source for tool names. Nodes and the mock both import
from here, so a rename cannot leave one side stale. When the real server lands,
run `list_tools()` and reconcile this list against it - that reconciliation is
the whole integration risk of moving to MCP.
"""

from app.tools.mcp.client import MCPClient, StreamableHTTPMCPClient, create_mcp_client


class VowTools:
    """Tool names we expect VOW's MCP server to expose.

    Provisional - confirm against the real server's `list_tools()` and correct
    here. Mapped to the REST endpoints they replace, from
    `VOW_API_Integration_Reference.md`.
    """

    LIST_DEALS = "vow.list_deals"  # GET /deals/
    CTV_RATE_CARD = "vow.get_ctv_rate_card"  # GET /rates/ctv/{market}/
    SUGGEST_AUDIENCES = "vow.suggest_audiences"  # POST /audience-sets/suggest/
    REACH_FORECAST = "vow.reach_forecast"  # POST /audience-sets/reach-forecast/

    # --- grounded registry (KNW-02) ---
    # Reference data the registry ingests so the flow's valid values come from
    # VOW rather than from constants in our nodes.
    DEAL_FILTER_PROPERTIES = "vow.get_deal_filter_properties"  # GET /deals/filter-properties/
    INVENTORY_SOURCES = "vow.list_inventory_sources"  # GET /inventory-sources/
    # GET /contextual-targeting/{market}/product-categories/
    PRODUCT_CATEGORIES = "vow.list_product_categories"
    # GET /strategies/check_strategy_name_uniqueness/
    CHECK_STRATEGY_NAME = "vow.check_strategy_name_uniqueness"
    LOCATIONS = "vow.list_locations"  # GET /strategies/locations/{market}/
    # Provisional - no single REST endpoint in the catalogue. The values behind
    # the config-driven targeting types of schema v2 section 3 step 5; confirm
    # the real shape against POST /contextual-targeting/{market}/products/.
    TARGETING_OPTIONS = "vow.get_targeting_options"

    @classmethod
    def all(cls) -> list[str]:
        """Every tool name we expect, for reconciliation against `list_tools()`.

        Used by the registry ingestor at first sync. Derived rather than listed
        again, so a new constant cannot be left out of the check that exists to
        catch exactly that.
        """
        return sorted(
            value
            for name, value in vars(cls).items()
            if not name.startswith("_") and isinstance(value, str)
        )


__all__ = ["MCPClient", "StreamableHTTPMCPClient", "VowTools", "create_mcp_client"]
