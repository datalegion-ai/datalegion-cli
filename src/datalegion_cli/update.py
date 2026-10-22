"""Auto-update — checks PyPI for a newer release and self-updates via brew, github, git, uv, or pip."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import httpx
from loguru import logger
from packaging.version import Version

from datalegion_cli import __version__

GITHUB_REPO = "datalegion-ai/datalegion-cli"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASE_TAG_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/v{{}}"
GITHUB_REPO_URL = f"https://github.com/{GITHUB_REPO}.git"
BREW_TAP = "datalegion-ai/tap"
BREW_FORMULA = "datalegion-cli"
PKG_NAME = "datalegion_cli"
DIST_NAME = "datalegion-cli"


def _source_checkout() -> Path | None:
    """The git checkout this CLI is installed from in editable mode, or None.

    Read from the install's own record (PEP 610 ``direct_url.json``), never by walking up from
    the package: a wheel installed into a project's ``.venv`` sits inside that project's git
    repo, and treating it as a checkout would ``git pull`` and ``uv sync`` the customer's project.
    """
    try:
        raw = distribution(DIST_NAME).read_text("direct_url.json")
    except PackageNotFoundError:
        return None
    if not raw:
        return None
    try:
        record = json.loads(raw)
    except ValueError:
        return None
    if not record.get("dir_info", {}).get("editable"):
        return None
    url = urlparse(record.get("url", ""))
    if url.scheme != "file":
        return None
    root = Path(url2pathname(url.path))
    return root if (root / ".git").exists() else None


def _installed_by_brew() -> bool:
    """True when this interpreter is the formula's own venv under Homebrew's Cellar."""
    return f"/Cellar/{BREW_FORMULA}/" in Path(sys.prefix).resolve().as_posix()


async def check_for_update(*, quiet: bool = False) -> str | None:
    """Check PyPI for a newer release. Returns new version string or None."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://pypi.org/pypi/datalegion-cli/json")
            if resp.status_code != 200:
                logger.debug("Update check failed: HTTP {}", resp.status_code)
                return None
            data = resp.json()
            latest = data.get("info", {}).get("version", "")
            if not latest:
                return None
            if Version(latest) > Version(__version__):
                if not quiet:
                    logger.info("New version available: {} → {}", __version__, latest)
                return latest
            logger.debug("Already on latest version ({})", __version__)
            return None
    except Exception as exc:
        logger.debug("Update check error: {}", exc)
        return None


async def _detect_install_method() -> str:
    """Detect how the CLI was installed. Returns: brew, github, git, or pip."""
    from datalegion_cli.config import load_config

    # Check config for explicit install_method
    cfg = load_config()
    method = str(cfg.get("install_method", "")).lower()
    if method in ("brew", "github", "git", "pip"):
        return method

    # The running interpreter decides, not what else is on the machine: a pip copy on a
    # machine that also has the formula is still a pip copy.
    if _installed_by_brew():
        return "brew"
    if _source_checkout() is not None:
        return "git"
    return "pip"


async def self_update(version: str | None = None) -> None:
    """Upgrade the package using the detected install method."""
    method = await _detect_install_method()
    logger.info("Detected install method: {}", method)

    if method == "brew":
        await _update_brew()
    elif method == "github":
        await _update_github(version)
    elif method == "git":
        await _update_git()
    else:
        await _update_pip(version)

    logger.info("Updated successfully. Restart the CLI to use the new version.")
    sys.exit(0)


async def _update_brew() -> None:
    """Update via Homebrew."""
    brew = shutil.which("brew")
    assert brew is not None
    await _run([brew, "update"])
    await _run([brew, "upgrade", f"{BREW_TAP}/{BREW_FORMULA}"])


async def _update_github(version: str | None = None) -> None:
    """Update by downloading a wheel from a GitHub release."""
    asset_url = await _find_release_asset(version)
    if not asset_url:
        logger.error("No compatible wheel found in GitHub release.")
        raise SystemExit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = await _download_asset(asset_url, tmpdir)
        if uv := shutil.which("uv"):
            await _run([uv, "pip", "install", "--upgrade", str(local_path)])
        elif pip := shutil.which("pip"):
            await _run([pip, "install", "--upgrade", str(local_path)])
        else:
            logger.error("Neither uv nor pip found — cannot install downloaded release.")
            raise SystemExit(1)


async def _find_release_asset(version: str | None = None) -> str | None:
    """Find a .whl or .tar.gz asset URL from a GitHub release."""
    url = RELEASE_TAG_URL.format(version) if version else RELEASES_URL

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.debug("GitHub release fetch failed: HTTP {}", resp.status_code)
                return None
            data = resp.json()

        assets = data.get("assets", [])
        # Prefer .whl, fall back to .tar.gz
        for ext in (".whl", ".tar.gz"):
            for asset in assets:
                name = asset.get("name", "")
                if name.endswith(ext) and PKG_NAME in name.replace("-", "_"):
                    return asset["browser_download_url"]

        return None
    except Exception as exc:
        logger.debug("GitHub asset lookup error: {}", exc)
        return None


async def _download_asset(url: str, dest_dir: str) -> Path:
    """Download a release asset to a local directory."""
    filename = url.rsplit("/", 1)[-1]
    local_path = Path(dest_dir) / filename
    logger.info("Downloading: {}", url)
    async with (
        httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client,
        client.stream("GET", url) as resp,
    ):
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            async for chunk in resp.aiter_bytes():
                f.write(chunk)
    logger.info("Downloaded: {}", local_path)
    return local_path


async def _update_git() -> None:
    """Update a local git clone via git pull + uv sync."""
    repo_root = _source_checkout()
    if repo_root is None:
        logger.error("Could not find git repo root.")
        raise SystemExit(1)

    await _run(["git", "-C", str(repo_root), "pull", "--ff-only"])

    if uv := shutil.which("uv"):
        await _run([uv, "sync"], cwd=repo_root)
    elif pip := shutil.which("pip"):
        await _run([pip, "install", "-e", str(repo_root)])
    else:
        logger.error("Neither uv nor pip found — cannot reinstall after pull.")
        raise SystemExit(1)


async def _update_pip(version: str | None = None) -> None:
    """Update via uv/pip, supporting a private index via LEGION_PIP_INDEX_URL."""
    pkg = "datalegion-cli"
    if version:
        pkg = f"{pkg}=={version}"

    index_url = os.environ.get("LEGION_PIP_INDEX_URL")

    if uv := shutil.which("uv"):
        cmd = [uv, "pip", "install", "--upgrade", pkg]
        if index_url:
            cmd.extend(["--extra-index-url", index_url])
    elif pip := shutil.which("pip"):
        cmd = [pip, "install", "--upgrade", pkg]
        if index_url:
            cmd.extend(["--extra-index-url", index_url])
    else:
        logger.error("Neither uv nor pip found — cannot self-update.")
        raise SystemExit(1)

    await _run(cmd)


async def _run(cmd: list[str], cwd: Path | str | None = None) -> None:
    """Run a subprocess without blocking the event loop."""
    logger.info("Running: {}", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("Command failed:\n{}", stderr.decode())
        raise SystemExit(1)
