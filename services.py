"""Общие сервисные функции для хендлеров."""
from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from typing import List, Optional, Tuple

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from i18n import RU, cat_name, tr
from search.engine import Hit, ResourceDoc, SearchEngine

MAX_MESSAGE_LEN = 4000  # запас до телеграмного лимита 4096


class QueryCache:
    """LRU-кэш «хеш запроса → (user_id, текст)» для кнопки «Ещё»."""

    def __init__(self, capacity: int = 1000) -> None:
        self.capacity = capacity
        self._store: "OrderedDict[str, Tuple[int, str]]" = OrderedDict()

    @staticmethod
    def hash_query(text: str) -> str:
        return hashlib.blake2b(text.strip().lower().encode("utf-8"), digest_size=4).hexdigest()

    def put(self, user_id: int, text: str) -> str:
        h = self.hash_query(text)
        self._store[h] = (user_id, text.strip())
        self._store.move_to_end(h)
        while len(self._store) > self.capacity:
            self._store.popitem(last=False)
        return h

    def get(self, user_id: int, h: str) -> Optional[str]:
        item = self._store.get(h)
        if item is None or item[0] != user_id:
            return None
        self._store.move_to_end(h)
        return item[1]


async def rebuild_index(engine: SearchEngine, db) -> int:
    docs = await db.all_resources_for_index()
    await asyncio.to_thread(engine.rebuild, docs)
    return len(docs)


def score_percent(score: float) -> int:
    """Человеко-понятная релевантность 0..99%."""
    return max(1, min(99, int(round(min(score, 1.25) * 80))))


def format_hit(doc: ResourceDoc, position: int, score: float, lang: str) -> str:
    desc = doc.ru if lang == RU else (doc.en or doc.ru)
    badge = ""
    if doc.score > 0:
        badge = tr("pro_badge", lang)
    return tr(
        "res_card", lang,
        i=position, title=doc.title, badge=badge, url=doc.url, desc=desc,
        cat=cat_name(doc.category, lang), tags=", ".join(doc.tags[:6]),
    ) + tr("res_footer", lang, score=score_percent(score))


async def send_long(message: Message, text: str, reply_markup=None) -> None:
    """Отправка текста длиннее 4096 символов частями."""
    chunk = text[:MAX_MESSAGE_LEN]
    rest = text[MAX_MESSAGE_LEN:]
    # режем по границе строки, чтобы не рвать разметку
    if rest:
        cut = chunk.rfind("\n")
        if cut > MAX_MESSAGE_LEN // 2:
            chunk, rest = chunk[:cut], text[cut + 1:]
    await message.answer(chunk, reply_markup=reply_markup if not rest else None,
                         disable_web_page_preview=True)
    if rest:
        await send_long(message, rest)


async def safe_edit(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    try:
        await callback.message.edit_text(
            text, reply_markup=reply_markup, disable_web_page_preview=True,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        try:
            await callback.message.answer(text, reply_markup=reply_markup,
                                          disable_web_page_preview=True)
        except TelegramBadRequest:
            pass


def category_hints_from_query(text: str) -> "dict[str, float]":
    """Если в запросе упомянута категория («для питона», «по геймдеву») — буст в её сторону."""
    from i18n import CATEGORY_ALIASES
    from search.vectorizer import tokenize

    hints: "dict[str, float]" = {}
    for raw in tokenize(text):
        stem = raw[2:]
        cat = CATEGORY_ALIASES.get(stem)
        if cat:
            hints[cat] = hints.get(cat, 0.0) + 0.15
    return hints


def format_rel_list(hits: List[Hit], lang: str) -> str:
    lines = []
    for i, hit in enumerate(hits, 1):
        desc = hit.doc.ru if lang == RU else (hit.doc.en or hit.doc.ru)
        short = desc.split(". ")[0]
        lines.append("%d. <a href=\"%s\">%s</a> — %s" % (i, hit.doc.url, hit.doc.title, short))
    return "\n".join(lines)


def fmt_uptime(started_at: float) -> str:
    delta = int(time.time() - started_at)
    days, rem = divmod(delta, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append("%dд" % days)
    if hours:
        parts.append("%dч" % hours)
    parts.append("%dм" % minutes)
    return " ".join(parts)
