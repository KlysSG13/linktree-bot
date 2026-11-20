"""Чётность локализаций: каждый ключ существует в обоих языках."""
from __future__ import annotations

import re

from i18n import (CATEGORIES, CATEGORY_ALIASES, EN, LANGS, RU, _TR, cat_name,
                  plural_ru, tr)


class TestParity:
    def test_all_keys_have_both_langs(self):
        missing = []
        for key, entry in _TR.items():
            for lang in LANGS:
                if lang not in entry or not entry[lang].strip():
                    missing.append((key, lang))
        assert not missing, missing

    def test_no_unknown_langs(self):
        for key, entry in _TR.items():
            assert set(entry) <= set(LANGS), (key, set(entry))

    def test_categories_both_langs(self):
        for key, entry in CATEGORIES.items():
            assert set(entry) == set(LANGS), key

    def test_no_cjk_or_placeholder_leaks(self):
        cjk = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]")
        for key, entry in _TR.items():
            for lang, text in entry.items():
                assert not cjk.search(text), (key, lang)

    def test_format_placeholders_consistent(self):
        pattern = re.compile(r"\{(\w+)\}")
        for key, entry in _TR.items():
            sets = [frozenset(pattern.findall(text)) for text in entry.values()]
            assert len(set(sets)) == 1, (key, sets)

    def test_category_aliases_point_to_valid_categories(self):
        for word, cat in CATEGORY_ALIASES.items():
            assert cat in CATEGORIES, (word, cat)


class TestTr:
    def test_format(self):
        out = tr("start_hello", RU, name="Иван")
        assert "Иван" in out

    def test_fallback_lang(self):
        assert tr("help", "xx") == tr("help", RU)

    def test_default_ru(self):
        assert tr("help") == tr("help", RU)

    def test_missing_key_returns_key(self):
        assert tr("no_such_key") == "no_such_key"

    def test_cat_name(self):
        assert "Python" in cat_name("python", EN)
        assert cat_name("python", "xx") == cat_name("python", RU)
        assert cat_name("unknown", RU) == "unknown"


class TestPlural:
    def test_ru_forms(self):
        assert plural_ru(1, RU) == "ресурс"
        assert plural_ru(21, RU) == "ресурс"
        assert plural_ru(2, RU) == "ресурсов"
        assert plural_ru(11, RU) == "ресурсов"

    def test_en_forms(self):
        assert plural_ru(1, EN) == "resource"
        assert plural_ru(5, EN) == "resources"
