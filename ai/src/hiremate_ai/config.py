from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수로 읽는 설정. 기본값은 로컬 개발(저장소 루트의 compose.yaml) 기준이다."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg://hiremate:hiremate@localhost:5432/hiremate"
    redis_url: str = "redis://localhost:6379/0"
    backend_base_url: str = "http://localhost:8080"
    # OpenAI 호환 API 주소와 모델. 모델이 비어 있으면 LLM을 부르지 않는다
    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    # backend는 ai 서버 응답을 60초 기다린다 (hiremate.ai.timeout)
    llm_timeout_seconds: float = 50
    llm_max_retries: int = 2
    # 구조화 출력 방식. 서버가 json_schema를 지원하지 않으면 function_calling이나 json_mode로 바꾼다
    llm_structured_output: Literal["json_schema", "function_calling", "json_mode"] = "json_schema"
    # 도구 루프 Agent가 질문 하나에 모델을 부르는 최대 횟수. 넘으면 답을 내지 못한 것으로 보고 실패한다
    llm_agent_max_calls: int = 8


settings = Settings()
