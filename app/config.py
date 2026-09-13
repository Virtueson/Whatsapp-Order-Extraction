"""Application settings, loaded from .env.

All paths resolve from the project root, never the working directory, so
the app behaves identically no matter where it is launched from.

Debug:  python -m app.config
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # --- SUMOPOD (OpenAI-compatible) ---
    sumopod_api_key: str
    sumopod_model: str = "gpt-4o-mini"
    sumopod_base_url: str = "https://ai.sumopod.com/v1"

    # --- LLM behaviour ---
    llm_temperature: float = 0.0
    llm_timeout_seconds: int = 30
    # How the model is asked for structured output.
    #   "json_mode"        - provider guarantees valid JSON (works with reasoning models)
    #   "function_calling" - OpenAI tool calling (rejected by some models behind gateways)
    llm_structured_mode: str = "json_mode"

    # --- Guards ---
    max_input_chars: int = 4000

    # --- Logging ---
    log_dir: Path = PROJECT_ROOT / "logs"
    log_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def masked_key(key: str) -> str:
    """Render an API key safe to print. Never show the middle."""
    if not key:
        return "<not set>"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings. Raises a readable error when the key is missing."""
    try:
        return Settings()
    except Exception as exc:  # pragma: no cover - startup path
        raise RuntimeError(
            "Could not load settings. Copy .env.example to .env and set "
            "SUMOPOD_API_KEY.\n"
            f"Original error: {exc}"
        ) from exc


if __name__ == "__main__":
    s = get_settings()
    print("PROJECT_ROOT      :", PROJECT_ROOT)
    print("sumopod_base_url  :", s.sumopod_base_url)
    print("sumopod_model     :", s.sumopod_model)
    print("sumopod_api_key   :", masked_key(s.sumopod_api_key))
    print("llm_temperature   :", s.llm_temperature)
    print("llm_timeout_secs  :", s.llm_timeout_seconds)
    print("structured_mode   :", s.llm_structured_mode)
    print("max_input_chars   :", s.max_input_chars)
    print("log_dir           :", s.log_dir)
    print("log_enabled       :", s.log_enabled)
