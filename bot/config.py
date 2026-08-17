"""Environment variables in, typed settings out."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # -- core -------------------------------------------------------------
    bot_token: str
    admin_ids: str = ""

    # -- webhook vs. long polling -----------------------------------------
    webhook_base: str = ""
    webhook_secret: str = ""
    webhook_port: int = 8080

    # -- OCR --------------------------------------------------------------
    default_langs: str = "eng"
    default_engine: str = "tesseract"
    ocr_concurrency: int = 4
    ocr_timeout_s: int = 60
    tesseract_cmd: str = "tesseract"
    max_pdf_pages: int = 20

    # -- vision engine (optional, disabled unless a key is supplied) ------
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # -- quotas / throttling ------------------------------------------------
    free_daily_pages: int = 30
    premium_daily_pages: int = 300
    burst_per_minute: int = 12

    # -- storage ------------------------------------------------------------
    store_text_history: bool = True
    history_retention_days: int = 30
    max_file_mb: int = 20

    # -- ops ------------------------------------------------------------------
    log_json: bool = False

    @property
    def admins(self) -> list[int]:
        return [int(p) for p in self.admin_ids.split(",") if p.strip()]

    @property
    def vision_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024
