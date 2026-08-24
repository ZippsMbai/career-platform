from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/career_platform"

    # AI provider: "anthropic" (paid, needs credits) or "gemini" (free tier available, no card)
    ai_provider: str = "anthropic"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    jwt_secret: str = "change-me-in-.env"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    auth_email: str = "you@example.com"
    auth_password_hash: str = ""

    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

if settings.jwt_secret == "change-me-in-.env":
    raise RuntimeError(
        "JWT_SECRET is still the placeholder default. Set a real random value in your .env "
        "(or your host's environment variables) before running this — "
        "e.g. `python -c \"import secrets; print(secrets.token_urlsafe(32))\"`"
    )