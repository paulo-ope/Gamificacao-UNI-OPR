from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "OPR Gamificacao Operacional API"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://opr:opr@db:5432/opr_gamification"
    frontend_url: str = "http://localhost:3000"
    auto_seed: bool = False
    demo_seed: bool = False
    auth_secret_key: str = ""
    auth_token_expire_minutes: int = 720
    initial_admin_name: str = ""
    initial_admin_email: str = ""
    initial_admin_password: str = ""
    debug_performance: bool = False
    ixc_api_base_url: str = ""
    ixc_api_token: str = ""
    ixc_api_verify_ssl: bool = True
    ixc_sync_enabled: bool = False
    ixc_sync_interval_minutes: int = 20
    cpk_api_base_url: str = ""
    cpk_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


WEAK_AUTH_SECRETS = {
    "",
    "change-me-local-gamification-secret",
    "changeme",
    "secret",
    "jwt-secret",
    "default",
    "123456",
}


def validate_runtime_settings(settings: Settings) -> Settings:
    secret = settings.auth_secret_key.strip()
    if not secret:
        raise RuntimeError("AUTH_SECRET_KEY é obrigatório para iniciar a aplicação.")
    if settings.app_env.lower() == "production":
        if secret in WEAK_AUTH_SECRETS or len(secret) < 32:
            raise RuntimeError("AUTH_SECRET_KEY fraco ou inseguro para produção.")
    return settings


@lru_cache
def get_settings() -> Settings:
    return validate_runtime_settings(Settings())
