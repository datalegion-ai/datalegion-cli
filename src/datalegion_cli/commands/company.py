"""Company enrichment, search, and discovery commands."""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer

from datalegion_cli.async_typer import async_command
from datalegion_cli.client import APIError, LegionClient
from datalegion_cli.output import emit_credits, emit_error, emit_json

app = typer.Typer(name="company", help="Company enrichment, search, and discovery.")

# ── Shared options ───────────────────────────────────────────────────

TitleOpt = Annotated[bool, typer.Option("--titlecase", help="Title-case text fields.")]
LimitOpt = Annotated[int, typer.Option("--limit", "-l", help="Max results.")]
FieldsInclude = Annotated[
    str | None, typer.Option("--fields", help="Comma-separated fields to include.")
]
FieldsExclude = Annotated[
    str | None, typer.Option("--exclude", help="Comma-separated fields to exclude.")
]
MinConfidence = Annotated[
    str | None,
    typer.Option("--min-confidence", help="Minimum confidence: high, moderate, low."),
]
RequiredFields = Annotated[
    str | None, typer.Option("--required", help="Comma-separated required fields.")
]


@app.command()
@async_command
async def enrich(
    domain: Annotated[str | None, typer.Option("--domain", "-d", help="Company domain.")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Company name.")] = None,
    legion_id: Annotated[str | None, typer.Option("--legion-id", help="Legion ID.")] = None,
    linkedin_id: Annotated[
        str | None, typer.Option("--linkedin-id", help="LinkedIn numeric ID.")
    ] = None,
    social_url: Annotated[
        str | None, typer.Option("--social-url", help="Social profile URL.")
    ] = None,
    ticker_symbol: Annotated[
        str | None, typer.Option("--ticker", "-t", help="Stock ticker symbol.")
    ] = None,
    industry: Annotated[
        str | None, typer.Option("--industry", help="Industry (narrows name matching).")
    ] = None,
    min_confidence: MinConfidence = None,
    titlecase: TitleOpt = False,
    required_fields: RequiredFields = None,
    include_fields: FieldsInclude = None,
    exclude_fields: FieldsExclude = None,
    stdin: Annotated[bool, typer.Option("--stdin", help="Read JSON payload from stdin.")] = False,
) -> None:
    """Enrich a company by domain, name, LinkedIn, or ticker symbol.

    Examples:
        datalegion-cli company enrich --domain google.com
        datalegion-cli company enrich --name "Acme Corp" --industry "Software"
        datalegion-cli company enrich --ticker AAPL --fields "name,industry,legion_employee_count"
        echo '{"domain":"stripe.com"}' | datalegion-cli company enrich --stdin
    """
    if stdin:
        payload = json.load(sys.stdin)
    else:
        payload = dict(
            domain=domain,
            name=name,
            legion_id=legion_id,
            linkedin_id=linkedin_id,
            social_url=social_url,
            ticker_symbol=ticker_symbol,
            industry=industry,
            min_confidence=min_confidence,
            titlecase=titlecase,
            required_fields=required_fields,
            include_fields=include_fields,
            exclude_fields=exclude_fields,
        )
    client = LegionClient()
    try:
        result = await client.company_enrich(**payload)
        emit_json(result)
        emit_credits(client.last_credits_used, client.last_credits_remaining)
    except APIError as e:
        emit_error(e.message, code=e.error, details=e.details, as_json=True)
        raise typer.Exit(1) from e
    finally:
        await client.close()


@app.command()
@async_command
async def search(
    query: Annotated[str, typer.Argument(help="SQL SELECT query against the companies table.")],
    limit: LimitOpt = 10,
    titlecase: TitleOpt = False,
    include_fields: FieldsInclude = None,
    exclude_fields: FieldsExclude = None,
) -> None:
    """Search for companies with a SQL SELECT over the companies table, no LIMIT (Beta).

    Examples:
        datalegion-cli company search "SELECT * FROM companies WHERE industry ILIKE '%software%' AND legion_employee_count > 100"
        datalegion-cli company search "SELECT * FROM companies WHERE name ILIKE '%tech%'" --limit 20
        datalegion-cli company search "SELECT * FROM companies WHERE domain = 'stripe.com'" --fields "name,domain,industry"
    """
    client = LegionClient()
    try:
        result = await client.company_search(
            query=query,
            limit=limit,
            titlecase=titlecase,
            include_fields=include_fields,
            exclude_fields=exclude_fields,
        )
        emit_json(result)
        emit_credits(client.last_credits_used, client.last_credits_remaining)
    except APIError as e:
        emit_error(e.message, code=e.error, details=e.details, as_json=True)
        raise typer.Exit(1) from e
    finally:
        await client.close()


@app.command()
@async_command
async def discover(
    query: Annotated[str, typer.Argument(help="Natural language company search query.")],
    limit: LimitOpt = 10,
    titlecase: TitleOpt = False,
    include_fields: FieldsInclude = None,
    exclude_fields: FieldsExclude = None,
) -> None:
    """Search for companies using natural language (Beta)."""
    client = LegionClient()
    try:
        result = await client.company_discover(
            query=query,
            limit=limit,
            titlecase=titlecase,
            include_fields=include_fields,
            exclude_fields=exclude_fields,
        )
        emit_json(result)
        emit_credits(client.last_credits_used, client.last_credits_remaining)
    except APIError as e:
        emit_error(e.message, code=e.error, details=e.details, as_json=True)
        raise typer.Exit(1) from e
    finally:
        await client.close()


# TODO: Uncomment when bulk enrichment is ready
# @app.command()
# @async_command
# async def bulk(
#     file: Annotated[str, typer.Argument(help="Path to JSON file with items array, or '-' for stdin.")],
#     titlecase: TitleOpt = False,
# ) -> None:
#     """Bulk enrich up to 100 companies from a JSON file."""
#     if file == "-":
#         data = json.load(sys.stdin)
#     else:
#         with open(file) as f:
#             data = json.load(f)
#
#     items = data if isinstance(data, list) else data.get("items", data)
#
#     client = LegionClient()
#     try:
#         result = await client.company_bulk(
#             items=items, titlecase=titlecase,
#         )
#         emit_json(result)
#         emit_credits(client.last_credits_used, client.last_credits_remaining)
#     except APIError as e:
#         emit_error(e.message, code=e.error, details=e.details, as_json=True)
#         raise typer.Exit(1) from e
#     finally:
#         await client.close()
