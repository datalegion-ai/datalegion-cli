"""Tests for output formatting."""

from __future__ import annotations

import json

from datalegion_cli.output import (
    emit_credits,
    emit_error,
    emit_json,
    emit_search_warning,
    emit_success,
)


class TestEmitJson:
    def test_pretty_json(self, capsys):
        emit_json({"key": "value"})
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed == {"key": "value"}
        assert "\n" in out  # pretty-printed

    def test_compact_json(self, capsys):
        emit_json({"key": "value"}, pretty=False)
        out = capsys.readouterr().out.strip()
        assert out == '{"key": "value"}'

    def test_handles_non_serializable(self, capsys):
        from datetime import datetime

        emit_json({"ts": datetime(2026, 1, 1)})
        out = capsys.readouterr().out
        assert "2026" in out


class TestEmitError:
    def test_json_mode(self, capsys):
        emit_error("Bad request", code="bad_request", as_json=True)
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is False
        assert out["error"] == "bad_request"
        assert out["message"] == "Bad request"

    def test_json_mode_with_details(self, capsys):
        emit_error("Fail", details={"field": "email"}, as_json=True)
        out = json.loads(capsys.readouterr().out)
        assert out["details"] == {"field": "email"}

    def test_rich_mode_no_stdout(self, capsys):
        emit_error("Oops", as_json=False)
        captured = capsys.readouterr()
        assert captured.out == ""  # error goes to stderr via rich


class TestEmitSuccess:
    def test_json_envelope(self, capsys):
        emit_success({"result": 1}, message="Done", as_json=True)
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is True
        assert out["message"] == "Done"
        assert out["data"] == {"result": 1}

    def test_no_message(self, capsys):
        emit_success({"result": 1}, as_json=True)
        out = json.loads(capsys.readouterr().out)
        assert "message" not in out
        assert out["data"] == {"result": 1}


class TestEmitCredits:
    def test_both_values(self, capsys):
        emit_credits("5", "95")
        err = capsys.readouterr().err
        assert "credits used: 5" in err
        assert "remaining: 95" in err

    def test_none_values_no_output(self, capsys):
        emit_credits(None, None)
        err = capsys.readouterr().err
        assert err == ""


class TestEmitSearchWarning:
    def test_warning_goes_to_stderr(self, capsys):
        emit_search_warning("No company_industry value matches '[x]'")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "search warning:" in captured.err and "'[x]'" in captured.err

    def test_none_no_output(self, capsys):
        emit_search_warning(None)
        assert capsys.readouterr().err == ""
