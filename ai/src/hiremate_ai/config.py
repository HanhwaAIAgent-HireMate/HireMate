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
    # Application Agent: 지원 접수 분석 한 번의 시간 한도. AI 워커가 대기열에서 꺼내 돌리므로 backend는 기다리지 않는다
    application_timeout_seconds: float = 170
    # 카드를 열 때 저장된 결과가 없어 새로 분석하면 backend 기본 60초 안에 끝내야 한다
    application_card_timeout_seconds: float = 50
    # 동시에 부르는 모델 호출 수 (문서별 추출, 우대사항별 판정)
    application_concurrency: int = 4
    # 제출 문서 본문이 이 글자 수 이하면 판정에 원문 전체를 넣고, 넘으면 조건과 맞닿은 문장만 넣는다
    application_full_text_chars: int = 8000
    # AI 워커: backend job 모듈이 작업을 넣는 Redis 스트림과 결과를 돌려주는 스트림 (hiremate.jobs.*와 같은 이름)
    worker_job_stream: str = "hiremate:jobs"
    worker_result_stream: str = "hiremate:job-results"
    worker_group: str = "ai-worker"
    # 동시에 처리하는 작업 수. 요청을 하나씩 처리하는 로컬 모델(llama.cpp -np 1)은 1, vLLM은 모델 용량에 맞춘다
    worker_concurrency: int = 1
    # 작업 하나를 처리하는 시도 횟수. 모두 실패하면 FAILED 결과를 보내고 담당자가 다시 요청한다
    worker_attempts: int = 2
    # 작업을 가진 워커가 이 시간 동안 소식이 없으면(멈췄으면) 다른 워커가 가져간다. 처리 중에는 주기적으로 알린다
    worker_claim_idle_seconds: float = 120


settings = Settings()
