from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Scraper settings
    scraper_default_rps: float = 1.0
    scraper_max_burst: int = 3
    scraper_connect_timeout: int = 10
    scraper_read_timeout: int = 30
    scraper_max_image_size_mb: int = 50
    scraper_min_image_size_kb: float = 0.5
    scraper_max_images_per_url: int = 10
    scraper_alert_threshold: float = 0.5
    scraper_max_concurrent: int = 5
    scraper_cache_ttl_days: int = 7
    use_browser_fallback: bool = False
    use_browser_primary: bool = False
    playwright_headless: bool = True
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "ImageFactory"
    app_version: str = "1.0.0"
    app_env: str = "production"
    debug: bool = False
    secret_key: str = "change-me"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    api_key: str = "image-factory-api-key-change-me"
    api_rate_limit: int = 100
    api_rate_limit_period: int = 60

    # Database
    database_url: str = "postgresql+asyncpg://imagefactory:imagefactory@postgres:5432/imagefactory"
    database_pool_size: int = 20
    database_max_overflow: int = 40

    # Redis
    redis_url: str = "redis://redis:6379/0"
    redis_broker_url: str = "redis://redis:6379/1"

    # Claude defaults (overridable from DB)
    claude_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 4096
    claude_temperature: float = 0.7

    # Google AI (shared key for Gemini + Nano Banana)
    google_api_key: str = ""
    gemini_api_key: str = ""  # kept for backward compat
    nano_banana_api_key: str = ""  # kept for backward compat
    gemini_vision_model: str = "gemini-2.0-flash"
    gemini_text_model: str = "gemini-2.0-flash"

    # OpenRouter defaults
    openrouter_api_key: str = ""

    # Image Provider defaults (overridable from DB)
    image_provider: str = "openrouter"
    image_provider_timeout: int = 120
    image_provider_max_retries: int = 3
    image_provider_poll_interval: int = 2
    replicate_api_key: str = ""
    stabilityai_api_key: str = ""
    openai_api_key: str = ""

    # Budget default (overridable from DB)
    monthly_budget_cents: int = 10000

    # Batch processing
    batch_max_concurrent: int = 3
    batch_avg_minutes_per_product: float = 2.0

    # Pipeline
    pipeline_ocr_cache_ttl: int = 86400
    pipeline_stage1_cache_ttl: int = 3600
    pipeline_max_output_images: int = 3
    pipeline_min_ranking_score: float = 0.4

    # Google Drive
    google_drive_credentials_path: str = "configs/gdrive_credentials.json"
    google_drive_token_path: str = "configs/gdrive_token.json"
    google_drive_root_folder: str = "ImageFactory Outputs"
    google_drive_auto_upload: bool = True
    google_drive_make_public: bool = False

    # Image Provider defaults (overridable from DB)
    image_provider_timeout: int = 120
    image_provider_max_retries: int = 3
    image_provider_poll_interval: int = 2

    # Storage (local only — no S3)
    storage_enabled: bool = True
    storage_local_path: str = "./outputs"

    # Delivery (local only — no S3)
    delivery_backends: str = "local"
    delivery_local_path: str = "./outputs"
    delivery_webhook_url: str = ""
    delivery_webhook_secret: str = ""

    # Celery
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    celery_worker_concurrency: int = 4
    celery_task_acks_late: bool = True
    celery_task_reject_on_worker_lost: bool = True
    celery_task_retry_max: int = 3
    celery_task_retry_delay: int = 30

    # Product Localization
    # Scrapfly
    scrapfly_enabled: bool = True
    scrapfly_monthly_budget: int = 3000

    # Proxy & request delay
    proxy_enabled: bool = True
    proxy_refresh_interval: int = 300
    proxy_max_latency: float = 5.0
    proxy_test_url: str = "http://httpbin.org/ip"
    request_delay_min: float = 2.0
    request_delay_max: float = 5.0
    request_delay_enabled: bool = True

    extractor_default_language: str = "en"
    extractor_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    extractor_timeout: int = 30

    # Smoke Test / Verification
    smoke_test_mode: bool = False
    smoke_max_text_calls: int = 1
    smoke_max_image_calls: int = 1
    smoke_max_retries: int = 1
    smoke_max_cost_cents: int = 50
    smoke_use_cheapest_model: bool = True

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    log_output: str = "stdout"

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_local_path).resolve()

    @property
    def delivery_path(self) -> Path:
        return Path(self.delivery_local_path).resolve()

    @property
    def delivery_backend_list(self) -> list[str]:
        return [b.strip() for b in self.delivery_backends.split(",") if b.strip()]


settings = Settings()
