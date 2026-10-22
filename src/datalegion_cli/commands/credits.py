"""Credit balance and usage commands."""

from __future__ import annotations

from typing import Annotated

import typer

from datalegion_cli.async_typer import async_command
from datalegion_cli.client import APIError, LegionClient
from datalegion_cli.output import emit_error, emit_json

app = typer.Typer(name="credits", help="Credit balance and usage tracking.")


@app.command("balance")
@async_command
async def balance() -> None:
    """Show current credit balance and active contracts.

    Examples:
        datalegion-cli credits balance
    """
    client = LegionClient()
    try:
        result = await client.credits_balance()
        emit_json(result)
    except APIError as e:
        emit_error(e.message, code=e.error, details=e.details, as_json=True)
        raise typer.Exit(1) from e
    finally:
        await client.close()


@app.command("usage")
@async_command
async def usage(
    start_date: Annotated[
        str | None, typer.Option("--from", help="Start date (YYYY-MM-DD).")
    ] = None,
    end_date: Annotated[str | None, typer.Option("--to", help="End date (YYYY-MM-DD).")] = None,
) -> None:
    """Show credit usage history.

    Examples:
        datalegion-cli credits usage
        datalegion-cli credits usage --from 2026-01-01 --to 2026-03-01
    """
    client = LegionClient()
    try:
        result = await client.credits_usage(start_date=start_date, end_date=end_date)
        emit_json(result)
    except APIError as e:
        emit_error(e.message, code=e.error, details=e.details, as_json=True)
        raise typer.Exit(1) from e
    finally:
        await client.close()
