"""Tests for the appearance.theme (light/dark/system) setting."""

import pytest

from src.core.repositories.credentials import CredentialsRepository
from src.core.repositories.settings import SettingsRepository
from src.models.config import SETTING_DEFINITIONS, ConfigCategory
from src.services.settings import SettingsService


def test_appearance_theme_definition_exists():
    """appearance.theme is registered with the expected shape."""
    definition = SETTING_DEFINITIONS.get("appearance.theme")
    assert definition is not None

    assert definition.category == ConfigCategory.APPEARANCE
    assert definition.default_value == "system"
    assert definition.options == ["system", "light", "dark"]
    assert definition.option_labels == ["System", "Light", "Dark"]
    assert definition.ui_widget == "select"


def test_option_labels_match_options_length():
    """Every definition that sets option_labels has one label per option.

    Guards against future drift where someone adds an option without
    updating its label (or vice versa) - the UI silently falls back to
    the raw value for the missing label, so this is easy to miss.
    """
    for key, definition in SETTING_DEFINITIONS.items():
        if definition.option_labels is not None:
            assert definition.options is not None, f"{key} has option_labels but no options"
            assert len(definition.option_labels) == len(
                definition.options
            ), f"{key}: option_labels length does not match options length"


@pytest.fixture
def settings_service(temp_env, clean_temp_db) -> SettingsService:
    settings_repo = SettingsRepository(clean_temp_db)
    credentials_repo = CredentialsRepository(clean_temp_db)
    return SettingsService(settings_repo, credentials_repo)


def test_validate_and_set_accepts_valid_theme(settings_service):
    result = settings_service.validate_and_set("appearance.theme", "light")
    assert result["valid"] is True
    assert result["errors"] == []
    assert settings_service.settings_repo.get("appearance.theme") == "light"


def test_validate_and_set_rejects_invalid_theme(settings_service):
    result = settings_service.validate_and_set("appearance.theme", "neon")
    assert result["valid"] is False
    assert any("must be one of" in e.lower() for e in result["errors"])
    # Nothing should have been written.
    assert settings_service.settings_repo.get("appearance.theme") is None


def test_appearance_category_default(settings_service):
    """With nothing set, the category listing falls back to the default."""
    from src.models.config import get_settings_by_category

    definitions = get_settings_by_category(ConfigCategory.APPEARANCE)
    assert "appearance.theme" in definitions
    assert settings_service.settings_repo.get("appearance.theme") is None
    assert definitions["appearance.theme"].default_value == "system"
