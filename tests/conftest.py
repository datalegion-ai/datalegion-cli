"""Shared fixtures for all tests."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from datalegion_cli.client import LegionClient


@pytest.fixture()
def tmp_config_dir(tmp_path, monkeypatch):
    """Point config to a temp directory so tests don't touch ~/.datalegion."""
    monkeypatch.setenv("LEGION_CONFIG_DIR", str(tmp_path))
    # Re-import to pick up the new env
    import datalegion_cli.config as cfg_mod

    cfg_mod.CONFIG_DIR = tmp_path
    cfg_mod.CONFIG_FILE = tmp_path / "config.toml"
    return tmp_path


@pytest.fixture()
def mock_api_key(monkeypatch):
    """Provide a fake API key via env so the client doesn't raise."""
    monkeypatch.setenv(
        "LEGION_API_KEY",
        "legion_test1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd",
    )
    return "legion_test1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd"


def make_response(
    status_code: int = 200,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Build a fake httpx.Response."""
    hdrs = {"content-type": "application/json"}
    if headers:
        hdrs.update(headers)
    return httpx.Response(
        status_code=status_code,
        json=json_body or {},
        headers=hdrs,
    )


@pytest.fixture()
def mock_client(mock_api_key):
    """Return a LegionClient with a mocked transport (no real HTTP)."""
    client = LegionClient(base_url="https://test.api.local", api_key=mock_api_key)
    return client
