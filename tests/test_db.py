"""Тесты слоя данных на временной БД."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from db import Database, make_slug, pick_weekly_resource
from search.engine import ResourceDoc

SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed_resources.json"


@pytest.fixture()
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.connect()
    await database.seed_from_json(str(SEED_PATH))
    yield database
    await database.close()


class TestSchemaAndSeed:
    async def test_seed_idempotent(self, db):
        first = await db.resources_count()
        added = await db.seed_from_json(str(SEED_PATH))
        assert added == 0
        assert await db.resources_count() == first

    async def test_seed_counts(self, db):
        assert await db.resources_count() >= 180
        counts = await db.category_counts()
        assert counts["python"] >= 30
        assert sum(counts.values()) == await db.resources_count()

    async def test_indexes_have_votes(self, db):
        docs = await db.all_resources_for_index()
        assert all(isinstance(d, ResourceDoc) for d in docs)
        assert all(d.score == 0 for d in docs)  # голосов пока нет


class TestSlug:
    def test_translit(self):
        assert make_slug("Библиотека Графиков") == "biblioteka-grafikov"

    def test_special_chars(self):
        assert make_slug("C++ / C#!") == "c-c"

    def test_fallback(self):
        assert make_slug("!!!") == "resource"


class TestUsers:
    async def test_ensure_user(self, db):
        await db.ensure_user(1, "ru")
        user = await db.get_user(1)
        assert user["lang"] == "ru"
        await db.ensure_user(1, "ru")
        assert user["first_seen"] > 0

    async def test_set_lang(self, db):
        await db.ensure_user(1, "ru")
        await db.set_lang(1, "en")
        assert (await db.get_user(1))["lang"] == "en"

    async def test_ban_unban(self, db):
        await db.ensure_user(1, "ru")
        assert not await db.is_banned(1)
        await db.ban_user(1, True)
        assert await db.is_banned(1)
        assert 1 not in await db.all_user_ids()
        await db.ban_user(1, False)
        assert not await db.is_banned(1)

    async def test_digest_subscribers(self, db):
        await db.ensure_user(1, "ru")
        await db.ensure_user(2, "ru")
        await db.set_digest(1, True)
        assert await db.digest_subscribers() == [1]


class TestFavorites:
    async def test_add_remove(self, db):
        await db.fav_add(7, 1)
        assert await db.is_favorite(7, 1)
        assert not await db.is_favorite(7, 2)
        assert not await db.fav_add(7, 1)  # повторно — уже есть
        await db.fav_remove(7, 1)
        assert not await db.is_favorite(7, 1)

    async def test_list_order(self, db):
        await db.fav_add(7, 2)
        await db.fav_add(7, 1)
        favs = await db.fav_list(7)
        assert [f["id"] for f in favs] == [1, 2]  # новые сверху


class TestVotes:
    async def test_vote_flow(self, db):
        assert await db.user_vote(7, 1) == 0
        assert await db.vote(7, 1, 1) == 1
        assert await db.user_vote(7, 1) == 1
        await db.vote(7, 1, -1)  # смена голоса
        assert await db.user_vote(7, 1) == -1
        await db.vote(7, 1, 0)  # сброс
        assert await db.user_vote(7, 1) == 0

    async def test_net_votes_in_index(self, db):
        await db.vote(7, 1, 1)
        await db.vote(8, 1, 1)
        await db.vote(9, 1, -1)
        docs = {d.rid: d for d in await db.all_resources_for_index()}
        assert docs[1].score == 1
        await db.vote(9, 1, 0)
        docs = {d.rid: d for d in await db.all_resources_for_index()}
        assert docs[1].score == 2


class TestSuggestions:
    async def test_full_flow(self, db):
        sid = await db.suggestion_add(7, "Cool tool", "https://example.com", "python", "", "полезно")
        assert (await db.pending_count()) == 1
        item = await db.suggestion_decide(sid, "approved")
        assert item["title"] == "Cool tool"
        assert (await db.pending_count()) == 0
        assert await db.suggestion_decide(sid, "rejected") is None  # уже решено

    async def test_notify_fields(self, db):
        sid = await db.suggestion_add(7, "X", "https://x.dev", "tools", "", "")
        item = await db.suggestion_get(sid)
        assert item["user_id"] == 7
        assert item["status"] == "pending"


class TestQueries:
    async def test_log_and_top(self, db):
        await db.log_query(7, "pdf python", "pdfplumber")
        await db.log_query(8, "PDF python ", "pdfplumber")
        await db.log_query(9, "docker", "docker-compose")
        top = await db.top_queries_24h(5)
        assert top[0][0] == "pdf python"
        assert top[0][1] == 2
        assert await db.queries_count_24h() == 3


class TestResourcesCRUD:
    async def test_add_resource_slug_unique(self, db):
        rid1, slug1 = await db.add_resource("My Unique Tool", "https://x.dev", "python", ["api"], "desc")
        rid2, slug2 = await db.add_resource("My Unique Tool", "https://y.dev", "python", ["api"], "desc")
        assert rid1 != rid2
        assert slug1 == "my-unique-tool" and slug2 == "my-unique-tool-2"

    async def test_import_upsert_by_url(self, db):
        added, updated = await db.import_resources([
            {"title": "New", "url": "https://new.dev", "category": "tools", "tags": ["x"]},
        ])
        assert (added, updated) == (1, 0)
        count_before = await db.resources_count()
        added, updated = await db.import_resources([
            {"title": "New2", "url": "https://new.dev", "category": "python", "tags": []},
        ])
        assert (added, updated) == (0, 1)
        assert await db.resources_count() == count_before
        row = await db.get_resource_by_url("https://new.dev")
        assert row["title"] == "New2"

    async def test_export_shape(self, db):
        items = await db.export_resources()
        first = items[0]
        assert {"slug", "title", "url", "category", "tags", "ru", "en"} <= set(first)
        assert isinstance(first["tags"], list)

    async def test_category_pagination(self, db):
        page1 = await db.resources_in_category("python", limit=5, offset=0)
        page2 = await db.resources_in_category("python", limit=5, offset=5)
        assert len(page1) == 5
        assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})

    async def test_random(self, db):
        row = await db.random_resource()
        assert row is not None
        again = await db.random_resource(exclude_ids=[row["id"]])
        assert again["id"] != row["id"]


class TestMeta:
    async def test_roundtrip(self, db):
        assert await db.get_meta("k") is None
        await db.set_meta("k", "v1")
        assert await db.get_meta("k") == "v1"
        await db.set_meta("k", "v2")
        assert await db.get_meta("k") == "v2"


class TestWeeklyPick:
    def test_deterministic(self):
        rows = [{"title": str(i)} for i in range(10)]
        assert pick_weekly_resource(rows, 5) == pick_weekly_resource(rows, 5)

    def test_rotates(self):
        rows = [{"title": str(i)} for i in range(10)]
        picks = {json.dumps(pick_weekly_resource(rows, w)) for w in range(10)}
        assert len(picks) > 1

    def test_empty(self):
        assert pick_weekly_resource([], 1) is None
