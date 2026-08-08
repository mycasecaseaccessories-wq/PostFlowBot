from __future__ import annotations

import pytest

from app.config.settings import ConfigurationError, load_settings


def valid_environment() -> dict[str, str]:
    return {
        "BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
        "API_ID": "12345",
        "API_HASH": "0123456789abcdef0123456789abcdef",
        "TELEGRAM_SESSION": "test-session",
        "ADMIN_USER_IDS": "100, 200,100",
    }


def test_configuration_loading() -> None:
    settings = load_settings(valid_environment(), dotenv_path=None)
    assert settings.api_id == 12345
    assert settings.admin_user_ids == frozenset({100, 200})
    assert settings.database_url.endswith("data/postflow.db")


@pytest.mark.parametrize("missing", ["BOT_TOKEN", "API_ID", "API_HASH", "TELEGRAM_SESSION", "ADMIN_USER_IDS"])
def test_missing_environment_variable(missing: str) -> None:
    environment = valid_environment()
    del environment[missing]
    with pytest.raises(ConfigurationError, match=missing):
        load_settings(environment, dotenv_path=None)


def test_invalid_admin_ids_are_rejected() -> None:
    environment = valid_environment()
    environment["ADMIN_USER_IDS"] = "not-a-number"
    with pytest.raises(ConfigurationError, match="ADMIN_USER_IDS"):
        load_settings(environment, dotenv_path=None)


def test_invalid_api_id_is_rejected() -> None:
    environment = valid_environment()
    environment["API_ID"] = "not-a-number"
    with pytest.raises(ConfigurationError, match="API_ID"):
        load_settings(environment, dotenv_path=None)


def test_invalid_api_hash_is_rejected() -> None:
    environment = valid_environment()
    environment["API_HASH"] = "not-a-hash"
    with pytest.raises(ConfigurationError, match="API_HASH"):
        load_settings(environment, dotenv_path=None)


def test_invalid_bot_token_is_rejected() -> None:
    environment = valid_environment()
    environment["BOT_TOKEN"] = "not-a-token"
    with pytest.raises(ConfigurationError, match="BOT_TOKEN"):
        load_settings(environment, dotenv_path=None)


def test_settings_does_not_expose_secret_values_in_missing_variable_error() -> None:
    environment = valid_environment()
    del environment["BOT_TOKEN"]
    with pytest.raises(ConfigurationError) as error:
        load_settings(environment, dotenv_path=None)
    assert "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk" not in str(error.value)
    assert "BOT_TOKEN" in str(error.value)