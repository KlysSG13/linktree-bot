"""Тесты функции «Разбор задачи»: хранилище планов + e2e-анкета через Dispatcher."""
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

SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed_resources.json"
USER_ID = 1
ADMIN_ID = 100500


@pytest.fixture()
async def db(tmp_path):
    database = Database(str(tmp_path / "plans.db"))
    await database.connect()
    await database.seed_from_json(str(SEED_PATH))
    yield database
    await database.close()


@pytest.fixture()
async def env(tmp_path):
    cfg = Config()
    cfg.admin_ids = [ADMIN_ID]
    database = Database(str(tmp_path / "e2e.db"))
    await database.connect()
    await database.seed_from_json(str(SEED_PATH))
    engine = SearchEngine()
    engine.rebuild(await database.all_resources_for_index())
    dp = build_dispatcher(cfg, database, engine, QueryCache(),
                          UserContextMiddleware(database))
    bot = MockBot()
    yield dp, bot, database, engine
    await database.close()


class TestPlansStorage:
    async def test_create_and_get(self, db):
        plan_id = await db.create_plan(USER_ID, "сделать бота",
                                       {"t": 0.8, "y": 0.6, "g": 0.4, "h": 0.8, "R": 0.6},
                                       [{"resource_id": 5, "title": "x"}])
        await db.add_plan_item(plan_id, 1, "aiogram", "https://x.dev", "python",
                               ["telegram"], False, 0.9, 0.45, 0.6, 0, True)
        await db.add_plan_item(plan_id, None, "купить домен", "", "tools",
                               [], True, 0.7, 0.5, 0.5, 1, False)
        plan = await db.get_plan(plan_id)
        assert plan["query"] == "сделать бота"
        assert len(plan["items"]) == 2
        assert plan["items"][0]["is_root"] == 1
        assert plan["items"][1]["custom"] == 1
        assert plan["items"][0]["tags"] == ["telegram"]

    async def test_save_state_and_finish(self, db):
        plan_id = await db.create_plan(USER_ID, "q", {}, [])
        i1 = await db.add_plan_item(plan_id, 1, "a", "https://a.dev", "python",
                                    [], False, 0.9, 0.4, 0.6, 0, False)
        i2 = await db.add_plan_item(plan_id, 2, "b", "https://b.dev", "python",
                                    [], False, 0.8, 0.4, 0.5, 1, False)
        await db.save_plan_state(plan_id, [
            {"id": i1, "weight": 0.0, "priority": 0.0, "position": 1,
             "is_root": False, "status": "done", "done_at": 1730000000},
            {"id": i2, "weight": 0.75, "priority": 0.4, "position": 0,
             "is_root": True, "status": "pending", "done_at": 0},
        ])
        plan = await db.get_plan(plan_id)
        assert plan["items"][0]["title"] == "b"  # позиции пересортированы
        assert plan["items"][0]["is_root"] == 1
        assert await db.finish_plan_if_done(plan_id) is False
        await db.set_item_status(i2, "done", weight=0.0)
        assert await db.finish_plan_if_done(plan_id) is True
        assert (await db.get_plan(plan_id))["status"] == "done"

    async def test_active_plans_and_archive(self, db):
        p1 = await db.create_plan(USER_ID, "задача один", {}, [])
        p2 = await db.create_plan(USER_ID, "задача два", {}, [])
        await db.add_plan_item(p1, 1, "a", "u", "python", [], False, 0.5, 0.4, 0.4, 0, True)
        plans = await db.active_plans(USER_ID)
        assert {p["id"] for p in plans} == {p1, p2}
        by_id = {p["id"]: p for p in plans}
        assert by_id[p1]["pending"] == 1
        assert by_id[p2]["pending"] == 0
        await db.archive_plan(p1)
        assert {p["id"] for p in await db.active_plans(USER_ID)} == {p2}

    async def test_owner_and_candidates(self, db):
        plan_id = await db.create_plan(USER_ID, "q", {}, [{"resource_id": 9}])
        assert await db.get_plan_owner(plan_id) == USER_ID
        assert await db.get_plan_owner(99999) is None
        await db.update_plan_candidates(plan_id, [{"resource_id": 10, "title": "next"}])
        plan = await db.get_plan(plan_id)
        assert json.loads(plan["candidates"])[0]["resource_id"] == 10

    async def test_plans_stats(self, db):
        stats = await db.plans_stats()
        assert stats == {"total": 0, "active": 0, "steps_done": 0}
        plan_id = await db.create_plan(USER_ID, "q", {}, [])
        item = await db.add_plan_item(plan_id, 1, "a", "u", "python", [], False,
                                      0.5, 0.4, 0.4, 0, False)
        await db.set_item_status(item, "done", weight=0.0)
        stats = await db.plans_stats()
        assert stats["total"] == 1 and stats["active"] == 1 and stats["steps_done"] == 1


class TestPlanE2E:
    async def _run_questionnaire(self, dp, bot, query="хочу сделать телеграм бота"):
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/plan", 40)))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, query, 41)))
        for i, digit in enumerate(["5", "4", "3", "4", "3"]):
            await dp.feed_update(bot, make_update(message_payload(USER_ID, digit, 42 + i)))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "-", 50)))

    async def test_full_flow_build(self, env):
        dp, bot, db, engine = env
        await self._run_questionnaire(dp, bot)
        plan_texts = [t for t in bot.texts() if "Разбор задачи" in t and "Первопричина" in t]
        assert plan_texts, "план должен быть показан"
        text = plan_texts[-1]
        assert "Клей плана" in text and "🎯" in text
        assert "вес" in text and "приоритет" in text
        plans = await db.active_plans(USER_ID)
        assert len(plans) == 1
        plan = await db.get_plan(plans[0]["id"])
        assert 1 <= len(plan["items"]) <= 5
        assert any(i["is_root"] for i in plan["items"])
        # у шагов с ресурсами есть url
        assert any(i["url"] for i in plan["items"])

    async def test_done_recomputes(self, env):
        dp, bot, db, engine = env
        await self._run_questionnaire(dp, bot)
        plan_row = (await db.active_plans(USER_ID))[0]
        plan = await db.get_plan(plan_row["id"])
        pending = [i for i in plan["items"] if i["status"] == "pending"]
        first = pending[0]
        await dp.feed_update(bot, make_update(
            callback_payload(USER_ID, "pl:done:%d" % first["id"], 60)))
        item = await db.get_plan_item(first["id"])
        assert item["status"] == "done"
        assert item["weight"] == 0.0
        assert any("Разбор задачи" in t for t in bot.edits())

    async def test_skip_replaces(self, env):
        dp, bot, db, engine = env
        await self._run_questionnaire(dp, bot, query="python парсинг сайтов и графики")
        plan_row = (await db.active_plans(USER_ID))[0]
        plan = await db.get_plan(plan_row["id"])
        pending = [i for i in plan["items"] if i["status"] == "pending"]
        target = pending[0]
        spare_before = json.loads(plan["candidates"])
        await dp.feed_update(bot, make_update(
            callback_payload(USER_ID, "pl:skip:%d" % target["id"], 61)))
        item = await db.get_plan_item(target["id"])
        assert item["status"] == "skipped"
        msgs = " ".join(bot.texts())
        if spare_before:
            assert ("заменил" in msgs.lower()) or ("замены" in msgs.lower())
        else:
            assert "замены" in msgs.lower()

    async def test_finish_all_steps(self, env):
        dp, bot, db, engine = env
        await self._run_questionnaire(dp, bot)
        plan_row = (await db.active_plans(USER_ID))[0]
        for _ in range(10):
            plan = await db.get_plan(plan_row["id"])
            pending = [i for i in plan["items"] if i["status"] == "pending"]
            if not pending:
                break
            await dp.feed_update(bot, make_update(
                callback_payload(USER_ID, "pl:done:%d" % pending[0]["id"], 70)))
        assert (await db.get_plan(plan_row["id"]))["status"] == "done"
        assert any("план закрыт" in t.lower() for t in bot.edits() + bot.texts())

    async def test_plans_list(self, env):
        dp, bot, db, engine = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/plans", 80)))
        assert any("Активных разборов нет" in t or "No active" in t for t in bot.texts())
        await self._run_questionnaire(dp, bot)
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/plans", 81)))
        assert any("осталось" in t for t in bot.texts())

    async def test_menu_button_starts_plan(self, env):
        dp, bot, db, engine = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/start", 90)))
        await dp.feed_update(bot, make_update(
            message_payload(USER_ID, "🧩 Разбор задачи", 91)))
        assert any("Разбор задачи" in t and "опрос" in t.lower() or "вопрос" in t.lower()
                   for t in bot.texts())

    async def test_bad_digit_reprompted(self, env):
        dp, bot, db, engine = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/plan", 95)))
        await dp.feed_update(bot, make_update(
            message_payload(USER_ID, "сделать сайт", 96)))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "семь", 97)))
        assert any("цифру от 1 до 5" in t for t in bot.texts())

    async def test_dontknow_button(self, env):
        dp, bot, db, engine = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/plan", 98)))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "q", 99)))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "5", 100)))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "4", 101)))
        await dp.feed_update(bot, make_update(
            message_payload(USER_ID, "🤷 Не знаю", 102)))
        # после 🤷 должен быть следующий вопрос (о ценности)
        assert any("пользы" in t.lower() for t in bot.texts())

    async def test_no_results_graceful(self, env):
        dp, bot, db, engine = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/plan", 110)))
        await dp.feed_update(bot, make_update(
            message_payload(USER_ID, "зфырщт qwertyzzz xzxy", 111)))
        for i, digit in enumerate(["5", "4", "3", "4", "3"]):
            await dp.feed_update(bot, make_update(
                message_payload(USER_ID, digit, 112 + i)))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "-", 120)))
        # garbage-запрос: либо не нашлось инструментов, либо план не построен
        assert any("не нашлось" in t.lower() for t in bot.texts())
        assert await db.active_plans(USER_ID) == []

    async def test_custom_steps_black_box(self, env):
        dp, bot, db, engine = env
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "/plan", 130)))
        await dp.feed_update(bot, make_update(
            message_payload(USER_ID, "python pdf таблицы", 131)))
        for i, digit in enumerate(["5", "4", "3", "4", "3"]):
            await dp.feed_update(bot, make_update(
                message_payload(USER_ID, digit, 132 + i)))
        await dp.feed_update(bot, make_update(
            message_payload(USER_ID, "проверить у мамы права", 140)))
        await dp.feed_update(bot, make_update(message_payload(USER_ID, "-", 141)))
        plan_row = (await db.active_plans(USER_ID))[0]
        plan = await db.get_plan(plan_row["id"])
        titles = {i["title"] for i in plan["items"]}
        assert "проверить у мамы права" in titles
        box = next(i for i in plan["items"] if i["custom"] == 1)
        assert box["url"] == ""
