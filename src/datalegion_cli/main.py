"""Main CLI entry point — assembles all sub-commands."""

from __future__ import annotations

import os
from typing import Annotated

import typer
from loguru import logger

from datalegion_cli import __version__
from datalegion_cli.async_typer import async_command
from datalegion_cli.commands import company, credits, person, utility
from datalegion_cli.config import get_base_url, load_config, save_config
from datalegion_cli.logging import setup_logging
from datalegion_cli.output import console, emit_error, emit_json
from datalegion_cli.update import check_for_update, self_update

app = typer.Typer(
    name="datalegion-cli",
    help="Data Legion CLI — enrich person and company data at scale.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ── Register sub-command groups ──────────────────────────────────────

app.add_typer(person.app, name="person")
app.add_typer(company.app, name="company")
app.add_typer(utility.app, name="utility")
app.add_typer(credits.app, name="credits")

# ── Global callback for shared flags ────────────────────────────────


@app.callback()
def main_callback(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging.")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress all log output.")] = False,
    sandbox: Annotated[
        bool,
        typer.Option(
            "--sandbox",
            help="Return sample records from enrich, search and discover, using no credits.",
        ),
    ] = False,
) -> None:
    """Data Legion CLI."""
    setup_logging(verbose=verbose, quiet=quiet)
    if sandbox:
        # Read by config.load_config, so every client this run creates is in sandbox mode.
        os.environ["LEGION_SANDBOX"] = "1"


# ── Top-level commands ───────────────────────────────────────────────


@app.command()
@async_command
async def version() -> None:
    """Show the CLI version."""
    emit_json({"version": __version__})


@app.command()
@async_command
async def config(
    action: Annotated[str, typer.Argument(help="Action: get, set, list, path.")],
    key: Annotated[str | None, typer.Argument(help="Config key.")] = None,
    value: Annotated[str | None, typer.Argument(help="Config value.")] = None,
) -> None:
    """Manage CLI configuration.

    Examples:
        datalegion-cli config set api_key legion_abc123...
        datalegion-cli config set api_base_url https://api.datalegion.ai
        datalegion-cli config get api_key
        datalegion-cli config list
        datalegion-cli config path
    """
    cfg = load_config()

    if action == "path":
        from datalegion_cli.config import CONFIG_FILE

        emit_json({"path": str(CONFIG_FILE)})
        return

    if action == "list":
        # Mask the API key for display
        display = dict(cfg)
        if display.get("api_key"):
            display["api_key"] = _mask(str(display["api_key"]))
        emit_json(display)
        return

    if action == "get":
        if not key:
            raise typer.BadParameter("Key is required for 'get'.")
        val = cfg.get(key)
        if val is None:
            raise typer.BadParameter(f"Unknown key: {key}")
        emit_json({key: val})
        return

    if action == "set":
        if not key or value is None:
            raise typer.BadParameter("Both key and value required for 'set'.")
        # Type coercion for booleans
        if value.lower() in ("true", "1", "yes"):
            cfg[key] = True
        elif value.lower() in ("false", "0", "no"):
            cfg[key] = False
        else:
            cfg[key] = value
        save_config(cfg)
        shown = _mask(str(cfg[key])) if key in _SECRET_KEYS else cfg[key]
        logger.info("Set {} = {}", key, shown)
        emit_json({"ok": True, "key": key, "value": shown})
        return

    raise typer.BadParameter(f"Unknown action: {action}. Use get, set, list, or path.")


_SECRET_KEYS = {"api_key"}


def _mask(value: str) -> str:
    """Show enough of a secret to recognize it, never the whole value."""
    return value[:10] + "..." + value[-4:] if len(value) > 14 else "***"


@app.command()
@async_command
async def login(
    team_id: Annotated[
        int | None, typer.Option("--team-id", help="Team the key bills, when you have several.")
    ] = None,
    device: Annotated[
        str | None,
        typer.Option(
            "--device", help="Name for this machine (default: a random id saved locally)."
        ),
    ] = None,
    no_browser: Annotated[
        bool, typer.Option("--no-browser", help="Print the sign-in link without opening it.")
    ] = False,
) -> None:
    """Sign in with your Data Legion account and store a key for this machine.

    Opens a sign-in link (approve the code it shows), then saves an API key that
    belongs to this machine. Signing in again replaces it. Disconnect it any time
    from Connected Apps in the dashboard.
    """
    import webbrowser

    import httpx

    from datalegion_cli import login as flow

    try:
        cfg = load_config()
        if not device and not cfg.get("device_id"):
            cfg["device_id"] = flow.new_device_id()
            save_config(cfg)
        device_name = flow.check_device_name(device or str(cfg["device_id"]))
        async with httpx.AsyncClient(timeout=30.0) as client:
            started = await flow.start_device_authorization(client)
            link = started.get("verification_uri_complete") or started["verification_uri"]
            console.print(
                f"Open [bold]{link}[/bold] and confirm the code [bold]{started['user_code']}[/bold]."
            )
            if not no_browser:
                webbrowser.open(link)
            token = await flow.poll_for_token(client, started)
            issued = await flow.exchange_for_key(
                client, get_base_url(), token, device_name, team_id
            )
    except flow.LoginError as exc:
        emit_error(str(exc), code=exc.code, details=exc.details, as_json=True)
        raise typer.Exit(1) from exc

    cfg = load_config()
    cfg["api_key"] = issued["api_key"]
    save_config(cfg)
    emit_json(
        {
            "ok": True,
            "device": device_name,
            "team_id": issued["team_id"],
            "api_key": _mask(issued["api_key"]),
            "replaced": issued.get("replaced", 0),
        }
    )


@app.command()
@async_command
async def update(
    check: Annotated[bool, typer.Option("--check", help="Only check, don't install.")] = False,
) -> None:
    """Check for updates and optionally self-update."""
    new_version = await check_for_update()
    if new_version:
        emit_json({"update_available": True, "current": __version__, "latest": new_version})
        if not check:
            await self_update(new_version)
    else:
        emit_json({"update_available": False, "current": __version__})


def run() -> None:
    """CLI entry point — called by the console script."""
    from datalegion_cli.async_typer import run as async_run

    async_run(app)
