from datetime import date
from typing import Any
from unittest.mock import MagicMock

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from hiremate_ai.llm.batch import BatchDispatcher, BatchLlm
from hiremate_ai.llm.batch_state import BatchJob, batch_job
from hiremate_ai.llm.call_log import CallLog
from hiremate_ai.llm.chat import ChatLlm
from hiremate_ai.llm.fake import FakeLlm


def chat(**kwargs: Any) -> ChatLlm:
    model = ChatOpenAI(model="actual-model", api_key=SecretStr("never-cache-this-key"), **kwargs)
    return ChatLlm(model, MagicMock(spec=CallLog), model_name="logging-label", method="json_schema", agent_max_calls=8)


def test_chat_recipe_tracks_actual_configuration_without_credentials() -> None:
    first = chat(temperature=0, base_url="https://user:password@example.com/v1")
    second = chat(temperature=0.7, base_url="https://example.com/v1")

    recipe = first.analysis_recipe()

    assert recipe is not None
    assert recipe != second.analysis_recipe()
    assert "actual-model" in str(recipe)
    assert "logging-label" not in str(recipe)
    assert all(secret not in str(recipe) for secret in ("password", "secret", "never-cache-this-key"))


def test_fake_recipe_is_stable_and_can_be_explicitly_changed() -> None:
    first = FakeLlm()
    assert first.analysis_recipe() == FakeLlm().analysis_recipe()
    assert first.analysis_recipe() != FakeLlm(recipe={"model": "different-fake"}).analysis_recipe()


def test_recipe_invalidates_sampling_and_rejects_unknown_provider_configuration() -> None:
    assert chat(top_p=0.2).analysis_recipe() != chat(top_p=0.9).analysis_recipe()
    assert chat(extra_body={"unknown_provider_setting": "value"}).analysis_recipe() is None
    assert chat(base_url="https://example.com/v1?api-version=one").analysis_recipe() is None


def test_batch_recipe_uses_frozen_job_instead_of_settings() -> None:
    dispatcher = MagicMock(spec=BatchDispatcher)
    dispatcher._model_client = MagicMock()
    llm = BatchLlm(dispatcher, MagicMock(spec=CallLog))
    job = BatchJob("job", 0, 100, date(2026, 10, 27), "frozen-model", "frozen-provider", 500, 0.3, "low")
    with batch_job(job):
        recipe = llm.analysis_recipe()
        assert recipe is not None
        assert recipe["model"] == "frozen-model"
        assert recipe["provider"] == "frozen-provider"
        assert recipe["max_tokens"] == 500
        assert recipe["temperature"] == 0.3
        assert recipe["reasoning_effort"] == "low"
    assert llm.analysis_recipe() is None
