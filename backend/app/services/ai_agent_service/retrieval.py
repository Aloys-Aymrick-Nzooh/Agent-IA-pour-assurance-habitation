"""
Recherche hybride (vecteur + BM25, fusion RRF) puis reranking cross-encoder.

Le corpus d'un (conversation, type de document) fait quelques centaines de
chunks : le BM25 est reconstruit à chaque recherche, ce qui évite toute
invalidation d'index. Si les corpus grossissent beaucoup, passe à l'index FTS
de LanceDB.
"""

import math
import os
import re
import unicodedata
from typing import Any

from . import config

Passage = dict[str, Any]

_WORD = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return [w for w in _WORD.findall(folded) if len(w) > 1]


def _sigmoid(x: float) -> float:
    if x < -500:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _rrf(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


def _to_passage(row: dict[str, Any]) -> Passage:
    titles = row.get("titles") or ""
    if isinstance(titles, list):
        titles = " > ".join(titles)
    return {
        "chunk_id": row["chunk_id"],
        "document_id": row["document_id"],
        "document_name": row["document_name"],
        "document_type": row["document_type"],
        "page_number": row["page_number"],
        "chapter": row.get("chapter") or "",
        "titles": titles,
        "text": row["chunk_text"],
        "score": 0.0,
    }


class Reranker:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or os.getenv(
            "RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"
        )
        self._model = None

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, max_length=512)

        raw = [
            float(s)
            for s in self._model.predict(
                [(query, t) for t in texts], batch_size=16, show_progress_bar=False
            )
        ]
        # Selon la version, predict() renvoie des logits ou des probabilités.
        if any(s < 0.0 or s > 1.0 for s in raw):
            raw = [_sigmoid(s) for s in raw]
        return raw


class HybridRetriever:
    def __init__(
        self,
        vector_store: Any,
        embedder: Any,
        reranker: Any,
        *,
        per_type: int = 20,
        pool: int = 30,
    ) -> None:
        self.vs = vector_store
        self.embedder = embedder
        self.reranker = reranker
        self.per_type = per_type
        self.pool = pool

    def _load(self, conversation_id: str, doc_type: str):
        table = self.vs.open_table(conversation_id, doc_type)
        if table is None:
            return None, []
        arrow = table.to_arrow()
        columns = [c for c in arrow.column_names if c != "vector"]
        return table, arrow.select(columns).to_pylist()

    def rescore(self, query: str, passages: list[Passage]) -> list[Passage]:
        if not passages:
            return []
        texts = [
            f"{p['document_type']} — {p['titles']}\n{p['text']}" for p in passages
        ]
        scores = self.reranker.score(query, texts)
        scored = [{**p, "score": s} for p, s in zip(passages, scores)]
        return sorted(scored, key=lambda p: p["score"], reverse=True)

    def search(
        self,
        conversation_id: str,
        query: str,
        doc_types: list[str],
        *,
        seeds: list[Passage] | None = None,
        top_k: int = config.TOP_K,
    ) -> list[Passage]:
        from rank_bm25 import BM25Okapi

        query_vector = self.embedder.embed_query(query)
        query_tokens = _tokens(query)
        fused: dict[str, tuple[float, dict[str, Any]]] = {}

        for doc_type in doc_types:
            table, rows = self._load(conversation_id, doc_type)
            if not rows:
                continue

            by_id = {r["chunk_id"]: r for r in rows}
            vector_ids = [
                h["chunk_id"]
                for h in table.search(query_vector).limit(self.per_type).to_list()
            ]

            bm25_ids: list[str] = []
            corpus = [_tokens(r["chunk_text"]) for r in rows]
            if any(corpus) and query_tokens:
                scores = BM25Okapi(corpus).get_scores(query_tokens)
                order = sorted(range(len(rows)), key=lambda i: scores[i], reverse=True)
                bm25_ids = [
                    rows[i]["chunk_id"] for i in order[: self.per_type] if scores[i] > 0
                ]

            for chunk_id, score in _rrf([vector_ids, bm25_ids]).items():
                if chunk_id in by_id:
                    fused[chunk_id] = (score, by_id[chunk_id])

        ranked = sorted(fused.values(), key=lambda t: t[0], reverse=True)[: self.pool]
        candidates = [_to_passage(row) for _, row in ranked]

        # Les passages déjà en cache entrent dans le même reranking.
        seen = {p["chunk_id"] for p in candidates}
        for seed in seeds or []:
            if seed["chunk_id"] not in seen:
                candidates.append({k: v for k, v in seed.items() if k != "score"} | {"score": 0.0})
                seen.add(seed["chunk_id"])

        return self.rescore(query, candidates)[:top_k]

    def get_passages(
        self, conversation_id: str, refs: list[dict[str, str]]
    ) -> list[Passage]:
        """Recharge des passages depuis leurs références {chunk_id, document_type}."""
        wanted: dict[str, set[str]] = {}
        for ref in refs:
            wanted.setdefault(ref["document_type"], set()).add(ref["chunk_id"])

        passages: list[Passage] = []
        for doc_type, ids in wanted.items():
            _, rows = self._load(conversation_id, doc_type)
            passages.extend(_to_passage(r) for r in rows if r["chunk_id"] in ids)
        return passages