"""Unit tests for OryxGate configuration schema and environment loading."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings, get_settings


@pytest.fixture
def valid_config_dict() -> dict[str, str]:
    """Provide a complete dictionary of valid configuration settings."""
    return {
        "GATEWAY_API_TOKENS": "test_gw_tok_1, test_gw_tok_2",
        "ADMIN_API_TOKENS": "test_admin_tok_1",
        "IF_API_KEY": "if_api_secret_key_12345",
        "IF_ORGANIZATION_ID": "e9b25123-0000-0000-0000-000000000000",
        "CC_API_KEY": "cc_api_secret_key_67890",
        "CC_API_BASE_URL": "https://crew.qatarairwaysvirtual.com/api/",
        "DB_HOST": "127.0.0.1",
        "DB_USER": "test_user",
        "DB_PASSWORD": "super_secret_db_password",
        "DB_NAME": "test_db",
    }


def test_settings_load_successfully(valid_config_dict: dict[str, str]) -> None:
    """Verify that settings instantiate and parse correctly with valid inputs."""
    settings = Settings(**valid_config_dict, _env_file=None)

    assert len(settings.gateway_api_tokens) == 2
    assert isinstance(settings.gateway_api_tokens[0], SecretStr)
    assert settings.gateway_api_tokens[0].get_secret_value() == "test_gw_tok_1"
    assert settings.gateway_api_tokens[1].get_secret_value() == "test_gw_tok_2"

    assert len(settings.admin_api_tokens) == 1
    assert settings.admin_api_tokens[0].get_secret_value() == "test_admin_tok_1"

    assert settings.if_api_key.get_secret_value() == "if_api_secret_key_12345"
    assert settings.if_organization_id == "e9b25123-0000-0000-0000-000000000000"
    assert settings.cc_api_key.get_secret_value() == "cc_api_secret_key_67890"

    # Trailing slash must be stripped
    assert settings.cc_api_base_url == "https://crew.qatarairwaysvirtual.com/api"

    assert settings.db_host == "127.0.0.1"
    assert settings.db_port == 3306
    assert settings.db_user == "test_user"
    assert settings.db_password.get_secret_value() == "super_secret_db_password"
    assert settings.db_name == "test_db"
    assert settings.environment == "development"
    assert settings.debug is False


def test_settings_load_from_environment(valid_config_dict: dict[str, str]) -> None:
    """Verify that settings are loaded from environment variables."""
    with patch.dict(os.environ, valid_config_dict, clear=True):
        settings = Settings(_env_file=None)
        assert settings.db_host == "127.0.0.1"
        assert settings.if_organization_id == "e9b25123-0000-0000-0000-000000000000"
        assert len(settings.gateway_api_tokens) == 2


def test_settings_load_from_env_file(tmp_path: Path, valid_config_dict: dict[str, str]) -> None:
    """Verify that settings load correctly from a .env file."""
    env_file = tmp_path / ".env.test"
    content = "\n".join(f"{k}={v}" for k, v in valid_config_dict.items())
    env_file.write_text(content, encoding="utf-8")

    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=str(env_file))
        assert settings.db_name == "test_db"
        assert settings.db_user == "test_user"
        assert settings.cc_api_key.get_secret_value() == "cc_api_secret_key_67890"


def test_secret_fields_masked_in_string_representations(
    valid_config_dict: dict[str, str],
) -> None:
    """AC: Secret fields are masked in string representations and logs."""
    settings = Settings(**valid_config_dict, _env_file=None)

    # Individual secret string assertions
    raw_secrets = [
        "test_gw_tok_1",
        "test_gw_tok_2",
        "test_admin_tok_1",
        "if_api_secret_key_12345",
        "cc_api_secret_key_67890",
        "super_secret_db_password",
    ]

    for secret in raw_secrets:
        assert secret not in str(settings.if_api_key)
        assert secret not in repr(settings.if_api_key)
        assert secret not in str(settings.cc_api_key)
        assert secret not in repr(settings.cc_api_key)
        assert secret not in str(settings.db_password)
        assert secret not in repr(settings.db_password)

    # Whole settings object string and repr representations must never leak raw secrets
    settings_repr = repr(settings)
    settings_str = str(settings)

    for secret in raw_secrets:
        assert secret not in settings_repr, f"Secret {secret} leaked in repr(settings)"
        assert secret not in settings_str, f"Secret {secret} leaked in str(settings)"


def test_missing_mandatory_settings_raise_validation_error() -> None:
    """AC: Missing mandatory settings raise descriptive validation errors on startup."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)

        errors = exc_info.value.errors()
        error_fields = {str(err["loc"][0]).upper() for err in errors}

        expected_mandatory = {
            "GATEWAY_API_TOKENS",
            "ADMIN_API_TOKENS",
            "IF_API_KEY",
            "IF_ORGANIZATION_ID",
            "CC_API_KEY",
            "CC_API_BASE_URL",
            "DB_HOST",
            "DB_USER",
            "DB_PASSWORD",
            "DB_NAME",
        }

        assert expected_mandatory.issubset(error_fields), (
            f"Expected missing fields {expected_mandatory - error_fields}"
        )


def test_token_parsing_json_format(valid_config_dict: dict[str, str]) -> None:
    """Verify that JSON array strings are properly parsed for token lists."""
    valid_config_dict["GATEWAY_API_TOKENS"] = '["tok_json_1", "tok_json_2"]'
    valid_config_dict["ADMIN_API_TOKENS"] = '["admin_json_1"]'

    settings = Settings(**valid_config_dict, _env_file=None)
    assert [t.get_secret_value() for t in settings.gateway_api_tokens] == [
        "tok_json_1",
        "tok_json_2",
    ]
    assert [t.get_secret_value() for t in settings.admin_api_tokens] == ["admin_json_1"]


@pytest.mark.parametrize(
    "malformed_tokens",
    [
        '["tok1", "tok2"',  # unclosed bracket
        '["tok1",]',  # trailing comma
        '["tok1" "tok2"]',  # missing delimiter
        '{"key": "value"}',  # object instead of array
        "[malformed_unquoted_string]",  # invalid JSON syntax
    ],
)
def test_malformed_json_tokens_raises_validation_error(
    valid_config_dict: dict[str, str], malformed_tokens: str
) -> None:
    """Verify that malformed bracketed JSON token lists fail fast rather than falling back to comma-split."""
    valid_config_dict["GATEWAY_API_TOKENS"] = malformed_tokens
    with pytest.raises(ValidationError) as exc_info:
        Settings(**valid_config_dict, _env_file=None)
    assert "GATEWAY_API_TOKENS" in str(exc_info.value).upper()


@pytest.mark.parametrize(
    "malformed_template",
    [
        '["{secret}",]',  # trailing comma
        '["{secret}"',  # unclosed bracket
        '"{secret}"]',  # missing opening bracket
        '{{"tok": "{secret}"}}',  # object with secret
    ],
)
def test_malformed_json_tokens_omits_raw_secrets_in_validation_error(
    valid_config_dict: dict[str, str], malformed_template: str
) -> None:
    """Verify that malformed token parsing errors do not leak credential values in ValidationError."""
    secret_marker = "super_confidential_raw_bearer_token_xyz"
    valid_config_dict["GATEWAY_API_TOKENS"] = malformed_template.format(secret=secret_marker)

    with pytest.raises(ValidationError) as exc_info:
        Settings(**valid_config_dict, _env_file=None)

    error_str = str(exc_info.value)
    error_repr = repr(exc_info.value)
    assert secret_marker not in error_str, f"Secret leaked in error string: {error_str}"
    assert secret_marker not in error_repr, f"Secret leaked in error repr: {error_repr}"


def test_empty_gateway_tokens_raises_validation_error(
    valid_config_dict: dict[str, str],
) -> None:
    """Verify that providing empty or whitespace-only gateway tokens raises validation error."""
    valid_config_dict["GATEWAY_API_TOKENS"] = ""
    with pytest.raises(ValidationError) as exc_info:
        Settings(**valid_config_dict, _env_file=None)
    assert "GATEWAY_API_TOKENS" in str(exc_info.value).upper()


def test_invalid_url_raises_validation_error(valid_config_dict: dict[str, str]) -> None:
    """Verify that malformed CC_API_BASE_URL raises validation error."""
    valid_config_dict["CC_API_BASE_URL"] = "not-a-valid-url"
    with pytest.raises(ValidationError) as exc_info:
        Settings(**valid_config_dict, _env_file=None)
    assert "CC_API_BASE_URL" in str(exc_info.value).upper()


def test_case_insensitive_attribute_access(valid_config_dict: dict[str, str]) -> None:
    """Verify that settings attributes are accessible in both uppercase and lowercase."""
    settings = Settings(**valid_config_dict, _env_file=None)

    assert settings.DB_HOST == settings.db_host == "127.0.0.1"
    assert settings.if_organization_id == settings.IF_ORGANIZATION_ID
    assert settings.cc_api_base_url == settings.CC_API_BASE_URL
    assert settings.gateway_api_tokens == settings.GATEWAY_API_TOKENS
    assert settings.admin_api_tokens == settings.ADMIN_API_TOKENS


def test_raw_token_helpers(valid_config_dict: dict[str, str]) -> None:
    """Verify raw token helper properties return unmasked string sets/lists."""
    settings = Settings(**valid_config_dict, _env_file=None)

    assert settings.raw_gateway_api_tokens == ["test_gw_tok_1", "test_gw_tok_2"]
    assert settings.raw_admin_api_tokens == ["test_admin_tok_1"]


def test_get_settings_caching(valid_config_dict: dict[str, str]) -> None:
    """Verify get_settings returns a cached instance and clears properly."""
    with patch.dict(os.environ, valid_config_dict, clear=True):
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

        get_settings.cache_clear()
        s3 = get_settings()
        assert s3 is not s1
        get_settings.cache_clear()
