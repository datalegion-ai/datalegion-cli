"""Live tests: every CLI command group against the real Data Legion API.

These run the commands end to end (argument parsing, the HTTP client, output) with no mocks.
They need DATALEGION_API_KEY, the same variable the SDKs' live tests use; CI sets it, and
without it they skip. The CLI itself reads LEGION_API_KEY, so each test passes the key on
through that, in a temporary config directory so a developer's own login is never used.
"""

from __future__ import annotations

import json
import os

import pytest
from typer.testing import CliRunner

from datalegion_cli.main import app

API_KEY = os.environ.get("DATALEGION_API_KEY", "").strip()

pytestmark = pytest.mark.skipif(not API_KEY, reason="No DATALEGION_API_KEY set")

runner = CliRunner()


@pytest.fixture(autouse=True)
def live_key(tmp_config_dir, monkeypatch):
    """Use the live key and a throwaway config for every test here."""
    monkeypatch.setenv("LEGION_API_KEY", API_KEY)
    monkeypatch.delenv("LEGION_SANDBOX", raising=False)


def run_json(*args: str) -> dict:
    """Run a CLI command, require exit 0, and parse its stdout as JSON."""
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, f"{args} exited {result.exit_code}: {result.output}"
    return json.loads(result.stdout)


class TestPerson:
    def test_search_returns_engineers_at_google(self):
        body = run_json(
            "person",
            "search",
            "SELECT * FROM people WHERE job_title ILIKE '%engineer%' "
            "AND company_name ILIKE '%google%'",
            "--limit",
            "1",
        )
        assert isinstance(body["matches"], list)
        assert len(body["matches"]) == 1
        assert body["matches"][0]["person"]["legion_id"]

    def test_discover_answers_a_plain_english_query(self):
        body = run_json("person", "discover", "find software engineers at google", "--limit", "1")
        assert isinstance(body["matches"], list)

    def test_sandbox_enrich_returns_the_sample_person(self):
        body = run_json("--sandbox", "person", "enrich", "--email", "anyone@example.com")
        assert body["matches"][0]["person"]["legion_id"] == "sandbox_person_001"


class TestCompany:
    def test_enrich_by_domain_finds_google(self):
        body = run_json("company", "enrich", "--domain", "google.com")
        company = body["matches"][0]["company"] if "matches" in body else body
        assert company["legion_id"]
        assert "google" in json.dumps(company.get("domain", "")).lower()

    def test_search_by_domain(self):
        body = run_json(
            "company",
            "search",
            "SELECT * FROM companies WHERE domain ILIKE '%google%'",
            "--limit",
            "1",
        )
        assert len(body["matches"]) == 1

    def test_discover_answers_a_plain_english_query(self):
        body = run_json(
            "company", "discover", "enterprise software companies with over 1000 employees",
            "--limit", "1",
        )  # fmt: skip
        assert isinstance(body["matches"], list)


class TestUtility:
    def test_clean_lowercases_and_trims_an_email(self):
        body = run_json("utility", "clean", '{"email": "  JOHN@GMAIL.COM  "}')
        assert body["results"]["email"]["cleaned"] == "john@gmail.com"

    def test_hash_returns_all_three_digests(self):
        body = run_json("utility", "hash", "jane.doe@gmail.com")
        assert set(body["hashes"]) >= {"sha256", "sha1", "md5"}

    def test_validate_accepts_a_real_email(self):
        body = run_json("utility", "validate", "--email", "jane.doe@gmail.com")
        assert body["valid"] is True


class TestAccount:
    def test_credits_balance_names_the_team(self):
        body = run_json("credits", "balance")
        assert body["team"]["team_id"]
