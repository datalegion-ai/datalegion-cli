"""Configuration management — stores API key encrypted in ~/.datalegion/."""

from __future__ import annotations

import base64
import getpass
import hashlib
import os
import platform
import tomllib
from pathlib import Path

import tomli_w
from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

CONFIG_DIR = Path(os.environ.get("LEGION_CONFIG_DIR", Path.home() / ".datalegion"))
CONFIG_FILE = CONFIG_DIR / "config.toml"

_DEFAULTS: dict[str, object] = {
    "api_base_url": "https://api.datalegion.ai",
    "api_key": "",
    "default_output": "json",  # json | table | raw
    "install_method": "",  # brew | github | git | pip
    "device_id": "",  # random name for this machine's login key (see login.new_device_id)
    "sandbox": False,  # sample records, no credits (see client.SANDBOX_PATHS)
}

# Fields that are stored encrypted on disk
_ENCRYPTED_FIELDS = {"api_key"}


# ── Encryption helpers ───────────────────────────────────────────────


def _derive_key() -> bytes:
    """Derive a Fernet key from machine-specific stable inputs.

    Uses PBKDF2 with a salt composed of hostname + username + a fixed
    application-level pepper. This ties the encrypted config to this
    machine and user — the file is unreadable if copied elsewhere.
    """
    identity = f"{platform.node()}:{getpass.getuser()}:datalegion-cli"
    salt = hashlib.sha256(identity.encode()).digest()
    dk = hashlib.pbkdf2_hmac("sha256", identity.encode(), salt, iterations=480_000)
    return base64.urlsafe_b64encode(dk[:32])


def _get_fernet() -> Fernet:
    return Fernet(_derive_key())


def _encrypt(value: str) -> str:
    """Encrypt a plaintext value, returning a base64 token string."""
    return _get_fernet().encrypt(value.encode()).decode()


def _decrypt(token: str) -> str:
    """Decrypt a token back to plaintext. Returns empty string on failure."""
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except (InvalidToken, Exception) as exc:
        logger.warning(
            "Failed to decrypt config value (re-set it with `datalegion-cli config set`): {}",
            exc,
        )
        return ""


# ── Config I/O ───────────────────────────────────────────────────────


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, object]:
    """Load config from disk, decrypting sensitive fields."""
    cfg = dict(_DEFAULTS)
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open("rb") as f:
            raw = tomllib.load(f)
        # Decrypt encrypted fields
        for field in _ENCRYPTED_FIELDS:
            if raw.get(field):
                raw[field] = _decrypt(str(raw[field]))
        cfg.update(raw)
    # Environment overrides (plaintext — user's responsibility)
    if env_key := os.environ.get("LEGION_API_KEY"):
        cfg["api_key"] = env_key
    if env_url := os.environ.get("LEGION_API_URL"):
        cfg["api_base_url"] = env_url
    if env_sandbox := os.environ.get("LEGION_SANDBOX"):
        cfg["sandbox"] = env_sandbox.strip().lower() in ("1", "true", "yes")
    return cfg


def save_config(cfg: dict[str, object]) -> None:
    """Persist config to disk, encrypting sensitive fields."""
    _ensure_dir()
    to_write = dict(cfg)
    for field in _ENCRYPTED_FIELDS:
        if to_write.get(field):
            to_write[field] = _encrypt(str(to_write[field]))
    with CONFIG_FILE.open("wb") as f:
        tomli_w.dump(to_write, f)
    # Restrict file permissions (owner read/write only)
    CONFIG_FILE.chmod(0o600)


# ── Public accessors ─────────────────────────────────────────────────


def get_api_key() -> str:
    """Return the configured API key or raise."""
    # Trimmed: a key from a file or a paste with a trailing newline is otherwise refused by httpx.
    key = str(load_config().get("api_key", "")).strip()
    if not key:
        raise SystemExit(
            "No API key configured. Run `datalegion-cli config set api_key <your-key>` "
            "or set LEGION_API_KEY."
        )
    return key


def get_base_url() -> str:
    return str(load_config().get("api_base_url", _DEFAULTS["api_base_url"]))


def get_sandbox() -> bool:
    """Sandbox mode: the --sandbox flag, LEGION_SANDBOX, or `config set sandbox true`."""
    return load_config().get("sandbox") is True
