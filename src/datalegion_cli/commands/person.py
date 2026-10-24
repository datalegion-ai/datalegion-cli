"""Person enrichment, search, and discovery commands."""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer

from datalegion_cli.async_typer import async_command
from datalegion_cli.client import APIError, LegionClient
from datalegion_cli.output import emit_credits, emit_error, emit_json, emit_search_warning

app = typer.Typer(name="person", help="Person enrichment, search, and discovery.")

# ── Shared options ───────────────────────────────────────────────────

TitleOpt = Annotated[bool, typer.Option("--titlecase", help="Title-case text fields in response.")]
LimitOpt = Annotated[int, typer.Option("--limit", "-l", help="Max results to return.")]
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
    email: Annotated[str | None, typer.Option("--email", "-e", help="Email address.")] = None,
    phone: Annotated[str | None, typer.Option("--phone", "-p", help="Phone number.")] = None,
    linkedin_id: Annotated[
        str | None, typer.Option("--linkedin-id", help="LinkedIn numeric ID.")
    ] = None,
    social_url: Annotated[
        str | None, typer.Option("--social-url", help="Social profile URL.")
    ] = None,
    legion_id: Annotated[str | None, typer.Option("--legion-id", help="Legion ID.")] = None,
    email_hash: Annotated[
        str | None, typer.Option("--email-hash", help="SHA-256/SHA-1/MD5 email hash.")
    ] = None,
    full_name: Annotated[str | None, typer.Option("--name", "-n", help="Full name.")] = None,
    first_name: Annotated[str | None, typer.Option("--first-name", help="First name.")] = None,
    last_name: Annotated[str | None, typer.Option("--last-name", help="Last name.")] = None,
    company: Annotated[
        str | None, typer.Option("--company", "-c", help="Company name/domain.")
    ] = None,
    job_title: Annotated[str | None, typer.Option("--title", help="Job title.")] = None,
    city: Annotated[str | None, typer.Option("--city", help="City.")] = None,
    state: Annotated[str | None, typer.Option("--state", help="State.")] = None,
    country: Annotated[str | None, typer.Option("--country", help="Country.")] = None,
    school: Annotated[str | None, typer.Option("--school", help="School name.")] = None,
    birth_date: Annotated[
        str | None, typer.Option("--birth-date", help="Birth date (YYYY-MM-DD).")
    ] = None,
    address: Annotated[str | None, typer.Option("--address", help="Full address string.")] = None,
    postal_code: Annotated[
        str | None, typer.Option("--postal-code", help="Postal/ZIP code.")
    ] = None,
    min_confidence: MinConfidence = None,
    titlecase: TitleOpt = False,
    required_fields: RequiredFields = None,
    include_fields: FieldsInclude = None,
    exclude_fields: FieldsExclude = None,
    stdin: Annotated[bool, typer.Option("--stdin", help="Read JSON payload from stdin.")] = False,
) -> None:
    """Enrich a person by email, phone, name, social URL, or other identifiers.

    Examples:
        datalegion-cli person enrich --email john@example.com
        datalegion-cli person enrich --name "Jane Doe" --company "Acme Corp"
        datalegion-cli person enrich --phone "+14155551234" --fields "full_name,work_email,job_title"
        echo '{"email":"jane@example.com"}' | datalegion-cli person enrich --stdin
    """
    if stdin:
        payload = json.load(sys.stdin)
    else:
        payload = dict(
            email=email,
            phone=phone,
            linkedin_id=linkedin_id,
            social_url=social_url,
            legion_id=legion_id,
            email_hash=email_hash,
            full_name=full_name,
            first_name=first_name,
            last_name=last_name,
            company=company,
            job_title=job_title,
            city=city,
            state=state,
            country=country,
            school=school,
            birth_date=birth_date,
            address=address,
            postal_code=postal_code,
            min_confidence=min_confidence,
            titlecase=titlecase,
            required_fields=required_fields,
            include_fields=include_fields,
            exclude_fields=exclude_fields,
        )
    client = LegionClient()
    try:
        result = await client.person_enrich(**payload)
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
    query: Annotated[str, typer.Argument(help="SQL SELECT query against the people table.")],
    limit: LimitOpt = 10,
    titlecase: TitleOpt = False,
    include_fields: FieldsInclude = None,
    exclude_fields: FieldsExclude = None,
) -> None:
    """Search for people with a SQL SELECT over the people table, no LIMIT (Beta).

    Examples:
        datalegion-cli person search "SELECT * FROM people WHERE job_title = 'ceo' AND company_name ILIKE '%acme%'"
        datalegion-cli person search "SELECT * FROM people WHERE city = 'san francisco'" --limit 20
    """
    client = LegionClient()
    try:
        result = await client.person_search(
            query=query,
            limit=limit,
            titlecase=titlecase,
            include_fields=include_fields,
            exclude_fields=exclude_fields,
        )
        emit_json(result)
        emit_credits(client.last_credits_used, client.last_credits_remaining)
        emit_search_warning(client.last_search_warning)
    except APIError as e:
        emit_error(e.message, code=e.error, details=e.details, as_json=True)
        raise typer.Exit(1) from e
    finally:
        await client.close()


@app.command()
@async_command
async def discover(
    query: Annotated[str, typer.Argument(help="Natural language search query.")],
    limit: LimitOpt = 10,
    titlecase: TitleOpt = False,
    include_fields: FieldsInclude = None,
    exclude_fields: FieldsExclude = None,
) -> None:
    """Search for people using natural language (Beta)."""
    client = LegionClient()
    try:
        result = await client.person_discover(
            query=query,
            limit=limit,
            titlecase=titlecase,
            include_fields=include_fields,
            exclude_fields=exclude_fields,
        )
        emit_json(result)
        emit_credits(client.last_credits_used, client.last_credits_remaining)
        emit_search_warning(client.last_search_warning)
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
#     """Bulk enrich up to 100 people from a JSON file."""
#     if file == "-":
#         data = json.load(sys.stdin)
#     else:
#         with open(file) as f:
#             data = json.load(f)
#
#     # Accept either {"items": [...]} or just [...]
#     items = data if isinstance(data, list) else data.get("items", data)
#
#     client = LegionClient()
#     try:
#         result = await client.person_bulk(
#             items=items, titlecase=titlecase,
#         )
#         emit_json(result)
#         emit_credits(client.last_credits_used, client.last_credits_remaining)
#     except APIError as e:
#         emit_error(e.message, code=e.error, details=e.details, as_json=True)
#         raise typer.Exit(1) from e
#     finally:
#         await client.close()
