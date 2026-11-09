"""CLI command modules."""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer

CursorOpt = Annotated[
    str | None,
    typer.Option(
        "--cursor",
        help="The previous page's next_cursor, for deep paging (instead of an offset).",
    ),
]


def search_query(text: str) -> str | dict[str, Any]:
    """SQL as given, or a query object when the argument is a JSON object."""
    if not text.lstrip().startswith("{"):
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"The query looks like JSON but doesn't parse: {e.msg}.") from e
