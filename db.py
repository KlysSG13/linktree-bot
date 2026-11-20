"""Хранилище: SQLite через aiosqlite. Ресурсы, пользователи, избранное, голоса,
предложения, лог запросов."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import aiosqlite

from search.engine import ResourceDoc

SCHEMA = """
CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    category TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    description_ru TEXT NOT NULL DEFAULT '',
    description_en TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'seed',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    lang TEXT NOT NULL DEFAULT 'ru',
    digest INTEGER NOT NULL DEFAULT 0,
    banned INTEGER NOT NULL DEFAULT 0,
    search_count INTEGER NOT NULL DEFAULT 0,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS favorites (
    user_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, resource_id)
);
CREATE TABLE IF NOT EXISTS votes (
    user_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    value INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, resource_id)
);
CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    category TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    comment TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    decided_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    top_slug TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    query TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    candidates TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plans_user ON plans(user_id, status);
CREATE TABLE IF NOT EXISTS plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    resource_id INTEGER,
    title TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'tools',
    tags TEXT NOT NULL DEFAULT '[]',
    custom INTEGER NOT NULL DEFAULT 0,
    weight REAL NOT NULL DEFAULT 0,
    complexity REAL NOT NULL DEFAULT 0,
    priority REAL NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    is_root INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    done_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_plan_items_plan ON plan_items(plan_id, status);
CREATE INDEX IF NOT EXISTS idx_queries_time ON queries(created_at);
CREATE INDEX IF NOT EXISTS idx_resources_category ON resources(category);
CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions(status);
"""

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}


def make_slug(title: str) -> str:
    text = title.lower()
    text = "".join(_TRANSLIT.get(ch, ch) for ch in text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or "resource"


def now() -> int:
    return int(time.time())


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    def _require(self) -> aiosqlite.Connection:
        if self.conn is None:
            raise RuntimeError("Database not connected")
        return self.conn

    # ---------- ресурсы ----------

    async def seed_from_json(self, path: str) -> int:
        """Заливка seed-базы. Существующие slug не трогаем (idempotent). Возвращает число добавленных."""
        items = json.loads(Path(path).read_text(encoding="utf-8"))
        conn = self._require()
        added = 0
        ts = now()
        for item in items:
            slug = item.get("slug") or make_slug(item["title"])
            try:
                await conn.execute(
                    "INSERT INTO resources (slug, title, url, category, tags, description_ru,"
                    " description_en, source, created_at, updated_at) VALUES (?,?,?,?,?,?,?, 'seed', ?, ?)",
                    (slug, item["title"], item["url"], item["category"],
                     json.dumps(item.get("tags", []), ensure_ascii=False),
                     item.get("ru", ""), item.get("en", item.get("ru", "")), ts, ts),
                )
                added += 1
            except sqlite3.IntegrityError:
                continue
        await conn.commit()
        return added

    async def add_resource(self, title: str, url: str, category: str, tags: List[str],
                           ru: str, en: str = "", source: str = "manual") -> Tuple[int, str]:
        conn = self._require()
        ts = now()
        slug = make_slug(title)
        base_slug, attempt = slug, 2
        while True:
            cur = await conn.execute("SELECT 1 FROM resources WHERE slug=?", (slug,))
            if await cur.fetchone() is None:
                break
            slug = "%s-%d" % (base_slug, attempt)
            attempt += 1
        cur = await conn.execute(
            "INSERT INTO resources (slug, title, url, category, tags, description_ru,"
            " description_en, source, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (slug, title.strip(), url.strip(), category, json.dumps(tags or [], ensure_ascii=False),
             ru.strip(), (en or ru).strip(), source, ts, ts),
        )
        await conn.commit()
        return cur.lastrowid, slug

    async def import_resources(self, items: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
        """Импорт из массива объектов: upsert по url (если найден — обновляем поля)."""
        conn = self._require()
        added = updated = 0
        ts = now()
        for item in items:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            cur = await conn.execute("SELECT id FROM resources WHERE url=?", (url,))
            row = await cur.fetchone()
            tags = json.dumps(item.get("tags", []), ensure_ascii=False)
            if row is None:
                slug = item.get("slug") or make_slug(item.get("title") or url)
                try:
                    await conn.execute(
                        "INSERT INTO resources (slug, title, url, category, tags, description_ru,"
                        " description_en, source, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (slug, item.get("title", url), url, item.get("category", "tools"), tags,
                         item.get("ru", ""), item.get("en", item.get("ru", "")), "import", ts, ts),
                    )
                    added += 1
                except sqlite3.IntegrityError:
                    continue
            else:
                await conn.execute(
                    "UPDATE resources SET title=?, category=?, tags=?, description_ru=?,"
                    " description_en=?, updated_at=? WHERE id=?",
                    (item.get("title", url), item.get("category", "tools"), tags,
                     item.get("ru", ""), item.get("en", item.get("ru", "")), ts, row["id"]),
                )
                updated += 1
        await conn.commit()
        return added, updated

    async def all_resources_for_index(self) -> List[ResourceDoc]:
        conn = self._require()
        cur = await conn.execute(
            "SELECT r.id, r.slug, r.title, r.url, r.category, r.tags, r.description_ru,"
            " r.description_en, COALESCE(v.net, 0) AS net FROM resources r"
            " LEFT JOIN (SELECT resource_id, SUM(value) AS net FROM votes GROUP BY resource_id) v"
            " ON v.resource_id = r.id"
        )
        docs = []
        for row in await cur.fetchall():
            try:
                tags = json.loads(row["tags"])
            except (ValueError, TypeError):
                tags = []
            docs.append(ResourceDoc(
                rid=row["id"], slug=row["slug"], title=row["title"], url=row["url"],
                category=row["category"], tags=tags, ru=row["description_ru"],
                en=row["description_en"], score=row["net"] or 0,
            ))
        return docs

    async def export_resources(self) -> List[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute("SELECT slug, title, url, category, tags, description_ru,"
                                 " description_en FROM resources ORDER BY id")
        out = []
        for row in await cur.fetchall():
            try:
                tags = json.loads(row["tags"])
            except (ValueError, TypeError):
                tags = []
            out.append({
                "slug": row["slug"], "title": row["title"], "url": row["url"],
                "category": row["category"], "tags": tags,
                "ru": row["description_ru"], "en": row["description_en"],
            })
        return out

    async def get_resource(self, rid: int) -> Optional[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute("SELECT * FROM resources WHERE id=?", (rid,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_resource_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute("SELECT * FROM resources WHERE url=?", (url,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def category_counts(self) -> Dict[str, int]:
        conn = self._require()
        cur = await conn.execute("SELECT category, COUNT(*) AS n FROM resources GROUP BY category")
        return {row["category"]: row["n"] for row in await cur.fetchall()}

    async def resources_in_category(self, category: str, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute(
            "SELECT id, title, url, description_ru, description_en, tags FROM resources"
            " WHERE category=? ORDER BY title LIMIT ? OFFSET ?",
            (category, limit, offset),
        )
        rows = []
        for row in await cur.fetchall():
            try:
                tags = json.loads(row["tags"])
            except (ValueError, TypeError):
                tags = []
            rows.append({**dict(row), "tags": tags})
        return rows

    async def random_resource(self, exclude_ids: Optional[List[int]] = None) -> Optional[Dict[str, Any]]:
        conn = self._require()
        exclude_ids = exclude_ids or []
        placeholders = ",".join("?" for _ in exclude_ids)
        sql = "SELECT id, title, url, description_ru, description_en, category, tags FROM resources"
        if exclude_ids:
            sql += " WHERE id NOT IN (%s)" % placeholders
        sql += " ORDER BY RANDOM() LIMIT 1"
        cur = await conn.execute(sql, exclude_ids)
        row = await cur.fetchone()
        if row is None:
            return None
        try:
            tags = json.loads(row["tags"])
        except (ValueError, TypeError):
            tags = []
        return {**dict(row), "tags": tags}

    async def resources_count(self) -> int:
        conn = self._require()
        cur = await conn.execute("SELECT COUNT(*) AS n FROM resources")
        row = await cur.fetchone()
        return row["n"]

    # ---------- пользователи ----------

    async def ensure_user(self, user_id: int, lang: str = "ru") -> None:
        conn = self._require()
        await conn.execute(
            "INSERT INTO users (user_id, lang, first_seen, last_seen) VALUES (?,?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET last_seen=excluded.last_seen",
            (user_id, lang, now(), now()),
        )
        await conn.commit()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def set_lang(self, user_id: int, lang: str) -> None:
        conn = self._require()
        await conn.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
        await conn.commit()

    async def set_digest(self, user_id: int, enabled: bool) -> None:
        conn = self._require()
        await conn.execute("UPDATE users SET digest=? WHERE user_id=?", (1 if enabled else 0, user_id))
        await conn.commit()

    async def digest_subscribers(self) -> List[int]:
        conn = self._require()
        cur = await conn.execute("SELECT user_id FROM users WHERE digest=1 AND banned=0")
        return [row["user_id"] for row in await cur.fetchall()]

    async def all_user_ids(self) -> List[int]:
        conn = self._require()
        cur = await conn.execute("SELECT user_id FROM users WHERE banned=0")
        return [row["user_id"] for row in await cur.fetchall()]

    async def users_count(self) -> int:
        conn = self._require()
        cur = await conn.execute("SELECT COUNT(*) AS n FROM users")
        return (await cur.fetchone())["n"]

    async def ban_user(self, user_id: int, banned: bool) -> None:
        conn = self._require()
        await conn.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, user_id))
        await conn.commit()

    async def is_banned(self, user_id: int) -> bool:
        conn = self._require()
        cur = await conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return bool(row and row["banned"])

    async def get_meta(self, key: str) -> Optional[str]:
        conn = self._require()
        cur = await conn.execute("SELECT value FROM meta WHERE key=?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else None

    async def set_meta(self, key: str, value: str) -> None:
        conn = self._require()
        await conn.execute(
            "INSERT INTO meta (key, value) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await conn.commit()

    async def bump_search_count(self, user_id: int) -> None:
        conn = self._require()
        await conn.execute("UPDATE users SET search_count=search_count+1 WHERE user_id=?", (user_id,))
        await conn.commit()

    # ---------- избранное ----------

    async def fav_add(self, user_id: int, resource_id: int) -> bool:
        conn = self._require()
        try:
            await conn.execute("INSERT INTO favorites (user_id, resource_id, created_at) VALUES (?,?,?)",
                               (user_id, resource_id, now()))
            await conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    async def fav_remove(self, user_id: int, resource_id: int) -> None:
        conn = self._require()
        await conn.execute("DELETE FROM favorites WHERE user_id=? AND resource_id=?", (user_id, resource_id))
        await conn.commit()

    async def fav_list(self, user_id: int) -> List[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute(
            "SELECT r.id, r.title, r.url, r.description_ru, r.description_en FROM favorites f"
            " JOIN resources r ON r.id=f.resource_id WHERE f.user_id=? ORDER BY f.created_at DESC",
            (user_id,),
        )
        return [dict(row) for row in await cur.fetchall()]

    async def is_favorite(self, user_id: int, resource_id: int) -> bool:
        conn = self._require()
        cur = await conn.execute("SELECT 1 FROM favorites WHERE user_id=? AND resource_id=?",
                                 (user_id, resource_id))
        return await cur.fetchone() is not None

    # ---------- голоса ----------

    async def vote(self, user_id: int, resource_id: int, value: int) -> int:
        """value: 1 | -1 | 0 (сброс). Возвращает итоговое значение голоса пользователя."""
        conn = self._require()
        if value == 0:
            await conn.execute("DELETE FROM votes WHERE user_id=? AND resource_id=?",
                               (user_id, resource_id))
            await conn.commit()
            return 0
        await conn.execute(
            "INSERT INTO votes (user_id, resource_id, value, created_at) VALUES (?,?,?,?)"
            " ON CONFLICT(user_id, resource_id) DO UPDATE SET value=excluded.value",
            (user_id, resource_id, value, now()),
        )
        await conn.commit()
        return value

    async def user_vote(self, user_id: int, resource_id: int) -> int:
        conn = self._require()
        cur = await conn.execute("SELECT value FROM votes WHERE user_id=? AND resource_id=?",
                                 (user_id, resource_id))
        row = await cur.fetchone()
        return row["value"] if row else 0

    # ---------- предложения ----------

    async def suggestion_add(self, user_id: int, title: str, url: str, category: str,
                             tags: str, comment: str) -> int:
        conn = self._require()
        cur = await conn.execute(
            "INSERT INTO suggestions (user_id, title, url, category, tags, comment, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (user_id, title, url, category, tags, comment, now()),
        )
        await conn.commit()
        return cur.lastrowid

    async def suggestion_get(self, sid: int) -> Optional[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute("SELECT * FROM suggestions WHERE id=?", (sid,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def suggestion_decide(self, sid: int, status: str) -> Optional[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute("SELECT * FROM suggestions WHERE id=? AND status='pending'", (sid,))
        row = await cur.fetchone()
        if row is None:
            return None
        await conn.execute("UPDATE suggestions SET status=?, decided_at=? WHERE id=?",
                           (status, now(), sid))
        await conn.commit()
        return dict(row)

    async def pending_suggestions(self) -> List[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute("SELECT * FROM suggestions WHERE status='pending' ORDER BY id")
        return [dict(row) for row in await cur.fetchall()]

    async def pending_count(self) -> int:
        conn = self._require()
        cur = await conn.execute("SELECT COUNT(*) AS n FROM suggestions WHERE status='pending'")
        return (await cur.fetchone())["n"]

    # ---------- лог запросов и статистика ----------

    async def log_query(self, user_id: int, text: str, top_slug: str = "") -> None:
        conn = self._require()
        await conn.execute("INSERT INTO queries (user_id, text, top_slug, created_at) VALUES (?,?,?,?)",
                           (user_id, text.strip()[:200], top_slug, now()))
        await conn.commit()

    async def queries_count_24h(self) -> int:
        conn = self._require()
        cur = await conn.execute("SELECT COUNT(*) AS n FROM queries WHERE created_at>=?",
                                 (now() - 86400,))
        return (await cur.fetchone())["n"]

    async def top_queries_24h(self, limit: int = 5) -> List[Tuple[str, int]]:
        conn = self._require()
        cur = await conn.execute(
            "SELECT lower(trim(text)) AS q, COUNT(*) AS n FROM queries WHERE created_at>=?"
            " GROUP BY q ORDER BY n DESC LIMIT ?",
            (now() - 86400, limit),
        )
        return [(row["q"], row["n"]) for row in await cur.fetchall()]

    # ---------- планы разбора задачи (МАРСИ) ----------

    async def create_plan(self, user_id: int, query: str, params: dict,
                           candidates: List[Dict[str, Any]]) -> int:
        conn = self._require()
        ts = now()
        cur = await conn.execute(
            "INSERT INTO plans (user_id, query, params, candidates, status, created_at, updated_at)"
            " VALUES (?,?,?,?, 'active', ?, ?)",
            (user_id, query.strip()[:300], json.dumps(params, ensure_ascii=False),
             json.dumps(candidates, ensure_ascii=False), ts, ts),
        )
        await conn.commit()
        return cur.lastrowid

    async def add_plan_item(self, plan_id: int, resource_id: Optional[int], title: str,
                            url: str, category: str, tags: List[str], custom: bool,
                            weight: float, complexity: float, priority: float,
                            position: int, is_root: bool) -> int:
        conn = self._require()
        cur = await conn.execute(
            "INSERT INTO plan_items (plan_id, resource_id, title, url, category, tags, custom,"
            " weight, complexity, priority, position, is_root, status, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)",
            (plan_id, resource_id, title, url, category,
             json.dumps(tags or [], ensure_ascii=False), 1 if custom else 0,
             round(weight, 4), round(complexity, 4), round(priority, 4),
             position, 1 if is_root else 0, now()),
        )
        await conn.commit()
        return cur.lastrowid

    async def get_plan(self, plan_id: int) -> Optional[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,))
        row = await cur.fetchone()
        if row is None:
            return None
        plan = dict(row)
        cur = await conn.execute(
            "SELECT * FROM plan_items WHERE plan_id=? ORDER BY position", (plan_id,))
        items = []
        for item in await cur.fetchall():
            d = dict(item)
            try:
                d["tags"] = json.loads(d["tags"])
            except (ValueError, TypeError):
                d["tags"] = []
            items.append(d)
        plan["items"] = items
        return plan

    async def active_plans(self, user_id: int) -> List[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute(
            "SELECT p.id, p.query, p.created_at,"
            " (SELECT COUNT(*) FROM plan_items i WHERE i.plan_id=p.id AND i.status='pending') AS pending"
            " FROM plans p WHERE p.user_id=? AND p.status='active' ORDER BY p.id DESC",
            (user_id,),
        )
        return [dict(row) for row in await cur.fetchall()]

    async def get_plan_owner(self, plan_id: int) -> Optional[int]:
        conn = self._require()
        cur = await conn.execute("SELECT user_id FROM plans WHERE id=?", (plan_id,))
        row = await cur.fetchone()
        return row["user_id"] if row else None

    async def get_plan_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        conn = self._require()
        cur = await conn.execute("SELECT * FROM plan_items WHERE id=?", (item_id,))
        row = await cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["tags"] = json.loads(d["tags"])
        except (ValueError, TypeError):
            d["tags"] = []
        return d

    async def save_plan_state(self, plan_id: int, items: List[Dict[str, Any]]) -> None:
        """Атомарное сохранение пересчитанного состояния шагов (i → i+1)."""
        conn = self._require()
        for item in items:
            await conn.execute(
                "UPDATE plan_items SET weight=?, priority=?, position=?, is_root=?, status=?,"
                " done_at=? WHERE id=?",
                (round(item["weight"], 4), round(item["priority"], 4), item["position"],
                 1 if item.get("is_root") else 0, item["status"],
                 item.get("done_at") or 0, item["id"]),
            )
        if items:
            await conn.execute("UPDATE plans SET updated_at=? WHERE id=?", (now(), plan_id))
        await conn.commit()

    async def finish_plan_if_done(self, plan_id: int) -> bool:
        """Если не осталось pending-шагов — план закрыт со статусом done."""
        conn = self._require()
        cur = await conn.execute(
            "SELECT COUNT(*) AS n FROM plan_items WHERE plan_id=? AND status='pending'", (plan_id,))
        pending = (await cur.fetchone())["n"]
        if pending == 0:
            await conn.execute(
                "UPDATE plans SET status='done', updated_at=? WHERE id=?", (now(), plan_id))
            await conn.commit()
            return True
        return False

    async def archive_plan(self, plan_id: int) -> None:
        conn = self._require()
        await conn.execute(
            "UPDATE plans SET status='archived', updated_at=? WHERE id=?", (now(), plan_id))
        await conn.commit()

    async def update_plan_candidates(self, plan_id: int, candidates: List[Dict[str, Any]]) -> None:
        conn = self._require()
        await conn.execute("UPDATE plans SET candidates=?, updated_at=? WHERE id=?",
                           (json.dumps(candidates, ensure_ascii=False), now(), plan_id))
        await conn.commit()

    async def set_item_status(self, item_id: int, status: str,
                              weight: Optional[float] = None) -> None:
        conn = self._require()
        if weight is None:
            await conn.execute("UPDATE plan_items SET status=? WHERE id=?",
                               (status, item_id))
        else:
            await conn.execute("UPDATE plan_items SET status=?, weight=? WHERE id=?",
                               (status, weight, item_id))
        await conn.commit()

    async def plans_stats(self) -> Dict[str, int]:
        conn = self._require()
        out: Dict[str, int] = {}
        cur = await conn.execute("SELECT COUNT(*) AS n FROM plans")
        out["total"] = (await cur.fetchone())["n"]
        cur = await conn.execute("SELECT COUNT(*) AS n FROM plans WHERE status='active'")
        out["active"] = (await cur.fetchone())["n"]
        cur = await conn.execute(
            "SELECT COUNT(*) AS n FROM plan_items WHERE status='done'")
        out["steps_done"] = (await cur.fetchone())["n"]
        return out


async def seed_if_empty(db: Database, seed_path: str) -> int:
    """Заливаем сид только если база пустая. Возвращает число добавленных ресурсов."""
    if await db.resources_count() > 0:
        return 0
    if not Path(seed_path).is_file():
        return 0
    return await db.seed_from_json(seed_path)


def pick_weekly_resource(rows: List[Dict[str, Any]], week_index: int) -> Optional[Dict[str, Any]]:
    """Детерминированный выбор «ресурса недели»: одинаковый для всех в рамках недели."""
    if not rows:
        return None
    return rows[(week_index * 7919 + 13) % len(rows)]
