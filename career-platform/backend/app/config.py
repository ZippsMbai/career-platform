from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/career_platform"
    anthropic_api_key: str = ""
    jwt_secret: str = "change-me-in-.env"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 1 week — single-user tool, not worth re-logging-in daily

    # Single-user credentials (V1 has no signup flow — you are the only user)
    auth_email: str = "you@example.com"
    auth_password_hash: str = ""  # generate with app.auth.hash_password, put the output here

    # Comma-separated list of allowed frontend origins, e.g.
    # "http://localhost:3000,https://your-app.vercel.app"
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

# Fail fast rather than silently running a public deployment with a known JWT secret —
# anyone could forge a valid login token if this default ever shipped as-is.
if settings.jwt_secret == "change-me-in-.env":
    raise RuntimeError(
        "JWT_SECRET is still the placeholder default. Set a real random value in your .env "
        "(or your host's environment variables) before running this — "
        "e.g. `python -c \"import secrets; print(secrets.token_urlsafe(32))\"`"
    )
