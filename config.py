"""Application configuration. Values can be overridden by environment variables."""
import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _load_local_env() -> None:
    """Load a simple local .env without adding a runtime dependency."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_local_env()


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
    storage_backend: str = os.getenv("STORAGE_BACKEND", "csv").lower()


settings = Settings()
