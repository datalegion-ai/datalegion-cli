"""Tests for CLI commands via typer CliRunner."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from datalegion_cli.main import app
from tests.conftest import make_response

runner = CliRunner()


# ── Helper ───────────────────────────────────────────────────────────


def _mock_client_request(response_json, status_code=200, headers=None):
    """Patch LegionClient to return a canned response without HTTP."""
    hdrs = headers or {"Credits-Used": "1", "Credits-Remaining": "99"}
    resp = make_response(status_code, response_json, hdrs)

    async def fake_request(self, method, endpoint, *, payload=None, params=None):
        if status_code >= 400:
            from datalegion_cli.client import APIError

            body = resp.json()
            raise APIError(
                status_code=status_code,
                error=body.get("error", "unknown"),
                message=body.get("message", "error"),
            )
        self.last_credits_used = hdrs.get("Credits-Used")
        self.last_credits_remaining = hdrs.get("Credits-Remaining")
        self.last_search_warning = hdrs.get("Search-Warning")
        return resp.json()

    return patch("datalegion_cli.client.LegionClient.request", fake_request)


def _mock_config(monkeypatch):
    """Provide fake config so commands don't need a real config file."""
    monkeypatch.setenv(
        "LEGION_API_KEY", "legion_testkey1234567890abcdef1234567890abcdef1234567890abcdef12345678"
    )
    monkeypatch.setenv("LEGION_API_URL", "https://test.api.local")


# ── Top-level commands ───────────────────────────────────────────────


class TestVersionCommand:
    def test_version_output(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "version" in data


class TestConfigCommand:
    def test_config_path(self, tmp_config_dir):
        result = runner.invoke(app, ["config", "path"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "path" in data

    def test_config_set_and_get(self, tmp_config_dir, monkeypatch):
        monkeypatch.delenv("LEGION_API_KEY", raising=False)
        # Set
        result = runner.invoke(app, ["config", "set", "api_key", "legion_testval123"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True

        # Get
        result = runner.invoke(app, ["config", "get", "api_key"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["api_key"] == "legion_testval123"

    def test_config_list_masks_key(self, tmp_config_dir, monkeypatch):
        monkeypatch.delenv("LEGION_API_KEY", raising=False)
        runner.invoke(app, ["config", "set", "api_key", "legion_thisisaverylongsecretkey"])
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "..." in data["api_key"]  # masked

    def test_config_set_boolean_coercion(self, tmp_config_dir):
        result = runner.invoke(app, ["config", "set", "some_flag", "true"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["value"] is True

    def test_config_get_unknown_key(self, tmp_config_dir):
        result = runner.invoke(app, ["config", "get", "nonexistent_key"])
        assert result.exit_code != 0

    def test_config_unknown_action(self, tmp_config_dir):
        result = runner.invoke(app, ["config", "delete"])
        assert result.exit_code != 0


# ── Person commands ──────────────────────────────────────────────────


class TestPersonEnrich:
    def test_enrich_by_email(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"matches": [{"full_name": "John Doe", "email": "john@example.com"}], "total": 1}
        with _mock_client_request(response):
            result = runner.invoke(app, ["person", "enrich", "--email", "john@example.com"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["matches"][0]["full_name"] == "John Doe"

    def test_enrich_by_name_and_company(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"matches": [{"full_name": "Jane Smith"}], "total": 1}
        with _mock_client_request(response):
            result = runner.invoke(
                app,
                [
                    "person",
                    "enrich",
                    "--name",
                    "Jane Smith",
                    "--company",
                    "Acme Corp",
                    "--city",
                    "NYC",
                ],
            )
        assert result.exit_code == 0

    def test_enrich_stdin(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"matches": [{"full_name": "Bob"}], "total": 1}
        payload = json.dumps({"email": "bob@test.com"})
        with _mock_client_request(response):
            result = runner.invoke(app, ["person", "enrich", "--stdin"], input=payload)
        assert result.exit_code == 0

    def test_enrich_api_error(self, monkeypatch):
        _mock_config(monkeypatch)
        with _mock_client_request({"error": "unauthorized", "message": "Bad key"}, status_code=401):
            result = runner.invoke(app, ["person", "enrich", "--email", "x@x.com"])
        assert result.exit_code == 1


class TestPersonSearch:
    def test_search(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"matches": [], "total": 0}
        with _mock_client_request(response):
            result = runner.invoke(
                app,
                [
                    "person",
                    "search",
                    "SELECT * FROM people WHERE city = 'Austin'",
                    "--limit",
                    "5",
                ],
            )
        assert result.exit_code == 0


class TestPersonDiscover:
    def test_discover(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {
            "matches": [{"full_name": "Engineer"}],
            "total": 1,
            "generated_query": "SELECT...",
        }
        with _mock_client_request(response):
            result = runner.invoke(
                app,
                [
                    "person",
                    "discover",
                    "software engineers in San Francisco",
                ],
            )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "generated_query" in data


# TODO: Uncomment when bulk enrichment is ready
# class TestPersonBulk:
#     def test_bulk_from_stdin(self, monkeypatch):
#         _mock_config(monkeypatch)
#         response = {"results": [{"matches": [{"full_name": "A"}], "total": 1}]}
#         payload = json.dumps([{"email": "a@b.com"}])
#         with _mock_client_request(response):
#             result = runner.invoke(app, ["person", "bulk", "-"], input=payload)
#         assert result.exit_code == 0
#
#     def test_bulk_from_file(self, monkeypatch, tmp_path):
#         _mock_config(monkeypatch)
#         response = {"results": []}
#         f = tmp_path / "items.json"
#         f.write_text(json.dumps({"items": [{"email": "x@y.com"}]}))
#         with _mock_client_request(response):
#             result = runner.invoke(app, ["person", "bulk", str(f)])
#         assert result.exit_code == 0


# ── Company commands ─────────────────────────────────────────────────


class TestCompanyEnrich:
    def test_enrich_by_domain(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"matches": [{"name": "Google", "domain": "google.com"}], "total": 1}
        with _mock_client_request(response):
            result = runner.invoke(app, ["company", "enrich", "--domain", "google.com"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["matches"][0]["name"] == "Google"

    def test_enrich_by_ticker(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"matches": [{"name": "Apple Inc.", "ticker_symbols": ["AAPL"]}], "total": 1}
        with _mock_client_request(response):
            result = runner.invoke(app, ["company", "enrich", "--ticker", "AAPL"])
        assert result.exit_code == 0

    def test_enrich_stdin(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"matches": [{"name": "X"}], "total": 1}
        with _mock_client_request(response):
            result = runner.invoke(
                app, ["company", "enrich", "--stdin"], input=json.dumps({"domain": "x.com"})
            )
        assert result.exit_code == 0


class TestCompanySearch:
    def test_search(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"matches": [], "total": 0}
        with _mock_client_request(response):
            result = runner.invoke(
                app,
                [
                    "company",
                    "search",
                    "SELECT * FROM companies WHERE industry ILIKE '%software%'",
                ],
            )
        assert result.exit_code == 0


class TestCompanyDiscover:
    def test_discover(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"matches": [{"name": "Startup"}], "total": 1, "generated_query": "SELECT..."}
        with _mock_client_request(response):
            result = runner.invoke(app, ["company", "discover", "AI startups in SF"])
        assert result.exit_code == 0


# TODO: Uncomment when bulk enrichment is ready
# class TestCompanyBulk:
#     def test_bulk_from_stdin(self, monkeypatch):
#         _mock_config(monkeypatch)
#         response = {"results": []}
#         with _mock_client_request(response):
#             result = runner.invoke(app, ["company", "bulk", "-"], input=json.dumps([{"domain": "x.com"}]))
#         assert result.exit_code == 0


# ── Utility commands ─────────────────────────────────────────────────


class TestUtilityClean:
    def test_clean_from_argument(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"cleaned": {"email": "john@gmail.com"}}
        with _mock_client_request(response):
            result = runner.invoke(
                app,
                [
                    "utility",
                    "clean",
                    '{"email": "John.Doe+tag@gmail.com"}',
                ],
            )
        assert result.exit_code == 0

    def test_clean_from_stdin(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"cleaned": {"phone": "+15551234567"}}
        with _mock_client_request(response):
            result = runner.invoke(
                app,
                [
                    "utility",
                    "clean",
                    "--stdin",
                ],
                input=json.dumps({"phone": "(555) 123-4567"}),
            )
        assert result.exit_code == 0


class TestUtilityHash:
    def test_hash_email(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"sha256": "abc...", "sha1": "def...", "md5": "ghi..."}
        with _mock_client_request(response):
            result = runner.invoke(app, ["utility", "hash", "john@example.com"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "sha256" in data


class TestUtilityReport:
    def test_report_person_field_issue(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"status": "received", "report_id": "rpt_123"}
        with _mock_client_request(response):
            result = runner.invoke(
                app,
                [
                    "utility",
                    "report",
                    "person",
                    "--legion-id",
                    "abc123",
                    "--issue-type",
                    "outdated",
                    "--issue-level",
                    "field",
                    "--field",
                    "job_title",
                    "--observed",
                    "CTO",
                    "--correct",
                    "CEO",
                ],
            )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["report_id"] == "rpt_123"

    def test_report_company_with_comment(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"status": "received", "report_id": "rpt_456"}
        with _mock_client_request(response):
            result = runner.invoke(
                app,
                [
                    "utility",
                    "report",
                    "company",
                    "--legion-id",
                    "xyz789",
                    "--issue-type",
                    "duplicate",
                    "--comment",
                    "Same company as legion_id def456",
                ],
            )
        assert result.exit_code == 0

    def test_report_rejects_bad_kind(self, monkeypatch):
        _mock_config(monkeypatch)
        result = runner.invoke(
            app,
            ["utility", "report", "robot", "--legion-id", "a", "--issue-type", "incorrect"],
        )
        assert result.exit_code != 0


class TestUtilityValidate:
    def test_validate_email(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"valid": True, "suggestions": []}
        with _mock_client_request(response):
            result = runner.invoke(app, ["utility", "validate", "--email", "test@example.com"])
        assert result.exit_code == 0

    def test_validate_stdin(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"valid": False, "errors": ["invalid email"]}
        with _mock_client_request(response):
            result = runner.invoke(
                app,
                [
                    "utility",
                    "validate",
                    "--stdin",
                ],
                input=json.dumps({"email": "bad"}),
            )
        assert result.exit_code == 0


# ── Credits commands ─────────────────────────────────────────────────


class TestCreditsBalance:
    def test_balance(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"credits_remaining": 1000, "contracts": []}
        with _mock_client_request(response):
            result = runner.invoke(app, ["credits", "balance"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["credits_remaining"] == 1000


class TestCreditsUsage:
    def test_usage_with_dates(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"usage": [], "total_credits_used": 50}
        with _mock_client_request(response):
            result = runner.invoke(
                app,
                [
                    "credits",
                    "usage",
                    "--from",
                    "2026-01-01",
                    "--to",
                    "2026-03-01",
                ],
            )
        assert result.exit_code == 0

    def test_usage_no_dates(self, monkeypatch):
        _mock_config(monkeypatch)
        response = {"usage": [], "total_credits_used": 0}
        with _mock_client_request(response):
            result = runner.invoke(app, ["credits", "usage"])
        assert result.exit_code == 0


# ── Several matches per lookup is an enterprise feature: no CLI option ──


class TestEnrichOffersNoMultipleResults:
    def test_enrich_rejects_multiple_and_limit(self, monkeypatch):
        _mock_config(monkeypatch)
        for entity, ident in (("person", ["--email", "a@b.co"]), ("company", ["--domain", "b.co"])):
            for option in (["--multiple"], ["--limit", "3"]):
                result = runner.invoke(app, [entity, "enrich", *ident, *option])
                assert result.exit_code != 0, (entity, option)

    def test_enrich_payload_carries_neither_field(self, monkeypatch):
        _mock_config(monkeypatch)
        sent: list[dict] = []

        async def capture(self, method, endpoint, *, payload=None, params=None):
            sent.append(payload or {})
            return {"matches": [], "total": 0}

        with patch("datalegion_cli.client.LegionClient.request", capture):
            runner.invoke(app, ["person", "enrich", "--email", "a@b.co"])
            runner.invoke(app, ["company", "enrich", "--domain", "b.co"])
        assert len(sent) == 2
        for payload in sent:
            assert "multiple_results" not in payload
            assert "limit" not in payload


class TestSearchWarning:
    """search and discover print the API's Search-Warning on stderr; stdout stays JSON."""

    @pytest.mark.parametrize(
        "args",
        [
            ["person", "search", "SELECT * FROM people WHERE company_industry = 'x'"],
            ["person", "discover", "people in x"],
            ["company", "search", "SELECT * FROM companies WHERE industry = 'x'"],
            ["company", "discover", "companies in x"],
        ],
    )
    def test_the_warning_reaches_stderr(self, monkeypatch, args):
        _mock_config(monkeypatch)
        warning = "No company_industry value matches 'x'"
        with _mock_client_request({"matches": [], "total": 0}, headers={"Search-Warning": warning}):
            result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"matches": [], "total": 0}
        assert f"search warning: {warning}" in result.stderr
