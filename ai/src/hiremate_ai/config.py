from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수로 읽는 설정. 기본값은 로컬 개발(저장소 루트의 compose.yaml) 기준이다."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # custom은 기존 LLM_* 설정을 그대로 사용한다. local/openai는 각각 별도 설정을 선택한다.
    llm_profile: Literal["custom", "local", "openai"] = "custom"
    local_llm_base_url: str = "http://127.0.0.1:11434/v1"
    local_llm_model: str = "gemma4:e4b"
    local_llm_api_key: SecretStr = SecretStr("ollama")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-6-luna"
    openai_api_key: SecretStr = SecretStr("")

    database_url: str = "postgresql+psycopg://hiremate:hiremate@localhost:5432/hiremate"
    redis_url: str = "redis://localhost:6379/0"
    backend_base_url: str = "http://localhost:8080"
    # OpenAI 호환 API 주소와 모델. 모델이 비어 있으면 LLM을 부르지 않는다
    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    # 문서 정제 전용 OpenAI 키. 비어 있고 공통 주소가 OpenAI면 공통 키를 사용한다.
    document_normalization_api_key: SecretStr = SecretStr("")
    # 모델 호출 한 번을 기다리는 시간. Root Chat은 전체 시간 제한이 없어 이 값과 도구 호출 상한이 끝을 정한다.
    # 다른 Agent의 동기 호출은 backend가 60초 기다린다 (hiremate.ai.timeout)
    llm_timeout_seconds: float = 50
    llm_max_retries: int = 2
    # 구조화 출력 방식. 서버가 json_schema를 지원하지 않으면 function_calling이나 json_mode로 바꾼다
    llm_structured_output: Literal["json_schema", "function_calling", "json_mode"] = "json_schema"
    # 도구 루프 Agent가 질문 하나에 모델을 부르는 최대 횟수. 넘으면 답을 내지 못한 것으로 보고 실패한다
    llm_agent_max_calls: int = 8
    # Report Agent의 상한. 백그라운드 작업이고 스킬 · 자료 · 근거를 읽은 뒤 검사에 걸리면 두 번까지 고쳐 쓴다
    llm_report_max_calls: int = 18
    # 호출 한 번에 모델이 쓰는 최대 토큰. 모델이 끝없이 쓰다 시간을 다 쓰는 것을 막는다.
    # 긴 자기소개서(1만 자 이상)의 문장 분석은 경험 목록이 길어 2048에서 답이 잘렸다
    llm_max_tokens: int = 16384
    # 0이면 같은 질문에 같은 답을 낸다. Root의 지원자 찾기는 같은 질문에 같은 후보가 나와야 한다.
    # none이면 temperature를 보내지 않는다 (temperature를 받지 않는 모델용). 비우면 기본값 0이다
    llm_temperature: float | None = 0
    # 추론형 로컬 모델이 JSON을 쓰기 전에 출력 한도를 다 쓰면 none으로 끈다. 비우면 서버 기본값을 쓴다.
    llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None
    # OpenRouter 전용. 요청을 처리할 업체를 쉼표로 적은 업체로만 보낸다 (예: baidu,coreweave).
    # 같은 모델도 업체마다 구조화 출력을 다르게 처리해 형식이 깨지는 곳이 있다. 비우면 OpenRouter가 고른다
    llm_providers: str = ""
    # 참이면 tests/eval의 실제 모델 평가를 돌린다. CI와 커밋 전 검사에서는 끈다
    llm_eval: bool = False
    # 선택적 포스터 디자인 참고 색인. 로컬 테스트 자료는 Git에서 제외한다.
    poster_references_path: str = ""
    poster_reference_images_path: str = ""
    # 키는 포스터 텍스트 설계에만 쓴다. 이전 키 이름도 읽어 기존 로컬 설정을 호환한다.
    poster_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("POSTER_API_KEY", "POSTER_IMAGE_API_KEY")
    )
    poster_llm_model: str = ""
    # 이미지 생성은 별도 로컬 Python 환경에서 실행한다. 비우면 배너 없이 디자인만 만든다.
    poster_local_model_path: str = ""
    poster_local_python: str = ""
    poster_local_image_cache: str = ".local/poster-images"
    poster_local_image_timeout: float = Field(default=300, gt=0, le=600)
    # 단일 GPU에서 Gemma 설계가 끝나면 가중치를 내리고 이미지 모델을 적재한다.
    poster_local_release_ollama: bool = False
    # 참이면 모델을 부르는 요청 · 작업을 LangSmith에 기록한다. 지시와 자료(지원 문서 본문 포함)가 외부 서버로 나가므로
    # 가상 지원자로 개발 · 평가할 때만 켠다. 단위 테스트는 켜 두어도 보내지 않는다 (tests/conftest.py)
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr = SecretStr("")
    # 기록을 모아 볼 LangSmith 프로젝트. 없으면 첫 기록 때 만들어진다
    langsmith_project: str = "hiremate"
    # Root Agent 대화방에 남기는 최근 턴 수
    root_memory_turns: int = 20
    # Application Agent: 지원 접수 분석 한 번의 시간 한도(정책 1000초). AI 워커가 대기열에서 꺼내 돌리므로
    # backend는 기다리지 않는다. 재확인은 남은 시간 안에서만 하고 다시 시도해도 한도를 새로 세지 않는다
    application_timeout_seconds: float = 1000
    # AI 워커의 모델 호출 한 번 시간 한도. 워커 작업은 화면이 기다리지 않는다. 1만 자가 넘는 자기소개서는 문장 분석
    # 답이 길어 LLM_TIMEOUT_SECONDS(50초, 화면이 기다리는 호출 기준)를 넘기도 했다. 작업의 전체 한도 안에서만 쓴다
    worker_llm_timeout_seconds: float = 500
    # 워커의 지원서 분석만 OpenRouter Batch로 실행한다. Chat과 다른 작업은 기존 LLM 설정을 쓴다.
    application_batch_enabled: bool = False
    application_batch_model: str = "deepseek/deepseek-v4.1-flash"
    application_batch_provider: str = "sail-research"
    application_batch_collection_seconds: float = Field(default=5, ge=0)
    application_batch_max_requests: int = Field(default=32, ge=1)
    application_batch_poll_seconds: float = Field(default=60, gt=0)
    application_batch_http_timeout_seconds: float = Field(default=30, gt=0)
    # 여러 의존 단계를 합친 중단 한도다. 제공자가 이 시간 안에 완료한다고 보장하는 값은 아니다.
    application_batch_timeout_seconds: float = Field(default=259200, gt=0)
    application_batch_concurrency: int = Field(default=4, ge=1)
    # 카드를 열 때 저장된 결과가 없어 새로 분석하면 backend 기본 60초 안에 끝내야 한다
    application_card_timeout_seconds: float = 50
    # 동시에 부르는 모델 호출 수 (문서별 추출, 우대사항별 판정)
    application_concurrency: int = 4
    # 제출 문서 본문이 이 글자 수 이하면 판정에 원문 전체를 넣고, 넘으면 조건과 맞닿은 문장만 넣는다.
    # 서류가 잘리지 않게 넉넉히 둔다 (긴 자기소개서 · 포트폴리오를 합쳐 2만 5천 자 안팎)
    application_full_text_chars: int = 50000
    # 확인 필요 항목의 재확인 횟수 (1차: 주변 문맥 · 본인 역할, 2차: 다른 제출 문서)
    application_rechecks: int = 2
    # 분석 예산이 이만큼 남지 않으면 재확인을 더 하지 않는다 (저장 · 응답에 쓸 여유)
    application_recheck_reserve_seconds: float = 20
    # AI 워커: backend job 모듈이 작업을 넣는 Redis 스트림과 결과를 돌려주는 스트림 (hiremate.jobs.*와 같은 이름)
    worker_job_stream: str = "hiremate:jobs"
    worker_result_stream: str = "hiremate:job-results"
    worker_group: str = "ai-worker"
    # 동시에 처리하는 작업 수. 요청을 하나씩 처리하는 로컬 모델(llama.cpp -np 1)은 1, vLLM은 모델 용량에 맞춘다
    worker_concurrency: int = 1
    # 문서 임베딩 작업(application/index-document)의 동시 처리 수. CPU 임베딩 서비스가 감당할 만큼만 둔다
    worker_index_concurrency: int = Field(default=1, ge=1)
    # 작업 하나를 처리하는 시도 횟수. 모두 실패하면 FAILED 결과를 보내고 담당자가 다시 요청한다
    worker_attempts: int = 2
    # 작업을 가진 워커가 이 시간 동안 소식이 없으면(멈췄으면) 다른 워커가 가져간다. 처리 중에는 주기적으로 알린다
    worker_claim_idle_seconds: float = 120
    # NCS 질의 임베딩 서비스(hiremate_ai.ncs_search). ai 서버는 이 주소로 요청 문장의 벡터를 받는다.
    # 서비스가 꺼져 있으면 공고 수정은 NCS 없이 진행한다
    ncs_embed_url: str = "http://127.0.0.1:8002"
    # 임베딩 요청 한 번의 한도. CPU에서 문장 두 개에 0.2초 안팎이라 짧게 둔다
    ncs_embed_timeout_seconds: float = 5
    # 공고 수정의 NCS 참고(검색어 만들기와 검색) 전체 한도. 넘으면 NCS 없이 진행한다.
    # backend가 공고 수정을 60초 기다리므로 본문 쓰기와 출처 판정에 쓸 시간을 남긴다
    ncs_reference_timeout_seconds: float = 20
    # 서비스가 듣는 주소. 내부망 밖에 열지 않는다
    ncs_embed_host: str = "127.0.0.1"
    ncs_embed_port: int = 8002
    # 질의 임베딩 모델(이름이나 로컬 경로)과 장치. 표의 벡터를 만든 BGE-M3와 같아야 한다
    ncs_model: str = "BAAI/bge-m3"
    ncs_device: Literal["cpu", "mps", "cuda"] = "cpu"

    @model_validator(mode="after")
    def _select_llm_profile(self) -> Self:
        if self.llm_profile == "local":
            self.llm_base_url = self.local_llm_base_url
            self.llm_model = self.local_llm_model
            self.llm_api_key = self.local_llm_api_key
        elif self.llm_profile == "openai":
            self.llm_base_url = self.openai_base_url
            self.llm_model = self.openai_model
            self.llm_api_key = self.openai_api_key
            self.llm_temperature = None
            self.llm_reasoning_effort = "none"
            self.llm_structured_output = "function_calling"
            self.poster_local_release_ollama = False
        return self

    @field_validator("llm_temperature", mode="before")
    @classmethod
    def _temperature(cls, value: object) -> object:
        """LLM_TEMPERATURE=none은 temperature를 보내지 않는다는 뜻이다. 빈 값은 기본값 0으로 둔다."""
        if isinstance(value, str):
            text = value.strip().lower()
            if text == "none":
                return None
            if not text:
                return 0
        return value


settings = Settings()
