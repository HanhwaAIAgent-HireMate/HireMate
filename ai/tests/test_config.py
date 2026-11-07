from pydantic import SecretStr

from hiremate_ai.config import Settings


def test_openai_profile_selects_api_settings_without_overwriting_local_settings() -> None:
    config = Settings(
        _env_file=None,
        llm_profile="openai",
        openai_api_key=SecretStr("example-key"),
        local_llm_model="gemma4:e4b",
        llm_base_url="http://host.docker.internal:11434/v1",
        poster_local_release_ollama=True,
    )
    assert config.llm_model == "gpt-6-luna"
    assert config.llm_base_url == "https://api.openai.com/v1"
    assert config.llm_api_key.get_secret_value() == "example-key"
    assert config.local_llm_model == "gemma4:e4b"
    assert config.llm_temperature is None
    assert config.llm_reasoning_effort == "none"
    assert config.llm_structured_output == "function_calling"
    assert not config.poster_local_release_ollama


def test_local_profile_preserves_openai_key_but_does_not_use_it() -> None:
    config = Settings(
        _env_file=None,
        llm_profile="local",
        local_llm_base_url="http://host.docker.internal:11434/v1",
        openai_api_key=SecretStr("example-key"),
    )
    assert config.llm_model == "gemma4:e4b"
    assert config.llm_base_url == "http://host.docker.internal:11434/v1"
    assert config.llm_api_key.get_secret_value() == "ollama"
    assert config.openai_api_key.get_secret_value() == "example-key"


def test_custom_profile_keeps_existing_llm_settings() -> None:
    config = Settings(_env_file=None, llm_profile="custom", llm_model="existing-model")
    assert config.llm_model == "existing-model"
