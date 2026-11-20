"""Тесты токенизатора и кэша запросов."""
from __future__ import annotations

from services import QueryCache, score_percent

from search.vectorizer import normalize_token, text_features, tokenize


class TestNormalize:
    def test_lower_and_yo(self):
        assert normalize_token("Ёлка") == "елка"

    def test_ru_suffix_strip(self):
        # «библиотеки» и «библиотека» должны сходиться к одной основе
        a = normalize_token("библиотеки")
        b = normalize_token("библиотека")
        assert a == b == "библиотек"

    def test_short_words_untouched(self):
        assert normalize_token("год") == "год"
        assert normalize_token("api") == "api"

    def test_latin_untouched(self):
        assert normalize_token("python") == "python"
        assert normalize_token("PDFs") == "pdfs"


class TestTokenize:
    def test_basic(self):
        toks = tokenize("Нужна библиотека для PDF в Python")
        # «нужна» нормализуется к основе (суффикс срезается)
        assert "w:нужн" in toks
        assert "w:pdf" in toks
        assert "w:python" in toks

    def test_punctuation_split(self):
        toks = tokenize("fast, async — web/framework!")
        assert "w:fast" in toks and "w:async" in toks and "w:web" in toks

    def test_single_chars_dropped(self):
        assert "w:а" not in tokenize("а б в")

    def test_hash_tags_kept(self):
        toks = tokenize("C++ и C#")
        assert any(t.startswith("w:c") for t in toks)


class TestTextFeatures:
    def test_words_and_char_grams(self):
        feats = text_features("docker compose")
        assert "w:docker" in feats
        assert any(f.startswith("c:^do") for f in feats)

    def test_morphology_overlap(self):
        # n-граммы ловят морфологию: у словоформ много общих фич
        a = set(text_features("библиотека"))
        b = set(text_features("библиотеки"))
        assert len(a & b) > 5


class TestQueryCache:
    def test_put_get_roundtrip(self):
        cache = QueryCache()
        h = cache.put(42, "графики на python")
        assert cache.get(42, h) == "графики на python"

    def test_other_user_denied(self):
        cache = QueryCache()
        h = cache.put(42, "secret query")
        assert cache.get(43, h) is None

    def test_capacity_eviction(self):
        cache = QueryCache(capacity=3)
        hashes = [cache.put(1, "q%d" % i) for i in range(5)]
        assert cache.get(1, hashes[0]) is None
        assert cache.get(1, hashes[-1]) == "q4"

    def test_stable_hash(self):
        assert QueryCache.hash_query("PyThon ") == QueryCache.hash_query("python")


class TestScorePercent:
    def test_bounds(self):
        assert score_percent(0.0) >= 1
        assert score_percent(0.5) == 40
        assert score_percent(99.0) == 99
