from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "TaskPilot"
    debug: bool = True

    # PostgreSQL
    db_host: str = "localhost"
    db_port: int = 5435
    db_user: str = "taskpilot"
    db_password: str = "taskpilot_dev_2026"
    db_name: str = "taskpilot_dev"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # Auth
    secret_key: str = "dev-secret-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 Tage fuer Dev

    # Owner (Phase 0: nur ein User)
    owner_email: str = "admin@innosmith.ai"
    owner_password: str = "changeme"
    owner_display_name: str = "InnoSmith"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = {"env_file": ".env.dev", "env_prefix": "TP_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
