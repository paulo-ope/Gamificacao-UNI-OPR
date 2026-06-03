from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OPR Gamificacao Operacional API"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://opr:opr@db:5432/opr_gamification"
    frontend_url: str = "http://localhost:3000"
    auto_seed: bool = True
    demo_seed: bool = False
    auth_secret_key: str = "change-me-local-gamification-secret"
    auth_token_expire_minutes: int = 720
    initial_admin_name: str = ""
    initial_admin_email: str = ""
    initial_admin_password: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
