"""Fail when a workflow, job or step name is not in sentence case, GitHub's own convention.

The first word starts with a capital; every later word is lowercase unless it is a proper noun or
product name (PROPER), an acronym or mixed-case name (GitHub, PyPI, AWS), or holds a digit. Text in
`${{ }}`, backticks and double quotes is left alone. A new proper noun goes in PROPER (or PHRASES for
a multi-word name). The same file lives in every repo's .github/scripts/; keep the copies identical.
"""

import re
import sys
from pathlib import Path

PROPER = {
    "Amazon",
    "Apify",
    "Bandit",
    "Blacksmith",
    "Buildx",
    "Bun",
    "ChatGPT",
    "Claude",
    "Codecov",
    "Dagster",
    "Docker",
    "Dockerfile",
    "Git",
    "GitHub",
    "Homebrew",
    "Java",
    "Lambda",
    "Linux",
    "Make",
    "Node",
    "Node.js",
    "OpenSearch",
    "Playwright",
    "Postgres",
    "PostgreSQL",
    "PyPI",
    "Python",
    "Redis",
    "Snowflake",
    "Tailscale",
    "Terraform",
    "Vercel",
    "Zapier",
}
PHRASES = [
    "Dagster Cloud",
    "Fast Snapshot Restore",
    "GitHub Packages",
    "Enrichment app",
    "Data Legion",
]
NAME = re.compile(r"^(?:|    |\s*- )name:\s*(.+?)\s*(?:#.*)?$")


def _allowed(word: str) -> bool:
    """Whether a capitalized word may stay capitalized after the first word."""
    if word == "X" or word.removesuffix("'s") in PROPER:
        return True
    if len(word) > 1 and (word.isupper() or any(c.isupper() for c in word[1:])):
        return True
    return re.search(r"\d", word) is not None


def problems(name: str) -> list[str]:
    """What is wrong with one name; empty when it is in sentence case."""
    s = name.strip()
    if s[:1] in "\"'" and s[-1:] == s[:1]:
        s = s[1:-1]
    s = re.sub(r"\$\{\{.*?\}\}|`[^`]*`|\"[^\"]*\"", " X ", s)
    for phrase in PHRASES:
        s = s.replace(phrase, " X ")
    words = re.findall(r"[A-Za-z][A-Za-z0-9.'_-]*", s)
    if not words:
        return []
    out = []
    if words[0][:1].islower() and words[0] != "X":
        out.append(f"starts lowercase: {words[0]!r}")
    # Each part of a hyphenated word counts as a word ("End-To-End" is Title Case).
    parts = [p for w in words for p in (w.split("-") if "-" in w and w not in PROPER else [w]) if p]
    for w in parts[1:]:
        if w[:1].isupper() and not _allowed(w):
            out.append(f"capitalized word {w!r}")
    return out


def main() -> int:
    """Check every name in .github/workflows; print each problem and return 1 if any."""
    failures = []
    for path in sorted(Path(".github/workflows").glob("*.y*ml")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            match = NAME.match(line)
            if match:
                for problem in problems(match.group(1)):
                    failures.append(f"{path}:{number}: {match.group(1)} ({problem})")
    for failure in failures:
        print(failure)
    if failures:
        print("Names use sentence case, GitHub's convention: see this script's docstring.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
