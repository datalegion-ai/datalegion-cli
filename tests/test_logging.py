"""Tests for loguru logging configuration."""

from __future__ import annotations

from loguru import logger

from datalegion_cli.logging import setup_logging


class TestSetupLogging:
    def test_default_level(self, capsys):
        setup_logging()
        # Debug should not appear at default level
        logger.debug("debug msg")
        err = capsys.readouterr().err
        assert "debug msg" not in err

    def test_verbose_shows_debug(self, capsys):
        setup_logging(verbose=True)
        logger.debug("verbose debug")
        err = capsys.readouterr().err
        assert "verbose debug" in err

    def test_quiet_suppresses_all(self, capsys):
        setup_logging(quiet=True)
        logger.warning("should not appear")
        logger.error("also hidden")
        err = capsys.readouterr().err
        assert err == ""

    def test_warning_shows_at_default(self, capsys):
        setup_logging()
        logger.warning("warn msg")
        err = capsys.readouterr().err
        assert "warn msg" in err
