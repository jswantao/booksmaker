# retrievers/hybrid.py -- HybridRetriever: vector + BM25 with RRF fusion
#
# Combines Chroma vector search (via langchain-chroma) with BM25Okapi keyword
# search using Reciprocal Rank Fusion (RRF). Optional CrossEncoder reranking
# for improved top-k accuracy.
#
# Replaces the hand-written weighted-sum + 1.15x boost in hybrid_search.py.

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

logger = logging.getLogger(__name__)

# RRF constant (Cormack et al., 2009)
_RRF_K = 60


class HybridRetriever(BaseRetriever):
    """Vector (Chroma) + BM25 hybrid retriever with RRF fusion.

    Architecture:
        1. vector_store (Chroma) retrieves top-k by embedding similarity
        2. bm25_retriever (QoderWorkBM25Retriever) retrieves top-k by BM25 score
        3. RRF merges both ranked lists into a unified ranking
        4. (Optional) CrossEncoder reranks the merged results

    This replaces the legacy weighted-sum + 1.15x dual-hit boost with a
    principled fusion algorithm that does not require score normalization.
    """

    collection_name: str = Field(description="ChromaDB collection name")
    k: int = Field(default=5, description="Final number of results to return")
    score_threshold: float = Field(default=0.0, description="Minimum RRF score")
    semantic_weight: float = Field(default=0.6)
    keyword_weight: float = Field(default=0.4)

    # Cross-encoder rerank (default off)
    use_reranker: bool = Field(default=False)
    reranker_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")

    # Internal state
    _vector_store: Any = None
    _bm25: Any = None
    _reranker: Any = None
    _initialized: bool = False

    class Config:
        arbitrary_types_allowed = True

    def __init__(
        self,
        collection_name: str,
        k: int = 5,
        score_threshold: float = 0.0,
        semantic_weight: float = 0.6,
        keyword_weight: float = 0.4,
        use_reranker: bool = False,
        reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        **kwargs: Any,
    ):
        super().__init__(
            collection_name=collection_name,
            k=k,
            score_threshold=score_threshold,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
            use_reranker=use_reranker,
            reranker_model=reranker_model,
            **kwargs,
        )
        self._initialize()

    def _initialize(self) -> None:
        """Set up vector store, BM25 retriever, and optional reranker."""
        # --- Vector store (langchain-chroma wrapping our ChromaDB collection) ---
        try:
            from langchain_chroma import Chroma
            from langchain_adapters.embeddings import QoderWorkEmbeddings

            self._vector_store = Chroma(
                collection_name=self.collection_name,
                embedding_function=QoderWorkEmbeddings(),
            )
            # Verify collection exists and has documents
            count = self._vector_store._collection.count()
            if count == 0:
                logger.debug("Hybrid: collection '%s' is empty", self.collection_name)
                self._vector_store = None
        except Exception as e:
            logger.debug("Hybrid: vector store init failed for '%s': %s",
                         self.collection_name, e)
            self._vector_store = None

        # --- BM25 retriever ---
        from retrievers.bm25 import QoderWorkBM25Retriever
        self._bm25 = QoderWorkBM25Retriever(
            collection_name=self.collection_name,
            k=max(self.k * 3, 10),
            load=True,
        )

        # --- Cross-encoder reranker (lazy, only if requested) ---
        self._reranker = None

        self._initialized = True

    # ------------------------------------------------------------------
    # RRF (Reciprocal Rank Fusion)
    # ------------------------------------------------------------------
    @staticmethod
    def _rrf_fusion(
        result_lists: List[List[Document]],
        weights: Optional[List[float]] = None,
        rrf_k: int = _RRF_K,
    ) -> List[Document]:
        """Merge multiple ranked document lists via Reciprocal Rank Fusion.

        RRF score = sum( weight_i / (rrf_k + rank_i) ) for each unique document.
        """
        if not result_lists:
            return []
        if weights is None:
            weights = [1.0] * len(result_lists)

        scores: Dict[str, float] = {}
        doc_map: Dict[str, Document] = {}

        for docs, weight in zip(result_lists, weights):
            for rank, doc in enumerate(docs):
                # Dedup key: prefer doc id, fall back to content hash
                if doc.id:
                    key = doc.id
                else:
                    key = hashlib.md5(doc.page_content.encode()).hexdigest()

                scores[key] = scores.get(key, 0.0) + weight / (rrf_k + rank + 1)
                if key not in doc_map:
                    doc_map[key] = doc

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        fused = []
        for key, score in ranked:
            doc = doc_map[key]
            # Store RRF score in metadata for downstream filtering
            doc.metadata = {**(doc.metadata or {}), "_rrf_score": round(score, 6)}
            fused.append(doc)
        return fused

    # ------------------------------------------------------------------
    # Cross-encoder reranking
    # ------------------------------------------------------------------
    def _get_reranker(self) -> Any:
        """Lazy-load CrossEncoder model (only on first use)."""
        if self._reranker is not None:
            return self._reranker
        try:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(self.reranker_model)
            return self._reranker
        except Exception as e:
            logger.warning("CrossEncoder load failed, skipping rerank: %s", e)
            self.use_reranker = False
            return None

    def _rerank(self, query: str, docs: List[Document], top_n: int) -> List[Document]:
        """Rerank with CrossEncoder. Falls back to original order on failure."""
        reranker = self._get_reranker()
        if reranker is None or not docs:
            return docs[:top_n]

        try:
            pairs = [[query, d.page_content] for d in docs]
            ce_scores = reranker.predict(pairs)

            # Attach scores and re-sort
            for doc, sc in zip(docs, ce_scores):
                doc.metadata["_ce_score"] = float(sc)

            docs.sort(key=lambda d: d.metadata.get("_ce_score", -1e9), reverse=True)
            return docs[:top_n]
        except Exception as e:
            logger.warning("Rerank failed, using original order: %s", e)
            return docs[:top_n]

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForRetrieverRun] = None,
    ) -> List[Document]:
        result_lists: List[List[Document]] = []
        weights: List[float] = []

        # 1. Vector search via langchain-chroma
        if self._vector_store is not None and self.semantic_weight > 0:
            try:
                vector_docs = self._vector_store.similarity_search(
                    query, k=max(self.k * 3, 10)
                )
                # Tag source for traceability
                for d in vector_docs:
                    d.metadata = {**(d.metadata or {}), "_source": "vector"}
                result_lists.append(vector_docs)
                weights.append(self.semantic_weight)
            except Exception as e:
                logger.debug("Vector search failed: %s", e)

        # 2. BM25 keyword search
        if self._bm25 is not None and self._bm25.is_ready and self.keyword_weight > 0:
            try:
                bm25_docs = self._bm25._get_relevant_documents(query)
                for d in bm25_docs:
                    d.metadata = {**(d.metadata or {}), "_source": "keyword"}
                result_lists.append(bm25_docs)
                weights.append(self.keyword_weight)
            except Exception as e:
                logger.debug("BM25 search failed: %s", e)

        if not result_lists:
            return []

        # 3. RRF fusion
        fused = self._rrf_fusion(result_lists, weights)

        # 4. Filter by threshold
        if self.score_threshold > 0:
            fused = [d for d in fused
                     if d.metadata.get("_rrf_score", 0) >= self.score_threshold]

        # 5. Cross-encoder rerank (optional)
        if self.use_reranker and fused:
            fused = self._rerank(query, fused, self.k)

        return fused[: self.k]

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Any = None,
    ) -> List[Document]:
        import asyncio
        return await asyncio.to_thread(self._get_relevant_documents, query)
