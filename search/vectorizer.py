"""Токенизация и нормализация для RU/EN текстов."""
from __future__ import annotations

import re
from typing import Iterable, List, Tuple

_WORD_RE = re.compile(r"[0-9a-zа-яё#+.-]+", re.IGNORECASE)

# Лёгкая нормализация окончаний для кириллических слов (применяется одинаково
# к запросам и документам, поэтому консистентна). Только для слов >= 5 букв.
_RU_SUFFIXES = (
    "ами", "ями", "ого", "его", "ому", "ему", "ыми", "ими", "ешь", "ишь",
    "ая", "яя", "ое", "ее", "ые", "ие", "ов", "ев", "ам", "ям", "ах", "ях",
    "ый", "ий", "ой", "ом", "ем", "ую", "юю", "ет", "ют", "ат", "ят", "ут",
    "ть", "ла", "ло", "ли", "ся", "сь", "ей",
    "а", "я", "ы", "и", "е", "у", "ю", "о",  # именительный/винительный падежи
)


def normalize_token(token: str) -> str:
    """Нижний регистр, ё→е, срез кириллических окончаний у длинных слов."""
    token = token.lower().replace("ё", "е")
    if len(token) >= 5 and re.search(r"[а-я]", token):
        for suffix in _RU_SUFFIXES:
            if len(token) - len(suffix) >= 4 and token.endswith(suffix):
                token = token[: -len(suffix)]
                break
    return token.strip(".-+")


def tokenize(text: str) -> List[str]:
    """Словесные токены: [w:слово, ...] с дубликатами (нужны для TF)."""
    out: List[str] = []
    for raw in _WORD_RE.findall(text or ""):
        token = normalize_token(raw)
        if token and len(token) >= 2:
            out.append("w:" + token)
    return out


def _char_ngrams(token: str, n_min: int = 3, n_max: int = 5) -> Iterable[str]:
    body = "^" + token + "$"
    for n in range(n_min, n_max + 1):
        if len(body) < n:
            continue
        for i in range(len(body) - n + 1):
            yield body[i : i + n]


def text_features(text: str) -> List[str]:
    """Полный мешок признаков: слова (вес выше через дублирование) + char n-граммы."""
    feats: List[str] = []
    words = tokenize(text)
    feats.extend(words)
    seen_words = set()
    for w in words:
        stem = w[2:]
        if stem in seen_words:
            continue
        seen_words.add(stem)
        for gram in _char_ngrams(stem):
            feats.append("c:" + gram)
    return feats


def feature_counts(feats: Iterable[str]) -> List[Tuple[str, int]]:
    counts: dict = {}
    for f in feats:
        counts[f] = counts.get(f, 0) + 1
    return list(counts.items())
