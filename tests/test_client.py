"""Tests for the async HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from datalegion_cli.client import APIError, LegionClient, _strip
from tests.conftest import make_response


class TestStrip:
    def test_removes_none_values(self):
        assert _strip({"a": 1, "b": None, "c": "x"}) == {"a": 1, "c": "x"}

    def test_keeps_falsy_non_none(self):
        assert _strip({"a": 0, "b": False, "c": ""}) == {"a": 0, "b": False, "c": ""}

    def test_empty_dict(self):
        assert _strip({}) == {}


class TestAPIError:
    def test_str_representation(self):
        err = APIError(401, "unauthorized", "Invalid API key")
        assert "401" in str(err)
        assert "unauthorized" in str(err)

    def test_to_dict_without_details(self):
        err = APIError(404, "not_found", "No match")
        d = err.to_dict()
        assert d == {"status_code": 404, "error": "not_found", "message": "No match"}
        assert "details" not in d

    def test_to_dict_with_details(self):
        err = APIError(422, "validation", "Bad input", details={"field": "email"})
        d = err.to_dict()
        assert d["details"] == {"field": "email"}


class TestLegionClientInit:
    def test_explicit_params(self):
        client = LegionClient(base_url="https://x.local", api_key="legion_k", timeout=10.0)
        assert client._base_url == "https://x.local"
        assert client._api_key == "legion_k"
        assert client._timeout == 10.0

    async def test_sends_identifying_user_agent(self):
        """The API's request log classifies datalegion-cli/* as CLI traffic."""
        from datalegion_cli import __version__

        client = LegionClient(base_url="https://x.local", api_key="legion_k")
        http = await client._get_client()
        assert http.headers["User-Agent"] == f"datalegion-cli/{__version__}"
        await client.close()

    def test_credit_headers_init_none(self, mock_api_key):
        client = LegionClient(base_url="https://x.local", api_key=mock_api_key)
        assert client.last_credits_used is None
        assert client.last_credits_remaining is None


@pytest.mark.asyncio
class TestRequest:
    async def test_successful_get(self, mock_client, monkeypatch):

        resp = make_response(
            200, {"status": "ok"}, {"Credits-Used": "1", "Credits-Remaining": "99"}
        )
        mock_get = AsyncMock(return_value=resp)

        async with httpx.AsyncClient():
            pass  # just to get type
        mock_client._client = AsyncMock()
        mock_client._client.is_closed = False
        mock_client._client.get = mock_get

        result = await mock_client.request("GET", "/health")
        assert result == {"status": "ok"}
        assert mock_client.last_credits_used == "1"
        assert mock_client.last_credits_remaining == "99"
        mock_get.assert_called_once()

    async def test_successful_post(self, mock_client, monkeypatch):

        resp = make_response(200, {"matches": [{"full_name": "John Doe"}]})
        mock_post = AsyncMock(return_value=resp)

        mock_client._client = AsyncMock()
        mock_client._client.is_closed = False
        mock_client._client.post = mock_post

        result = await mock_client.request("POST", "/person/enrich", payload={"email": "j@x.com"})
        assert result["matches"][0]["full_name"] == "John Doe"
        mock_post.assert_called_once()

    async def test_api_error_json_body(self, mock_client, monkeypatch):

        resp = make_response(401, {"error": "unauthorized", "message": "Invalid API key"})
        mock_client._client = AsyncMock()
        mock_client._client.is_closed = False
        mock_client._client.post = AsyncMock(return_value=resp)

        with pytest.raises(APIError) as exc_info:
            await mock_client.request("POST", "/person/enrich", payload={})
        assert exc_info.value.status_code == 401
        assert exc_info.value.error == "unauthorized"

    async def test_api_error_plain_text(self, mock_client, monkeypatch):

        resp = httpx.Response(500, text="Internal Server Error")
        mock_client._client = AsyncMock()
        mock_client._client.is_closed = False
        mock_client._client.post = AsyncMock(return_value=resp)

        with pytest.raises(APIError) as exc_info:
            await mock_client.request("POST", "/person/enrich", payload={})
        assert exc_info.value.status_code == 500

    async def test_close_idempotent(self, mock_client):
        mock_client._client = AsyncMock()
        mock_client._client.is_closed = False
        await mock_client.close()
        mock_client._client.aclose.assert_called_once()

        # Already closed
        mock_client._client.is_closed = True
        await mock_client.close()  # should not raise


@pytest.mark.asyncio
class TestConvenienceMethods:
    """Verify convenience methods route to the correct endpoints."""

    async def _setup_mock(self, mock_client, monkeypatch):

        resp = make_response(200, {"ok": True})
        mock_client._client = AsyncMock()
        mock_client._client.is_closed = False
        mock_client._client.post = AsyncMock(return_value=resp)
        mock_client._client.get = AsyncMock(return_value=resp)
        return mock_client._client

    async def test_person_enrich(self, mock_client, monkeypatch):
        http = await self._setup_mock(mock_client, monkeypatch)
        await mock_client.person_enrich(email="a@b.com")
        http.post.assert_called_once()
        args = http.post.call_args
        assert args[0][0] == "/person/enrich"

    async def test_person_search(self, mock_client, monkeypatch):
        http = await self._setup_mock(mock_client, monkeypatch)
        await mock_client.person_search(query="SELECT * FROM people", limit=5)
        assert http.post.call_args[0][0] == "/person/search"

    # async def test_person_discover(self, mock_client, monkeypatch):
    #     http = await self._setup_mock(mock_client, monkeypatch)
    #     await mock_client.person_discover(query="engineers in SF")
    #     assert http.post.call_args[0][0] == "/person/discover"

    async def test_person_bulk(self, mock_client, monkeypatch):
        http = await self._setup_mock(mock_client, monkeypatch)
        await mock_client.person_bulk(items=[{"email": "a@b.com"}])
        assert http.post.call_args[0][0] == "/person/enrich/bulk"

    async def test_company_enrich(self, mock_client, monkeypatch):
        http = await self._setup_mock(mock_client, monkeypatch)
        await mock_client.company_enrich(domain="google.com")
        assert http.post.call_args[0][0] == "/company/enrich"

    async def test_company_search(self, mock_client, monkeypatch):
        http = await self._setup_mock(mock_client, monkeypatch)
        await mock_client.company_search(query="SELECT * FROM companies", limit=5)
        assert http.post.call_args[0][0] == "/company/search"

    # async def test_company_discover(self, mock_client, monkeypatch):
    #     http = await self._setup_mock(mock_client, monkeypatch)
    #     await mock_client.company_discover(query="AI startups")
    #     assert http.post.call_args[0][0] == "/company/discover"

    async def test_company_bulk(self, mock_client, monkeypatch):
        http = await self._setup_mock(mock_client, monkeypatch)
        await mock_client.company_bulk(items=[{"domain": "x.com"}])
        assert http.post.call_args[0][0] == "/company/enrich/bulk"

    async def test_utility_clean(self, mock_client, monkeypatch):
        http = await self._setup_mock(mock_client, monkeypatch)
        await mock_client.utility_clean(fields={"email": "test@x.com"})
        assert http.post.call_args[0][0] == "/utility/clean"

    async def test_utility_hash(self, mock_client, monkeypatch):
        http = await self._setup_mock(mock_client, monkeypatch)
        await mock_client.utility_hash("test@x.com")
        assert http.post.call_args[0][0] == "/utility/hash/email"

    async def test_utility_validate(self, mock_client, monkeypatch):
        http = await self._setup_mock(mock_client, monkeypatch)
        await mock_client.utility_validate(email="test@x.com")
        assert http.post.call_args[0][0] == "/utility/validate"

    async def test_credits_balance(self, mock_client, monkeypatch):
        http = await self._setup_mock(mock_client, monkeypatch)
        await mock_client.credits_balance()
        http.get.assert_called_once()
        assert http.get.call_args[0][0] == "/credits"

    async def test_credits_usage(self, mock_client, monkeypatch):
        http = await self._setup_mock(mock_client, monkeypatch)
        await mock_client.credits_usage(start_date="2026-01-01", end_date="2026-03-01")
        assert http.get.call_args[0][0] == "/credits/usage"


@pytest.mark.asyncio
class TestSandbox:
    """Sandbox mode sends only the endpoints the API mirrors to /sandbox/."""

    async def _paths(self, monkeypatch, sandbox_env: str | None, endpoints: list[str]) -> list[str]:
        if sandbox_env is None:
            monkeypatch.delenv("LEGION_SANDBOX", raising=False)
        else:
            monkeypatch.setenv("LEGION_SANDBOX", sandbox_env)
        client = LegionClient(base_url="https://x.local", api_key="legion_k")
        mock_post = AsyncMock(return_value=make_response(200, {"matches": []}))
        client._client = AsyncMock()
        client._client.is_closed = False
        client._client.post = mock_post
        for endpoint in endpoints:
            await client.request("POST", endpoint, payload={})
        return [call.args[0] for call in mock_post.call_args_list]

    async def test_sandbox_routes_only_mirrored_paths(self, monkeypatch):
        paths = await self._paths(
            monkeypatch, "1", ["/person/enrich", "/company/search", "/utility/clean"]
        )
        assert paths == ["/sandbox/person/enrich", "/sandbox/company/search", "/utility/clean"]

    async def test_off_by_default(self, monkeypatch):
        assert await self._paths(monkeypatch, None, ["/person/enrich"]) == ["/person/enrich"]

    async def test_env_false_is_off(self, monkeypatch):
        assert await self._paths(monkeypatch, "false", ["/person/enrich"]) == ["/person/enrich"]


def test_sandbox_flag_turns_it_on(monkeypatch):
    from typer.testing import CliRunner

    from datalegion_cli.main import app

    # setenv first so monkeypatch records the variable's original state and restores it. A
    # delenv after the CLI set it would record "1" as the value to put back, leaking sandbox
    # mode into every later test.
    monkeypatch.setenv("LEGION_SANDBOX", "")
    monkeypatch.delenv("LEGION_SANDBOX")
    CliRunner().invoke(app, ["--sandbox", "version"])
    import os

    assert os.environ.get("LEGION_SANDBOX") == "1"
