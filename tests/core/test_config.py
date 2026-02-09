"""Tests for Configuration management (dcaf.core.config)."""

import os

from dcaf.core.config import (
    DEFAULTS,
    PROVIDER_MODEL_DEFAULTS,
    get_env,
    get_model_from_env,
    get_provider_from_env,
    is_provider_configured,
    load_agent_config,
)

# =============================================================================
# DEFAULTS Tests
# =============================================================================


class TestDefaults:
    def test_defaults_has_required_keys(self):
        required = ["provider", "model", "framework", "temperature", "max_tokens", "aws_region"]
        for key in required:
            assert key in DEFAULTS, f"Missing default: {key}"

    def test_default_provider_is_bedrock(self):
        assert DEFAULTS["provider"] == "bedrock"

    def test_default_framework_is_agno(self):
        assert DEFAULTS["framework"] == "agno"

    def test_default_temperature_is_float(self):
        assert isinstance(DEFAULTS["temperature"], float)
        assert 0.0 <= DEFAULTS["temperature"] <= 1.0

    def test_default_max_tokens_is_positive(self):
        assert isinstance(DEFAULTS["max_tokens"], int)
        assert DEFAULTS["max_tokens"] > 0

    def test_provider_model_defaults_has_all_providers(self):
        expected_providers = ["bedrock", "anthropic", "google", "openai", "azure", "ollama"]
        for provider in expected_providers:
            assert provider in PROVIDER_MODEL_DEFAULTS, (
                f"Missing provider model default: {provider}"
            )


# =============================================================================
# get_env Tests
# =============================================================================


class TestGetEnv:
    def test_returns_default_when_not_set(self, monkeypatch):
        monkeypatch.delenv("TEST_DCAF_VAR", raising=False)
        assert get_env("TEST_DCAF_VAR", "default") == "default"

    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("TEST_DCAF_VAR", "hello")
        assert get_env("TEST_DCAF_VAR") == "hello"

    def test_cast_bool_true(self, monkeypatch):
        for val in ("true", "1", "yes", "on"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert get_env("TEST_BOOL", cast=bool) is True

    def test_cast_bool_false(self, monkeypatch):
        for val in ("false", "0", "no", "off"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert get_env("TEST_BOOL", cast=bool) is False

    def test_cast_int(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "42")
        assert get_env("TEST_INT", cast=int) == 42

    def test_cast_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "0.5")
        assert get_env("TEST_FLOAT", cast=float) == 0.5

    def test_cast_int_invalid_returns_default(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "not_a_number")
        assert get_env("TEST_INT", default=99, cast=int) == 99

    def test_returns_none_when_not_set_and_no_default(self, monkeypatch):
        monkeypatch.delenv("TEST_DCAF_VAR", raising=False)
        assert get_env("TEST_DCAF_VAR") is None


# =============================================================================
# load_agent_config Tests
# =============================================================================


class TestLoadAgentConfig:
    def test_loads_defaults_with_no_env(self, monkeypatch):
        # Clear all DCAF env vars
        for key in list(os.environ.keys()):
            if key.startswith("DCAF_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv("AWS_PROFILE", raising=False)
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)

        config = load_agent_config()
        assert config["provider"] == DEFAULTS["provider"]
        assert config["framework"] == DEFAULTS["framework"]

    def test_override_provider(self, monkeypatch):
        monkeypatch.delenv("DCAF_PROVIDER", raising=False)
        monkeypatch.delenv("DCAF_MODEL", raising=False)
        config = load_agent_config(provider="google")
        assert config["provider"] == "google"

    def test_override_model(self, monkeypatch):
        monkeypatch.delenv("DCAF_MODEL", raising=False)
        config = load_agent_config(model="custom-model")
        assert config["model"] == "custom-model"

    def test_env_var_provider(self, monkeypatch):
        monkeypatch.setenv("DCAF_PROVIDER", "anthropic")
        monkeypatch.delenv("DCAF_MODEL", raising=False)
        config = load_agent_config()
        assert config["provider"] == "anthropic"

    def test_env_var_temperature(self, monkeypatch):
        monkeypatch.setenv("DCAF_TEMPERATURE", "0.5")
        config = load_agent_config()
        assert config["temperature"] == 0.5

    def test_keyword_overrides(self, monkeypatch):
        monkeypatch.delenv("DCAF_PROVIDER", raising=False)
        config = load_agent_config(custom_field="custom_value")
        assert config["custom_field"] == "custom_value"


# =============================================================================
# get_provider_from_env / get_model_from_env
# =============================================================================


class TestProviderModelHelpers:
    def test_get_provider_from_env_default(self, monkeypatch):
        monkeypatch.delenv("DCAF_PROVIDER", raising=False)
        assert get_provider_from_env() == DEFAULTS["provider"]

    def test_get_provider_from_env_set(self, monkeypatch):
        monkeypatch.setenv("DCAF_PROVIDER", "openai")
        assert get_provider_from_env() == "openai"

    def test_get_model_from_env_default(self, monkeypatch):
        monkeypatch.delenv("DCAF_MODEL", raising=False)
        monkeypatch.delenv("DCAF_PROVIDER", raising=False)
        result = get_model_from_env()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_model_from_env_provider_specific(self, monkeypatch):
        monkeypatch.delenv("DCAF_MODEL", raising=False)
        result = get_model_from_env(provider="google")
        assert result == PROVIDER_MODEL_DEFAULTS["google"]


# =============================================================================
# is_provider_configured
# =============================================================================


class TestIsProviderConfigured:
    def test_bedrock_with_profile(self, monkeypatch):
        monkeypatch.setenv("AWS_PROFILE", "test-profile")
        assert is_provider_configured("bedrock") is True

    def test_bedrock_without_credentials(self, monkeypatch):
        monkeypatch.delenv("AWS_PROFILE", raising=False)
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        assert is_provider_configured("bedrock") is False

    def test_google_always_configured(self):
        # Google uses ADC, always returns True
        assert is_provider_configured("google") is True

    def test_ollama_always_configured(self):
        assert is_provider_configured("ollama") is True

    def test_unknown_provider(self):
        assert is_provider_configured("unknown_provider") is False
