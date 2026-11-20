"""LinkTree — Telegram-бот с курируемой базой dev-ресурсов и семантическим поиском.

Запуск: BOT_TOKEN=... ADMIN_IDS=... python3 bot.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import sys
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

import handlers.admin  # noqa: F401 — регистрирует свои хендлеры при импорте
import handlers.plan  # noqa: F401
import handlers.user  # noqa: F401
from config import BASE_DIR, Config, load_config
from db import Database, pick_weekly_resource, seed_if_empty
from i18n import RU, tr
from middlewares import ErrorMiddleware, ThrottlingMiddleware, UserContextMiddleware
from search.engine import SearchEngine, backend_factory
from services import QueryCache, rebuild_index

log = logging.getLogger("linktree")

USER_COMMANDS = [
    BotCommand(command="start", description="Главная"),
    BotCommand(command="plan", description="🧩 Разбор задачи"),
    BotCommand(command="plans", description="Мои разборы"),
    BotCommand(command="cats", description="Категории базы"),
    BotCommand(command="random", description="Случайный ресурс"),
    BotCommand(command="fav", description="Избранное"),
    BotCommand(command="suggest", description="Предложить ресурс"),
    BotCommand(command="digest", description="Ресурс недели вкл/выкл"),
    BotCommand(command="lang", description="Language / Язык"),
    BotCommand(command="help", description="Помощь"),
]
ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="admin", description="Панель и статистика"),
    BotCommand(command="pending", description="Предложения на модерации"),
    BotCommand(command="add", description="Добавить ресурс (JSON)"),
    BotCommand(command="export", description="Экспорт базы"),
    BotCommand(command="import", description="Импорт базы"),
    BotCommand(command="broadcast", description="Рассылка"),
    BotCommand(command="reindex", description="Пересобрать индекс"),
]


def build_dispatcher(cfg: Config, db: Database, engine: SearchEngine,
                     qcache: QueryCache, user_ctx: UserContextMiddleware) -> Dispatcher:
    """Собирает Dispatcher с подключёнными зависимостями (используется и в тестах)."""
    dp = Dispatcher()
    dp["cfg"] = cfg
    dp["db"] = db
    dp["engine"] = engine
    dp["qcache"] = qcache
    dp["middleware_cache"] = user_ctx
    dp["started_at"] = time.time()

    user_mw = user_ctx
    error_mw = ErrorMiddleware()
    throttle_mw = ThrottlingMiddleware()
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(error_mw)
        observer.middleware(user_mw)
        observer.middleware(throttle_mw)

    dp.include_router(handlers.admin.create_router())
    dp.include_router(handlers.plan.create_router())
    dp.include_router(handlers.user.create_router())
    return dp


async def digest_loop(bot: Bot, db: Database, cfg: Config) -> None:
    """«Ресурс недели»: каждый понедельник в DIGEST_HOUR локального времени."""
    sent_for_week: str = await db.get_meta("digest_week") or ""
    while True:
        now = dt.datetime.now()
        monday = now.date() - dt.timedelta(days=now.weekday())
        week_key = "%d-W%02d" % (now.isocalendar().year, now.isocalendar().week)
        target = dt.datetime.combine(monday, dt.time(hour=cfg.digest_hour))
        if now >= target and sent_for_week != week_key:
            try:
                rows = await db.export_resources()
                pick = pick_weekly_resource(rows, now.isocalendar().week)
                if pick:
                    card = "%s — %s" % (pick["title"], pick["url"])
                    subscribers = await db.digest_subscribers()
                    for uid in subscribers:
                        try:
                            await bot.send_message(
                                uid, tr("digest_msg", RU, card=card),
                                disable_web_page_preview=False,
                            )
                        except Exception:  # noqa: BLE001
                            log.debug("digest not delivered to %s", uid)
                        await asyncio.sleep(0.05)
                    await db.set_meta("digest_week", week_key)
                    sent_for_week = week_key
                    log.info("digest sent to %d users", len(subscribers))
            except Exception:  # noqa: BLE001 — цикл не должен умирать
                log.exception("digest_loop iteration failed")
        # ждём до следующей проверки (полчаса)
        await asyncio.sleep(1800)


async def main() -> int:
    cfg = load_config()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not cfg.bot_token:
        print("Ошибка: не задан BOT_TOKEN. Создай бота у @BotFather, затем:")
        print("  export BOT_TOKEN=123:ABC...   # или пропиши в .env")
        print("  export ADMIN_IDS=<твой telegram id>")
        return 1
    if not cfg.is_admin_configured:
        print("Предупреждение: ADMIN_IDS пуст — админ-команды будут недоступны.")

    bot = Bot(token=cfg.bot_token, request_timeout=30.0,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    db = Database(cfg.db_path)
    await db.connect()
    seeded = await seed_if_empty(db, str(BASE_DIR / "data" / "seed_resources.json"))
    log.info("seed: добавлено %d ресурсов", seeded)

    engine = SearchEngine(backend_factory(cfg))
    started = time.perf_counter()
    n = await rebuild_index(engine, db)
    log.info("индекс: %d ресурсов, бэкенд «%s», сборка %.0f мс",
             n, engine.backend.name, (time.perf_counter() - started) * 1000)

    dp = build_dispatcher(cfg, db, engine, QueryCache(), UserContextMiddleware(db))

    try:
        me = await asyncio.wait_for(bot.get_me(), timeout=20)
    except asyncio.TimeoutError:
        log.error("Telegram API не ответил за 20 с: проверь интернет и BOT_TOKEN")
        await bot.session.close()
        await db.close()
        return 1
    except Exception as exc:  # noqa: BLE001 — токен/сеть
        log.error("не удалось подключиться к Telegram: %s", exc)
        await bot.session.close()
        await db.close()
        return 1

    await bot.set_my_commands(USER_COMMANDS)
    if cfg.is_admin_configured:
        from aiogram.types import BotCommandScopeChat
        try:
            for admin_id in cfg.admin_ids:
                await bot.set_my_commands(ADMIN_COMMANDS, BotCommandScopeChat(chat_id=admin_id))
        except Exception:  # noqa: BLE001 — админ мог не нажать /start
            log.warning("не удалось выставить админ-команды")

    log.info("запущен как @%s (ресурсов в базе: %d)", me.username, n)
    print("LinkTree запущен: @%s · ресурсов: %d · бэкенд поиска: %s" %
          (me.username, n, engine.backend.name))

    digest_task = asyncio.create_task(digest_loop(bot, db, cfg))
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        digest_task.cancel()
        try:
            await bot.session.close()
        finally:
            await db.close()
    return 0


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
