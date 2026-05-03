from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


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
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 Tage für Dev

    # Owner (Phase 0: nur ein User)
    owner_email: str = "admin@innosmith.ai"
    owner_password: str = "changeme"
    owner_display_name: str = "InnoSmith"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # nanobot WebSocket Bridge
    nanobot_ws_url: str = "ws://127.0.0.1:8765"
    nanobot_ws_token: str = "taskpilot-dev-token"

    # Unsplash (optional, for background image search)
    unsplash_access_key: str = ""

    # Microsoft Graph API (E-Mail-Integration)
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_user_email: str = ""

    # LiteLLM Gateway
    litellm_base_url: str = "http://localhost:4000"
    triage_model: str = "ollama/qwen3.5:35b"

    # Pipedrive CRM
    pipedrive_api_token: str = ""
    pipedrive_domain: str = "innosmith"

    # Toggl Track
    toggl_api_token: str = ""
    toggl_workspace_id: int = 0

    # Bexio Buchhaltung
    bexio_api_token: str = ""

    # LLM Provider API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    perplexity_api_key: str = ""

    # Web Search
    tavily_api_key: str = ""

    # SIGNA Strategic Intelligence (read-only DB)
    isi_host: str = ""
    isi_db: str = ""
    isi_user: str = ""
    isi_secret: str = ""
    isi_port: int = 5432

    # InvoiceInsight (Kreditoren-Analyse)
    invoiceinsight_api_key: str = ""
    invoiceinsight_url: str = "http://127.0.0.1:8055/mcp"

    # Triage
    triage_interval_seconds: int = 120

    model_config = {
        "env_file": str(_PROJECT_ROOT / ".env.dev"),
        "env_prefix": "TP_",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
