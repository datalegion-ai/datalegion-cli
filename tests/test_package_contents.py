"""What the published wheel and sdist contain.

Customers install the wheel: it must hold only the ``datalegion_cli`` package, and its only
command is ``datalegion-cli``. The sdist carries the source and tests, never repo tooling.
"""

import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    # Each straight from the source tree: a default build makes the wheel from the sdist, which
    # would hide a wheel misconfiguration behind the sdist's own include list.
    for target in ("--sdist", "--wheel"):
        subprocess.run(
            ["uv", "build", target, "--quiet", "--out-dir", str(out)], cwd=ROOT, check=True
        )
    return out


def test_wheel_ships_only_the_cli(dist: Path) -> None:
    (wheel,) = dist.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        commands = next(
            (archive.read(n).decode() for n in names if n.endswith("entry_points.txt")), ""
        )
    top_level = {n.split("/")[0] for n in names if not n.split("/")[0].endswith(".dist-info")}
    assert top_level == {"datalegion_cli"}
    assert any(n.endswith(".dist-info/licenses/LICENSE") for n in names)
    assert commands.split() == [
        "[console_scripts]",
        "datalegion-cli",
        "=",
        "datalegion_cli.main:run",
    ]


def test_sdist_carries_no_repo_tooling(dist: Path) -> None:
    (sdist,) = dist.glob("*.tar.gz")
    with tarfile.open(sdist) as archive:
        names = archive.getnames()
    leaked = [
        n
        for n in names
        if any(part in n.split("/") for part in (".claude", ".github", "scripts", "lefthook.yml"))
    ]
    assert leaked == []
    assert any(n.endswith("src/datalegion_cli/main.py") for n in names)


def test_sdist_carries_the_license_and_no_git_bound_tests(dist: Path) -> None:
    (sdist,) = dist.glob("*.tar.gz")
    with tarfile.open(sdist) as archive:
        names = {n.split("/", 1)[1] for n in archive.getnames() if "/" in n}
    assert "LICENSE" in names
    assert "tests/test_conventions.py" not in names
    assert "tests/_conventions.py" not in names


def test_sdist_tests_pass_from_the_sdist_alone(dist: Path, tmp_path: Path) -> None:
    (sdist,) = dist.glob("*.tar.gz")
    with tarfile.open(sdist) as archive:
        archive.extractall(tmp_path, filter="data")
    (root,) = [p for p in tmp_path.iterdir() if p.is_dir()]
    # A clean environment: nothing from this run (LEGION_* settings an earlier test left, the
    # user's own config) may reach the sdist's tests.
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LEGION_", "DATALEGION_"))}
    env["HOME"] = str(tmp_path / "home")
    # The sdist's own source first on the path, on the interpreter running these tests (it has
    # every dependency already), so nothing is installed or fetched: no network, no resolution.
    # Code comes from the sdist; package metadata (version, direct_url.json) still comes from the
    # running environment's install, so a test here must not rely on how the package was installed.
    env["PYTHONPATH"] = str(root / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests",
            "--ignore",
            "tests/test_package_contents.py",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    imported = subprocess.run(
        [sys.executable, "-c", "import datalegion_cli; print(datalegion_cli.__file__)"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    # The tests exercised the sdist's copy, not this checkout's installed one.
    assert Path(imported).resolve().is_relative_to((root / "src").resolve())
    assert result.returncode == 0, result.stdout[-2000:]
