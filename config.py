"""Application configuration. Values can be overridden by environment variables."""
import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    base_dir: Path = BASE_DIR
    data_dir: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
    front_dir: Path = BASE_DIR / "front"
    initial_capital: float = float(os.getenv("INITIAL_CAPITAL", "500000"))
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "5000"))
    debug: bool = _bool("FLASK_DEBUG", True)
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me-in-env")
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "futures_ranking")


settings = Settings()
