from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./leadflow.db"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24
    google_places_api_key: str = ""
    # Encrypts stored SMTP passwords. Generate once with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Losing it makes stored passwords unreadable; leaking it exposes them. Keep it out of git.
    encryption_key: str = ""
    # Dev only: allow SMTP hosts on localhost/private networks (for a local capture server).
    # Must stay false in production, or clients could point the server at your internal network.
    allow_private_smtp: bool = False
    # Where unsubscribe links point. Must be the real public URL in production.
    public_base_url: str = "http://localhost:8000"
    gemini_api_key: str = ""
    # Pin an exact model. Names get retired ("gemini-2.5-flash" already 404s for new users),
    # so override with LLM_MODEL in .env instead of editing code.
    llm_model: str = "gemini-3.1-flash-lite"


settings = Settings()
