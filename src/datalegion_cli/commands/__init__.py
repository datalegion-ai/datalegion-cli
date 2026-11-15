"""CLI command modules."""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer

CursorOpt = Annotated[
    str | None,
    typer.Option(
        "--cursor",
        help="The previous page's next_cursor, with the same query, for the next page.",
    ),
]


QueryArg = Annotated[
    str | None,
    typer.Argument(
        help="SQL, or a query object as JSON (the same as --sql or --es-query). Optional with --filters."
    ),
]
FiltersOpt = Annotated[
    str | None,
    typer.Option(
        "--filters",
        help=(
            "Filters as JSON, on the record's own field names: a value or a list (any of them), "
            '{"gte": .., "lte": ..}, {"exists": true}; {"and"|"or"|"not": ...} groups; keywords takes a Boolean string.'
        ),
    ),
]
SqlOpt = Annotated[
    str | None, typer.Option("--sql", help="A SELECT statement (no LIMIT: use --limit).")
]
EsQueryOpt = Annotated[
    str | None,
    typer.Option("--es-query", help="A query object in the Elasticsearch query syntax, as JSON."),
]


def _json_object(text: str, what: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"{what} looks like JSON but doesn't parse: {e.msg}.") from e
    if not isinstance(value, dict):
        raise typer.BadParameter(f"{what} must be a JSON object.")
    return value


def search_inputs(
    query: str | None, filters: str | None, sql: str | None, es_query: str | None
) -> dict[str, Any]:
    """Exactly one of the search inputs, each sent by its own name; the positional query is SQL or a query object."""
    given = [
        name
        for name, v in (
            ("query", query),
            ("--filters", filters),
            ("--sql", sql),
            ("--es-query", es_query),
        )
        if v
    ]
    if len(given) != 1:
        raise typer.BadParameter("Give exactly one of a query, --filters, --sql or --es-query.")
    if filters:
        return {"filters": _json_object(filters, "--filters")}
    if es_query:
        return {"es_query": _json_object(es_query, "--es-query")}
    if sql:
        return {"sql": sql}
    assert query is not None
    if query.lstrip().startswith("{"):
        return {"es_query": _json_object(query, "The query")}
    return {"sql": query}
