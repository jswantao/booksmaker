# services/hybrid_search.py -- Hybrid index model (Dify-style) v3
# keyword (BM25Okapi) + semantic (Chroma vector) + RRF fusion
#
# Delegates to retrievers.HybridRetriever (RRF fusion).
# External API (HybridSearcher.search / hybrid_query_multiple / GroupedHybridSearcher)
# is 100% backward-compatible: same signatures, same dict output format.

import hashlib
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class HybridSearcher:
    """Dify-style hybrid: vector + BM25 keyword + RRF rerank, scoped to group/chapter.

    Delegates to retrievers.HybridRetriever which uses BM25Okapi + Chroma vector
    + RRF fusion.
    """

    def __init__(self, top_k: int = 3, score_threshold: float = 0.35,
                 semantic_weight: float = 0.6, keyword_weight: float = 0.4):
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
        # normalize weights to sum to 1.0
        total = semantic_weight + keyword_weight
        if total > 0:
            self.semantic_weight /= total
            self.keyword_weight /= total

    def search(self, collection_name: str, query: str,
               group: Optional[str] = None,
               chapter: Optional[str] = None) -> List[Dict]:
        """Hybrid search scoped to group/chapter, returns legacy dict format."""
        from retrievers.hybrid import HybridRetriever

        retriever = HybridRetriever(
            collection_name=collection_name,
            k=self.top_k,
            score_threshold=0.0,  # we filter below after conversion
            semantic_weight=self.semantic_weight,
            keyword_weight=self.keyword_weight,
        )

        docs = retriever._get_relevant_documents(query)

        results = []
        for doc in docs:
            meta = doc.metadata or {}
            rrf_score = meta.get("_rrf_score", 0.0)

            # Filter by threshold
            if rrf_score < self.score_threshold:
                continue

            # Determine method from _source tags
            sources = set()
            if meta.get("_source"):
                sources.add(meta["_source"])

            # Build detail scores (approximate from RRF contribution)
            detail = {"vector": 0.0, "keyword": 0.0}
            if "vector" in sources:
                detail["vector"] = rrf_score
            if "keyword" in sources:
                detail["keyword"] = rrf_score

            method = "+".join(sorted(sources)) if sources else "rrf"

            results.append({
                "document": doc.page_content,
                "score": round(rrf_score, 4),
                "method": method,
                "metadata": {k: v for k, v in meta.items()
                             if not k.startswith("_")},
                "detail": detail,
            })

        return results[:self.top_k]


def hybrid_query_multiple(kb_ids: List[str], query: str,
                          group: Optional[str] = None,
                          chapter: Optional[str] = None,
                          **searcher_kwargs) -> List[Dict]:
    """Cross-KB hybrid search, still scoped to group/chapter."""
    from services.knowledge_manager import kb_manager
    if not kb_ids:
        return []
    kbs = kb_manager.get_kbs_by_ids(kb_ids)
    if not kbs:
        return []
    searcher = HybridSearcher(**searcher_kwargs)
    all_results, seen = [], set()
    for kb in kbs:
        try:
            results = searcher.search(kb['collection_name'], query,
                                      group=group, chapter=chapter)
            for r in results:
                h = hashlib.md5(r['document'].encode()).hexdigest()
                if h not in seen:
                    seen.add(h)
                    r['kb_id'] = kb['id']
                    r['kb_name'] = kb['name']
                    all_results.append(r)
        except Exception as e:
            logger.warning("Hybrid search KB %s failed: %s", kb['name'], e)
    all_results.sort(key=lambda x: x['score'], reverse=True)
    return all_results[:searcher.top_k]


class GroupedHybridSearcher:
    """Group-scoped: each group has independent kb_ids, weight, top_k, threshold."""

    def __init__(self, kb_groups: Dict[str, Dict]):
        self.groups = kb_groups

    def search(self, query: str, group_name: str = None,
               chapter: str = None) -> List[Dict]:
        if group_name:
            g = self.groups.get(group_name)
            if not g:
                return []
            res = hybrid_query_multiple(
                g.get("kb_ids", []), query,
                group=group_name, chapter=chapter,
                top_k=g.get("top_k", 2),
                score_threshold=g.get("threshold", 0.35),
                semantic_weight=g.get("semantic_weight", 0.6),
                keyword_weight=g.get("keyword_weight", 0.4),
            )
            for r in res:
                r["group"] = group_name
            return res

        # all groups
        out, seen = [], set()
        for name, cfg in self.groups.items():
            weight = cfg.get("weight", 1.0)
            res = hybrid_query_multiple(
                cfg.get("kb_ids", []), query,
                group=name, chapter=chapter,
                top_k=cfg.get("top_k", 2),
                score_threshold=cfg.get("threshold", 0.35),
                semantic_weight=cfg.get("semantic_weight", 0.6),
                keyword_weight=cfg.get("keyword_weight", 0.4),
            )
            for r in res:
                h = hashlib.md5(r.get('document', '').encode()).hexdigest()
                if h not in seen:
                    seen.add(h)
                    r["group"] = name
                    r["score"] *= weight
                    out.append(r)
        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:5]
