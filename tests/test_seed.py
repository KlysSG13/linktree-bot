"""Валидация seed-базы: структура, уникальность, категории, URL, описания."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from i18n import CATEGORIES

SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed_resources.json"


@pytest.fixture(scope="module")
def items():
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


class TestSeedStructure:
    def test_size(self, items):
        assert len(items) >= 150

    def test_required_fields(self, items):
        for item in items:
            for field in ("slug", "title", "url", "category", "tags", "ru", "en"):
                assert item.get(field), (item.get("slug"), field)

    def test_unique_slugs(self, items):
        slugs = [i["slug"] for i in items]
        assert len(slugs) == len(set(slugs))

    def test_unique_urls(self, items):
        urls = [i["url"] for i in items]
        assert len(urls) == len(set(urls))

    def test_categories_valid(self, items):
        for item in items:
            assert item["category"] in CATEGORIES, item["slug"]

    def test_all_categories_used(self, items):
        used = {i["category"] for i in items}
        assert used == set(CATEGORIES)

    def test_https_only(self, items):
        for item in items:
            assert item["url"].startswith("https://"), item["url"]

    def test_tags_are_lists(self, items):
        for item in items:
            assert isinstance(item["tags"], list)
            assert all(isinstance(t, str) and t.strip() for t in item["tags"])

    def test_no_cjk(self, items):
        cjk = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]")
        for item in items:
            for field in ("title", "ru", "en"):
                assert not cjk.search(item[field]), (item["slug"], field)

    def test_descriptions_substantial(self, items):
        for item in items:
            assert len(item["ru"]) >= 30, item["slug"]
            assert len(item["en"]) >= 20, item["slug"]

    def test_github_urls_wellformed(self, items):
        gh = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$")
        for item in items:
            if "github.com" in item["url"]:
                assert gh.match(item["url"]), item["url"]
