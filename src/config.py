from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE, override=False)  # populate os.environ before Settings() reads it


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://postgres:password@localhost:5432/si_payroll"
    db_min_pool: int = 2
    db_max_pool: int = 10
    rate_limit_per_minute: int = 100
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    groq_api_key: str = ""


settings = Settings()
