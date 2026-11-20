"""Middlewares: регистрация пользователя + язык, антифлуд, перехват ошибок."""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from i18n import DEFAULT_LANG, tr

log = logging.getLogger("linktree")

USER_TTL = 600.0  # кэш ensure_user на 10 минут, чтобы не дёргать БД на каждое сообщение


def _is_message_like(event: Any) -> bool:
    """Message отличается от CallbackQuery наличием .chat (работает и с заглушками)."""
    return hasattr(event, "chat")


async def notify(event: Any, text: str) -> None:
    """Аккуратно доставить пользователю уведомление, не роняя обработку."""
    try:
        if _is_message_like(event):
            await event.answer(text)
        else:
            await event.answer(text, show_alert=True)
    except Exception:  # noqa: BLE001 — уведомление не должно ломать апдейт
        log.debug("notify failed", exc_info=True)


class UserContextMiddleware(BaseMiddleware):
    """Готовит пользователя: ensure_user, язык, проверка бана. Инжектит lang в хендлеры."""

    def __init__(self, db) -> None:
        self.db = db
        self._seen: dict = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)
        if await self.db.is_banned(user.id):
            await notify(event, tr("banned_notice", data.get("lang", DEFAULT_LANG)))
            return None
        now = time.monotonic()
        cached = self._seen.get(user.id)
        if cached is None or now - cached[0] > USER_TTL:
            await self.db.ensure_user(user.id, DEFAULT_LANG)
            row = await self.db.get_user(user.id)
            self._seen[user.id] = (now, row["lang"] if row else DEFAULT_LANG)
        data["lang"] = self._seen[user.id][1]
        return await handler(event, data)

    def invalidate(self, user_id: int) -> None:
        self._seen.pop(user_id, None)


class ThrottlingMiddleware(BaseMiddleware):
    """Простое окно: не более `limit` событий за `window` секунд на пользователя.

    Активное FSM-состояние (анкета разбора задачи, предложение ресурса) не считается
    флудом: пользователь по определению шлёт много коротких сообщений подряд.
    """

    def __init__(self, limit: int = 8, window: float = 10.0, fsm_limit: int = 30) -> None:
        self.limit = limit
        self.window = window
        self.fsm_limit = fsm_limit
        self._events: defaultdict = defaultdict(deque)
        self._warned: dict = {}

    async def _state_active(self, data: dict) -> bool:
        state = data.get("state")
        if state is None:
            return False
        try:
            return await state.get_state() is not None
        except Exception:  # noqa: BLE001 — состояние недоступно — считаем обычным режимом
            return False

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or not _is_message_like(event):
            # колбэки — клики по кнопкам, выданным самим ботом: не троттлим
            return await handler(event, data)
        if await self._state_active(data):
            # пошаговый диалог (анкета, предложение): короткие сообщения — норма,
            # не считаем их против окна
            return await handler(event, data)
        now = time.monotonic()
        limit = self.limit
        q = self._events[user.id]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= limit:
            last_warn = self._warned.get(user.id)
            if last_warn is None or now - last_warn > self.window:
                self._warned[user.id] = now
                await notify(event, tr("flood_warning", data.get("lang", DEFAULT_LANG)))
            return None
        q.append(now)
        return await handler(event, data)


class ErrorMiddleware(BaseMiddleware):
    """Ловит исключения хендлеров, логирует и вежливо отвечает пользователю."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            log.exception("Unhandled error in handler")
            await notify(event, tr("error_generic", data.get("lang", DEFAULT_LANG)))
            return None
