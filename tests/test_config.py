from app.config import PROJECT_ROOT, Settings, masked_key


def _settings(**overrides) -> Settings:
    """Build Settings without reading the developer's real .env file."""
    base = {"sumopod_api_key": "test-key-123"}
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_project_root_contains_app_package():
    assert (PROJECT_ROOT / "app").is_dir()


def test_defaults_are_applied():
    s = _settings()
    assert s.sumopod_base_url == "https://ai.sumopod.com/v1"
    assert s.llm_temperature == 0.0
    assert s.llm_timeout_seconds == 30
    assert s.max_input_chars == 4000
    assert s.log_enabled is True
    assert s.llm_structured_mode == "json_mode"


def test_log_dir_is_absolute_and_under_project_root():
    s = _settings()
    assert s.log_dir.is_absolute()
    assert s.log_dir == PROJECT_ROOT / "logs"


def test_overrides_win_over_defaults():
    s = _settings(sumopod_model="my-model", max_input_chars=50)
    assert s.sumopod_model == "my-model"
    assert s.max_input_chars == 50


def test_masked_key_hides_the_middle():
    assert masked_key("sk-abcdefghijklmnop") == "sk-a...mnop"


def test_masked_key_handles_short_and_empty():
    assert masked_key("") == "<not set>"
    assert masked_key("abc") == "***"
