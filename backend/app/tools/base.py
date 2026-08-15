"""Base adapter for all VOW API calls.

Every wrapper subclasses this. The base handles auth, advertiser scoping,
pagination, timeouts, retries, error mapping, and logging — once.
Individual wrappers only describe WHAT to call, never HOW.

Usage:
    class DealsTool(BaseVOWTool):
        async def list_deals(self, market: str) -> list[dict]:
            return await self._get_paginated("/deals/", params={"markets": market})
"""

import logging
import time

import httpx

from app.config import get_settings
from app.core.exceptions import (
    AdvertiserContextMissingError,
    VowApiError,
    VowAuthError,
)
from app.tools.auth import VOWAuthProvider

logger = logging.getLogger(__name__)


class BaseVOWTool:
    """Base class every VOW API wrapper inherits from.

    Args:
        client: A shared httpx.AsyncClient (connection pooling).
        auth: The auth provider (StubAuth for now).
        advertiser_id: The advertiser this session is scoped to.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        auth: VOWAuthProvider,
        advertiser_id: str,
    ):
        self.client = client
        self.auth = auth
        self.advertiser_id = advertiser_id
        self.settings = get_settings()

    async def _headers(self) -> dict[str, str]:
        """Build the headers every call needs."""
        if not self.advertiser_id:
            raise AdvertiserContextMissingError(
                "Cannot call VOW without an advertiser context — fail closed."
            )

        # Start with auth headers (empty for now, real ones later)
        headers = await self.auth.get_headers()

        # Advertiser scoping — VOW requires this on every scoped call
        headers["Vowmade-Advertiser-Id"] = self.advertiser_id
        headers["Content-Type"] = "application/json"

        return headers

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        """Make one authenticated, scoped, retried request to VOW."""
        url = f"{self.settings.vow_api_base_url}{path}"
        headers = await self._headers()
        last_error = None

        for attempt in range(1, self.settings.vow_api_max_retries + 1):
            start = time.monotonic()
            try:
                response = await self.client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=self.settings.vow_api_timeout_seconds,
                )
                elapsed = time.monotonic() - start

                logger.info(
                    "VOW %s %s → %s (%.2fs)",
                    method,
                    path,
                    response.status_code,
                    elapsed,
                )

                # Auth failure — don't retry, it won't help
                if response.status_code == 401:
                    raise VowAuthError("Authentication failed", status_code=401, endpoint=path)
                if response.status_code == 403:
                    raise VowAuthError("Forbidden", status_code=403, endpoint=path)

                # Server error — retry if we have attempts left
                if response.status_code >= 500:
                    last_error = VowApiError(
                        f"Server error {response.status_code}",
                        status_code=response.status_code,
                        endpoint=path,
                    )
                    if attempt < self.settings.vow_api_max_retries:
                        logger.warning(
                            "VOW returned %s on %s, retry %s/%s",
                            response.status_code,
                            path,
                            attempt,
                            self.settings.vow_api_max_retries,
                        )
                        continue
                    raise last_error

                # Client error — don't retry
                if response.status_code >= 400:
                    raise VowApiError(
                        f"Client error {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                        endpoint=path,
                    )

                # Success
                return response.json()

            except httpx.TimeoutException:
                elapsed = time.monotonic() - start
                last_error = VowApiError(f"Timeout after {elapsed:.1f}s", endpoint=path)
                if attempt < self.settings.vow_api_max_retries:
                    logger.warning(
                        "Timeout on %s, retry %s/%s",
                        path,
                        attempt,
                        self.settings.vow_api_max_retries,
                    )
                    continue

            except httpx.RequestError as exc:
                last_error = VowApiError(f"Network error: {exc}", endpoint=path)
                if attempt < self.settings.vow_api_max_retries:
                    logger.warning(
                        "Network error on %s, retry %s/%s",
                        path,
                        attempt,
                        self.settings.vow_api_max_retries,
                    )
                    continue

        raise last_error or VowApiError("Failed after retries", endpoint=path)

    # --- Convenience methods ---

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """GET request."""
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, data: dict | None = None) -> dict:
        """POST request."""
        return await self._request("POST", path, json=data)

    async def _patch(self, path: str, data: dict | None = None) -> dict:
        """PATCH request."""
        return await self._request("PATCH", path, json=data)

    async def _get_paginated(self, path: str, params: dict | None = None) -> list:
        """Follow VOW's pagination and collect all results.

        VOW uses page-number pagination with a default page size of 8:
          { "count": 42, "next": "...?page=2", "previous": null, "results": [...] }
        """
        all_results = []
        page = 1

        while True:
            p = {**(params or {}), "page": page}
            response = await self._get(path, params=p)
            results = response.get("results", [])
            all_results.extend(results)

            if not response.get("next"):
                break
            page += 1

            # Safety: don't loop forever on a bug
            if page > 200:
                logger.warning("Pagination exceeded 200 pages on %s — stopping", path)
                break

        return all_results
