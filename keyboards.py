"""Клавиатуры: главное меню (reply) и инлайн-кнопки результатов/категорий."""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from i18n import CATEGORIES, EN, RU, tr

# Тексты reply-кнопок (маршрутизируются в хендлерах)
BTN_PLAN = {RU: "🧩 Разбор задачи", EN: "🧩 Task breakdown"}
BTN_SEARCH = {RU: "🔍 Как искать", EN: "🔍 How to search"}
BTN_CATS = {RU: "🗂 Категории", EN: "🗂 Categories"}
BTN_RANDOM = {RU: "🎲 Случайный", EN: "🎲 Random"}
BTN_FAV = {RU: "⭐ Избранное", EN: "⭐ Favorites"}
BTN_SUGGEST = {RU: "💡 Предложить", EN: "💡 Suggest"}
BTN_LANG = {RU: "🌐 Language", EN: "🌐 Language"}

MENU_BUTTONS = (BTN_PLAN, BTN_SEARCH, BTN_CATS, BTN_RANDOM, BTN_FAV, BTN_SUGGEST, BTN_LANG)


def all_menu_texts() -> set:
    return {text for btn in MENU_BUTTONS for text in btn.values()}


def main_menu(lang: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=BTN_PLAN[lang]), KeyboardButton(text=BTN_CATS[lang]),
    )
    builder.row(
        KeyboardButton(text=BTN_RANDOM[lang]), KeyboardButton(text=BTN_FAV[lang]),
    )
    builder.row(
        KeyboardButton(text=BTN_SUGGEST[lang]), KeyboardButton(text=BTN_SEARCH[lang]),
    )
    builder.row(KeyboardButton(text=BTN_LANG[lang]))
    return builder.as_markup(resize_keyboard=True)


def lang_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=tr("lang_btn", RU), callback_data="lang:ru")
    builder.button(text=tr("lang_btn", EN), callback_data="lang:en")
    builder.adjust(2)
    return builder.as_markup()


def categories_kb(counts: Dict[str, int], lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key in sorted(CATEGORIES, key=lambda k: -counts.get(k, 0)):
        if counts.get(key, 0) <= 0:
            continue
        builder.button(text="%s · %d" % (i18n_cat(key, lang), counts[key]),
                       callback_data="cat:%s:0" % key)
    builder.adjust(2)
    return builder.as_markup()


def i18n_cat(key: str, lang: str) -> str:
    from i18n import cat_name
    return cat_name(key, lang)


def category_page_kb(category: str, offset: int, total: int, page_size: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav: List[InlineKeyboardButton] = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text=tr("prev_btn", lang),
                                        callback_data="cat:%s:%d" % (category, max(offset - page_size, 0))))
    if offset + page_size < total:
        nav.append(InlineKeyboardButton(text=tr("next_btn", lang),
                                        callback_data="cat:%s:%d" % (category, offset + page_size)))
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text=tr("back_to_cats_btn", lang), callback_data="cats"))
    return builder.as_markup()


def results_kb(hits: Sequence, offset: int, total_hits: int, lang: str,
               fav_ids: Iterable[int], query_hash: Optional[str] = None) -> InlineKeyboardMarkup:
    """Клавиатура под страницей результатов: 2 строки на ресурс + навигация."""
    builder = InlineKeyboardBuilder()
    fav_set = set(fav_ids)
    for hit in hits:
        rid = hit.doc.rid
        fav_label = tr("fav_del_btn", lang) if rid in fav_set else tr("fav_add_btn", lang)
        builder.row(
            InlineKeyboardButton(text=tr("open_btn", lang), url=hit.doc.url),
            InlineKeyboardButton(text=fav_label, callback_data="fav:%d" % rid),
        )
        builder.row(
            InlineKeyboardButton(text=tr("up_btn", lang), callback_data="vote:up:%d" % rid),
            InlineKeyboardButton(text=tr("down_btn", lang), callback_data="vote:down:%d" % rid),
            InlineKeyboardButton(text=tr("related_btn", lang), callback_data="rel:%d" % rid),
        )
    if query_hash and offset < total_hits:
        builder.row(InlineKeyboardButton(text=tr("more_btn", lang),
                                         callback_data="more:%s:%d" % (query_hash, offset)))
    return builder.as_markup()


def single_resource_kb(rid: int, url: str, lang: str, is_fav: bool = False,
                       random_btn: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    fav_label = tr("fav_del_btn", lang) if is_fav else tr("fav_add_btn", lang)
    builder.row(
        InlineKeyboardButton(text=tr("open_btn", lang), url=url),
        InlineKeyboardButton(text=fav_label, callback_data="fav:%d" % rid),
    )
    builder.row(
        InlineKeyboardButton(text=tr("up_btn", lang), callback_data="vote:up:%d" % rid),
        InlineKeyboardButton(text=tr("down_btn", lang), callback_data="vote:down:%d" % rid),
        InlineKeyboardButton(text=tr("related_btn", lang), callback_data="rel:%d" % rid),
    )
    if random_btn:
        builder.row(InlineKeyboardButton(text=tr("random_btn", lang), callback_data="rnd"))
    return builder.as_markup()


def favorites_kb(favs: Sequence, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row in favs:
        builder.row(
            InlineKeyboardButton(text=str(row["title"])[:40], url=row["url"]),
            InlineKeyboardButton(text=tr("fav_del_btn", lang),
                                 callback_data="favdel:%d" % row["id"]),
        )
    return builder.as_markup()


def suggest_categories_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    from i18n import CATEGORIES
    for key in CATEGORIES:
        builder.button(text=key, callback_data="suggcat:%s" % key)
    builder.adjust(3)
    return builder.as_markup()


def admin_suggestion_kb(sid: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅", callback_data="sugg:ok:%d" % sid),
        InlineKeyboardButton(text="🗑", callback_data="sugg:no:%d" % sid),
    )
    return builder.as_markup()


def admin_broadcast_confirm_kb(text_hash: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Отправить", callback_data="bc:yes:%s" % text_hash),
        InlineKeyboardButton(text="🗑 Отмена", callback_data="bc:no:0"),
    )
    return builder.as_markup()


def cancel_kb(lang: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="/cancel"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def scale_kb(lang: str, include_dontknow: bool = False) -> ReplyKeyboardMarkup:
    """Шкала ответа 1..5 для анкеты разбора задачи."""
    builder = ReplyKeyboardBuilder()
    row = [KeyboardButton(text=str(n)) for n in range(1, 6)]
    if include_dontknow:
        row.append(KeyboardButton(text=tr("plan_dontknow_btn", lang)))
    builder.row(*row)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def plan_steps_kb(items: list, plan_id: int, lang: str) -> InlineKeyboardMarkup:
    """Клавиатура под планом: на каждый pending-шаг — открыть/сделал/заменить."""
    builder = InlineKeyboardBuilder()
    for item in items:
        if item["status"] != "pending":
            continue
        buttons = []
        if item.get("url"):
            buttons.append(InlineKeyboardButton(text=tr("open_btn", lang), url=item["url"]))
        buttons.append(InlineKeyboardButton(text=tr("plan_done_btn", lang),
                                            callback_data="pl:done:%d" % item["id"]))
        buttons.append(InlineKeyboardButton(text=tr("plan_skip_btn", lang),
                                            callback_data="pl:skip:%d" % item["id"]))
        builder.row(*buttons)
    builder.row(InlineKeyboardButton(text=tr("plan_close_btn", lang),
                                     callback_data="pl:del:%d" % plan_id))
    return builder.as_markup()


def plans_list_kb(plans: list, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        label = "%s · %d ⬜" % (str(plan["query"])[:28], plan["pending"])
        builder.row(InlineKeyboardButton(text=label,
                                         callback_data="pl:view:%d" % plan["id"]))
    return builder.as_markup()
