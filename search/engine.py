"""Гибридный поисковый движок: hashed n-gram TF-IDF косинус + BM25F + синонимы + голоса."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .synonyms import expand
from .vectorizer import feature_counts, text_features, tokenize

DIMS = 8192  # размерность хешированного вектора

# Веса полей для BM25F
FIELD_WEIGHTS = (("title", 3.0), ("tags", 2.5), ("category", 2.0), ("ru", 1.2), ("en", 1.2))
COSINE_WEIGHT = 0.55
BM25_WEIGHT = 0.45
BM25_SATURATION = 8.0  # bm25n = bm25 / (bm25 + SATURATION) * SATURATION_FACTOR
BM25_SATURATION_FACTOR = 1.6
MIN_SCORE = 0.10  # ниже — считаем, что релевантного ничего нет
VOTE_UP_W = 0.045
VOTE_DOWN_W = 0.030


@dataclass
class ResourceDoc:
    rid: int
    slug: str
    title: str
    url: str
    category: str
    tags: List[str]
    ru: str
    en: str
    score: int = 0  # чистые голоса пользователей (up - down)

    def field_text(self, name: str) -> str:
        if name == "title":
            return self.title
        if name == "tags":
            return " ".join(self.tags)
        if name == "category":
            return self.category.replace("-", " ")
        if name == "ru":
            return self.ru
        if name == "en":
            return self.en
        return ""


class EmbeddingBackend:
    """Опциональный бэкенд настоящих embedding-моделей (вместо хешированных векторов)."""

    name = "base"

    def encode_batch(self, texts: Sequence[str]) -> List[List[float]]:
        raise NotImplementedError

    def encode_one(self, text: str) -> List[float]:
        return self.encode_batch([text])[0]


class LocalHashedBackend(EmbeddingBackend):
    """Офлайн-векторизатор: мешок слов + char n-граммы, feature hashing, TF-IDF, L2."""

    name = "local"

    def __init__(self) -> None:
        self.df: Dict[str, int] = {}
        self.n_docs = 0

    def fit(self, docs: Sequence[str]) -> None:
        df: Dict[str, int] = {}
        for text in docs:
            for f, _ in feature_counts(text_features(text)):
                df[f] = df.get(f, 0) + 1
        self.df = df
        self.n_docs = len(docs)

    def idf(self, feat: str) -> float:
        df = self.df.get(feat, 0)
        return math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))

    def vectorize(self, text: str) -> Dict[int, float]:
        vec: Dict[int, float] = {}
        for f, tf in feature_counts(text_features(text)):
            if self.df and f not in self.df:
                continue  # фича нигде не встречается — только хеш-коллизии
            w = (1.0 + math.log(tf)) * self.idf(f)
            dim, sign = _hash_feature(f)
            vec[dim] = vec.get(dim, 0.0) + sign * w
        return _l2_normalize_sparse(vec)

    def encode_batch(self, texts: Sequence[str]) -> List[List[float]]:
        raise TypeError("local backend работает со sparse-векторами, используйте vectorize")

    def encode_one(self, text: str) -> List[float]:
        raise TypeError("local backend работает со sparse-векторами, используйте vectorize")


class SentenceTransformersBackend(EmbeddingBackend):
    """Настоящие эмбеддинги, если установлен sentence-transformers (загружается лениво)."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # тяжёлый импорт

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode_batch(self, texts: Sequence[str]) -> List[List[float]]:
        model = self._load()
        embs = model.encode(list(texts), normalize_embeddings=True)
        return [[float(x) for x in row] for row in embs]

    def encode_one(self, text: str) -> List[float]:
        return self.encode_batch([text])[0]


class OpenAICompatBackend(EmbeddingBackend):
    """OpenAI-совместимый /embeddings endpoint (Ollama, LM Studio, vLLM, OpenAI и т.п.).

    Синхронный urllib — вызывать через asyncio.to_thread (engine.search_async).
    """

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def encode_batch(self, texts: Sequence[str]) -> List[List[float]]:
        import json
        import urllib.request

        payload = json.dumps({"model": self.model, "input": list(texts)}).encode()
        req = urllib.request.Request(
            self.base_url + "/embeddings",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return [[float(x) for x in item["embedding"]] for item in data["data"]]

    def encode_one(self, text: str) -> List[float]:
        return self.encode_batch([text])[0]


def backend_factory(cfg) -> Optional[EmbeddingBackend]:
    """Выбор бэкенда по конфигу: api > sentence-transformers > local."""
    mode = (cfg.search_backend or "auto").lower()
    if mode in ("api",) or (mode == "auto" and cfg.embedding_api_base):
        if cfg.embedding_api_base:
            return OpenAICompatBackend(cfg.embedding_api_base, cfg.embedding_api_key, cfg.embedding_model)
    if mode in ("st",) or mode == "auto":
        import importlib.util

        if importlib.util.find_spec("sentence_transformers") is not None:
            return SentenceTransformersBackend(cfg.embedding_model)
    if mode in ("local", "auto"):
        return LocalHashedBackend()
    raise ValueError("Неизвестный SEARCH_BACKEND: %r" % mode)


def _hash_feature(feat: str) -> Tuple[int, int]:
    digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
    n = int.from_bytes(digest, "little")
    return n % DIMS, 1 if (n >> 63) & 1 else -1


def _l2_normalize_sparse(vec: Dict[int, float]) -> Dict[int, float]:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm <= 0:
        return vec
    return {k: v / norm for k, v in vec.items()}


def _cosine_sparse(a: Dict[int, float], b: Dict[int, float]) -> float:
    if len(b) < len(a):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def _cosine_dense(a: Sequence[float], b: Sequence[float]) -> float:
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return s / (na * nb)


@dataclass
class _DocIndex:
    doc: ResourceDoc
    vec: Dict[int, float] = field(default_factory=dict)
    dense: List[float] = field(default_factory=list)
    bm25_fields: Dict[str, Dict[str, int]] = field(default_factory=dict)


@dataclass
class Hit:
    doc: ResourceDoc
    score: float


class SearchEngine:
    def __init__(self, backend: Optional[EmbeddingBackend] = None) -> None:
        self.backend: EmbeddingBackend = backend or LocalHashedBackend()
        self._docs: Dict[int, _DocIndex] = {}
        self._df_words: Dict[str, int] = {}
        self._n_docs = 0

    # ---------- индексация ----------

    def rebuild(self, docs: Iterable[ResourceDoc]) -> None:
        docs = list(docs)
        self._docs = {}
        texts = [d.title + " " + " ".join(d.tags) + " " + d.category + " " + d.ru + " " + d.en for d in docs]
        if isinstance(self.backend, LocalHashedBackend):
            self.backend.fit(texts)
        df_words: Dict[str, int] = {}
        for d in docs:
            for tok in set(self._doc_tokens(d)):
                df_words[tok] = df_words.get(tok, 0) + 1
        self._df_words = df_words
        self._n_docs = len(docs)
        dense_vecs: List[List[float]] = []
        if not isinstance(self.backend, LocalHashedBackend):
            dense_vecs = self.backend.encode_batch(texts)
        for i, d in enumerate(docs):
            idx = _DocIndex(doc=d)
            if isinstance(self.backend, LocalHashedBackend):
                idx.vec = self.backend.vectorize(texts[i])
            else:
                idx.dense = dense_vecs[i]
            idx.bm25_fields = {
                fname: _count_tokens(d.field_text(fname)) for fname, _ in FIELD_WEIGHTS
            }
            self._docs[d.rid] = idx

    def _doc_tokens(self, d: ResourceDoc) -> List[str]:
        toks: List[str] = []
        for fname, _ in FIELD_WEIGHTS:
            toks.extend(tokenize(d.field_text(fname)))
        return toks

    @property
    def size(self) -> int:
        return len(self._docs)

    def get(self, rid: int) -> Optional[ResourceDoc]:
        idx = self._docs.get(rid)
        return idx.doc if idx else None

    # ---------- поиск ----------

    def _query_vector(self, text: str):
        if isinstance(self.backend, LocalHashedBackend):
            return self.backend.vectorize(text)
        return self.backend.encode_one(text)

    def _cosine(self, qv, idx: _DocIndex) -> float:
        if isinstance(self.backend, LocalHashedBackend):
            return _cosine_sparse(qv, idx.vec)
        return _cosine_dense(qv, idx.dense)

    def _word_idf(self, tok: str) -> float:
        df = self._df_words.get(tok, 0)
        return math.log(1.0 + (self._n_docs - df + 0.5) / (df + 0.5))

    def _bm25(self, q_tokens: Iterable[str], idx: _DocIndex) -> float:
        score = 0.0
        for tok in q_tokens:
            idf = self._word_idf(tok)
            field_sum = 0.0
            for fname, weight in FIELD_WEIGHTS:
                tf = idx.bm25_fields.get(fname, {}).get(tok, 0)
                if tf:
                    field_sum += weight * (tf / (tf + 1.2))
            score += idf * field_sum
        return score

    @staticmethod
    def _vote_boost(net_votes: int) -> float:
        up = max(net_votes, 0)
        down = max(-net_votes, 0)
        return VOTE_UP_W * math.log1p(up) - VOTE_DOWN_W * math.log1p(down)

    def search(self, query: str, k: int = 5, user_votes: Optional[Dict[int, int]] = None,
               category_hints: Optional[Dict[str, float]] = None) -> List[Hit]:
        """Главная функция. Возвращает топ-хиты со score ~0..1 (может чуть больше)."""
        if not self._docs or not (query or "").strip():
            return []
        base_tokens = tokenize(query)
        if not base_tokens:
            return []
        expanded = expand(base_tokens)
        q_text = query + " " + " ".join(t[2:] for t in expanded)
        qv = self._query_vector(q_text)
        hits: List[Hit] = []
        for idx in self._docs.values():
            cos = self._cosine(qv, idx)
            bm25 = self._bm25(expanded, idx)
            bm25n = bm25 / (bm25 + BM25_SATURATION) * BM25_SATURATION_FACTOR
            net = idx.doc.score
            if user_votes:
                net += user_votes.get(idx.doc.rid, 0)
            score = COSINE_WEIGHT * max(cos, 0.0) + BM25_WEIGHT * min(bm25n, 1.0)
            score += self._vote_boost(net)
            if category_hints:
                score += category_hints.get(idx.doc.category, 0.0)
            if score >= MIN_SCORE:
                hits.append(Hit(doc=idx.doc, score=score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    def related(self, rid: int, k: int = 5) -> List[Hit]:
        """Похожие ресурсы: документ сам себе запрос (без синонимов — прямой cosine)."""
        idx = self._docs.get(rid)
        if idx is None:
            return []
        text = idx.doc.title + " " + " ".join(idx.doc.tags) + " " + idx.doc.category + " " + idx.doc.ru + " " + idx.doc.en
        qv = self._query_vector(text)
        hits: List[Hit] = []
        for other in self._docs.values():
            if other.doc.rid == rid:
                continue
            cos = max(self._cosine(qv, other), 0.0)
            # лёгкий буст за общие теги
            shared = len(set(idx.doc.tags) & set(other.doc.tags))
            score = cos + 0.02 * shared
            if score >= MIN_SCORE:
                hits.append(Hit(doc=other.doc, score=score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    async def search_async(self, query: str, **kwargs) -> List[Hit]:
        """Обёртка для хендлеров: тяжёлые бэкенды не блокируют event loop."""
        import asyncio

        return await asyncio.to_thread(self.search, query, **kwargs)

    async def related_async(self, rid: int, k: int = 5) -> List[Hit]:
        import asyncio

        return await asyncio.to_thread(self.related, rid, k)


def _count_tokens(text: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for tok in tokenize(text):
        counts[tok] = counts.get(tok, 0) + 1
    return counts
