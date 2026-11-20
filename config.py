"""Конфигурация LinkTree-бота. Всё читается из переменных окружения или .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Мини-парсер .env без внешних зависимостей."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BASE_DIR / ".env")


def _parse_admin_ids(raw: str) -> list:
    ids = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            ids.append(int(chunk))
    return ids


@dataclass
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_ids: list = field(default_factory=lambda: _parse_admin_ids(os.getenv("ADMIN_IDS", "")))
    db_path: str = os.getenv("DB_PATH", str(BASE_DIR / "linktree.db"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Поиск: auto | local | st | api
    #   local — офлайн-гибрид (по умолчанию, без внешних зависимостей);
    #   st    — sentence-transformers, если пакет установлен;
    #   api   — OpenAI-совместимый /embeddings endpoint.
    search_backend: str = os.getenv("SEARCH_BACKEND", "auto")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
    embedding_api_base: str = os.getenv("EMBEDDING_API_BASE", "")
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", "")

    results_per_page: int = int(os.getenv("RESULTS_PER_PAGE", "3"))
    digest_hour: int = int(os.getenv("DIGEST_HOUR", "10"))  # час рассылки «ресурс недели»

    @property
    def is_admin_configured(self) -> bool:
        return bool(self.admin_ids)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


def load_config() -> Config:
    return Config()
