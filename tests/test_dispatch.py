"""E2E-диспетчеризация: настоящие Update проходят через Dispatcher с мок-ботом.
Проверяет связку фильтров, middlewares и хендлеров целиком, без сети."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from bot import build_dispatcher
from config import Config
from db import Database
from middlewares import UserContextMiddleware
from mockbot import MockBot, callback_payload, make_update, message_payload
from search.engine import SearchEngine
from services import QueryCache

USER_ID = 1
ADMIN_ID = 100500
SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed_resources.json"


@pytest.fixture()
async def env(tmp_path):
    cfg = Config()
    cfg.admin_ids = [ADMIN_ID]
    db = Database(str(tmp_path / "e2e.db"))
    await db.connect()
    await db.seed_from_json(str(SEED_PATH))
    engine = SearchEngine()
    engine.rebuild(await db.all_resources_for_index())
    user_ctx = UserContextMiddleware(db)
    dp = build_dispatcher(cfg, db, engine, QueryCache(), user_ctx)
    bot = MockBot()
    yield dp, bot, db, engine
    await db.close()


class TestUserFlows:
    async def test_start(self, env):
        dp, bot, *_ = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/start")))
        texts = bot.texts()
        assert texts and "LinkTree" in texts[0]
        assert bot.last().get("reply_markup") is not None

    async def test_search_pdf(self, env):
        dp, bot, *_ = env
        await dp.feed_update(bot, make_update(
            message_payload(USER_ID, "нужна библиотека для работы с PDF в Python")))
        texts = bot.texts()
        assert texts and ("pdfplumber" in texts[0] or "pypdf" in texts[0])
        assert bot.last().get("reply_markup") is not None

    async def test_search_garbage_graceful(self, env):
        dp, bot, *_ = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "зфырщт qwertyzzz")))
        texts = bot.texts()
        assert texts and "не нашлось" in texts[0]

    async def test_categories(self, env):
        dp, bot, *_ = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/cats")))
        assert any("Категории" in t or "Python" in t for t in bot.texts())

    async def test_random(self, env):
        dp, bot, *_ = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/random")))
        texts = bot.texts()
        assert texts and "https://" in texts[0]

    async def test_favorites_empty(self, env):
        dp, bot, *_ = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/fav")))
        assert any("пусто" in t for t in bot.texts())

    async def test_vote_callback(self, env):
        dp, bot, db, engine = env
        rid = engine.get(1).rid
        await dp.feed_update(bot, make_update(
            callback_payload(USER_ID, "vote:up:%d" % rid)))
        assert await db.user_vote(USER_ID, rid) == 1
        answers = [r for r in bot.calls if r["method"] == "AnswerCallbackQuery"]
        assert answers and answers[0].get("text")

    async def test_fav_callback(self, env):
        dp, bot, db, engine = env
        rid = engine.get(2).rid
        await dp.feed_update(bot, make_update(callback_payload(USER_ID, "fav:%d" % rid)))
        assert await db.is_favorite(USER_ID, rid)

    async def test_help_and_about(self, env):
        dp, bot, *_ = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/help")))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/about")))
        assert len(bot.texts()) >= 2

    async def test_digest_toggle(self, env):
        dp, bot, db, *_ = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/digest")))
        assert (await db.get_user(USER_ID))["digest"] == 1
        assert any("дайджест" in t.lower() for t in bot.texts())

    async def test_suggest_fsm_full(self, env):
        dp, bot, db, *_ = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/suggest", 30)))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "Мой инструмент", 31)))
        await dp.feed_update(bot, make_update(
            message_payload(USER_ID, "https://example.com", 32)))
        await dp.feed_update(bot, make_update(
            callback_payload(USER_ID, "suggcat:tools", 33)))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "очень полезен", 34)))
        assert await db.pending_count() == 1
        assert any("на модерацию" in t for t in bot.texts())

    async def test_query_logged(self, env):
        dp, bot, db, *_ = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "docker деплой")))
        assert await db.queries_count_24h() == 1


class TestAdminFlows:
    async def test_admin_panel(self, env):
        dp, bot, *_ = env
        await dp.feed_update(bot, make_update(message_payload(ADMIN_ID, "/admin")))
        assert any("Админ-панель" in t for t in bot.texts())

    async def test_add_resource_json(self, env):
        dp, bot, db, engine = env
        payload = json.dumps({"title": "Тестовый инструмент", "url": "https://test.dev",
                              "category": "tools", "tags": ["тест"], "ru": "описание теста"})
        await dp.feed_update(bot, make_update(message_payload(ADMIN_ID, "/add " + payload)))
        assert any("Добавлено" in t for t in bot.texts())
        assert engine.size == await db.resources_count()  # индекс пересобран

    async def test_non_admin_add_ignored(self, env):
        dp, bot, *_ = env
        await dp.feed_update(bot, make_update(
            message_payload(USER_ID, '/add {"title":"x","url":"https://x.dev","category":"tools"}')))
        assert not bot.texts(), "не-админ не должен получать ответ от админ-команды"

    async def test_export_document(self, env):
        dp, bot, *_ = env
        await dp.feed_update(bot, make_update(message_payload(ADMIN_ID, "/export")))
        assert any(r["method"] == "SendDocument" for r in bot.calls)
        assert not any("сломалось" in t for t in bot.texts())

    async def test_bad_add_json(self, env):
        dp, bot, *_ = env
        await dp.feed_update(bot, make_update(message_payload(ADMIN_ID, "/add not-json")))
        assert any("JSON" in t for t in bot.texts())


class TestSecurity:
    async def test_banned_user_silenced(self, env):
        dp, bot, db, *_ = env
        await db.ensure_user(USER_ID, "ru")
        await db.ban_user(USER_ID, True)
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/start")))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "поиск")))
        texts = bot.texts()
        assert texts and all("ограничен" in t for t in texts)

    async def test_flood_throttled(self, env):
        dp, bot, *_ = env
        # 12 сообщений подряд — часть должна срезаться троттлингом
        for i in range(12):
            await dp.feed_update(bot, make_update(message_payload(USER_ID, "pdf python", 100 + i)))
        handled = sum(1 for t in bot.texts() if "pdfplumber" in t or "pypdf" in t)
        assert handled < 12, "троттлинг должен срезать часть запросов"
        assert any("Не так быстро" in t for t in bot.texts())
