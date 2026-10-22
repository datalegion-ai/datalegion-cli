"""The fleet's test conventions, from the vendored copy of datalegion-shared's module.

Every test can fail, no test swallows an exception, and no two tests share a body. This repo
doesn't depend on datalegion-shared, so ``_conventions.py`` is a byte-identical copy under a
header naming the release it came from; the copy itself is checked here.
"""

from pathlib import Path

from tests import _conventions as conventions

REPO = Path(__file__).resolve().parents[1]
VENDORED = Path(conventions.__file__)


def test_every_test_can_fail() -> None:
    assert conventions.silent_tests(REPO) == []


def test_no_test_swallows_an_exception() -> None:
    assert conventions.swallowing_tests(REPO) == []


def test_no_two_tests_share_a_body() -> None:
    assert conventions.duplicate_test_bodies(REPO) == []


def test_the_vendored_copy_names_its_release() -> None:
    header = VENDORED.read_text().splitlines()[0]
    assert header.startswith("# Vendored from datalegion-shared v")
