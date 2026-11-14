# datalegion-cli

The official command-line interface for the [Data Legion](https://www.datalegion.ai) API. Built for both humans and AI agents.

Look up people and companies by email, phone, name, domain, LinkedIn, or ticker symbol. Search using SQL syntax. Clean, hash, and validate data fields before or after enrichment. Track credit usage and manage your configuration, all from the terminal.

```bash
pip install datalegion-cli
datalegion-cli config set api_key legion_your_key_here
datalegion-cli person enrich --email john@example.com
```

## Features

- **Fully async**: async from entry point to HTTP client, powered by `asyncio` and `httpx`
- **Agent-friendly**: all output is JSON to stdout, logs go to stderr, supports `--stdin` for piping
- **Search warnings**: when `search` or `discover` flags one of your filters (for example an industry name no stored value matches), the API's explanation is printed on stderr as `search warning: ...`; stdout stays JSON
- **Encrypted config**: API keys are stored encrypted at rest (Fernet + PBKDF2, machine-tied)
- **Auto-update**: checks PyPI for a newer release and self-updates via Homebrew, GitHub release, git pull, or pip/uv
- **Multiple install methods**: Homebrew, GitHub release, pip/uv (with private index support), or from source

## Installation

### Homebrew

```bash
brew install datalegion-ai/tap/datalegion-cli
```

### From PyPI (or Private Index)

```bash
uv pip install datalegion-cli
```

Or with pip:

```bash
pip install datalegion-cli
```

To install from a private index:

```bash
uv pip install datalegion-cli --extra-index-url https://your-private-index.com/simple
```

### From GitHub Release

Download the `.whl` from the [latest release](https://github.com/datalegion-ai/datalegion-cli/releases/latest) and install:

```bash
uv pip install datalegion_cli-*.whl
```

### From Source

```bash
git clone https://github.com/datalegion-ai/datalegion-cli.git
cd datalegion-cli
uv sync
```

## Configuration

Sign in with your Data Legion account (admin or developer role) and the CLI stores a key for this machine:

```bash
datalegion-cli login                 # opens a sign-in link; confirm the code it shows
datalegion-cli login --team-id 7     # when your account has several teams
datalegion-cli login --no-browser    # headless: prints the link to open on another device
```

The key belongs to this machine, named with a random id (`cli-` plus 8 hex characters) that the CLI generates on first login and keeps in its config, so nothing about the machine (such as its hostname) is sent. Pass `--device <name>` for a readable label instead. Signing in again replaces it, and you can disconnect it from Connected Apps in the dashboard.

Or set an API key yourself (stored encrypted on disk):

```bash
datalegion-cli config set api_key legion_your_key_here
```

Or via environment variable (takes precedence over file config):

```bash
export LEGION_API_KEY=legion_your_key_here
```

### Other Config Options

```bash
# Set the API base URL
datalegion-cli config set api_base_url https://api.datalegion.ai

# Set install method for auto-update (brew, github, git, or pip)
datalegion-cli config set install_method brew

# View all config
datalegion-cli config list

# Show config file path
datalegion-cli config path
```

Config is stored at `~/.datalegion/config.toml`. Override the location with `LEGION_CONFIG_DIR`.

### Install Method Detection

The `update` command auto-detects how the CLI was installed:

| Method | Detection | Update strategy |
|--------|-----------|-----------------|
| `brew` | The running Python is the formula's own venv under Homebrew's Cellar | `brew upgrade` |
| `github` | Set via config | Downloads `.whl` from GitHub release |
| `git` | An editable install from a git checkout (its `direct_url.json`) | `git pull --ff-only` + `uv sync` in that checkout |
| `pip` | Default fallback | `uv pip install --upgrade` |

You can override detection by setting `install_method` in config. For pip installs from a private index, set the `LEGION_PIP_INDEX_URL` environment variable.

## Usage

### Person Enrichment

```bash
# By email
datalegion-cli person enrich --email john@example.com

# By name + company
datalegion-cli person enrich --name "Jane Smith" --company "Acme Corp" --city "NYC"

# By LinkedIn
datalegion-cli person enrich --social-url "https://linkedin.com/in/johndoe"

# Minimum confidence
datalegion-cli person enrich --email john@example.com --min-confidence high

# Select specific fields
datalegion-cli person enrich --email john@example.com --fields "full_name,emails,phones"
```

### Person Search

```bash
# SQL-based search
datalegion-cli person search "SELECT * FROM people WHERE company_name ILIKE '%google%' AND state = 'CA'" --limit 5
```

`query` can also be an Elasticsearch-style query object as JSON (`bool`, `term`, `terms`, `match`, `match_phrase`, `range`, `exists`, `prefix`, `wildcard`, `nested`), on the response's own field names. For deep paging, pass each page's `next_cursor` back with `--cursor`; the last page has none. Company search takes both too.

```bash
datalegion-cli person search '{"bool": {"filter": [{"term": {"company_name": "google"}}, {"match": {"job_title": "engineer"}}]}}' --limit 100
datalegion-cli person search "SELECT * FROM people WHERE state = 'ohio'" --limit 100 --cursor "<next_cursor from the last page>"
```

### Person Discovery (Beta)

```bash
# Natural-language search
datalegion-cli person discover "software engineers in San Francisco who know Rust" --limit 10
```

For the next page, pass the last page's `next_cursor` with `--cursor` and the same query: it reruns the same search. Company discover takes it too.

```bash
query="software engineers in San Francisco who know Rust"
cursor=""
while :; do
  # A failed page (a 429, 402 or 403) prints its error and stops the loop
  page=$(datalegion-cli person discover "$query" --limit 100 ${cursor:+--cursor} ${cursor:+"$cursor"}) || { echo "$page" >&2; break; }
  echo "$page" | jq -r '.matches[].person.legion_id'
  cursor=$(echo "$page" | jq -r '.next_cursor // empty')
  [ -z "$cursor" ] && break
  sleep 6  # Discover answers 10 requests a minute
done
```

### Company Enrichment

```bash
# By domain
datalegion-cli company enrich --domain google.com

# By ticker symbol
datalegion-cli company enrich --ticker AAPL

# By name with industry context
datalegion-cli company enrich --name "Stripe" --industry "Financial Services"
```

### Company Search

```bash
# SQL-based search
datalegion-cli company search "SELECT * FROM companies WHERE industry ILIKE '%software%' AND legion_employee_count > 100"
```

### Company Discovery (Beta)

```bash
# Natural-language search
datalegion-cli company discover "fintech startups in New York with under 50 employees"
```

### Utility Commands

```bash
# Clean and normalize fields
datalegion-cli utility clean '{"email": "John.Doe+tag@gmail.com", "phone": "(555) 123-4567"}'

# Hash an email for privacy-preserving lookups
datalegion-cli utility hash john@example.com

# Validate fields before enrichment
datalegion-cli utility validate --email "test@example.com" --phone "+15551234567"

# Report a data issue on a record (no credit cost; include --correct or --comment)
datalegion-cli utility report person --legion-id abc123 --issue-type outdated \
    --issue-level field --field job_title --observed "CTO" --correct "CEO"
```

### Credits

```bash
# Check balance
datalegion-cli credits balance

# View usage history
datalegion-cli credits usage --from 2026-01-01 --to 2026-03-01
```

### Other Commands

```bash
# Check for updates
datalegion-cli update --check

# Self-update
datalegion-cli update

# Show version
datalegion-cli version
```

## Agent / Automation Usage

The CLI is designed to be called by AI agents and scripts. Key patterns:

```bash
# All output is JSON to stdout; parse it directly
datalegion-cli person enrich --email john@example.com | jq '.matches[0].person.full_name'

# Pipe JSON payloads via stdin
echo '{"email":"john@example.com","company":"Acme"}' | datalegion-cli person enrich --stdin

# Suppress logs with --quiet (only JSON on stdout)
datalegion-cli --quiet person enrich --email john@example.com

# Errors are also JSON
datalegion-cli person enrich --email bad 2>/dev/null
# {"ok": false, "error": "bad_request", "message": "..."}
```

## Sandbox

Try commands without spending credits: `--sandbox` (or `LEGION_SANDBOX=1`, or `datalegion-cli config set sandbox true`) makes enrich, search and discover return sample records with every field a real record has. Utilities, which are free, still call the real API. Sandbox discover answers only a few fixed example queries.

```bash
datalegion-cli --sandbox person enrich --email anyone@example.com
```

## Global Flags

| Flag | Description |
|------|-------------|
| `--verbose` / `-v` | Enable debug logging to stderr |
| `--quiet` / `-q` | Suppress all log output |
| `--sandbox` | Return sample records from enrich, search and discover, using no credits |
| `--help` | Show help for any command |

## Development

```bash
# Install dev dependencies
uv sync

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/

# Build wheel
uv build
```

## License

MIT