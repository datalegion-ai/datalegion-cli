"""`datalegion-cli login`: device authorization, polling, the key exchange, and what is stored."""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from datalegion_cli import login as flow
from datalegion_cli.main import app

runner = CliRunner()
KEY = "legion_" + "c0ffee" * 10 + "abcd"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.fixture
def tmp_config(tmp_config_dir, monkeypatch):
    """A throwaway config dir with no LEGION_API_KEY override."""
    monkeypatch.delenv("LEGION_API_KEY", raising=False)
    return tmp_config_dir


class TestDeviceName:
    def test_new_ids_are_random_and_api_safe(self):
        ids = {flow.new_device_id() for _ in range(50)}
        assert len(ids) == 50
        for device_id in ids:
            assert re.fullmatch(r"cli-[0-9a-f]{8}", device_id)
            assert flow.check_device_name(device_id) == device_id

    def test_the_hostname_is_never_read(self):
        assert not hasattr(flow, "platform")

    @pytest.mark.parametrize("name", ["", " lead", "a\nb", "x" * 101, "semi;colon", "two  spaces"])
    def test_rejects_what_the_api_rejects(self, name):
        with pytest.raises(flow.LoginError):
            flow.check_device_name(name)

    @pytest.mark.parametrize("name", ["laptop", "build-box.internal", "ci runner 3", "me@host:1"])
    def test_accepts_ordinary_names(self, name):
        assert flow.check_device_name(name) == name


class TestFlow:
    async def test_start_sends_the_cli_client(self):
        seen = {}

        def handler(req: httpx.Request) -> httpx.Response:
            seen["url"] = str(req.url)
            seen["body"] = req.content.decode()
            return httpx.Response(200, json={"device_code": "d", "user_code": "BCDF-GHJK"})

        async with _client(handler) as c:
            out = await flow.start_device_authorization(c)
        assert out["user_code"] == "BCDF-GHJK"
        assert seen["url"] == "https://signin.datalegion.ai/oauth2/device_authorization"
        assert f"client_id={flow.CLI_CLIENT_ID}" in seen["body"]

    async def test_start_failure_is_reported(self):
        async with _client(
            lambda r: httpx.Response(400, json={"error": "unauthorized_client"})
        ) as c:
            with pytest.raises(flow.LoginError, match="unauthorized_client"):
                await flow.start_device_authorization(c)

    async def test_poll_waits_through_pending_and_slow_down(self):
        answers = iter(
            [
                httpx.Response(400, json={"error": "authorization_pending"}),
                httpx.Response(400, json={"error": "slow_down"}),
                httpx.Response(200, json={"access_token": "tok"}),
            ]
        )
        slept: list[float] = []

        async def sleep(s: float) -> None:
            slept.append(s)

        async with _client(lambda r: next(answers)) as c:
            token = await flow.poll_for_token(
                c, {"device_code": "d", "interval": 5, "expires_in": 300}, sleep=sleep
            )
        assert token == "tok"
        assert slept == [5, 5, 10]  # slow_down adds 5 seconds

    @pytest.mark.parametrize(
        ("error", "code"), [("access_denied", "access_denied"), ("expired_token", "expired")]
    )
    async def test_poll_terminal_answers(self, error, code):
        async with _client(lambda r: httpx.Response(400, json={"error": error})) as c:
            with pytest.raises(flow.LoginError) as exc:
                await flow.poll_for_token(c, {"device_code": "d", "interval": 1}, sleep=_no_sleep)
        assert exc.value.code == code

    async def test_exchange_sends_the_bearer_and_device(self):
        seen = {}

        def handler(req: httpx.Request) -> httpx.Response:
            seen["auth"] = req.headers["authorization"]
            seen["url"] = str(req.url)
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json={"api_key": KEY, "team_id": 7, "replaced": 0})

        async with _client(handler) as c:
            out = await flow.exchange_for_key(c, "https://api.datalegion.ai/", "tok", "laptop", 7)
        assert out["api_key"] == KEY
        assert seen == {
            "auth": "Bearer tok",
            "url": "https://api.datalegion.ai/agent/key",
            "body": {"device": "laptop", "team_id": 7},
        }

    async def test_exchange_several_teams(self):
        teams = [{"team_id": 7, "team_name": "Sales"}]
        reply = httpx.Response(
            409, json={"error": "conflict", "message": "x", "details": {"teams": teams}}
        )
        async with _client(lambda r: reply) as c:
            with pytest.raises(flow.LoginError) as exc:
                await flow.exchange_for_key(c, "https://api.datalegion.ai", "tok", "laptop", None)
        assert exc.value.code == "choose_team" and "--team-id" in str(exc.value)
        assert exc.value.details == {"teams": teams}

    async def test_exchange_refusal_relays_the_message(self):
        reply = httpx.Response(
            403,
            json={
                "error": "forbidden",
                "message": "Your Data Legion account is waiting for approval.",
            },
        )
        async with _client(lambda r: reply) as c:
            with pytest.raises(flow.LoginError, match="waiting for approval"):
                await flow.exchange_for_key(c, "https://api.datalegion.ai", "tok", "laptop", None)


class TestLoginCommand:
    @pytest.fixture
    def steps(self):
        with (
            patch.object(
                flow,
                "start_device_authorization",
                new=AsyncMock(
                    return_value={
                        "verification_uri": "https://signin.datalegion.ai/device",
                        "user_code": "BCDF-GHJK",
                        "device_code": "d",
                    }
                ),
            ),
            patch.object(flow, "poll_for_token", new=AsyncMock(return_value="tok")),
            patch.object(
                flow,
                "exchange_for_key",
                new=AsyncMock(return_value={"api_key": KEY, "team_id": 7, "replaced": 1}),
            ) as exchange,
            patch("webbrowser.open") as browser,
        ):
            yield exchange, browser

    def test_stores_the_key_and_never_prints_it(self, steps, tmp_config):
        exchange, browser = steps
        result = runner.invoke(app, ["login", "--device", "laptop", "--team-id", "7"])
        assert result.exit_code == 0, result.output
        out = json.loads(result.stdout)
        assert out["ok"] is True and out["team_id"] == 7 and out["device"] == "laptop"
        assert KEY not in result.output and out["api_key"].endswith(KEY[-4:])
        assert exchange.await_args.args[3:] == ("laptop", 7)
        browser.assert_called_once()
        from datalegion_cli.config import load_config

        assert load_config()["api_key"] == KEY

    def test_default_device_is_a_saved_random_id_reused_next_time(self, steps, tmp_config):
        exchange, _ = steps
        assert runner.invoke(app, ["login"]).exit_code == 0
        first = exchange.await_args.args[3]
        assert re.fullmatch(r"cli-[0-9a-f]{8}", first)
        from datalegion_cli.config import load_config

        assert load_config()["device_id"] == first
        assert runner.invoke(app, ["login"]).exit_code == 0
        assert exchange.await_args.args[3] == first  # same machine, same key slot

    def test_device_flag_wins_and_leaves_the_saved_id(self, steps, tmp_config):
        exchange, _ = steps
        assert runner.invoke(app, ["login"]).exit_code == 0
        from datalegion_cli.config import load_config

        saved = load_config()["device_id"]
        assert runner.invoke(app, ["login", "--device", "laptop"]).exit_code == 0
        assert exchange.await_args.args[3] == "laptop"
        assert load_config()["device_id"] == saved

    def test_no_browser(self, steps, tmp_config):
        _, browser = steps
        assert runner.invoke(app, ["login", "--device", "laptop", "--no-browser"]).exit_code == 0
        browser.assert_not_called()

    def test_a_refusal_is_json_and_exit_1(self, steps, tmp_config):
        exchange, _ = steps
        exchange.side_effect = flow.LoginError(
            "Pick a team.", code="choose_team", details={"teams": []}
        )
        result = runner.invoke(app, ["login", "--device", "laptop"])
        assert result.exit_code == 1
        assert json.loads(result.stdout) == {
            "ok": False,
            "error": "choose_team",
            "message": "Pick a team.",
            "details": {"teams": []},
        }

    def test_a_bad_device_name_stops_before_sign_in(self, steps, tmp_config):
        result = runner.invoke(app, ["login", "--device", "semi;colon"])
        assert result.exit_code == 1
        assert json.loads(result.stdout)["error"] == "invalid_device"
        flow.start_device_authorization.assert_not_awaited()


def test_config_set_never_echoes_the_key(tmp_config):
    result = runner.invoke(app, ["config", "set", "api_key", KEY])
    assert result.exit_code == 0
    assert KEY not in result.output
    assert json.loads(result.stdout)["value"].endswith(KEY[-4:])
