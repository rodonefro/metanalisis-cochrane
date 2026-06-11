from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "MetaAnalysis Cochrane App"
    # Render.com provides DATABASE_URL automatically when a DB is attached;
    # falls back to local SQLite for development.
    database_url: str = f"sqlite:///{BASE_DIR}/metanalisis.db"
    anthropic_api_key: str = ""
    upload_dir: str = str(BASE_DIR / "uploads")
    plots_dir: str = str(BASE_DIR / "plots")
    # Comma-separated list of allowed CORS origins
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    class Config:
        env_file = str(BASE_DIR / ".env")


settings = Settings()

# Ensure directories exist
Path(settings.upload_dir).mkdir(exist_ok=True)
Path(settings.plots_dir).mkdir(exist_ok=True)
