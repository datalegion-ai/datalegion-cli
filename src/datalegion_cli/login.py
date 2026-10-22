"""Sign in from the terminal and get a key for this machine (OAuth device authorization).

``datalegion-cli login`` asks Data Legion's sign-in server (WorkOS AuthKit) for a
device code, shows the person a link and a short code to approve, polls until they
do, then trades the access token at ``POST /agent/key`` for an API key that belongs
to this machine. The key is stored encrypted like one set with ``config set``.
Signing in again on the same machine replaces its key; the person can disconnect it
from the Connected Apps page in the dashboard.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

# The sign-in server and the CLI's OAuth app ("Data Legion CLI", a public PKCE app;
# the id is not a secret). Overridable for testing against another environment.
SIGNIN_URL = os.environ.get("LEGION_SIGNIN_URL", "https://signin.datalegion.ai")
CLI_CLIENT_ID = os.environ.get("LEGION_CLI_CLIENT_ID", "client_01M4ABTVGMNFRS52XMF8YDC1H5")

_DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
# What the API accepts as a device name: words separated by single spaces.
_DEVICE_OK = re.compile(r"^[\w.@:-]+( [\w.@:-]+)*$")


class LoginError(Exception):
    """Sign-in failed; the message is fit to show the person."""

    def __init__(self, message: str, *, code: str = "login_failed", details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


def new_device_id() -> str:
    """A random name for this machine's key: ``cli-`` plus 8 hex characters.

    Random rather than the hostname (or a hash of it): hostnames often carry a
    person's name and are guessable, so nothing about the machine leaves it. Saved
    in the config on first login and reused, so signing in again replaces this
    machine's key instead of adding another.
    """
    return f"cli-{secrets.token_hex(4)}"


def check_device_name(name: str) -> str:
    """Return the name if the API will accept it, else raise LoginError."""
    if not (1 <= len(name) <= 100) or not _DEVICE_OK.match(name):
        raise LoginError(
            "Device names use letters, digits and . _ @ : - (single spaces between words), "
            "up to 100 characters.",
            code="invalid_device",
        )
    return name


async def start_device_authorization(client: httpx.AsyncClient) -> dict[str, Any]:
    """Ask the sign-in server for a device code and the link the person approves at."""
    resp = await client.post(
        f"{SIGNIN_URL}/oauth2/device_authorization",
        data={"client_id": CLI_CLIENT_ID, "scope": "openid"},
    )
    if resp.status_code != 200:
        raise LoginError(f"Sign-in could not start ({resp.status_code}): {_oauth_error(resp)}")
    return resp.json()


async def poll_for_token(
    client: httpx.AsyncClient,
    device: dict[str, Any],
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> str:
    """Poll until the person approves (RFC 8628), returning the access token."""
    interval = float(device.get("interval") or 5)
    deadline = asyncio.get_running_loop().time() + float(device.get("expires_in") or 300)
    while asyncio.get_running_loop().time() < deadline:
        await sleep(interval)
        resp = await client.post(
            f"{SIGNIN_URL}/oauth2/token",
            data={
                "grant_type": _DEVICE_GRANT,
                "device_code": device["device_code"],
                "client_id": CLI_CLIENT_ID,
            },
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            if token:
                return str(token)
            raise LoginError("Sign-in returned no access token.")
        error = _oauth_error(resp)
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error == "access_denied":
            raise LoginError("Sign-in was declined.", code="access_denied")
        if error == "expired_token":
            break
        raise LoginError(f"Sign-in failed: {error}")
    raise LoginError("The sign-in code expired. Run `datalegion-cli login` again.", code="expired")


async def exchange_for_key(
    client: httpx.AsyncClient,
    api_base_url: str,
    access_token: str,
    device_name: str,
    team_id: int | None,
) -> dict[str, Any]:
    """Trade the access token for this machine's API key (POST /agent/key)."""
    body: dict[str, Any] = {"device": device_name}
    if team_id is not None:
        body["team_id"] = team_id
    resp = await client.post(
        f"{api_base_url.rstrip('/')}/agent/key",
        json=body,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {}
    if resp.status_code == 200 and payload.get("api_key"):
        return payload
    message = payload.get("message") or f"Getting a key failed ({resp.status_code})."
    details = payload.get("details")
    if resp.status_code == 409:
        message = "This account has several teams. Run again with --team-id <id> to choose one."
        raise LoginError(message, code="choose_team", details=details)
    raise LoginError(
        message, code=str(payload.get("error") or "key_exchange_failed"), details=details
    )


def _oauth_error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200] or str(resp.status_code)
    return str(body.get("error") or body.get("message") or resp.status_code)
