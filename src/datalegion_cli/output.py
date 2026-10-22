"""Output formatting — JSON (agent-friendly), table (human), or raw."""

from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console(stderr=True)
_out = Console()  # stdout for data


def emit_json(data: Any, *, pretty: bool = True) -> None:
    """Write JSON to stdout. This is the primary agent-friendly format."""
    indent = 2 if pretty else None
    print(json.dumps(data, indent=indent, default=str))


def emit_table(rows: list[dict[str, Any]], *, columns: list[str] | None = None) -> None:
    """Render a Rich table to stdout for human consumption."""
    if not rows:
        _out.print("[dim]No results.[/dim]")
        return
    cols = columns or list(rows[0].keys())
    table = Table(show_lines=False, expand=False)
    for c in cols:
        table.add_column(c, overflow="fold")
    for row in rows:
        table.add_row(*(str(row.get(c, "")) for c in cols))
    _out.print(table)


def emit_error(
    message: str, *, code: str = "error", details: Any = None, as_json: bool = False
) -> None:
    """Print an error. In JSON mode, writes structured error to stdout."""
    if as_json:
        err: dict[str, Any] = {"ok": False, "error": code, "message": message}
        if details:
            err["details"] = details
        print(json.dumps(err, default=str), file=sys.stdout)
    else:
        console.print(f"[bold red]Error:[/bold red] {message}")
        if details:
            console.print(f"[dim]{details}[/dim]")


def emit_success(data: Any, *, message: str | None = None, as_json: bool = True) -> None:
    """Wrap data in an ok envelope for agents, or just print it."""
    if as_json:
        envelope: dict[str, Any] = {"ok": True}
        if message:
            envelope["message"] = message
        envelope["data"] = data
        emit_json(envelope)
    else:
        if message:
            console.print(f"[green]{message}[/green]")
        emit_json(data)


def emit_credits(used: str | None, remaining: str | None) -> None:
    """Show credit usage on stderr (never pollutes stdout for agents)."""
    parts = []
    if used:
        parts.append(f"credits used: {used}")
    if remaining:
        parts.append(f"remaining: {remaining}")
    if parts:
        console.print(f"[dim]({', '.join(parts)})[/dim]")
