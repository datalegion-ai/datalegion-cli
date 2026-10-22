"""Utility commands — clean, hash, validate, report."""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer

from datalegion_cli.async_typer import async_command
from datalegion_cli.client import APIError, LegionClient
from datalegion_cli.output import emit_error, emit_json

app = typer.Typer(name="utility", help="Data cleaning, hashing, validation, and issue reporting.")


@app.command()
@async_command
async def clean(
    fields: Annotated[
        str | None,
        typer.Argument(
            help='JSON object of fields to clean, e.g. \'{"email":"John+tag@gmail.com"}\'.'
        ),
    ] = None,
    stdin: Annotated[bool, typer.Option("--stdin", help="Read JSON fields from stdin.")] = False,
    default_region: Annotated[str, typer.Option("--region", help="Default phone region.")] = "US",
) -> None:
    """Clean and normalize data fields.

    Examples:
        datalegion-cli utility clean '{"email":"John+tag@gmail.com"}'
        datalegion-cli utility clean '{"phone":"(415) 555-1234"}' --region US
        echo '{"email":"test@EXAMPLE.com","phone":"5551234"}' | datalegion-cli utility clean --stdin
    """
    if stdin:
        data = json.load(sys.stdin)
    elif fields:
        data = json.loads(fields)
    else:
        raise typer.BadParameter("Provide fields as argument or use --stdin.")

    client = LegionClient()
    try:
        result = await client.utility_clean(fields=data, default_region=default_region)
        emit_json(result)
    except APIError as e:
        emit_error(e.message, code=e.error, details=e.details, as_json=True)
        raise typer.Exit(1) from e
    finally:
        await client.close()


@app.command("hash")
@async_command
async def hash_email(
    email: Annotated[str, typer.Argument(help="Email address to hash.")],
) -> None:
    """Hash an email address (SHA-256, SHA-1, MD5) for privacy-preserving lookups.

    Examples:
        datalegion-cli utility hash john@example.com
    """
    client = LegionClient()
    try:
        result = await client.utility_hash(email)
        emit_json(result)
    except APIError as e:
        emit_error(e.message, code=e.error, details=e.details, as_json=True)
        raise typer.Exit(1) from e
    finally:
        await client.close()


@app.command()
@async_command
async def validate(
    email: Annotated[str | None, typer.Option("--email", help="Email to validate.")] = None,
    phone: Annotated[str | None, typer.Option("--phone", help="Phone to validate.")] = None,
    full_name: Annotated[str | None, typer.Option("--name", help="Name to validate.")] = None,
    domain: Annotated[str | None, typer.Option("--domain", help="Domain to validate.")] = None,
    social_url: Annotated[
        str | None, typer.Option("--social-url", help="Social URL to validate.")
    ] = None,
    company: Annotated[
        str | None, typer.Option("--company", help="Company name to validate.")
    ] = None,
    ticker_symbol: Annotated[
        str | None, typer.Option("--ticker", help="Ticker symbol to validate.")
    ] = None,
    stdin: Annotated[bool, typer.Option("--stdin", help="Read JSON from stdin.")] = False,
) -> None:
    """Validate data fields and get cleaning suggestions.

    Examples:
        datalegion-cli utility validate --email john@example.com
        datalegion-cli utility validate --phone "+14155551234" --domain example.com
        echo '{"email":"test@example.com","company":"Acme"}' | datalegion-cli utility validate --stdin
    """
    if stdin:
        kwargs = json.load(sys.stdin)
    else:
        kwargs = dict(
            email=email,
            phone=phone,
            full_name=full_name,
            domain=domain,
            social_url=social_url,
            company=company,
            ticker_symbol=ticker_symbol,
        )

    client = LegionClient()
    try:
        result = await client.utility_validate(**kwargs)
        emit_json(result)
    except APIError as e:
        emit_error(e.message, code=e.error, details=e.details, as_json=True)
        raise typer.Exit(1) from e
    finally:
        await client.close()


@app.command()
@async_command
async def report(
    kind: Annotated[str, typer.Argument(help="Record type: person or company.")],
    legion_id: Annotated[str, typer.Option("--legion-id", help="Legion ID of the record.")],
    issue_type: Annotated[
        str,
        typer.Option(
            "--issue-type",
            help=(
                "Issue type: incorrect, outdated, misattributed, frankenstein, "
                "not_a_real_person (person only), or duplicate."
            ),
        ),
    ],
    issue_level: Annotated[
        str,
        typer.Option("--issue-level", help="Issue level: record, group, or field."),
    ] = "record",
    field: Annotated[
        str | None,
        typer.Option("--field", help="Group or field name (for group/field level issues)."),
    ] = None,
    observed_value: Annotated[
        str | None, typer.Option("--observed", help="The incorrect value you observed.")
    ] = None,
    correct_value: Annotated[
        str | None, typer.Option("--correct", help="The correct value, if known.")
    ] = None,
    comment: Annotated[
        str | None, typer.Option("--comment", help="Free-form description of the issue.")
    ] = None,
) -> None:
    """Report a data issue on a person or company record (no credit cost).

    Include at least one of --correct or --comment.

    Examples:
        datalegion-cli utility report person --legion-id abc123 --issue-type outdated \\
            --issue-level field --field job_title --observed "CTO" --correct "CEO"
        datalegion-cli utility report company --legion-id xyz789 --issue-type duplicate \\
            --comment "Same company as legion_id def456"
    """
    if kind not in ("person", "company"):
        raise typer.BadParameter("kind must be 'person' or 'company'.")

    client = LegionClient()
    try:
        result = await client.utility_report(
            kind,
            legion_id=legion_id,
            issue_type=issue_type,
            issue_level=issue_level,
            field=field,
            observed_value=observed_value,
            correct_value=correct_value,
            comment=comment,
        )
        emit_json(result)
    except APIError as e:
        emit_error(e.message, code=e.error, details=e.details, as_json=True)
        raise typer.Exit(1) from e
    finally:
        await client.close()
