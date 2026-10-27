"""분석 재사용용 모델 설정. 비밀정보를 제외한 실제 출력 설정만 허용한다."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def analysis_recipe(llm: object) -> dict[str, Any] | None:
    """미지원 클라이언트는 추정하지 않는다. None이면 저장 결과 재사용을 생략한다."""
    method = getattr(llm, "analysis_recipe", None)
    result = method() if callable(method) else None
    return result if isinstance(result, dict) and result else None


def model_recipe(model: BaseChatModel, *, method: str) -> dict[str, Any] | None:
    if not isinstance(model, ChatOpenAI):
        return None
    if model.default_query or model.default_headers or model.disabled_params:
        return None
    reasoning_options = model.reasoning or {}
    if not isinstance(reasoning_options, dict) or set(reasoning_options) - {"effort", "summary"}:
        return None
    if not all(value is None or isinstance(value, str) for value in reasoning_options.values()):
        return None
    # 임의 provider 본문과 임의 kwargs는 의미와 비밀 여부를 알 수 없어 재사용하지 않는다.
    kwargs = model.model_kwargs
    allowed = {"top_p", "seed", "presence_penalty", "frequency_penalty", "stop", "logit_bias", "verbosity"}
    if set(kwargs) - allowed:
        return None
    extra = model.extra_body or {}
    if not isinstance(extra, Mapping) or set(extra) - {"provider", "reasoning"}:
        return None
    provider = extra.get("provider", {})
    reasoning = extra.get("reasoning", {})
    if not isinstance(provider, dict) or set(provider) - {"only"}:
        return None
    if not isinstance(reasoning, dict) or set(reasoning) - {"effort"}:
        return None
    only = provider.get("only", [])
    effort = reasoning.get("effort")
    if not isinstance(only, list) or not all(isinstance(name, str) for name in only):
        return None
    if effort is not None and not isinstance(effort, str):
        return None
    endpoint = urlsplit(model.openai_api_base or "https://api.openai.com/v1")
    if endpoint.query or endpoint.fragment:
        return None
    host = endpoint.hostname or ""
    if endpoint.port is not None:
        host += f":{endpoint.port}"
    return {
        "implementation": "chat-v1",
        "model": model.model_name,
        "endpoint": urlunsplit((endpoint.scheme, host, endpoint.path, "", "")),
        "method": method,
        "temperature": model.temperature,
        "max_tokens": model.max_tokens,
        "reasoning_effort": model.reasoning_effort,
        "provider": only,
        "extra_reasoning_effort": effort,
        "n": model.n,
        "top_p": model.top_p,
        "seed": model.seed,
        "presence_penalty": model.presence_penalty,
        "frequency_penalty": model.frequency_penalty,
        "stop": model.stop,
        "logit_bias": model.logit_bias,
        "service_tier": model.service_tier,
        "verbosity": model.verbosity,
        "reasoning": reasoning_options,
        "truncation": model.truncation,
        "use_responses_api": model.use_responses_api,
        "output_version": model.output_version,
        "kwargs": kwargs,
    }
