"""Общий мок-бот и билдеры апдейтов для e2e-тестов диспетчеризации."""
from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.methods.base import TelegramMethod
from aiogram.types import Update


class MockBot(Bot):
    """Перехватывает любой исходящий метод Telegram API на уровне bot(method)."""

    def __init__(self):
        super().__init__(token="42:" + "A" * 30,
                         default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.calls = []  # dict(method=..., chat_id=..., text=..., ...)

    async def __call__(self, method: TelegramMethod, request_timeout=None):
        record = {"method": type(method).__name__}
        for field in ("chat_id", "text", "callback_query_id", "message_id",
                      "caption", "reply_markup", "show_alert", "document"):
            value = getattr(method, field, None)
            if value is not None:
                record[field] = value
        self.calls.append(record)
        return None

    def texts(self, method_name="SendMessage"):
        return [r.get("text") or r.get("caption") or ""
                for r in self.calls if r["method"] == method_name]

    def edits(self):
        return [r.get("text") or "" for r in self.calls if r["method"] == "EditMessageText"]

    def cb_answers(self):
        return [r.get("text") for r in self.calls if r["method"] == "AnswerCallbackQuery"]

    def last(self, method_name="SendMessage"):
        matching = [r for r in self.calls if r["method"] == method_name]
        return matching[-1] if matching else None


def make_update(payload: dict) -> Update:
    return Update.model_validate(payload)


def message_payload(user_id: int, text: str, msg_id: int = 10) -> dict:
    return {
        "update_id": msg_id,
        "message": {
            "message_id": msg_id,
            "from": {"id": user_id, "is_bot": False, "first_name": "Тест",
                     "username": "tester", "language_code": "ru"},
            "chat": {"id": user_id, "type": "private", "first_name": "Тест"},
            "date": 1730000000,
            "text": text,
        },
    }


def callback_payload(user_id: int, data: str, msg_id: int = 20) -> dict:
    return {
        "update_id": msg_id,
        "callback_query": {
            "id": "cbq%d" % msg_id,
            "from": {"id": user_id, "is_bot": False, "first_name": "Тест",
                     "username": "tester", "language_code": "ru"},
            "chat_instance": "ci",
            "data": data,
            "message": {
                "message_id": msg_id,
                "from": {"id": 42, "is_bot": True, "first_name": "LinkTree"},
                "chat": {"id": user_id, "type": "private", "first_name": "Тест"},
                "date": 1730000000,
                "text": "plan",
            },
        },
    }
