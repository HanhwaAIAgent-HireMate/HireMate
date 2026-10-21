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
    # 호출 한 번에 모델이 쓰는 최대 토큰. 모델이 끝없이 쓰다 시간을 다 쓰는 것을 막는다
    llm_max_tokens: int = 2048
    # 0이면 같은 질문에 같은 답을 낸다. Root의 지원자 찾기는 같은 질문에 같은 후보가 나와야 한다
    llm_temperature: float = 0
    # 참이면 tests/eval의 실제 모델 평가를 돌린다. CI와 커밋 전 검사에서는 끈다
    llm_eval: bool = False
    # Root Agent 대화방에 남기는 최근 턴 수
    root_memory_turns: int = 20
    # 공공데이터포털 인증키. scripts/ncs_download.py로 NCS 자료를 받을 때만 쓰고, ai 서버는 실행 중에 쓰지 않는다
    ncs_api_key: SecretStr = SecretStr("")


settings = Settings()
