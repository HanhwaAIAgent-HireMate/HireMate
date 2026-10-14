from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수로 읽는 설정. 기본값은 로컬 개발(저장소 루트의 compose.yaml) 기준이다."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg://hiremate:hiremate@localhost:5432/hiremate"
    redis_url: str = "redis://localhost:6379/0"
    backend_base_url: str = "http://localhost:8080"
    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = ""


settings = Settings()
