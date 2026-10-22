"""Tests for config management — encryption, load/save, env overrides."""

from __future__ import annotations

import pytest


class TestConfigEncryption:
    """API key encryption round-trip."""

    def test_encrypt_decrypt_round_trip(self, tmp_config_dir):
        from datalegion_cli.config import _decrypt, _encrypt

        original = "legion_abc123secret"
        token = _encrypt(original)
        assert token != original  # must be different on disk
        assert _decrypt(token) == original

    def test_decrypt_invalid_token_returns_empty(self, tmp_config_dir):
        from datalegion_cli.config import _decrypt

        assert _decrypt("not-a-valid-fernet-token") == ""

    def test_decrypt_empty_string_returns_empty(self, tmp_config_dir):
        from datalegion_cli.config import _decrypt

        assert _decrypt("") == ""


class TestSaveAndLoad:
    """Config persistence with encryption."""

    def test_save_encrypts_api_key_on_disk(self, tmp_config_dir):
        from datalegion_cli.config import CONFIG_FILE, save_config

        save_config({"api_key": "legion_mysecretkey", "api_base_url": "https://test.local"})

        raw = CONFIG_FILE.read_text()
        assert "legion_mysecretkey" not in raw  # must not appear in plaintext
        assert "gAAAAA" in raw  # Fernet token prefix

    def test_load_decrypts_api_key(self, tmp_config_dir, monkeypatch):
        from datalegion_cli.config import load_config, save_config

        # Clear env override so file value is used
        monkeypatch.delenv("LEGION_API_KEY", raising=False)

        save_config({"api_key": "legion_roundtrip", "api_base_url": "https://test.local"})
        cfg = load_config()
        assert cfg["api_key"] == "legion_roundtrip"

    def test_api_key_is_trimmed(self, tmp_config_dir, monkeypatch):
        from datalegion_cli.config import get_api_key, save_config

        monkeypatch.setenv("LEGION_API_KEY", "legion_fromenv\n")
        assert get_api_key() == "legion_fromenv"
        monkeypatch.delenv("LEGION_API_KEY")
        save_config({"api_key": "  legion_fromfile  "})
        assert get_api_key() == "legion_fromfile"

    def test_whitespace_only_api_key_is_missing(self, tmp_config_dir, monkeypatch):
        from datalegion_cli.config import get_api_key

        monkeypatch.setenv("LEGION_API_KEY", " \n")
        with pytest.raises(SystemExit):
            get_api_key()

    def test_save_sets_file_permissions_600(self, tmp_config_dir):
        from datalegion_cli.config import CONFIG_FILE, save_config

        save_config({"api_key": "legion_permtest"})
        mode = CONFIG_FILE.stat().st_mode & 0o777
        assert mode == 0o600

    def test_save_and_load_non_sensitive_fields(self, tmp_config_dir, monkeypatch):
        from datalegion_cli.config import load_config, save_config

        monkeypatch.delenv("LEGION_API_KEY", raising=False)
        monkeypatch.delenv("LEGION_API_URL", raising=False)

        save_config(
            {
                "api_key": "legion_test",
                "api_base_url": "https://custom.api",
            }
        )
        cfg = load_config()
        assert cfg["api_base_url"] == "https://custom.api"

    def test_load_returns_defaults_when_no_file(self, tmp_config_dir, monkeypatch):
        from datalegion_cli.config import load_config

        monkeypatch.delenv("LEGION_API_KEY", raising=False)
        monkeypatch.delenv("LEGION_API_URL", raising=False)

        cfg = load_config()
        assert cfg["api_base_url"] == "https://api.datalegion.ai"
        assert cfg["api_key"] == ""


class TestEnvOverrides:
    """Environment variables take precedence over file config."""

    def test_env_api_key_overrides_file(self, tmp_config_dir, monkeypatch):
        from datalegion_cli.config import load_config, save_config

        save_config({"api_key": "legion_fromfile"})
        monkeypatch.setenv("LEGION_API_KEY", "legion_fromenv")

        cfg = load_config()
        assert cfg["api_key"] == "legion_fromenv"

    def test_env_api_url_overrides_file(self, tmp_config_dir, monkeypatch):
        from datalegion_cli.config import load_config, save_config

        save_config({"api_base_url": "https://file.local"})
        monkeypatch.setenv("LEGION_API_URL", "https://env.local")

        cfg = load_config()
        assert cfg["api_base_url"] == "https://env.local"


class TestAccessors:
    """get_api_key, get_base_url."""

    def test_get_api_key_raises_when_empty(self, tmp_config_dir, monkeypatch):
        monkeypatch.delenv("LEGION_API_KEY", raising=False)
        from datalegion_cli.config import get_api_key

        with pytest.raises(SystemExit):
            get_api_key()

    def test_get_api_key_returns_key(self, tmp_config_dir, monkeypatch):
        monkeypatch.setenv("LEGION_API_KEY", "legion_test123")
        from datalegion_cli.config import get_api_key

        assert get_api_key() == "legion_test123"

    def test_get_base_url_default(self, tmp_config_dir, monkeypatch):
        monkeypatch.delenv("LEGION_API_URL", raising=False)
        from datalegion_cli.config import get_base_url

        assert get_base_url() == "https://api.datalegion.ai"
