"""
Central config. Everything tunable lives here, sourced from environment
variables / .env — never hardcoded inside pipeline logic.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Judge LLM
    anthropic_api_key: str = ""
    judge_model: str = "claude-sonnet-4-6"
    judge_votes: int = 3
    judge_temperature: float = 0.0

    # Voice bot SDK (Houndify)
    houndify_client_id: str = ""
    houndify_client_key: str = ""
    houndify_endpoint: str = "https://api.houndify.com/"
    houndify_request_info_path: str = "vendor/houndify/requestInfo.json"
    houndify_lang: str = "0"

    # Run behavior
    max_concurrent_workers: int = 5
    request_timeout_seconds: int = 30
    latency_sla_ms: int = 3000
    pass_score_threshold: int = 80


settings = Settings()
