"""Tests for auto-update functionality."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from datalegion_cli.update import (
    _detect_install_method,
    _run,
    _source_checkout,
    _update_git,
    check_for_update,
    self_update,
)


@pytest.mark.asyncio
class TestCheckForUpdate:
    async def test_newer_version_available(self):
        resp = httpx.Response(200, json={"info": {"version": "99.0.0"}})
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("datalegion_cli.update.httpx.AsyncClient", return_value=mock_client):
            result = await check_for_update(quiet=True)
        assert result == "99.0.0"

    async def test_already_latest(self):
        resp = httpx.Response(200, json={"info": {"version": "0.0.1"}})
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("datalegion_cli.update.httpx.AsyncClient", return_value=mock_client):
            result = await check_for_update(quiet=True)
        assert result is None

    async def test_pypi_returns_non_200(self):
        resp = httpx.Response(404, json={})
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("datalegion_cli.update.httpx.AsyncClient", return_value=mock_client):
            result = await check_for_update(quiet=True)
        assert result is None

    async def test_network_error_returns_none(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("fail"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("datalegion_cli.update.httpx.AsyncClient", return_value=mock_client):
            result = await check_for_update(quiet=True)
        assert result is None

    async def test_empty_tag_returns_none(self):
        resp = httpx.Response(200, json={"tag_name": ""})
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("datalegion_cli.update.httpx.AsyncClient", return_value=mock_client):
            result = await check_for_update(quiet=True)
        assert result is None


@pytest.mark.asyncio
class TestRun:
    async def test_successful_command(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
        mock_proc.returncode = 0

        with patch(
            "datalegion_cli.update.asyncio.create_subprocess_exec", return_value=mock_proc
        ) as exec_:
            await _run(["echo", "hello"])

        exec_.assert_awaited_once()
        assert exec_.await_args.args == ("echo", "hello")
        assert exec_.await_args.kwargs["cwd"] is None
        mock_proc.communicate.assert_awaited_once()

    async def test_failed_command_raises(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"some error"))
        mock_proc.returncode = 1

        with (
            patch("datalegion_cli.update.asyncio.create_subprocess_exec", return_value=mock_proc),
            pytest.raises(SystemExit),
        ):
            await _run(["false"])


@pytest.mark.asyncio
class TestDetectInstallMethod:
    async def test_config_override(self):
        with patch("datalegion_cli.config.load_config", return_value={"install_method": "github"}):
            assert await _detect_install_method() == "github"

    async def test_detects_brew_from_the_running_interpreter(self, tmp_path):
        prefix = tmp_path / "Cellar" / "datalegion-cli" / "1.5.2" / "libexec" / "venv"
        prefix.mkdir(parents=True)
        with (
            patch("datalegion_cli.config.load_config", return_value={"install_method": ""}),
            patch("datalegion_cli.update.sys.prefix", str(prefix)),
        ):
            assert await _detect_install_method() == "brew"

    async def test_pip_copy_is_pip_even_when_brew_has_the_formula(self, tmp_path):
        # brew on PATH says nothing about which copy is running.
        with (
            patch("datalegion_cli.config.load_config", return_value={"install_method": ""}),
            patch("datalegion_cli.update.sys.prefix", str(tmp_path / ".venv")),
            patch("datalegion_cli.update.shutil.which", return_value="/opt/homebrew/bin/brew"),
            patch("datalegion_cli.update._source_checkout", return_value=None),
        ):
            assert await _detect_install_method() == "pip"

    async def test_detects_git_for_an_editable_checkout(self, tmp_path):
        with (
            patch("datalegion_cli.config.load_config", return_value={"install_method": ""}),
            patch("datalegion_cli.update.sys.prefix", str(tmp_path / ".venv")),
            patch("datalegion_cli.update._source_checkout", return_value=tmp_path),
        ):
            assert await _detect_install_method() == "git"

    async def test_wheel_inside_a_customers_repo_is_pip(self, tmp_path):
        # A wheel installed into a project's .venv sits under that project's .git; updating
        # must never git pull or uv sync the customer's own repository.
        (tmp_path / ".git").mkdir()
        fake_file = tmp_path / ".venv" / "lib" / "site-packages" / "datalegion_cli" / "update.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.touch()
        with (
            patch("datalegion_cli.config.load_config", return_value={"install_method": ""}),
            patch("datalegion_cli.update.sys.prefix", str(tmp_path / ".venv")),
            patch("datalegion_cli.update.__file__", str(fake_file)),
            patch("datalegion_cli.update._source_checkout", return_value=None),
        ):
            assert await _detect_install_method() == "pip"


class _Dist:
    def __init__(self, direct_url: str | None) -> None:
        self._direct_url = direct_url

    def read_text(self, name: str) -> str | None:
        return self._direct_url if name == "direct_url.json" else None


class TestSourceCheckout:
    def _with(self, direct_url: str | None) -> object:
        return patch("datalegion_cli.update.distribution", return_value=_Dist(direct_url))

    def test_editable_install_from_a_git_checkout(self, tmp_path):
        (tmp_path / ".git").mkdir()
        record = {"url": tmp_path.as_uri(), "dir_info": {"editable": True}}
        with self._with(json.dumps(record)):
            assert _source_checkout() == tmp_path

    @pytest.mark.parametrize(
        "record",
        [
            None,
            "not json",
            json.dumps({"url": "https://files.pythonhosted.org/x.whl", "archive_info": {}}),
            json.dumps({"url": "file:///tmp/x", "dir_info": {}}),
        ],
        ids=["wheel-from-pypi", "unreadable", "archive", "non-editable-dir"],
    )
    def test_anything_but_an_editable_checkout_is_none(self, record):
        with self._with(record):
            assert _source_checkout() is None

    def test_editable_install_without_git_is_none(self, tmp_path):
        record = {"url": tmp_path.as_uri(), "dir_info": {"editable": True}}
        with self._with(json.dumps(record)):
            assert _source_checkout() is None


@pytest.mark.asyncio
class TestUpdateGit:
    async def test_pulls_and_syncs_the_checkout_it_came_from(self, tmp_path):
        with (
            patch("datalegion_cli.update._source_checkout", return_value=tmp_path),
            patch("datalegion_cli.update.shutil.which", return_value="/usr/bin/uv"),
            patch("datalegion_cli.update._run", new_callable=AsyncMock) as mock_run,
        ):
            await _update_git()
            assert mock_run.call_args_list[0][0][0] == [
                "git",
                "-C",
                str(tmp_path),
                "pull",
                "--ff-only",
            ]
            assert mock_run.call_args_list[1].kwargs["cwd"] == tmp_path

    async def test_refuses_without_a_checkout(self):
        with (
            patch("datalegion_cli.update._source_checkout", return_value=None),
            patch("datalegion_cli.update._run", new_callable=AsyncMock) as mock_run,
            pytest.raises(SystemExit),
        ):
            await _update_git()
        mock_run.assert_not_called()


@pytest.mark.asyncio
class TestSelfUpdate:
    async def test_uses_uv_when_pip_method(self):
        with (
            patch("datalegion_cli.update._detect_install_method", return_value="pip"),
            patch(
                "datalegion_cli.update.shutil.which",
                side_effect=lambda x: "/usr/bin/uv" if x == "uv" else None,
            ),
            patch("datalegion_cli.update._run", new_callable=AsyncMock) as mock_run,
            patch("datalegion_cli.update.sys.exit"),
        ):
            await self_update("1.0.0")
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "/usr/bin/uv"
            assert "datalegion-cli==1.0.0" in cmd

    async def test_falls_back_to_pip(self):
        def which(name):
            return "/usr/bin/pip" if name == "pip" else None

        with (
            patch("datalegion_cli.update._detect_install_method", return_value="pip"),
            patch("datalegion_cli.update.shutil.which", side_effect=which),
            patch("datalegion_cli.update._run", new_callable=AsyncMock) as mock_run,
            patch("datalegion_cli.update.sys.exit"),
        ):
            await self_update("2.0.0")
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "/usr/bin/pip"

    async def test_raises_when_no_installer(self):
        with (
            patch("datalegion_cli.update._detect_install_method", return_value="pip"),
            patch("datalegion_cli.update.shutil.which", return_value=None),
            pytest.raises(SystemExit),
        ):
            await self_update("1.0.0")

    async def test_brew_method(self):
        with (
            patch("datalegion_cli.update._detect_install_method", return_value="brew"),
            patch("datalegion_cli.update.shutil.which", return_value="/usr/local/bin/brew"),
            patch("datalegion_cli.update._run", new_callable=AsyncMock) as mock_run,
            patch("datalegion_cli.update.sys.exit"),
        ):
            await self_update()
            assert mock_run.call_count == 2
            assert "upgrade" in mock_run.call_args_list[1][0][0]
