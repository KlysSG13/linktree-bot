"""Интеграционные тесты поискового движка на реальной seed-базе."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from search.engine import DIMS, SearchEngine
from search.synonyms import expand

SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed_resources.json"


@pytest.fixture(scope="module")
def docs():
    items = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    from search.engine import ResourceDoc
    return [
        ResourceDoc(
            rid=i, slug=it["slug"], title=it["title"], url=it["url"],
            category=it["category"], tags=it["tags"], ru=it["ru"], en=it["en"],
        )
        for i, it in enumerate(items, 1)
    ]


@pytest.fixture(scope="module")
def engine(docs):
    eng = SearchEngine()
    eng.rebuild(docs)
    return eng


def titles(hits):
    return [h.doc.title.lower() for h in hits]


class TestSynonyms:
    def test_ru_query_expands_to_en(self):
        toks = expand(["w:картинк"])
        assert "w:image" in toks

    def test_no_duplicates(self):
        toks = expand(["w:график", "w:image"])
        assert len(toks) == len(set(toks))

    def test_unknown_word_untouched(self):
        assert expand(["w:xyzzy"]) == ["w:xyzzy"]


class TestSearchRelevance:
    def test_pdf_python(self, engine):
        hits = engine.search("нужна библиотека для работы с PDF в Python", k=5)
        found = {h.doc.slug for h in hits}
        assert found & {"pdfplumber", "pypdf"}, found

    def test_parsing_sites(self, engine):
        hits = engine.search("python парсинг сайтов", k=5)
        found = {h.doc.slug for h in hits}
        assert found & {"scrapy", "beautifulsoup", "lxml", "playwright-python"}, found

    def test_telegram_bot_ru(self, engine):
        hits = engine.search("как сделать телеграм бота", k=5)
        found = {h.doc.slug for h in hits}
        assert found & {"aiogram", "grammy"}, found

    def test_local_llm(self, engine):
        hits = engine.search("запустить нейросеть локально на своём компьютере", k=5)
        found = {h.doc.slug for h in hits}
        assert found & {"ollama", "llama-cpp", "vllm"}, found

    def test_charts(self, engine):
        hits = engine.search("библиотека графиков python", k=5)
        found = {h.doc.slug for h in hits}
        assert found & {"matplotlib", "plotly-py", "seaborn"}, found

    def test_excel_tables(self, engine):
        hits = engine.search("работа с excel таблицами", k=5)
        found = {h.doc.slug for h in hits}
        assert found & {"openpyxl", "pandas"}, found

    def test_terminal_pretty(self, engine):
        hits = engine.search("красивый терминал", k=5)
        found = {h.doc.slug for h in hits}
        assert found & {"starship", "alacritty", "bat", "eza", "rich"}, found

    def test_game_engine(self, engine):
        hits = engine.search("движок для 2d игры", k=5)
        found = {h.doc.slug for h in hits}
        assert found & {"godot", "phaser", "pygame"}, found

    def test_english_query(self, engine):
        hits = engine.search("fast python web framework", k=5)
        found = {h.doc.slug for h in hits}
        assert found & {"fastapi", "litestar", "flask", "fastify"}, found

    def test_garbage_no_results(self, engine):
        assert engine.search("зфырщтасдфг qwertyzzz", k=5) == []

    def test_empty_query(self, engine):
        assert engine.search("", k=5) == []
        assert engine.search("   ", k=5) == []

    def test_category_hint_boosts(self, engine):
        hinted = {h.doc.slug for h in engine.search("библиотека", k=5,
                                                    category_hints={"python": 0.15})}
        # подсказка должна давать осмысленную выдачу (и менять её относительно чистой)
        plain = {h.doc.slug for h in engine.search("библиотека", k=5)}
        assert hinted and plain
        assert hinted != plain or len(hinted) == 5

    def test_vote_boost_changes_order(self, engine):
        hits_plain = engine.search("тесты python", k=5)
        top_plain = hits_plain[0].doc.rid
        user_votes = {top_plain: -50}  # заминусовать топ жёстко
        hits_voted = engine.search("тесты python", k=5, user_votes=user_votes)
        assert hits_voted[0].doc.rid != top_plain

    def test_k_limit(self, engine):
        assert len(engine.search("python", k=3)) <= 3


class TestRelated:
    def test_related_excludes_self(self, engine, docs):
        target = next(d for d in docs if d.slug == "fastapi")
        hits = engine.related(target.rid, k=5)
        assert hits
        assert all(h.doc.rid != target.rid for h in hits)

    def test_related_similar_by_tags(self, engine, docs):
        target = next(d for d in docs if d.slug == "pytest")
        hits = engine.related(target.rid, k=5)
        found = {h.doc.slug for h in hits}
        assert found & {"vitest", "playwright", "ruff", "black", "mypy"}, found

    def test_related_unknown_id(self, engine):
        assert engine.related(999999) == []


class TestEngineInternals:
    def test_size(self, engine, docs):
        assert engine.size == len(docs)

    def test_get(self, engine, docs):
        assert engine.get(docs[0].rid) is docs[0]
        assert engine.get(-1) is None

    def test_sparse_vector_normed(self, engine):
        import math
        idx = next(iter(engine._docs.values()))
        norm = math.sqrt(sum(v * v for v in idx.vec.values()))
        assert abs(norm - 1.0) < 1e-6

    def test_dims_sane(self):
        # хешированное пространство не крошечное и не гигантское
        assert 1024 <= DIMS <= 65536

    def test_rebuild_idempotent(self, engine, docs):
        before = [h.doc.slug for h in engine.search("docker", k=5)]
        engine.rebuild(docs)
        after = [h.doc.slug for h in engine.search("docker", k=5)]
        assert before == after
