"""Админские хендлеры: панель, добавление ресурсов, импорт/экспорт, модерация, рассылка."""
from __future__ import annotations

import asyncio
import json
import logging
import time

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, TelegramObject

import keyboards as kb
from config import Config
from i18n import tr
from services import rebuild_index, safe_edit

log = logging.getLogger("linktree.admin")


class AdminFilter(BaseFilter):
    """Пропускает только админов из конфига."""

    async def __call__(self, event: TelegramObject, cfg: Config) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and cfg.is_admin(user.id))


class AdminStates(StatesGroup):
    wait_import = State()
    wait_broadcast = State()


# ---------------------------------------------------------------- панель и статистика

async def cmd_admin(message: Message, lang: str, db, engine) -> None:
    users = await db.users_count()
    resources = await db.resources_count()
    queries = await db.queries_count_24h()
    pending = await db.pending_count()
    plans = await db.plans_stats()
    top = await db.top_queries_24h(5)
    if top:
        top_text = tr("top_queries_header", lang, list="\n".join(
            "• «%s» × %d" % (q, n) for q, n in top))
    else:
        top_text = tr("no_queries_yet", lang) + "\n"
    await message.answer(tr("admin_panel", lang, users=users, resources=resources,
                            queries=queries, pending=pending, top=top_text,
                            plans_total=plans["total"], plans_active=plans["active"],
                            steps_done=plans["steps_done"]))


async def cmd_pending(message: Message, lang: str, db) -> None:
    items = await db.pending_suggestions()
    if not items:
        await message.answer(tr("sugg_empty", lang))
        return
    for item in items:
        card = tr("sugg_card", lang, sid=item["id"], user=str(item["user_id"]),
                  title=item["title"], url=item["url"], cat=item["category"],
                  comment=item["comment"] or "—")
        await message.answer(card, reply_markup=kb.admin_suggestion_kb(item["id"]),
                             disable_web_page_preview=True)


async def cb_suggestion(callback: CallbackQuery, lang: str, db, engine, bot: Bot) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    action, sid = parts[1], int(parts[2])
    if action == "ok":
        item = await db.suggestion_decide(sid, "approved")
        if item is None:
            await callback.answer()
            return
        rid, slug = await db.add_resource(
            title=item["title"], url=item["url"], category=item["category"],
            tags=[t.strip() for t in item["tags"].split(",") if t.strip()] or [],
            ru=item["comment"] or item["title"], en=item["comment"] or "", source="suggestion",
        )
        await rebuild_index(engine, db)
        await safe_edit(callback, tr("sugg_approved", lang, sid=sid))
        if item["user_id"]:
            try:
                await bot.send_message(item["user_id"],
                                       tr("sugg_user_notify", "ru", title=item["title"]))
            except Exception:  # noqa: BLE001 — пользователь мог остановить бота
                log.debug("не уведомить автора предложения %s", item["user_id"])
    else:
        await db.suggestion_decide(sid, "rejected")
        await safe_edit(callback, tr("sugg_rejected", lang, sid=sid))
    await callback.answer()


# ---------------------------------------------------------------- добавление и импорт/экспорт

def parse_add_payload(raw: str) -> dict:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("expected object")
    for field in ("title", "url", "category"):
        if not str(data.get(field, "")).strip():
            raise ValueError("missing " + field)
    return data


async def cmd_add(message: Message, lang: str, command: CommandObject, db, engine) -> None:
    if not command.args:
        await message.answer(tr("admin_bad_json", lang))
        return
    try:
        data = parse_add_payload(command.args)
    except (ValueError, json.JSONDecodeError) as exc:
        await message.answer(tr("admin_bad_json", lang) + "\n<code>%s</code>" % exc)
        return
    rid, slug = await db.add_resource(
        title=data["title"], url=data["url"], category=data["category"],
        tags=[str(t) for t in data.get("tags", [])],
        ru=data.get("ru", data["title"]), en=data.get("en", ""),
    )
    await rebuild_index(engine, db)
    await message.answer(tr("admin_res_added", lang, title=data["title"], rid=rid))


async def cmd_export(message: Message, lang: str, db) -> None:
    items = await db.export_resources()
    payload = json.dumps(items, ensure_ascii=False, indent=1).encode("utf-8")
    await message.answer_document(
        BufferedInputFile(payload, filename="linktree_resources.json"),
        caption=tr("admin_export_ready", lang),
    )


async def cmd_import(message: Message, lang: str, state: FSMContext) -> None:
    await state.set_state(AdminStates.wait_import)
    await message.answer(tr("admin_import_prompt", lang))


async def import_file(message: Message, lang: str, state: FSMContext, db, engine) -> None:
    await state.clear()
    if not message.document:
        await message.answer(tr("admin_import_prompt", lang))
        await state.set_state(AdminStates.wait_import)
        return
    try:
        raw = await message.bot.download(message.document.file_id)
        items = json.loads(raw.read().decode("utf-8"))
        if not isinstance(items, list):
            raise ValueError("expected array")
    except Exception as exc:  # noqa: BLE001 — любая ошибка разбора
        await message.answer(tr("admin_import_bad", lang, err=exc))
        return
    added, updated = await db.import_resources(items)
    await rebuild_index(engine, db)
    await message.answer(tr("admin_import_done", lang, added=added, updated=updated))


# ---------------------------------------------------------------- рассылка

async def cmd_broadcast(message: Message, lang: str, command: CommandObject,
                        state: FSMContext, db) -> None:
    text = command.args or ""
    if not text and message.reply_to_message and message.reply_to_message.text:
        text = message.reply_to_message.text
    if not text:
        await state.set_state(AdminStates.wait_broadcast)
        await message.answer(tr("admin_bc_prompt", lang))
        return
    users = await db.all_user_ids()
    text_hash = str(hash(text.strip()))[-8:]
    store_broadcast(text_hash, text)
    markup = kb.admin_broadcast_confirm_kb(text_hash)
    await message.answer(tr("admin_bc_confirm", lang, users=len(users), preview=text),
                         reply_markup=markup, disable_web_page_preview=True)


async def broadcast_text(message: Message, lang: str, state: FSMContext, db) -> None:
    text = message.html_text if message.html_text else message.text
    await state.clear()
    users = await db.all_user_ids()
    text_hash = str(hash(text.strip()))[-8:]
    store_broadcast(text_hash, text)
    markup = kb.admin_broadcast_confirm_kb(text_hash)
    await message.answer(tr("admin_bc_confirm", lang, users=len(users), preview=text),
                         reply_markup=markup, disable_web_page_preview=True)


_BC_CACHE: dict = {}


async def cb_broadcast(callback: CallbackQuery, lang: str, db, bot: Bot) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    action = parts[1]
    if action == "no":
        try:
            await callback.message.delete()
        except Exception:  # noqa: BLE001
            pass
        await callback.answer(tr("cancelled", "ru"))
        return
    text = _BC_CACHE.pop(parts[2], None)
    if text is None:
        await callback.answer("⚠️ Текст рассылки потерян, отправь заново", show_alert=True)
        return
    users = await db.all_user_ids()
    sent = errors = 0
    for uid in users:
        try:
            await bot.send_message(uid, text, disable_web_page_preview=True)
            sent += 1
        except Exception:  # noqa: BLE001 — блокировки, остановки бота и т.п.
            errors += 1
        await asyncio.sleep(0.05)
    await callback.answer()
    await safe_edit(callback, tr("admin_bc_done", lang, sent=sent, errors=errors))


def store_broadcast(text_hash: str, text: str) -> None:
    _BC_CACHE[text_hash] = text
    if len(_BC_CACHE) > 20:
        for key in list(_BC_CACHE)[:-20]:
            _BC_CACHE.pop(key, None)


# ---------------------------------------------------------------- бан / reindex

async def cmd_ban(message: Message, lang: str, command: CommandObject, db,
                  middleware_cache) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("/ban <user_id>")
        return
    uid = int(command.args.strip())
    await db.ban_user(uid, True)
    middleware_cache.invalidate(uid)
    await message.answer(tr("admin_banned", lang, uid=uid))


async def cmd_unban(message: Message, lang: str, command: CommandObject, db,
                    middleware_cache) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("/unban <user_id>")
        return
    uid = int(command.args.strip())
    await db.ban_user(uid, False)
    middleware_cache.invalidate(uid)
    await message.answer(tr("admin_unbanned", lang, uid=uid))


async def cmd_reindex(message: Message, lang: str, db, engine) -> None:
    started = time.perf_counter()
    n = await rebuild_index(engine, db)
    ms = int((time.perf_counter() - started) * 1000)
    await message.answer(tr("admin_reindexed", lang, n=n, ms=ms))


# ---------------------------------------------------------------- регистрация

def create_router() -> Router:
    """Свежий Router с админскими хендлерами (фильтр админа на всём роутере)."""
    router = Router()
    router.message.filter(AdminFilter())
    router.callback_query.filter(AdminFilter())
    router.message.register(cmd_admin, Command("admin", "stats"))
    router.message.register(cmd_pending, Command("pending"))
    router.message.register(cmd_add, Command("add"))
    router.message.register(cmd_export, Command("export"))
    router.message.register(cmd_import, Command("import"))
    router.message.register(cmd_broadcast, Command("broadcast"))
    router.message.register(cmd_ban, Command("ban"))
    router.message.register(cmd_unban, Command("unban"))
    router.message.register(cmd_reindex, Command("reindex"))
    router.callback_query.register(cb_suggestion, F.data.startswith("sugg:"))
    router.callback_query.register(cb_broadcast, F.data.startswith("bc:"))
    router.message.register(import_file, StateFilter(AdminStates.wait_import))
    router.message.register(broadcast_text, StateFilter(AdminStates.wait_broadcast))
    return router
