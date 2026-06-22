# retrievers/bm25.py -- BM25Okapi keyword retriever with jieba tokenization
#
# Replaces the legacy hand-written bigram TF scorer in hybrid_search.py.
# Uses rank_bm25.BM25Okapi (proper BM25 with IDF + document length normalization)
# and jieba for Chinese word segmentation.
#
# Documents are loaded once from a ChromaDB collection at construction time
# and indexed in memory. Call reload() to refresh after adding new documents.

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import jieba
from rank_bm25 import BM25Okapi

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

logger = logging.getLogger(__name__)


class QoderWorkBM25Retriever(BaseRetriever):
    """BM25Okapi keyword retriever backed by a ChromaDB collection.

    Tokenizes Chinese text with jieba and English with whitespace split.
    Builds an in-memory BM25 index from all documents in the collection.
    """

    collection_name: str = Field(description="ChromaDB collection to index")
    k: int = Field(default=5, description="Number of results to return")
    min_score: float = Field(default=0.0, description="Minimum BM25 score threshold")

    # Internal state (not Pydantic fields)
    _bm25: Optional[BM25Okapi] = None
    _docs: List[str] = []
    _metas: List[Dict[str, Any]] = []
    _ids: List[str] = []

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, collection_name: str, k: int = 5,
                 min_score: float = 0.0, load: bool = True, **kwargs: Any):
        super().__init__(collection_name=collection_name, k=k,
                         min_score=min_score, **kwargs)
        if load:
            self.reload()

    # ------------------------------------------------------------------
    # Tokenization
    # ------------------------------------------------------------------
    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Chinese: jieba word segmentation; English/digits: lowercased whitespace split."""
        if not text:
            return []
        return [w for w in jieba.lcut(text.lower()) if w.strip()]

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------
    def reload(self) -> int:
        """Load (or reload) all documents from the ChromaDB collection and rebuild index.

        Returns:
            Number of documents indexed.
        """
        from core.database import chroma_client  # lazy import

        try:
            col = chroma_client.get_collection(self.collection_name)
        except Exception as e:
            logger.debug("BM25: collection '%s' not found: %s", self.collection_name, e)
            self._bm25 = None
            self._docs = []
            self._metas = []
            self._ids = []
            return 0

        data = col.get()
        self._docs = data.get("documents") or []
        self._metas = data.get("metadatas") or [{}] * len(self._docs)
        self._ids = data.get("ids") or [""] * len(self._docs)

        if not self._docs:
            self._bm25 = None
            return 0

        tokenized = [self.tokenize(d) for d in self._docs]
        # BM25Okapi requires at least one non-empty document
        if all(len(t) == 0 for t in tokenized):
            self._bm25 = None
            return 0

        self._bm25 = BM25Okapi(tokenized)
        # Smooth IDF: BM25Okapi gives IDF=0 for terms in half the corpus
        # (log((N-n+0.5)/(n+0.5))=0 when N=2n). Add smoothing floor.
        self._smooth_idf()
        logger.info("BM25 indexed %d documents from '%s'",
                     len(self._docs), self.collection_name)
        return len(self._docs)

    def _smooth_idf(self) -> None:
        """Apply IDF smoothing to prevent zero-IDF for common terms.

        BM25Okapi uses IDF = log((N - n + 0.5) / (n + 0.5)), which gives 0
        when a term appears in exactly half the corpus (N=2n). We add a
        smoothing constant to keep IDF positive for all corpus terms.
        """
        if self._bm25 is None:
            return
        import math
        N = self._bm25.corpus_size
        smooth = 1.0  # smoothing constant
        for term, freq in self._bm25.doc_freqs.items():
            # Recompute IDF with smoothing: log((N + smooth) / (n + smooth)) + 1
            raw_idf = math.log((N + smooth) / (freq + smooth)) + 1.0
            self._bm25.idf[term] = max(raw_idf, 0.1)  # floor at 0.1

    @property
    def is_ready(self) -> bool:
        return self._bm25 is not None and len(self._docs) > 0

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForRetrieverRun] = None,
    ) -> List[Document]:
        if not self.is_ready:
            return []

        query_tokens = self.tokenize(query)
        if not query_tokens:
            return []

        # Filter query tokens to those in the BM25 vocabulary
        known_tokens = [t for t in query_tokens if t in self._bm25.idf]
        # For OOV tokens, add them with high IDF (unseen = informative)
        import math
        for t in query_tokens:
            if t not in self._bm25.idf:
                self._bm25.idf[t] = math.log(self._bm25.corpus_size + 1) + 1.0

        scores = self._bm25.get_scores(query_tokens)

        # Build scored results: (index, score)
        scored = []
        for i, sc in enumerate(scores):
            if sc > self.min_score:
                scored.append((i, float(sc)))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scored[: self.k]:
            meta = dict(self._metas[idx]) if idx < len(self._metas) else {}
            meta["bm25_score"] = round(score, 4)
            results.append(Document(
                page_content=self._docs[idx],
                metadata=meta,
                id=self._ids[idx] if idx < len(self._ids) else None,
            ))

        return results

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Any = None,
    ) -> List[Document]:
        # BM25 scoring is CPU-bound and fast; run in executor
        import asyncio
        return await asyncio.to_thread(self._get_relevant_documents, query)
