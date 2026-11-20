"""Тесты middlewares на заглушках."""
from __future__ import annotations

import asyncio

from middlewares import ErrorMiddleware, ThrottlingMiddleware, UserContextMiddleware


class FakeUser:
    def __init__(self, uid=1):
        self.id = uid
        self.is_bot = False


class FakeMessage:
    def __init__(self, answers=None):
        self.from_user = FakeUser()
        self.chat = None  # признак «сообщения» для утиной типизации
        self._answers = answers if answers is not None else []

    async def answer(self, text, **kwargs):
        self._answers.append(text)


class FakeCallback:
    def __init__(self):
        self.from_user = FakeUser()
        self.alerts = []

    async def answer(self, text=None, show_alert=False, **kwargs):
        self.alerts.append(text)


class FakeState:
    def __init__(self, state=None):
        self._state = state

    async def get_state(self):
        return self._state


class FakeDB:
    def __init__(self, users=None, banned=()):
        self.users = users or {}
        self.banned = set(banned)

    async def is_banned(self, uid):
        return uid in self.banned

    async def ensure_user(self, uid, lang="ru"):
        self.users.setdefault(uid, {"lang": lang})

    async def get_user(self, uid):
        return self.users.get(uid)


class TestThrottling:
    async def test_under_limit_passes(self):
        mw = ThrottlingMiddleware(limit=3, window=10.0)
        called = 0

        async def handler(event, data):
            nonlocal called
            called += 1
            return "ok"

        for _ in range(3):
            result = await mw(handler, FakeMessage(), {"event_from_user": FakeUser()})
            assert result == "ok"
        assert called == 3

    async def test_over_limit_blocks(self):
        mw = ThrottlingMiddleware(limit=2, window=10.0)
        called = 0

        async def handler(event, data):
            nonlocal called
            called += 1

        msg = FakeMessage()
        for _ in range(5):
            await mw(handler, msg, {"event_from_user": FakeUser(), "lang": "ru"})
        assert called == 2
        assert msg._answers, "должно прийти предупреждение о флуде"

    async def test_window_recovery(self):
        mw = ThrottlingMiddleware(limit=2, window=0.05)
        called = 0

        async def handler(event, data):
            nonlocal called
            called += 1

        for _ in range(3):
            await mw(handler, FakeMessage(), {"event_from_user": FakeUser()})
        await asyncio.sleep(0.1)
        await mw(handler, FakeMessage(), {"event_from_user": FakeUser()})
        assert called == 3  # 2 прошли, 1 срезан, после окна — ещё один прошёл

    async def test_no_user_passes(self):
        mw = ThrottlingMiddleware(limit=1, window=10.0)
        marker = object()

        async def handler(event, data):
            return marker

        assert await mw(handler, FakeMessage(), {}) is marker

    async def test_fsm_dialog_not_counted(self):
        """Сообщения в FSM-анкете не занимают слоты окна."""
        mw = ThrottlingMiddleware(limit=3, window=10.0)
        called = 0

        async def handler(event, data):
            nonlocal called
            called += 1
            return "ok"

        state = FakeState("PlanStates:query")
        for _ in range(8):  # лимит 3 — без exemта всё бы срезалось
            assert await mw(handler, FakeMessage(),
                            {"event_from_user": FakeUser(), "state": state}) == "ok"
        assert called == 8
        # после выхода из FSM окно чистое
        state._state = None
        assert mw._events == {}
        assert await mw(handler, FakeMessage(),
                        {"event_from_user": FakeUser(), "state": state}) == "ok"

    async def test_callbacks_bypass_throttle(self):
        mw = ThrottlingMiddleware(limit=1, window=10.0)
        called = 0

        async def handler(event, data):
            nonlocal called
            called += 1

        cb = FakeCallback()
        for _ in range(5):
            await mw(handler, cb, {"event_from_user": FakeUser()})
        assert called == 5


class TestUserContext:
    async def test_lang_injected(self):
        db = FakeDB(users={1: {"lang": "en"}})
        mw = UserContextMiddleware(db)
        seen = {}

        async def handler(event, data):
            seen.update(data)
            return "ok"

        result = await mw(handler, FakeMessage(), {"event_from_user": FakeUser(1)})
        assert result == "ok"
        assert seen["lang"] == "en"

    async def test_banned_user_blocked(self):
        db = FakeDB(banned={5})
        mw = UserContextMiddleware(db)
        called = False

        async def handler(event, data):
            nonlocal called
            called = True

        msg = FakeMessage()
        result = await mw(handler, msg, {"event_from_user": FakeUser(5)})
        assert result is None
        assert not called
        assert msg._answers, "забаненный должен получить уведомление"

    async def test_new_user_created_with_ru(self):
        db = FakeDB()
        mw = UserContextMiddleware(db)
        seen = {}

        async def handler(event, data):
            seen.update(data)

        await mw(handler, FakeMessage(), {"event_from_user": FakeUser(9)})
        assert seen["lang"] == "ru"
        assert 9 in db.users

    async def test_invalidate(self):
        db = FakeDB(users={1: {"lang": "en"}})
        mw = UserContextMiddleware(db)
        seen = {}

        async def handler(event, data):
            seen.update(data)

        await mw(handler, FakeMessage(), {"event_from_user": FakeUser(1)})
        db.users[1]["lang"] = "ru"
        mw.invalidate(1)
        await mw(handler, FakeMessage(), {"event_from_user": FakeUser(1)})
        assert seen["lang"] == "ru"


class TestErrorMiddleware:
    async def test_catches_and_answers(self):
        mw = ErrorMiddleware()
        msg = FakeMessage()

        async def handler(event, data):
            raise RuntimeError("boom")

        assert await mw(handler, msg, {"lang": "ru"}) is None
        assert msg._answers, "пользователь должен получить сообщение об ошибке"

    async def test_passes_ok(self):
        mw = ErrorMiddleware()

        async def handler(event, data):
            return "fine"

        assert await mw(handler, FakeMessage(), {"lang": "ru"}) == "fine"
