"""Пользовательские хендлеры: поиск, категории, случайное, избранное, голоса, предложения."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import keyboards as kb
from i18n import CATEGORIES, EN, RU, cat_name, plural_ru, tr
from services import (QueryCache, category_hints_from_query, format_hit, format_rel_list,
                      safe_edit, send_long)

log = logging.getLogger("linktree.user")

_MENU_TEXTS = kb.all_menu_texts()


class SuggestStates(StatesGroup):
    title = State()
    url = State()
    category = State()
    comment = State()


# ---------------------------------------------------------------- старт / общие

async def cmd_start(message: Message, lang: str) -> None:
    name = message.from_user.first_name if message.from_user else "friend"
    await message.answer(tr("start_hello", lang, name=name),
                         reply_markup=kb.main_menu(lang), disable_web_page_preview=True)


async def cmd_help(message: Message, lang: str) -> None:
    await send_long(message, tr("help", lang))


async def cmd_about(message: Message, lang: str) -> None:
    await message.answer(tr("about", lang), disable_web_page_preview=True)


async def cmd_ping(message: Message, lang: str, started_at: float) -> None:
    from services import fmt_uptime
    await message.answer(tr("ping_ok", lang, uptime=fmt_uptime(started_at)))


async def btn_search_hint(message: Message, lang: str) -> None:
    await message.answer(tr("search_hint", lang))


async def cmd_lang(message: Message, lang: str) -> None:
    await message.answer("Language / Язык", reply_markup=kb.lang_kb())


async def cb_lang(callback: CallbackQuery, db, cfg, middleware_cache, lang: str) -> None:
    parts = callback.data.split(":")
    new_lang = parts[1] if len(parts) > 1 else RU
    if new_lang not in (RU, EN):
        new_lang = RU
    await db.ensure_user(callback.from_user.id, new_lang)
    await db.set_lang(callback.from_user.id, new_lang)
    middleware_cache.invalidate(callback.from_user.id)
    await callback.answer(tr("lang_set", new_lang))
    await safe_edit(callback, tr("lang_set", new_lang), reply_markup=kb.main_menu(new_lang))


# ---------------------------------------------------------------- поиск

async def do_search(message: Message, query: str, lang: str, db, engine, qcache: QueryCache,
                    page: int = 0) -> None:
    hints = category_hints_from_query(query)
    hits = await engine.search_async(query, k=20, category_hints=hints)
    if not hits:
        counts = await db.category_counts()
        await message.answer(tr("no_results", lang), reply_markup=kb.categories_kb(counts, lang))
        return
    await db.log_query(message.from_user.id, query, hits[0].doc.slug if hits else "")
    await db.bump_search_count(message.from_user.id)
    qh = qcache.put(message.from_user.id, query)
    await render_results(message, query, hits, page, lang, db, qh)


async def render_results(message: Message, query: str, hits, page: int, lang: str, db,
                         qh: str) -> None:
    from config import load_config
    per_page = load_config().results_per_page
    start = page * per_page
    chunk = hits[start : start + per_page]
    if not chunk:
        await message.answer(tr("no_results", lang))
        return
    fav_ids = {row["id"] for row in await db.fav_list(message.from_user.id)}
    lines = [format_hit(hit.doc, start + i + 1, hit.score, lang) for i, hit in enumerate(chunk)]
    text = tr("results_header", lang, query=query, rank=start + 1, total=len(hits))
    text += "\n\n".join(lines)
    markup = kb.results_kb(chunk, start + per_page, len(hits), lang, fav_ids, query_hash=qh)
    await send_long(message, text, reply_markup=markup)


async def search_message(message: Message, lang: str, db, engine, qcache: QueryCache) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer(tr("unknown_message", lang))
        return
    await do_search(message, query, lang, db, engine, qcache)


async def cb_more(callback: CallbackQuery, lang: str, db, engine, qcache: QueryCache) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, qh, page_raw = parts
    query = qcache.get(callback.from_user.id, qh)
    if query is None:
        await callback.answer(tr("no_results", lang).split(".")[0] + " — повтори запрос 🔁",
                              show_alert=True)
        return
    hints = category_hints_from_query(query)
    hits = await engine.search_async(query, k=20, category_hints=hints)
    if not hits:
        await callback.answer()
        return
    fav_ids = {row["id"] for row in await db.fav_list(callback.from_user.id)}
    from config import load_config
    per_page = load_config().results_per_page
    start = int(page_raw) * per_page
    chunk = hits[start : start + per_page]
    if not chunk:
        await callback.answer()
        return
    lines = [format_hit(hit.doc, start + i + 1, hit.score, lang) for i, hit in enumerate(chunk)]
    text = tr("results_header", lang, query=query, rank=start + 1, total=len(hits))
    text += "\n\n".join(lines)
    markup = kb.results_kb(chunk, start + per_page, len(hits), lang, fav_ids, query_hash=qh)
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------------------------------------------------------------- категории

async def cmd_cats(message: Message, lang: str, db) -> None:
    counts = await db.category_counts()
    text = tr("cats_header", lang) + "\n".join(
        "• %s — %d %s" % (cat_name(key, lang), counts[key], plural_ru(counts[key], lang))
        for key in sorted(CATEGORIES, key=lambda k: -counts.get(k, 0)) if counts.get(key)
    )
    await message.answer(text, reply_markup=kb.categories_kb(counts, lang))


async def cb_cats(callback: CallbackQuery, lang: str, db) -> None:
    await cmd_cats(callback.message, lang, db)
    await callback.answer()


async def cb_category(callback: CallbackQuery, lang: str, db) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    category, offset = parts[1], int(parts[2])
    from config import load_config
    per_page = load_config().results_per_page * 2
    rows = await db.resources_in_category(category, limit=per_page, offset=offset)
    total = (await db.category_counts()).get(category, 0)
    lines = []
    for i, row in enumerate(rows, start=offset + 1):
        desc = row["description_ru"] if lang == RU else (row["description_en"] or row["description_ru"])
        lines.append("%d. <a href=\"%s\">%s</a> — %s" % (i, row["url"], row["title"], desc.split(". ")[0]))
    text = tr("cat_items_header", lang, cat=cat_name(category, lang), count=total,
              word=plural_ru(total, lang)) + "\n".join(lines)
    markup = kb.category_page_kb(category, offset, total, per_page, lang)
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------------------------------------------------------------- случайное

async def cmd_random(message: Message, lang: str, db, engine) -> None:
    row = await db.random_resource()
    if row is None:
        await message.answer(tr("no_results", lang))
        return
    await send_resource_card(message, row, lang, db, random_btn=True)


async def cb_random(callback: CallbackQuery, lang: str, db) -> None:
    row = await db.random_resource()
    if row is None:
        await callback.answer()
        return
    await send_resource_card(callback.message, row, lang, db, random_btn=True)
    await callback.answer()


async def send_resource_card(message: Message, row: dict, lang: str, db, random_btn: bool = False) -> None:
    desc = row["description_ru"] if lang == RU else (row.get("description_en") or row["description_ru"])
    is_fav = await db.is_favorite(message.chat.id, row["id"])
    text = tr("res_card", lang, i="🎲", title=row["title"], badge="", url=row["url"], desc=desc,
              cat=cat_name(row["category"], lang), tags=", ".join(row["tags"][:6]))
    markup = kb.single_resource_kb(row["id"], row["url"], lang, is_fav=is_fav,
                                   random_btn=random_btn)
    await send_long(message, text, reply_markup=markup)


# ---------------------------------------------------------------- избранное

async def cmd_fav(message: Message, lang: str, db) -> None:
    favs = await db.fav_list(message.from_user.id)
    if not favs:
        await message.answer(tr("fav_empty", lang))
        return
    lines = ["%d. <a href=\"%s\">%s</a>" % (i, row["url"], row["title"])
             for i, row in enumerate(favs, 1)]
    await message.answer(tr("fav_header", lang) + "\n".join(lines),
                         reply_markup=kb.favorites_kb(favs, lang), disable_web_page_preview=True)


async def cb_fav(callback: CallbackQuery, lang: str, db) -> None:
    try:
        rid = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer()
        return
    user_id = callback.from_user.id
    if await db.is_favorite(user_id, rid):
        await callback.answer(tr("fav_removed", lang))
    else:
        await db.fav_add(user_id, rid)
        await callback.answer(tr("fav_added", lang))
    await _refresh_fav_button(callback, rid, lang, db)


async def cb_favdel(callback: CallbackQuery, lang: str, db) -> None:
    try:
        rid = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer()
        return
    await db.fav_remove(callback.from_user.id, rid)
    await callback.answer(tr("fav_removed", lang))
    favs = await db.fav_list(callback.from_user.id)
    if not favs:
        await safe_edit(callback, tr("fav_empty", lang))
        return
    lines = ["%d. <a href=\"%s\">%s</a>" % (i, row["url"], row["title"])
             for i, row in enumerate(favs, 1)]
    await safe_edit(callback, tr("fav_header", lang) + "\n".join(lines),
                    kb.favorites_kb(favs, lang))


async def _refresh_fav_button(callback: CallbackQuery, rid: int, lang: str, db) -> None:
    """Перерисовываем кнопку избранного в текущем сообщении, сохраняя остальное."""
    try:
        markup = callback.message.reply_markup
        if markup is None:
            return
        is_fav = await db.is_favorite(callback.from_user.id, rid)
        label = tr("fav_del_btn", lang) if is_fav else tr("fav_add_btn", lang)
        data_old = "fav:%d" % rid
        found = False
        for row in markup.inline_keyboard:
            for button in row:
                if button.callback_data == data_old:
                    button.text = label
                    found = True
        if found:
            from aiogram.exceptions import TelegramBadRequest
            try:
                await callback.message.edit_reply_markup(reply_markup=markup)
            except TelegramBadRequest:
                pass
    except Exception:  # noqa: BLE001 — косметика, не роняем флоу
        log.debug("fav button refresh failed", exc_info=True)


# ---------------------------------------------------------------- голоса

async def cb_vote(callback: CallbackQuery, lang: str, db) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    value = 1 if parts[1] == "up" else -1
    try:
        rid = int(parts[2])
    except ValueError:
        await callback.answer()
        return
    current = await db.user_vote(callback.from_user.id, rid)
    if current == value:
        await db.vote(callback.from_user.id, rid, 0)
        await callback.answer(tr("vote_reset", lang))
    else:
        await db.vote(callback.from_user.id, rid, value)
        await callback.answer(tr("vote_saved", lang))


# ---------------------------------------------------------------- похожие

async def cb_related(callback: CallbackQuery, lang: str, engine) -> None:
    try:
        rid = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer()
        return
    hits = await engine.related_async(rid, k=5)
    if not hits:
        await callback.answer(tr("related_empty", lang), show_alert=True)
        return
    doc = engine.get(rid)
    title = doc.title if doc else "?"
    await safe_edit(callback, tr("related_header", lang, title=title, list=format_rel_list(hits, lang)))
    await callback.answer()


# ---------------------------------------------------------------- предложения

async def cmd_suggest(message: Message, lang: str, state: FSMContext) -> None:
    await state.set_state(SuggestStates.title)
    await message.answer(tr("suggest_intro", lang), reply_markup=kb.cancel_kb(lang))


async def suggest_title(message: Message, lang: str, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip()[:120])
    await state.set_state(SuggestStates.url)
    await message.answer(tr("suggest_url", lang))


async def suggest_url(message: Message, lang: str, state: FSMContext) -> None:
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer(tr("invalid_url", lang))
        return
    await state.update_data(url=url[:300])
    await state.set_state(SuggestStates.category)
    await message.answer(tr("suggest_category", lang), reply_markup=kb.suggest_categories_kb())


async def cb_suggest_category(callback: CallbackQuery, lang: str, state: FSMContext) -> None:
    category = callback.data.split(":", 1)[1]
    if category not in CATEGORIES:
        category = "tools"
    await state.update_data(category=category)
    await state.set_state(SuggestStates.comment)
    await callback.message.answer(tr("suggest_comment", lang))
    await callback.answer()


async def suggest_comment(message: Message, lang: str, state: FSMContext, db, cfg,
                          bot) -> None:
    data = await state.get_data()
    comment = message.text.strip()
    if comment in ("/", "-"):
        comment = ""
    sid = await db.suggestion_add(
        message.from_user.id, data["title"], data["url"], data.get("category", "tools"),
        "", comment[:500],
    )
    await state.clear()
    await message.answer(tr("suggest_done", lang), reply_markup=kb.main_menu(lang))
    card = tr("sugg_card", "ru", sid=sid, user=message.from_user.full_name,
              title=data["title"], url=data["url"], cat=data.get("category", "tools"),
              comment=comment or "—")
    for admin_id in cfg.admin_ids:
        try:
            await bot.send_message(admin_id, card, reply_markup=kb.admin_suggestion_kb(sid))
        except Exception:  # noqa: BLE001 — админ мог не запустить бота
            log.warning("не доставить предложение админу %s", admin_id)


async def cmd_cancel(message: Message, lang: str, state: FSMContext) -> None:
    await state.clear()
    await message.answer(tr("cancelled", lang), reply_markup=kb.main_menu(lang))


# ---------------------------------------------------------------- дайджест

async def cmd_digest(message: Message, lang: str, db) -> None:
    user = await db.get_user(message.from_user.id)
    enabled = not (user and user["digest"])
    await db.set_digest(message.from_user.id, enabled)
    await message.answer(tr("digest_on", lang) if enabled else tr("digest_off", lang))


# ---------------------------------------------------------------- fallback

async def non_text_fallback(message: Message, lang: str) -> None:
    await message.answer(tr("unknown_message", lang))


# ---------------------------------------------------------------- регистрация

def menu_text_filter(message: Message) -> bool:
    return bool(message.text and message.text in _MENU_TEXTS)


def search_btn_filter(message: Message) -> bool:
    """Только кнопка «Как искать» — у остальных кнопок свои хендлеры."""
    return message.text in (kb.BTN_SEARCH["ru"], kb.BTN_SEARCH["en"])


def search_text_filter(message: Message) -> bool:
    """Любой текст: не команда, не кнопка меню — значит поисковый запрос."""
    text = message.text
    if not text:
        return False
    return not text.startswith("/") and text not in _MENU_TEXTS


def non_text_filter(message: Message) -> bool:
    """Сообщения без текста (стикеры, фото, войсы) — вежливый fallback."""
    return message.text is None and message.content_type != "unknown"


def create_router() -> Router:
    """Свежий Router с зарегистрированными пользовательскими хендлерами.
    Фабрика нужна: один Router можно подключить только к одному Dispatcher."""
    router = Router()
    router.message.filter(F.chat.type == "private")
    router.message.register(cmd_start, Command("start"))
    router.message.register(cmd_help, Command("help"))
    router.message.register(cmd_about, Command("about"))
    router.message.register(cmd_ping, Command("ping"))
    router.message.register(cmd_lang, Command("lang"))
    router.message.register(cmd_suggest, Command("suggest"))
    router.message.register(cmd_digest, Command("digest"))
    router.message.register(cmd_cats, Command("cats"))
    router.message.register(cmd_random, Command("random"))
    router.message.register(cmd_fav, Command("fav", "favorites"))
    router.message.register(cmd_cancel, Command("cancel"))
    router.message.register(btn_search_hint, search_btn_filter)
    router.callback_query.register(cb_lang, F.data.startswith("lang:"))
    router.callback_query.register(cb_more, F.data.startswith("more:"))
    router.callback_query.register(cb_cats, F.data == "cats")
    router.callback_query.register(cb_category, F.data.startswith("cat:"))
    router.callback_query.register(cb_random, F.data == "rnd")
    router.callback_query.register(cb_fav, F.data.startswith("fav:"))
    router.callback_query.register(cb_favdel, F.data.startswith("favdel:"))
    router.callback_query.register(cb_vote, F.data.startswith("vote:"))
    router.callback_query.register(cb_related, F.data.startswith("rel:"))
    router.callback_query.register(cb_suggest_category, F.data.startswith("suggcat:"))
    router.message.register(suggest_title, StateFilter(SuggestStates.title), F.text)
    router.message.register(suggest_url, StateFilter(SuggestStates.url), F.text)
    router.message.register(suggest_comment, StateFilter(SuggestStates.comment), F.text)
    # поиск — последний среди текстовых, чтобы не перехватывать команды/кнопки
    router.message.register(search_message, search_text_filter)
    router.message.register(non_text_fallback, non_text_filter)
    return router
