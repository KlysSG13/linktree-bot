"""Поисковое ядро LinkTree.

Гибридная схема без обязательных внешних зависимостей:
  1) «семантический» канал — hashed char/word n-gram TF-IDF векторы + косинус
     (fastText-подход: символьные n-граммы ловят морфологию и опечатки);
  2) лексический канал — BM25F по полям (title/tags/ category/description) с бустами;
  3) синонимический мост RU→EN — русские запросы находят англоязычные ресурсы;
  4) поведенческий сигнал — голоса 👍/👎 пользователей слегка сдвигают ранжирование.

Опционально можно включить настоящие embedding-модели (sentence-transformers
или OpenAI-совместимый API) — тогда канал 1 заменяется их косинусом.
"""
from .engine import SearchEngine, ResourceDoc, backend_factory
from .vectorizer import tokenize, normalize_token, text_features

__all__ = [
    "SearchEngine",
    "ResourceDoc",
    "backend_factory",
    "tokenize",
    "normalize_token",
    "text_features",
]
