"""Async bridge for typer — single asyncio.run() at the entry point."""

import asyncio
import functools
import inspect
from collections.abc import Callable
from typing import Any, get_type_hints

_loop: asyncio.AbstractEventLoop | None = None


def get_loop() -> asyncio.AbstractEventLoop:
    """Return the shared event loop (created once by ``run``)."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def async_command(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that lets typer call an ``async def`` command.

    Typer expects sync callables.  This wraps them so the coroutine is
    scheduled on the shared event loop created by ``run()``.

    We also forward ``__annotations__`` with resolved types so that typer
    can properly distinguish Arguments from Options even when the source
    module uses ``from __future__ import annotations``.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return get_loop().run_until_complete(fn(*args, **kwargs))

    # Preserve the original signature so typer can inspect parameters.
    wrapper.__signature__ = inspect.signature(fn, eval_str=True)  # type: ignore[attr-defined]

    # Resolve stringified annotations so typer sees real types.
    try:
        wrapper.__annotations__ = get_type_hints(fn, include_extras=True)
    except Exception:
        wrapper.__annotations__ = fn.__annotations__

    return wrapper


def run(app: Any) -> None:
    """Entry point — creates the event loop, runs typer, then cleans up."""
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        app()
    finally:
        _loop.close()
        _loop = None
