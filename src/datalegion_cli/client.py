"""Async HTTP client for the Data Legion API."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from datalegion_cli import __version__
from datalegion_cli.config import get_api_key, get_base_url, get_sandbox


class APIError(Exception):
    """Raised on non-2xx API responses."""

    def __init__(self, status_code: int, error: str, message: str, details: Any = None):
        self.status_code = status_code
        self.error = error
        self.message = message
        self.details = details
        super().__init__(f"[{status_code}] {error}: {message}")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "status_code": self.status_code,
            "error": self.error,
            "message": self.message,
        }
        if self.details:
            d["details"] = self.details
        return d


# Endpoints the API mirrors under /sandbox/: sample records (Jane Sandbox, Sandbox Corp), no credits.
# Utilities, reports, credits and dynamic bulk have no sandbox and call the real API.
SANDBOX_PATHS = frozenset(
    f"/{entity}/{op}"
    for entity in ("person", "company")
    for op in ("enrich", "enrich/bulk", "search", "discover")
)


class LegionClient:
    """Async client wrapping the Data Legion API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
    ):
        self._base_url = base_url or get_base_url()
        self._api_key = (api_key or "").strip() or get_api_key()
        self._timeout = timeout
        self._sandbox = get_sandbox()
        self._client: httpx.AsyncClient | None = None
        self.last_credits_used: str | None = None
        self.last_credits_remaining: str | None = None
        self.last_search_warning: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={
                    "API-Key": self._api_key,
                    "Content-Type": "application/json",
                    # Lets the API tell CLI traffic apart (its request log
                    # classifies datalegion-cli/* as 'cli').
                    "User-Agent": f"datalegion-cli/{__version__}",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        client = await self._get_client()
        if self._sandbox and endpoint in SANDBOX_PATHS:
            endpoint = f"/sandbox{endpoint}"
        logger.debug("{} {}", method.upper(), endpoint)

        if method.upper() == "GET":
            resp = await client.get(endpoint, params=params)
        else:
            resp = await client.post(endpoint, json=payload, params=params)

        if resp.status_code >= 400:
            logger.warning("API error {}: {}", resp.status_code, endpoint)
            try:
                body = resp.json()
                raise APIError(
                    status_code=resp.status_code,
                    error=body.get("error", "unknown"),
                    message=body.get("message", body.get("detail", resp.text)),
                    details=body.get("details"),
                )
            except (ValueError, KeyError) as exc:
                raise APIError(
                    status_code=resp.status_code,
                    error="unknown",
                    message=resp.text,
                ) from exc

        # Expose credit headers
        self.last_credits_used = resp.headers.get("Credits-Used")
        self.last_credits_remaining = resp.headers.get("Credits-Remaining")
        # search/discover: why a filter was flagged and what to change
        self.last_search_warning = resp.headers.get("Search-Warning")

        return resp.json()

    # ── Convenience methods ──────────────────────────────────────────

    async def person_enrich(self, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", "/person/enrich", payload=_strip(kwargs))

    async def person_search(self, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", "/person/search", payload=_strip(kwargs))

    async def person_discover(self, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", "/person/discover", payload=_strip(kwargs))

    async def person_bulk(self, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", "/person/enrich/bulk", payload=_strip(kwargs))

    async def company_enrich(self, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", "/company/enrich", payload=_strip(kwargs))

    async def company_search(self, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", "/company/search", payload=_strip(kwargs))

    async def company_discover(self, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", "/company/discover", payload=_strip(kwargs))

    async def company_bulk(self, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", "/company/enrich/bulk", payload=_strip(kwargs))

    async def utility_clean(self, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", "/utility/clean", payload=_strip(kwargs))

    async def utility_hash(self, email: str) -> dict[str, Any]:
        return await self.request("POST", "/utility/hash/email", payload={"email": email})

    async def utility_validate(self, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", "/utility/validate", payload=_strip(kwargs))

    async def utility_report(self, kind: str, **kwargs: Any) -> dict[str, Any]:
        return await self.request("POST", f"/utility/report/{kind}", payload=_strip(kwargs))

    async def credits_balance(self) -> dict[str, Any]:
        return await self.request("GET", "/credits")

    async def credits_usage(self, **kwargs: Any) -> dict[str, Any]:
        return await self.request("GET", "/credits/usage", params=_strip(kwargs))


def _strip(d: dict[str, Any]) -> dict[str, Any]:
    """Remove None values for clean payloads."""
    return {k: v for k, v in d.items() if v is not None}
