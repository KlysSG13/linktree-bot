"""Интроспекционные тесты: хендлеры зарегистрированы, фильтры и клавиатуры валидны."""
from __future__ import annotations

from pathlib import Path

import pytest
from aiogram import Dispatcher

import handlers.admin as admin_mod
import handlers.user as user_mod
from bot import build_dispatcher
from config import Config
from db import Database
from middlewares import UserContextMiddleware
from search.engine import SearchEngine
from services import QueryCache, format_hit

SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed_resources.json"


@pytest.fixture()
async def env(tmp_path):
    cfg = Config()
    cfg.admin_ids = [100500]
    db = Database(str(tmp_path / "handlers.db"))
    await db.connect()
    await db.seed_from_json(str(SEED_PATH))
    engine = SearchEngine()
    docs = await db.all_resources_for_index()
    engine.rebuild(docs)
    dp = build_dispatcher(cfg, db, engine, QueryCache(), UserContextMiddleware(db))
    yield dp, cfg, db, engine
    await db.close()


def registered_names(observer):
    names = []
    for handler in observer.handlers:
        cb = handler.callback
        names.append(getattr(cb, "__name__", str(cb)))
    return names


def all_registered_names(root):
    """Обход дерева роутеров: хендлеры лежат в sub-роутерах, а не в корневом Dispatcher."""
    names = registered_names(root.message) + registered_names(root.callback_query)
    for sub in getattr(root, "sub_routers", []):
        names.extend(all_registered_names(sub))
    return names


class TestHandlersRegistered:
    async def test_dispatcher_has_routers(self, env):
        dp, *_ = env
        assert isinstance(dp, Dispatcher)

    async def test_user_commands_registered(self, env):
        dp, *_ = env
        names = all_registered_names(dp)
        for expected in ("cmd_start", "cmd_help", "cmd_about", "cmd_ping", "cmd_lang",
                         "cmd_suggest", "cmd_digest", "cmd_cats", "cmd_random", "cmd_fav",
                         "cmd_cancel", "search_message", "btn_search_hint"):
            assert expected in names, expected

    async def test_user_callbacks_registered(self, env):
        dp, *_ = env
        names = all_registered_names(dp)
        for expected in ("cb_lang", "cb_more", "cb_cats", "cb_category", "cb_random",
                         "cb_fav", "cb_favdel", "cb_vote", "cb_related", "cb_suggest_category"):
            assert expected in names, expected

    async def test_admin_commands_registered(self, env):
        dp, *_ = env
        names = all_registered_names(dp)
        for expected in ("cmd_admin", "cmd_pending", "cmd_add", "cmd_export", "cmd_import",
                         "cmd_broadcast", "cmd_ban", "cmd_unban", "cmd_reindex"):
            assert expected in names, expected

    async def test_admin_callbacks_registered(self, env):
        dp, *_ = env
        names = all_registered_names(dp)
        assert "cb_suggestion" in names
        assert "cb_broadcast" in names

    async def test_handlers_count(self, env):
        dp, *_ = env
        assert len(all_registered_names(dp)) >= 35

    async def test_every_user_handler_injects_lang(self, env):
        """Все хендлеры пользовательского роутера должны принимать lang из middleware."""
        import inspect
        router = user_mod.create_router()
        for handler in router.message.handlers:
            sig = inspect.signature(handler.callback)
            assert "lang" in sig.parameters, handler.callback.__name__


class TestAdminFilter:
    async def test_admin_passes(self, env):
        dp, cfg, *_ = env
        flt = admin_mod.AdminFilter()
        class FakeUser:
            id = 100500
        class FakeEvent:
            from_user = FakeUser()
        assert await flt(FakeEvent(), cfg=cfg) is True

    async def test_non_admin_blocked(self, env):
        dp, cfg, *_ = env
        flt = admin_mod.AdminFilter()
        class FakeUser:
            id = 1
        class FakeEvent:
            from_user = FakeUser()
        assert await flt(FakeEvent(), cfg=cfg) is False


class TestAddPayload:
    def test_ok(self):
        data = admin_mod.parse_add_payload(
            '{"title":"T","url":"https://t.dev","category":"python","tags":["a"],"ru":"опис"}')
        assert data["title"] == "T"

    def test_missing_field(self):
        with pytest.raises(ValueError):
            admin_mod.parse_add_payload('{"title":"T"}')

    def test_not_object(self):
        with pytest.raises(ValueError):
            admin_mod.parse_add_payload("[1,2]")


class TestTextFilters:
    def test_menu_text(self):
        msg = type("M", (), {"text": "🗂 Категории"})()
        assert user_mod.menu_text_filter(msg) is True
        assert user_mod.search_text_filter(msg) is False

    def test_command_not_search(self):
        msg = type("M", (), {"text": "/start"})()
        assert user_mod.search_text_filter(msg) is False

    def test_plain_query_is_search(self):
        msg = type("M", (), {"text": "нужна библиотека для pdf"})()
        assert user_mod.search_text_filter(msg) is True

    def test_english_menu_button(self):
        msg = type("M", (), {"text": "🎲 Random"})()
        assert user_mod.menu_text_filter(msg) is True


class TestKeyboards:
    async def test_callback_data_length(self, env):
        """Все callback_data ≤ 64 байт (лимит Telegram)."""
        dp, cfg, db, engine = env
        docs = await db.all_resources_for_index()
        fake_hits = [type("H", (), {"doc": d, "score": 0.5})() for d in docs[:5]]
        marks = [
            __import__("keyboards").results_kb(fake_hits, 3, 10, "ru", {1, 2}, "deadbeef"),
            __import__("keyboards").single_resource_kb(1, "https://x.dev", "ru", False, True),
            __import__("keyboards").admin_broadcast_confirm_kb("12345678"),
            __import__("keyboards").admin_suggestion_kb(42),
        ]
        for markup in marks:
            for row in markup.inline_keyboard:
                for button in row:
                    if button.callback_data:
                        assert len(button.callback_data.encode()) <= 64, button.callback_data

    async def test_url_buttons_https(self, env):
        dp, cfg, db, engine = env
        docs = (await db.all_resources_for_index())[:3]
        fake_hits = [type("H", (), {"doc": d, "score": 0.5})() for d in docs]
        markup = __import__("keyboards").results_kb(fake_hits, 0, 3, "en", set())
        urls = [b.url for row in markup.inline_keyboard for b in row if b.url]
        assert urls and all(u.startswith("https://") for u in urls)

    def test_categories_kb_respects_counts(self, env):
        import keyboards as kb
        markup = kb.categories_kb({"python": 10, "web": 0}, "ru")
        flat = [b.text for row in markup.inline_keyboard for b in row]
        assert any("10" in t for t in flat)
        assert not any("web" in t.lower() for t in flat)


class TestFormatHit:
    def test_contains_essentials(self, env):
        dp, cfg, db, engine = env
        doc = engine.get(1)
        text = format_hit(doc, 1, 0.42, "ru")
        assert doc.title in text
        assert doc.url in text
        assert "%" in text

    def test_score_percent_bounds_in_card(self, env):
        dp, cfg, db, engine = env
        doc = engine.get(1)
        for score in (0.01, 0.5, 1.4):
            text = format_hit(doc, 1, score, "ru")
            m = __import__("re").search(r"(\d+)%", text)
            value = int(m.group(1))
            assert 1 <= value <= 99
