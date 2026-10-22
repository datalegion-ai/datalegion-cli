"""Loguru configuration for the CLI."""

from __future__ import annotations

import sys

from loguru import logger


def setup_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """Configure loguru for CLI use.

    - Default: WARNING+ to stderr (doesn't pollute stdout for agents)
    - --verbose: DEBUG+ to stderr
    - --quiet: suppress all log output
    """
    logger.remove()  # Remove default handler

    if quiet:
        return

    level = "DEBUG" if verbose else "WARNING"
    logger.add(
        sys.stderr,
        level=level,
        format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        colorize=True,
    )
